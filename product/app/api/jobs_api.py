"""Recruiter endpoints for jobs, screening questions and rubrics (phase 1 design section 3).

No `from __future__ import annotations` here: FastAPI resolves the dependency types at
runtime.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.agents.rubric_builder import MAX_CRITERIA, WEIGHTS, Criterion, WordingFlag
from app.domain.guard import find_protected_terms
from app.domain.jobs import JobState, WorkArrangement
from app.domain.questions import QuestionSpec
from app.domain.states import ActorType
from app.workflow import jobs as J
from app.workflow.machine import TransitionRefused


class CreateJob(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=200, max_length=20000)
    location: str = Field(min_length=2, max_length=120)
    work_arrangement: WorkArrangement
    salary_min: int = Field(ge=0, le=2_000_000)
    salary_max: int = Field(ge=0, le=2_000_000)
    questions: list[QuestionSpec] = Field(default_factory=list, max_length=20)


class Reason(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int | None = None


class EditDescription(Reason):
    description: str = Field(min_length=200, max_length=20000)


class EditRubric(Reason):
    criteria: list[Criterion] = Field(min_length=1, max_length=MAX_CRITERIA)
    flags: list[WordingFlag] = Field(default_factory=list)


class Approve(Reason):
    version: int = Field(ge=1)


class JobOut(BaseModel):
    id: uuid.UUID
    state: JobState
    state_version: int
    review_return_state: JobState | None
    title: str
    location: str
    work_arrangement: str
    salary_min: int
    salary_max: int
    approved_rubric_version: int | None


class QuestionOut(BaseModel):
    key: str
    position: int
    prompt: str
    answer_type: str
    choices: list[str] | None
    required: bool
    standard: bool
    knockout_rule: dict[str, Any] | None


class RubricOut(BaseModel):
    version: int
    source: str
    criteria: list[dict[str, Any]]
    flags: list[dict[str, Any]]
    prompt_id: str | None
    prompt_version: str | None
    model: str | None
    cost_usd: float | None
    created_by: str
    created_at: datetime
    approved_by: str | None
    approved_at: datetime | None


class JobAuditOut(BaseModel):
    transition_id: str
    from_state: str | None
    to_state: str
    actor_type: str
    actor_id: str
    reason: str
    occurred_at: datetime


class JobDetail(JobOut):
    description: str
    questions: list[QuestionOut]
    rubrics: list[RubricOut]
    audit: list[JobAuditOut]


def _out(j: J.JobSnapshot) -> JobOut:
    return JobOut(**{k: v for k, v in j.__dict__.items() if k != "description"})


def check_recruiter_rubric(body: EditRubric) -> None:
    """A recruiter's rubric skips the 'quote must be in the ad' check (the recruiter is
    accountable for it) but keeps ids, weights and the protected attribute guard."""
    problems: list[str] = []
    ids = [c.id for c in body.criteria]
    if len(ids) != len(set(ids)):
        problems.append("criterion ids must be unique")
    if not any(c.kind == "must_have" for c in body.criteria):
        problems.append("at least one criterion must be a must_have")
    for c in body.criteria:
        if c.weight not in WEIGHTS[c.kind]:
            problems.append(f"{c.id}: weight out of range for {c.kind}")
        hits = find_protected_terms(c.text)
        if hits:
            problems.append(f"{c.id}: protected attribute wording ({', '.join(hits)})")
    if problems:
        raise ValueError("; ".join(problems))


def register(app: FastAPI, Recruiter: Any, Pl: Any) -> None:  # noqa: N803 (dependency types)
    @app.post("/jobs", status_code=201)
    async def create_job(body: CreateJob, actor: Recruiter, p: Pl) -> JobOut:
        job = await J.create_job(
            p.sessions,
            J.JobFields(
                body.title,
                body.description,
                body.location,
                body.work_arrangement,
                body.salary_min,
                body.salary_max,
            ),
            body.questions,
            actor_id=actor,
        )
        await p.schedule_job(job)
        return _out(job)

    @app.get("/jobs/{job_id}")
    async def job_detail(job_id: uuid.UUID, _: Recruiter, p: Pl) -> JobDetail:
        job = await J.get_job(p.sessions, job_id)
        return JobDetail(
            **_out(job).model_dump(),
            description=job.description,
            questions=[
                QuestionOut.model_validate(q, from_attributes=True)
                for q in await J.questions(p.sessions, job_id)
            ],
            rubrics=[
                RubricOut.model_validate(r, from_attributes=True)
                for r in await J.rubrics(p.sessions, job_id)
            ],
            audit=[
                JobAuditOut.model_validate(e, from_attributes=True)
                for e in await J.job_audit(p.sessions, job_id)
            ],
        )

    @app.put("/jobs/{job_id}/description")
    async def edit_description(
        job_id: uuid.UUID, body: EditDescription, actor: Recruiter, p: Pl
    ) -> JobOut:
        job = await J.update_description(
            p.sessions,
            job_id,
            description=body.description,
            actor_id=actor,
            reason=body.reason,
            expected_version=body.expected_version,
        )
        await p.schedule_job(job)
        return _out(job)

    @app.post("/jobs/{job_id}/rubric")
    async def edit_rubric(job_id: uuid.UUID, body: EditRubric, actor: Recruiter, p: Pl) -> JobOut:
        check_recruiter_rubric(body)
        job = await J.get_job(p.sessions, job_id)
        trigger = {
            JobState.RUBRIC_READY: "edit rubric",
            JobState.CLOSED: "revise rubric",
            JobState.NEEDS_REVIEW: "supply rubric by hand",
        }.get(job.state)
        if trigger is None:
            raise TransitionRefused(f"the rubric cannot be changed while the job is {job.state}")
        moved, _version = await J.save_rubric(
            p.sessions,
            job_id,
            criteria=[c.model_dump() for c in body.criteria],
            flags=[f.model_dump() for f in body.flags],
            source="recruiter",
            actor_type=ActorType.RECRUITER,
            actor_id=actor,
            to=JobState.RUBRIC_READY,
            reason=body.reason,
            expected_state=job.state,
            expected_version=body.expected_version
            if body.expected_version is not None
            else job.state_version,
            trigger=trigger,
        )
        return _out(moved)

    @app.post("/jobs/{job_id}/approve")
    async def approve(job_id: uuid.UUID, body: Approve, actor: Recruiter, p: Pl) -> JobOut:
        return _out(
            await J.approve_and_open(
                p.sessions, job_id, version=body.version, actor_id=actor, reason=body.reason
            )
        )

    async def simple(job_id: uuid.UUID, to: JobState, body: Reason, actor: str, p: Any) -> JobOut:
        job = await J.transition_job(
            p.sessions,
            job_id,
            to,
            actor_type=ActorType.RECRUITER,
            actor_id=actor,
            reason=body.reason,
            expected_version=body.expected_version,
        )
        await p.schedule_job(job)
        return _out(job)

    @app.post("/jobs/{job_id}/close")
    async def close(job_id: uuid.UUID, body: Reason, actor: Recruiter, p: Pl) -> JobOut:
        return await simple(job_id, JobState.CLOSED, body, actor, p)

    @app.post("/jobs/{job_id}/reopen")
    async def reopen(job_id: uuid.UUID, body: Reason, actor: Recruiter, p: Pl) -> JobOut:
        return await simple(job_id, JobState.OPEN, body, actor, p)

    @app.post("/jobs/{job_id}/retry-build")
    async def retry_build(job_id: uuid.UUID, body: Reason, actor: Recruiter, p: Pl) -> JobOut:
        return await simple(job_id, JobState.DRAFT, body, actor, p)

    _ = (create_job, job_detail, edit_description, edit_rubric, approve, close, reopen, retry_build)
