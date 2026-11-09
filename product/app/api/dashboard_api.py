"""Endpoints the recruiter dashboard needs (phase 4 design section 5): jobs list, review
queue, contact details after shortlist (logged), and rescoring on a newer rubric."""

import uuid
from collections import Counter
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from app.db.models import AccessEvent, AuditEvent, Candidate, Decision, Job, Rubric
from app.domain.jobs import JobState
from app.domain.states import CandidateState
from app.scoring.agreement import agreement
from app.workflow.decisions import CONTACT_STATES

S = CandidateState


def register(app: FastAPI, Recruiter: Any, Pl: Any) -> None:  # noqa: N803
    @app.get("/jobs")
    async def list_jobs(_: Recruiter, p: Pl) -> JSONResponse:
        async with p.sessions() as s:
            jobs = (await s.execute(select(Job).order_by(Job.created_at.desc()))).scalars().all()
            states = (
                await s.execute(
                    select(Candidate.job_id, Candidate.state, func.count())
                    .where(Candidate.job_id.is_not(None))
                    .group_by(Candidate.job_id, Candidate.state)
                )
            ).all()
            versions = dict(
                (
                    await s.execute(
                        select(Rubric.job_id, func.max(Rubric.version))
                        .where(Rubric.approved_at.is_not(None))
                        .group_by(Rubric.job_id)
                    )
                ).all()
            )
            decisions = (
                await s.execute(
                    select(
                        Candidate.job_id,
                        Decision.candidate_id,
                        Decision.recommended,
                        Decision.decision,
                    )
                    .join(Candidate, Candidate.id == Decision.candidate_id)
                    .order_by(Decision.created_at)
                )
            ).all()
        by_job: dict[uuid.UUID, Counter[str]] = {}
        for job_id, state, n in states:
            by_job.setdefault(job_id, Counter())[state] = n
        last: dict[uuid.UUID, dict[uuid.UUID, tuple[str, str]]] = {}
        for job_id, cid, rec, dec in decisions:
            last.setdefault(job_id, {})[cid] = (rec, dec)
        out = []
        for j in jobs:
            counts = by_job.get(j.id, Counter())
            out.append(
                {
                    "id": str(j.id),
                    "title": j.title,
                    "state": j.state,
                    "location": j.location,
                    "approved_rubric_version": versions.get(j.id),
                    "candidates": sum(counts.values()),
                    "by_state": dict(counts),
                    "undecided": counts.get(S.SCORED.value, 0),
                    "needs_review": counts.get(S.NEEDS_REVIEW.value, 0),
                    "agreement": agreement(last.get(j.id, {}).values()).as_dict(),
                }
            )
        return JSONResponse(content={"jobs": out})

    @app.get("/review-queue")
    async def review_queue(_: Recruiter, p: Pl) -> JSONResponse:
        async with p.sessions() as s:
            cands = (
                await s.execute(
                    select(Candidate, Job.title)
                    .outerjoin(Job, Job.id == Candidate.job_id)
                    .where(Candidate.state == S.NEEDS_REVIEW.value)
                    .order_by(Candidate.updated_at)
                )
            ).all()
            reasons: dict[uuid.UUID, str] = {}
            for c, _title in cands:
                last = (
                    await s.execute(
                        select(AuditEvent.reason)
                        .where(AuditEvent.candidate_id == c.id)
                        .order_by(AuditEvent.occurred_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                reasons[c.id] = last or ""
            jobs = (
                (await s.execute(select(Job).where(Job.state == JobState.NEEDS_REVIEW.value)))
                .scalars()
                .all()
            )
        return JSONResponse(
            content={
                "candidates": [
                    {
                        "id": str(c.id),
                        "label": c.display_label,
                        "job_id": str(c.job_id) if c.job_id else None,
                        "job_title": title,
                        "state_version": c.state_version,
                        "return_state": c.review_return_state,
                        "reason": reasons[c.id],
                    }
                    for c, title in cands
                ],
                "jobs": [{"id": str(j.id), "title": j.title} for j in jobs],
            }
        )

    @app.get("/candidates/{candidate_id}/contact")
    async def contact(candidate_id: uuid.UUID, actor: Recruiter, p: Pl) -> JSONResponse:
        """Blind review: contact details only after shortlist. Every read is logged."""
        async with p.sessions() as s, s.begin():
            c = await s.get(Candidate, candidate_id)
            if c is None:
                return JSONResponse(status_code=404, content={"error": "not_found"})
            if c.erased_at is not None:
                return JSONResponse(
                    status_code=410, content={"error": "erased", "detail": "personal data erased"}
                )
            if S(c.state) not in CONTACT_STATES:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "blind_review",
                        "detail": "contact details are shown once the candidate is shortlisted",
                    },
                )
            s.add(AccessEvent(candidate_id=c.id, what="contact", actor_id=actor))
            body = {"name": c.full_name, "email": c.email, "phone": c.phone}
        return JSONResponse(content=body)

    @app.get("/candidates/{candidate_id}/access")
    async def access_log(candidate_id: uuid.UUID, _: Recruiter, p: Pl) -> JSONResponse:
        async with p.sessions() as s:
            rows = (
                (
                    await s.execute(
                        select(AccessEvent)
                        .where(AccessEvent.candidate_id == candidate_id)
                        .order_by(AccessEvent.created_at)
                    )
                )
                .scalars()
                .all()
            )
        return JSONResponse(
            content={
                "events": [
                    {"what": r.what, "actor_id": r.actor_id, "at": r.created_at.isoformat()}
                    for r in rows
                ]
            }
        )

    @app.post("/jobs/{job_id}/rescore")
    async def rescore(job_id: uuid.UUID, actor: Recruiter, p: Pl) -> JSONResponse:
        try:
            queued = await p.request_rescore(job_id, actor_id=actor)
        except LookupError:
            return JSONResponse(status_code=404, content={"error": "not_found"})
        return JSONResponse(status_code=202, content={"queued": queued})

    _ = (list_jobs, review_queue, contact, access_log, rescore)
