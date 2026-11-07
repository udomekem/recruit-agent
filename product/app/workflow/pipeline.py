"""Runs system steps. One `advance` call moves a candidate at most one step.

- A job carries the state and version it was queued for. If the candidate has moved on,
  the job is a no-op (duplicates and late retries are harmless).
- A step gets `step_max_attempts` tries, each with a timeout. If all fail, the candidate
  goes to NEEDS_REVIEW with the reason (T19). Nothing stops silently.
- The pipeline never acts on a decision point; only recruiter API calls leave those states.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from app.config import Settings
from app.db.session import SessionMaker
from app.domain.states import SYSTEM_STEPS, ActorType, CandidateState
from app.observability.tracing import Tracer
from app.workflow.dispatch import AdvanceJob, Dispatcher, InlineDispatcher
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
    ) -> None:
        self.sessions = sessions
        self.dispatcher = dispatcher
        self.tracer = tracer
        self.settings = settings
        self.steps = steps or StubSteps()

    async def schedule(self, cand: Snapshot) -> None:
        """Queue the next system step if the candidate's state has one."""
        if cand.state not in SYSTEM_STEPS:
            return
        defer = self.settings.no_answer_retry_delay_seconds if cand.state == S.NO_ANSWER else 0
        await self.dispatcher.enqueue(
            AdvanceJob(cand.id, cand.state, cand.state_version, defer_seconds=defer)
        )

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
            await self.advance(job.candidate_id, job.expected_state, job.expected_version)
            ran += 1
        return ran
