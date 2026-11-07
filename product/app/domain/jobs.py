"""Job states and the job transition table (phase 1 design section 2).

Same guarantees as candidates: this table is the single source of legal job moves.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.domain.states import ActorType


class JobState(StrEnum):
    DRAFT = "DRAFT"
    RUBRIC_READY = "RUBRIC_READY"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class WorkArrangement(StrEnum):
    ONSITE = "onsite"
    HYBRID = "hybrid"
    REMOTE = "remote"


@dataclass(frozen=True)
class JobTransition:
    id: str
    from_state: JobState | None
    to_state: JobState
    actor: ActorType
    trigger: str


J = JobState
SYS, REC = ActorType.SYSTEM, ActorType.RECRUITER

JOB_TRANSITIONS: tuple[JobTransition, ...] = (
    JobTransition("J1", None, J.DRAFT, REC, "create job"),
    JobTransition("J2", J.DRAFT, J.RUBRIC_READY, SYS, "rubric built"),
    JobTransition("J3", J.DRAFT, J.NEEDS_REVIEW, SYS, "rubric build failed"),
    JobTransition("J4", J.RUBRIC_READY, J.RUBRIC_READY, REC, "edit rubric"),
    JobTransition("J5", J.RUBRIC_READY, J.DRAFT, REC, "edit job description"),
    JobTransition("J6", J.RUBRIC_READY, J.OPEN, REC, "approve rubric and open"),
    JobTransition("J7", J.OPEN, J.CLOSED, REC, "close"),
    JobTransition("J8", J.CLOSED, J.OPEN, REC, "reopen"),
    JobTransition("J9", J.CLOSED, J.RUBRIC_READY, REC, "revise rubric"),
    JobTransition("J10", J.NEEDS_REVIEW, J.DRAFT, REC, "retry build"),
    JobTransition("J11", J.NEEDS_REVIEW, J.RUBRIC_READY, REC, "supply rubric by hand"),
)


def find_job_transition(
    from_state: JobState | None, to_state: JobState, actor: ActorType, trigger: str | None = None
) -> JobTransition | None:
    """Return the row allowing this move. `trigger` picks between rows with the same
    from/to pair (none today, but J4 is a self move and must be asked for by name)."""
    for t in JOB_TRANSITIONS:
        same = t.from_state == from_state and t.to_state == to_state and t.actor == actor
        if same and (trigger is None or t.trigger == trigger):
            return t
    return None


# The job step that runs automatically on entering a state.
JOB_SYSTEM_STEPS: dict[JobState, str] = {J.DRAFT: "build_rubric"}
