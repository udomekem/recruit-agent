"""Runs system steps. One `advance` call moves a candidate at most one step.

- A job carries the state and version it was queued for. If the candidate has moved on,
  the job is a no-op (duplicates and late retries are harmless).
- A step gets `step_max_attempts` tries, each with a timeout. If all fail, the candidate
  goes to NEEDS_REVIEW with the reason (T19). Nothing stops silently.
- The pipeline never acts on a decision point; only recruiter API calls leave those states.
- Job steps (phase 1): `build_rubric` runs the rubric builder for a DRAFT job. Any failure
  (invalid output after retries, refusal, provider error, no model configured) moves the
  job to NEEDS_REVIEW with the reason (J3).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.agents.rubric_builder import build_rubric
from app.config import Settings
from app.db.session import SessionMaker
from app.domain.jobs import JobState
from app.domain.states import SYSTEM_STEPS, ActorType, CandidateState
from app.llm.client import LLMClient, LLMError
from app.observability.tracing import Tracer
from app.workflow.dispatch import AdvanceJob, Dispatcher, InlineDispatcher, RubricJob
from app.workflow.jobs import JobNotFound, JobSnapshot, get_job, save_rubric, transition_job
from app.workflow.machine import (
    CandidateNotFound,
    Snapshot,
    StaleTransition,
    apply_transition,
    get_candidate,
)
from app.workflow.steps import StepOutcome, StubSteps

log = logging.getLogger(__name__)
S = CandidateState

STUB_PROMPT_VERSION = "stub-v0"
STUB_MODEL = "none"


class Pipeline:
    def __init__(
        self,
        sessions: SessionMaker,
        dispatcher: Dispatcher,
        tracer: Tracer,
        settings: Settings,
        steps: StubSteps | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.sessions = sessions
        self.dispatcher = dispatcher
        self.tracer = tracer
        self.settings = settings
        self.steps = steps or StubSteps()
        self.llm = llm

    async def schedule(self, cand: Snapshot) -> None:
        """Queue the next system step if the candidate's state has one."""
        if cand.state not in SYSTEM_STEPS:
            return
        defer = self.settings.no_answer_retry_delay_seconds if cand.state == S.NO_ANSWER else 0
        await self.dispatcher.enqueue(
            AdvanceJob(cand.id, cand.state, cand.state_version, defer_seconds=defer)
        )

    async def schedule_job(self, job: JobSnapshot) -> None:
        if job.state == JobState.DRAFT:
            await self.dispatcher.enqueue(RubricJob(job.id, job.state, job.state_version))

    async def build_rubric(
        self, job_id: uuid.UUID, expected_state: JobState, expected_version: int
    ) -> JobSnapshot | None:
        try:
            job = await get_job(self.sessions, job_id)
        except JobNotFound:
            log.warning("build_rubric: job %s not found", job_id)
            return None
        if job.state != expected_state or job.state_version != expected_version:
            log.info("build_rubric: job %s already moved on, no-op", job_id)
            return None
        if job.state != JobState.DRAFT:
            return None
        with self.tracer.span(
            "step:build_rubric",
            job_id=str(job.id),
            candidate_id="none",
            step="build_rubric",
            prompt_version="rubric-builder-v1",
            model=self.settings.model_judgement,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        ) as span:
            try:
                if self.llm is None:
                    raise LLMError("no language model configured (ANTHROPIC_API_KEY not set)")
                result = await build_rubric(
                    self.llm,
                    title=job.title,
                    location=job.location,
                    work_arrangement=job.work_arrangement,
                    salary_min=job.salary_min,
                    salary_max=job.salary_max,
                    description=job.description,
                    job_id=str(job.id),
                )
            except LLMError as exc:
                span.update(outcome="needs_review", error=type(exc).__name__)
                try:
                    return await transition_job(
                        self.sessions,
                        job.id,
                        JobState.NEEDS_REVIEW,
                        actor_type=ActorType.SYSTEM,
                        actor_id="worker:build_rubric",
                        reason=f"rubric build failed: {type(exc).__name__}: {str(exc)[:500]}",
                        expected_state=job.state,
                        expected_version=job.state_version,
                        trace_id=self.tracer.current_trace_id(),
                    )
                except StaleTransition:
                    return None
            span.update(
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_usd=result.cost_usd,
                attempts=result.attempts,
                flags=len(result.output.flags),
                criteria=len(result.output.criteria),
                outcome="rubric_ready",
            )
            try:
                moved, _version = await save_rubric(
                    self.sessions,
                    job.id,
                    criteria=[c.model_dump() for c in result.output.criteria],
                    flags=[f.model_dump() for f in result.output.flags],
                    source="ai",
                    actor_type=ActorType.SYSTEM,
                    actor_id="worker:build_rubric",
                    to=JobState.RUBRIC_READY,
                    reason="rubric drafted by the rubric builder",
                    expected_state=job.state,
                    expected_version=job.state_version,
                    llm={
                        "prompt_id": result.prompt_id,
                        "prompt_version": result.prompt_version,
                        "model": result.model,
                        "cost_usd": result.cost_usd,
                    },
                    trace_id=self.tracer.current_trace_id(),
                )
            except StaleTransition:
                span.update(outcome="stale")
                return None
        return moved

    async def advance(
        self, candidate_id: uuid.UUID, expected_state: CandidateState, expected_version: int
    ) -> Snapshot | None:
        try:
            cand = await get_candidate(self.sessions, candidate_id)
        except CandidateNotFound:
            log.warning("advance: candidate %s not found", candidate_id)
            return None
        if cand.state != expected_state or cand.state_version != expected_version:
            log.info("advance: %s already moved on, job is a no-op", candidate_id)
            return None
        step = SYSTEM_STEPS.get(cand.state)
        if step is None:
            return None  # decision point or terminal: wait for a recruiter

        with self.tracer.span(
            f"step:{step}",
            candidate_id=str(cand.id),
            from_state=cand.state.value,
            step=step,
            prompt_version=STUB_PROMPT_VERSION,
            model=STUB_MODEL,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
        ) as span:
            outcome, attempts, error = await self._run_with_retries(step, cand)
            span.update(attempts=attempts)
            if outcome is None:
                to_state, reason = (
                    S.NEEDS_REVIEW,
                    f"step {step} failed after {attempts} attempts: {error}",
                )
            else:
                to_state, reason = outcome.to_state, outcome.reason
            span.update(outcome=to_state.value)
            try:
                moved = await apply_transition(
                    self.sessions,
                    candidate_id=cand.id,
                    to_state=to_state,
                    actor_type=ActorType.SYSTEM,
                    actor_id=f"worker:{step}",
                    reason=reason,
                    expected_state=cand.state,
                    expected_version=cand.state_version,
                    trace_id=self.tracer.current_trace_id(),
                )
            except StaleTransition:
                log.info("advance: %s moved during step %s, result discarded", cand.id, step)
                span.update(outcome="stale")
                return None
            with self.tracer.span(
                "transition",
                kind="event",
                candidate_id=str(cand.id),
                from_state=cand.state.value,
                to_state=moved.state.value,
                actor="system",
            ):
                pass
        await self.schedule(moved)
        return moved

    async def _run_with_retries(
        self, step: str, cand: Snapshot
    ) -> tuple[StepOutcome | None, int, str | None]:
        if step == "screen_call_retry_rule":
            return self._no_answer_rule(cand), 1, None
        error: str | None = None
        for attempt in range(1, self.settings.step_max_attempts + 1):
            try:
                outcome = await asyncio.wait_for(
                    self.steps.run(step, cand), timeout=self.settings.step_timeout_seconds
                )
                return outcome, attempt, None
            except Exception as exc:  # any step failure is retried, then reviewed
                error = f"{type(exc).__name__}: {exc}"
                log.warning("step %s attempt %d failed: %s", step, attempt, error)
                if attempt < self.settings.step_max_attempts:
                    await asyncio.sleep(self.settings.step_retry_backoff_seconds * attempt)
        return None, self.settings.step_max_attempts, error

    def _no_answer_rule(self, cand: Snapshot) -> StepOutcome:
        if cand.screen_call_attempts < self.settings.screen_call_max_attempts:
            return StepOutcome(
                S.SCREEN_CALL_QUEUED,
                f"retrying screen call ({cand.screen_call_attempts} unanswered so far)",
            )
        return StepOutcome(S.NEEDS_REVIEW, f"no answer after {cand.screen_call_attempts} attempts")

    async def drain(self) -> int:
        """Run queued jobs in-process until the queue is empty (InlineDispatcher only)."""
        if not isinstance(self.dispatcher, InlineDispatcher):
            raise TypeError("drain() needs an InlineDispatcher")
        ran = 0
        while self.dispatcher.queue:
            job = self.dispatcher.queue.pop(0)
            if isinstance(job, RubricJob):
                await self.build_rubric(job.job_id, job.expected_state, job.expected_version)
            else:
                await self.advance(job.candidate_id, job.expected_state, job.expected_version)
            ran += 1
        return ran
