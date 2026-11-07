"""Job state machine and job service: the only code that writes job state.

Same guarantees as the candidate machine: table checked, version checked, one audit row
per move, idempotency key unique per job. Rubric versions are immutable rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job, JobAuditEvent, Rubric, ScreeningQuestion
from app.db.session import SessionMaker
from app.domain.jobs import JobState, WorkArrangement, find_job_transition
from app.domain.questions import STANDARD_KEYS, QuestionSpec, standard_questions
from app.domain.states import ActorType
from app.workflow.machine import StaleTransition, TransitionRefused

J = JobState


class JobNotFound(Exception):
    pass


@dataclass(frozen=True)
class JobSnapshot:
    id: uuid.UUID
    state: JobState
    state_version: int
    review_return_state: JobState | None
    title: str
    description: str
    location: str
    work_arrangement: str
    salary_min: int
    salary_max: int
    approved_rubric_version: int | None

    @classmethod
    def of(cls, j: Job) -> JobSnapshot:
        return cls(
            id=j.id,
            state=JobState(j.state),
            state_version=j.state_version,
            review_return_state=JobState(j.review_return_state) if j.review_return_state else None,
            title=j.title,
            description=j.description,
            location=j.location,
            work_arrangement=j.work_arrangement,
            salary_min=j.salary_min,
            salary_max=j.salary_max,
            approved_rubric_version=j.approved_rubric_version,
        )


@dataclass(frozen=True)
class JobFields:
    title: str
    description: str
    location: str
    work_arrangement: WorkArrangement
    salary_min: int
    salary_max: int


def _key(job_id: uuid.UUID, transition_id: str, from_version: int) -> str:
    return f"{job_id}:{transition_id}:v{from_version}"


async def create_job(
    sessions: SessionMaker, fields: JobFields, custom: list[QuestionSpec], *, actor_id: str
) -> JobSnapshot:
    if fields.salary_min > fields.salary_max:
        raise ValueError("salary_min is above salary_max")
    keys = [q.key for q in custom]
    if set(keys) & set(STANDARD_KEYS) or len(keys) != len(set(keys)):
        raise ValueError("custom question keys must be unique and not reuse a standard key")
    t = find_job_transition(None, J.DRAFT, ActorType.RECRUITER)
    assert t is not None
    jid = uuid.uuid4()
    async with sessions() as s, s.begin():
        job = Job(
            id=jid,
            state=J.DRAFT,
            state_version=1,
            title=fields.title,
            description=fields.description,
            location=fields.location,
            work_arrangement=fields.work_arrangement.value,
            salary_min=fields.salary_min,
            salary_max=fields.salary_max,
        )
        s.add(job)
        await s.flush()
        specs = standard_questions(fields.location, fields.work_arrangement.value) + custom
        for pos, q in enumerate(specs, start=1):
            s.add(
                ScreeningQuestion(
                    job_id=jid,
                    key=q.key,
                    position=pos,
                    prompt=q.prompt,
                    answer_type=q.answer_type.value,
                    choices=q.choices,
                    required=q.required,
                    standard=q.key in STANDARD_KEYS,
                    knockout_rule=q.knockout_rule.model_dump() if q.knockout_rule else None,
                )
            )
        s.add(
            JobAuditEvent(
                job_id=jid,
                transition_id=t.id,
                from_state=None,
                to_state=J.DRAFT,
                actor_type=ActorType.RECRUITER,
                actor_id=actor_id,
                reason="job created",
                idempotency_key=_key(jid, t.id, 0),
            )
        )
    return JobSnapshot.of(job)


async def get_job(sessions: SessionMaker, job_id: uuid.UUID) -> JobSnapshot:
    async with sessions() as s:
        job = await s.get(Job, job_id)
        if job is None:
            raise JobNotFound(str(job_id))
        return JobSnapshot.of(job)


async def _locked(s: AsyncSession, job_id: uuid.UUID) -> Job:
    job = (
        await s.execute(select(Job).where(Job.id == job_id).with_for_update())
    ).scalar_one_or_none()
    if job is None:
        raise JobNotFound(str(job_id))
    return job


async def _move(
    s: AsyncSession,
    job: Job,
    to: JobState,
    actor_type: ActorType,
    actor_id: str,
    reason: str,
    *,
    trigger: str | None = None,
    expected_version: int | None = None,
    trace_id: str | None = None,
) -> None:
    current = JobState(job.state)
    if expected_version is not None and job.state_version != expected_version:
        raise StaleTransition(f"job is at version {job.state_version}, expected {expected_version}")
    t = find_job_transition(current, to, actor_type, trigger)
    if t is None:
        raise TransitionRefused(f"{actor_type} may not move a job from {current} to {to}")
    s.add(
        JobAuditEvent(
            job_id=job.id,
            transition_id=t.id,
            from_state=current,
            to_state=to,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            idempotency_key=_key(job.id, t.id, job.state_version),
            trace_id=trace_id,
        )
    )
    job.state = to
    job.state_version += 1
    job.review_return_state = current if to == J.NEEDS_REVIEW else None
    if to == J.CLOSED:
        job.closed_at = datetime.now(UTC)


async def _next_version(s: AsyncSession, job_id: uuid.UUID) -> int:
    current = (
        await s.execute(select(func.max(Rubric.version)).where(Rubric.job_id == job_id))
    ).scalar()
    return int(current or 0) + 1


async def transition_job(
    sessions: SessionMaker,
    job_id: uuid.UUID,
    to: JobState,
    *,
    actor_type: ActorType,
    actor_id: str,
    reason: str,
    expected_state: JobState | None = None,
    expected_version: int | None = None,
    trigger: str | None = None,
    trace_id: str | None = None,
) -> JobSnapshot:
    try:
        async with sessions() as s, s.begin():
            job = await _locked(s, job_id)
            if expected_state is not None and job.state != expected_state:
                raise StaleTransition(f"job is {job.state}, expected {expected_state}")
            await _move(
                s,
                job,
                to,
                actor_type,
                actor_id,
                reason,
                trigger=trigger,
                expected_version=expected_version,
                trace_id=trace_id,
            )
            await s.flush()
            return JobSnapshot.of(job)
    except IntegrityError as exc:
        raise StaleTransition("this move was already applied") from exc


async def save_rubric(
    sessions: SessionMaker,
    job_id: uuid.UUID,
    *,
    criteria: list[dict[str, Any]],
    flags: list[dict[str, Any]],
    source: str,
    actor_type: ActorType,
    actor_id: str,
    to: JobState,
    reason: str,
    expected_state: JobState,
    expected_version: int,
    trigger: str | None = None,
    llm: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> tuple[JobSnapshot, int]:
    """Store a new rubric version and move the job, in one transaction."""
    try:
        async with sessions() as s, s.begin():
            job = await _locked(s, job_id)
            if job.state != expected_state or job.state_version != expected_version:
                raise StaleTransition(f"job is {job.state} v{job.state_version}")
            version = await _next_version(s, job_id)
            s.add(
                Rubric(
                    job_id=job_id,
                    version=version,
                    source=source,
                    criteria=criteria,
                    flags=flags,
                    prompt_id=(llm or {}).get("prompt_id"),
                    prompt_version=(llm or {}).get("prompt_version"),
                    model=(llm or {}).get("model"),
                    cost_usd=(llm or {}).get("cost_usd"),
                    created_by=actor_id,
                )
            )
            await _move(
                s,
                job,
                to,
                actor_type,
                actor_id,
                f"{reason} (rubric v{version})",
                trigger=trigger,
                trace_id=trace_id,
            )
            await s.flush()
            return JobSnapshot.of(job), version
    except IntegrityError as exc:
        raise StaleTransition("this move was already applied") from exc


async def approve_and_open(
    sessions: SessionMaker, job_id: uuid.UUID, *, version: int, actor_id: str, reason: str
) -> JobSnapshot:
    try:
        async with sessions() as s, s.begin():
            job = await _locked(s, job_id)
            latest = await _next_version(s, job_id) - 1
            if version != latest:
                raise StaleTransition(f"rubric v{version} is not the latest (v{latest})")
            rubric = (
                await s.execute(
                    select(Rubric).where(Rubric.job_id == job_id, Rubric.version == version)
                )
            ).scalar_one()
            await _move(
                s,
                job,
                J.OPEN,
                ActorType.RECRUITER,
                actor_id,
                f"{reason} (approved rubric v{version})",
            )
            rubric.approved_by, rubric.approved_at = actor_id, datetime.now(UTC)
            job.approved_rubric_version = version
            await s.flush()
            return JobSnapshot.of(job)
    except IntegrityError as exc:
        raise StaleTransition("this move was already applied") from exc


async def update_description(
    sessions: SessionMaker,
    job_id: uuid.UUID,
    *,
    description: str,
    actor_id: str,
    reason: str,
    expected_version: int | None = None,
) -> JobSnapshot:
    async with sessions() as s, s.begin():
        job = await _locked(s, job_id)
        await _move(
            s,
            job,
            J.DRAFT,
            ActorType.RECRUITER,
            actor_id,
            reason,
            expected_version=expected_version,
        )
        job.description = description
        await s.flush()
        return JobSnapshot.of(job)


async def rubrics(sessions: SessionMaker, job_id: uuid.UUID) -> list[Rubric]:
    async with sessions() as s:
        rows = await s.execute(
            select(Rubric).where(Rubric.job_id == job_id).order_by(Rubric.version)
        )
        return list(rows.scalars())


async def questions(sessions: SessionMaker, job_id: uuid.UUID) -> list[ScreeningQuestion]:
    async with sessions() as s:
        rows = await s.execute(
            select(ScreeningQuestion)
            .where(ScreeningQuestion.job_id == job_id)
            .order_by(ScreeningQuestion.position)
        )
        return list(rows.scalars())


async def job_audit(sessions: SessionMaker, job_id: uuid.UUID) -> list[JobAuditEvent]:
    async with sessions() as s:
        rows = await s.execute(
            select(JobAuditEvent)
            .where(JobAuditEvent.job_id == job_id)
            .order_by(JobAuditEvent.occurred_at, JobAuditEvent.id)
        )
        return list(rows.scalars())
