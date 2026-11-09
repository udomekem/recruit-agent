"""Recruiter decisions, the access log and rescoring (phase 4 design sections 5 to 7)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Candidate, Decision, Job, JobAuditEvent, Rubric, Score
from app.db.session import SessionMaker
from app.domain.states import ActorType, CandidateState
from app.llm.client import LLMClient
from app.scoring.agreement import check_reason, is_override

S = CandidateState

# States a shortlisted candidate can be in; contact details are shown only here.
CONTACT_STATES = {
    S.SHORTLISTED,
    S.SCREEN_CALL_QUEUED,
    S.SCREEN_CALL_DONE,
    S.NO_ANSWER,
    S.SCREEN_SCORED,
    S.ADVANCED,
    S.BOOKING_CALL_QUEUED,
    S.BOOKING_CALL_DONE,
    S.INTERVIEW_BOOKED,
}


async def latest_score(s: AsyncSession, candidate_id: uuid.UUID) -> Score | None:
    return (
        await s.execute(
            select(Score)
            .where(Score.candidate_id == candidate_id)
            .order_by(Score.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def decision_extra(
    sessions: SessionMaker,
    candidate_id: uuid.UUID,
    *,
    choice: str,
    reason: str,
    actor_id: str,
) -> Callable[[AsyncSession, Candidate], None]:
    """Check the override reason now (before anything moves) and return the hook that
    writes the Decision row in the move's transaction."""
    async with sessions() as s:
        score = await latest_score(s, candidate_id)
    recommended = score.band if score is not None else "none"
    check_reason(recommended, choice, reason)
    row: dict[str, Any] = {
        "candidate_id": candidate_id,
        "score_id": score.id if score is not None else None,
        "recommended": recommended,
        "decision": choice,
        "override": is_override(recommended, choice),
        "reason": reason,
        "actor_id": actor_id,
    }

    def add(s: AsyncSession, _c: Candidate) -> None:
        s.add(Decision(**row))

    return add


def _job_note(job: Job, reason: str, actor_type: ActorType, actor_id: str) -> JobAuditEvent:
    """A job audit note that is not a state move (rescore requested or failed)."""
    return JobAuditEvent(
        job_id=job.id,
        transition_id="RESCORE",
        from_state=job.state,
        to_state=job.state,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
        idempotency_key=f"{job.id}:RESCORE:{uuid.uuid4().hex}",
    )


async def outdated_candidates(
    sessions: SessionMaker, job_id: uuid.UUID
) -> tuple[Job, Any, list[uuid.UUID]]:
    """Undecided (SCORED) candidates whose latest score is on an older rubric version."""
    async with sessions() as s:
        job = await s.get(Job, job_id)
        if job is None:
            raise LookupError("no such job")
        rubric = (
            await s.execute(
                select(Rubric)
                .where(Rubric.job_id == job_id, Rubric.approved_at.is_not(None))
                .order_by(Rubric.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        cands = (
            (
                await s.execute(
                    select(Candidate.id).where(
                        Candidate.job_id == job_id, Candidate.state == S.SCORED.value
                    )
                )
            )
            .scalars()
            .all()
        )
        out = []
        for cid in cands:
            sc = await latest_score(s, cid)
            if rubric is not None and sc is not None and sc.rubric_version < rubric.version:
                out.append(cid)
    return job, rubric, out


async def request_rescore(
    sessions: SessionMaker, job_id: uuid.UUID, *, actor_id: str
) -> tuple[list[uuid.UUID], uuid.UUID | None]:
    job, rubric, ids = await outdated_candidates(sessions, job_id)
    if ids and rubric is not None:
        async with sessions() as s, s.begin():
            s.add(
                _job_note(
                    job,
                    f"rescore requested: {len(ids)} candidates against rubric v{rubric.version}",
                    ActorType.RECRUITER,
                    actor_id,
                )
            )
    return ids, rubric.id if rubric is not None else None


async def rescore_candidate(
    sessions: SessionMaker, llm: LLMClient | None, candidate_id: uuid.UUID, *, production: bool
) -> str:
    """Score again against the current approved rubric; store a new Score row; never move
    the candidate. A repeat is a no-op (unique per candidate and rubric)."""
    from app.scoring.step import run_score

    async with sessions() as s:
        cand = await s.get(Candidate, candidate_id)
        if cand is None or cand.state != S.SCORED.value or cand.job_id is None:
            return "skipped: not undecided"
        job_id = cand.job_id
        label = cand.display_label
    decision = await run_score(sessions, llm, candidate_id, production=production)
    if decision.to_state != S.SCORED or decision.row is None:
        async with sessions() as s, s.begin():
            job = await s.get(Job, job_id)
            assert job is not None
            s.add(
                _job_note(
                    job,
                    f"rescore failed for {label}: {decision.reason}; the old score stays",
                    ActorType.SYSTEM,
                    "worker:rescore",
                )
            )
        return "failed"
    try:
        async with sessions() as s, s.begin():
            s.add(Score(candidate_id=candidate_id, **decision.row))
    except IntegrityError:
        return "no-op: already scored on this rubric"
    return "rescored"
