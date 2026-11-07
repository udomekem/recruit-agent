"""Phase 0 stub steps: canned results, no LLM, no external side effects.

Each step returns the state to move to. Real steps replace these in later phases
(parse: phase 2, score: phase 3, draft_rejection: phase 5, calls: phases 6 and 8).
`StubBehaviour` lets tests make a step fail or a call go unanswered.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.states import CandidateState as S
from app.workflow.machine import Snapshot


@dataclass(frozen=True)
class StepOutcome:
    to_state: S
    reason: str


@dataclass
class StubBehaviour:
    failing_steps: set[str] = field(default_factory=set)
    unanswered_calls: int = 0  # how many screen calls go unanswered before one is answered
    _calls_made: dict[str, int] = field(default_factory=dict)

    def unanswered(self, candidate_id: str) -> bool:
        made = self._calls_made.get(candidate_id, 0)
        self._calls_made[candidate_id] = made + 1
        return made < self.unanswered_calls


class StepFailed(Exception):
    pass


_CANNED: dict[str, StepOutcome] = {
    "parse": StepOutcome(S.PARSED, "stub parse: canned profile"),
    "score": StepOutcome(S.SCORED, "stub score: canned report"),
    "draft_rejection": StepOutcome(S.REJECTION_DRAFTED, "stub draft: canned rejection email"),
    "queue_screen_call": StepOutcome(S.SCREEN_CALL_QUEUED, "screen call queued"),
    "score_transcript": StepOutcome(S.SCREEN_SCORED, "stub transcript score: canned report"),
    "queue_booking_call": StepOutcome(S.BOOKING_CALL_QUEUED, "booking call queued"),
    "booking_call": StepOutcome(S.BOOKING_CALL_DONE, "stub booking call: canned slot"),
    "book_slot": StepOutcome(S.INTERVIEW_BOOKED, "stub booking: intent recorded, nothing sent"),
}


class StubSteps:
    def __init__(self, behaviour: StubBehaviour | None = None) -> None:
        self.behaviour = behaviour or StubBehaviour()

    async def run(self, step: str, candidate: Snapshot) -> StepOutcome:
        if step in self.behaviour.failing_steps:
            raise StepFailed(f"stub {step} configured to fail")
        if step == "screen_call":
            if self.behaviour.unanswered(str(candidate.id)):
                return StepOutcome(S.NO_ANSWER, "stub call: no answer")
            return StepOutcome(S.SCREEN_CALL_DONE, "stub call: canned transcript")
        try:
            return _CANNED[step]
        except KeyError as exc:
            raise StepFailed(f"unknown step {step}") from exc
