"""Candidate states and the transition table.

This table is the single source of every legal move (design section 2). Nothing else
decides where a candidate may go. Anything not listed here is illegal.
"""

from dataclasses import dataclass
from enum import StrEnum


class CandidateState(StrEnum):
    APPLIED = "APPLIED"
    PARSED = "PARSED"
    SCORED = "SCORED"
    SHORTLISTED = "SHORTLISTED"
    REJECTED = "REJECTED"
    REJECTION_DRAFTED = "REJECTION_DRAFTED"
    REJECTION_SENT = "REJECTION_SENT"
    SCREEN_CALL_QUEUED = "SCREEN_CALL_QUEUED"
    SCREEN_CALL_DONE = "SCREEN_CALL_DONE"
    NO_ANSWER = "NO_ANSWER"
    SCREEN_SCORED = "SCREEN_SCORED"
    ADVANCED = "ADVANCED"
    BOOKING_CALL_QUEUED = "BOOKING_CALL_QUEUED"
    BOOKING_CALL_DONE = "BOOKING_CALL_DONE"
    INTERVIEW_BOOKED = "INTERVIEW_BOOKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    WITHDRAWN = "WITHDRAWN"


class ActorType(StrEnum):
    SYSTEM = "system"
    RECRUITER = "recruiter"
    CANDIDATE = "candidate"


S = CandidateState
TERMINAL: frozenset[CandidateState] = frozenset({S.REJECTION_SENT, S.INTERVIEW_BOOKED, S.WITHDRAWN})
NON_TERMINAL: tuple[CandidateState, ...] = tuple(s for s in S if s not in TERMINAL)

# Sentinel target for T20: "go back to the state saved when the candidate entered review".
RETURN_TO_SAVED = "RETURN_TO_SAVED"


@dataclass(frozen=True)
class Transition:
    id: str
    from_state: CandidateState | None
    to_state: CandidateState | str  # CandidateState, or RETURN_TO_SAVED
    actor: ActorType
    trigger: str


SYS, REC, CAN = ActorType.SYSTEM, ActorType.RECRUITER, ActorType.CANDIDATE

_EXPLICIT: list[Transition] = [
    Transition("T1", None, S.APPLIED, REC, "create candidate"),
    Transition("T2", S.APPLIED, S.PARSED, SYS, "parse step"),
    Transition("T3", S.PARSED, S.SCORED, SYS, "score step"),
    Transition("T4", S.SCORED, S.SHORTLISTED, REC, "shortlist decision"),
    Transition("T5", S.SCORED, S.REJECTED, REC, "reject decision"),
    Transition("T6", S.SCREEN_SCORED, S.REJECTED, REC, "reject decision"),
    Transition("T7", S.REJECTED, S.REJECTION_DRAFTED, SYS, "draft step"),
    Transition("T8", S.REJECTION_DRAFTED, S.REJECTION_SENT, REC, "send rejection decision"),
    Transition("T9", S.SHORTLISTED, S.SCREEN_CALL_QUEUED, SYS, "queue call step"),
    Transition("T10", S.SCREEN_CALL_QUEUED, S.SCREEN_CALL_DONE, SYS, "call step"),
    Transition("T11", S.SCREEN_CALL_QUEUED, S.NO_ANSWER, SYS, "call step"),
    Transition("T12", S.NO_ANSWER, S.SCREEN_CALL_QUEUED, SYS, "retry rule"),
    Transition("T13", S.NO_ANSWER, S.NEEDS_REVIEW, SYS, "retry rule"),
    Transition("T14", S.SCREEN_CALL_DONE, S.SCREEN_SCORED, SYS, "transcript score step"),
    Transition("T15", S.SCREEN_SCORED, S.ADVANCED, REC, "advance decision"),
    Transition("T16", S.ADVANCED, S.BOOKING_CALL_QUEUED, SYS, "queue booking step"),
    Transition("T17", S.BOOKING_CALL_QUEUED, S.BOOKING_CALL_DONE, SYS, "booking call step"),
    Transition("T18", S.BOOKING_CALL_DONE, S.INTERVIEW_BOOKED, SYS, "book slot step"),
    Transition("T20", S.NEEDS_REVIEW, RETURN_TO_SAVED, REC, "resolve: retry"),
    Transition("T21", S.NEEDS_REVIEW, S.REJECTED, REC, "resolve: reject"),
    Transition("T23", None, S.APPLIED, CAN, "apply via the apply page"),
]

_HAS_EXPLICIT_REVIEW = {t.from_state for t in _EXPLICIT if t.to_state == S.NEEDS_REVIEW}

_EXPANDED: list[Transition] = [
    # T19: any non-terminal step state can fail into review (unless a rule row covers it).
    *(
        Transition("T19", s, S.NEEDS_REVIEW, SYS, "step failed all retries")
        for s in NON_TERMINAL
        if s is not S.NEEDS_REVIEW and s not in _HAS_EXPLICIT_REVIEW
    ),
    # T22: a recruiter can withdraw any non-terminal candidate.
    *(Transition("T22", s, S.WITHDRAWN, REC, "withdraw") for s in NON_TERMINAL),
]

TRANSITIONS: tuple[Transition, ...] = tuple(_EXPLICIT + _EXPANDED)


def find_transition(
    from_state: CandidateState | None,
    to_state: CandidateState,
    actor: ActorType,
    saved_return_state: CandidateState | None = None,
) -> Transition | None:
    """Return the table row allowing this move, or None if the move is illegal."""
    for t in TRANSITIONS:
        if t.from_state != from_state or t.actor != actor:
            continue
        if t.to_state == RETURN_TO_SAVED:
            if saved_return_state is not None and to_state == saved_return_state:
                return t
        elif t.to_state == to_state:
            return t
    return None


# System steps fire automatically on entering these states (design section 2).
SYSTEM_STEPS: dict[CandidateState, str] = {
    S.APPLIED: "parse",
    S.PARSED: "score",
    S.REJECTED: "draft_rejection",
    S.SHORTLISTED: "queue_screen_call",
    S.SCREEN_CALL_QUEUED: "screen_call",
    S.NO_ANSWER: "screen_call_retry_rule",
    S.SCREEN_CALL_DONE: "score_transcript",
    S.ADVANCED: "queue_booking_call",
    S.BOOKING_CALL_QUEUED: "booking_call",
    S.BOOKING_CALL_DONE: "book_slot",
}

# States where the pipeline waits for a recruiter decision.
DECISION_POINTS: frozenset[CandidateState] = frozenset(
    {S.SCORED, S.SCREEN_SCORED, S.REJECTION_DRAFTED, S.NEEDS_REVIEW}
)
