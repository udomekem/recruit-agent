"""The state machine: the only code that writes candidate state.

Every move:
- must be a row in the transition table (else TransitionRefused, nothing written)
- must start from the state and version the caller expects (else StaleTransition)
- writes the state change and one audit row in a single transaction
- carries an idempotency key (candidate + transition + starting version), unique in the
  audit table, so the same move can never be applied twice
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models import AuditEvent, Candidate
from app.db.session import SessionMaker
from app.domain.states import ActorType, CandidateState, find_transition


class TransitionRefused(Exception):
    """The move is not in the transition table."""


class StaleTransition(Exception):
    """The candidate already moved (duplicate job, double click, or out of date caller)."""


class CandidateNotFound(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    id: uuid.UUID
    state: CandidateState
    state_version: int
    review_return_state: CandidateState | None
    screen_call_attempts: int
    display_label: str

    @classmethod
    def of(cls, c: Candidate) -> Snapshot:
        return cls(
            id=c.id,
            state=CandidateState(c.state),
            state_version=c.state_version,
            review_return_state=CandidateState(c.review_return_state)
            if c.review_return_state
            else None,
            screen_call_attempts=c.screen_call_attempts,
            display_label=c.display_label,
        )


def idempotency_key(candidate_id: uuid.UUID, transition_id: str, from_version: int) -> str:
    return f"{candidate_id}:{transition_id}:v{from_version}"


async def create_candidate(
    sessions: SessionMaker, *, display_label: str, actor_id: str, trace_id: str | None = None
) -> Snapshot:
    t = find_transition(None, CandidateState.APPLIED, ActorType.RECRUITER)
    assert t is not None
    cid = uuid.uuid4()
    async with sessions() as s, s.begin():
        cand = Candidate(
            id=cid, state=CandidateState.APPLIED, state_version=1, display_label=display_label
        )
        s.add(cand)
        await s.flush()
        s.add(
            AuditEvent(
                candidate_id=cid,
                transition_id=t.id,
                from_state=None,
                to_state=CandidateState.APPLIED,
                actor_type=ActorType.RECRUITER,
                actor_id=actor_id,
                reason="candidate created",
                idempotency_key=idempotency_key(cid, t.id, 0),
                trace_id=trace_id,
            )
        )
    return Snapshot.of(cand)


async def get_candidate(sessions: SessionMaker, candidate_id: uuid.UUID) -> Snapshot:
    async with sessions() as s:
        cand = await s.get(Candidate, candidate_id)
        if cand is None:
            raise CandidateNotFound(str(candidate_id))
        return Snapshot.of(cand)


async def apply_transition(
    sessions: SessionMaker,
    *,
    candidate_id: uuid.UUID,
    to_state: CandidateState,
    actor_type: ActorType,
    actor_id: str,
    reason: str,
    expected_state: CandidateState | None = None,
    expected_version: int | None = None,
    trace_id: str | None = None,
) -> Snapshot:
    if not reason.strip():
        raise ValueError("every transition needs a reason")
    try:
        async with sessions() as s, s.begin():
            cand = (
                await s.execute(
                    select(Candidate).where(Candidate.id == candidate_id).with_for_update()
                )
            ).scalar_one_or_none()
            if cand is None:
                raise CandidateNotFound(str(candidate_id))
            current = CandidateState(cand.state)
            if expected_state is not None and current != expected_state:
                raise StaleTransition(f"candidate is {current}, expected {expected_state}")
            if expected_version is not None and cand.state_version != expected_version:
                raise StaleTransition(
                    f"candidate is at version {cand.state_version}, expected {expected_version}"
                )
            saved = CandidateState(cand.review_return_state) if cand.review_return_state else None
            t = find_transition(current, to_state, actor_type, saved_return_state=saved)
            if t is None:
                raise TransitionRefused(
                    f"{actor_type} may not move a candidate from {current} to {to_state}"
                )
            from_version = cand.state_version
            s.add(
                AuditEvent(
                    candidate_id=cand.id,
                    transition_id=t.id,
                    from_state=current,
                    to_state=to_state,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    reason=reason,
                    idempotency_key=idempotency_key(cand.id, t.id, from_version),
                    trace_id=trace_id,
                )
            )
            cand.state = to_state
            cand.state_version = from_version + 1
            cand.review_return_state = current if to_state == CandidateState.NEEDS_REVIEW else None
            if to_state == CandidateState.NO_ANSWER:
                cand.screen_call_attempts += 1
            await s.flush()
            return Snapshot.of(cand)
    except IntegrityError as exc:  # same idempotency key committed by a concurrent writer
        raise StaleTransition("this move was already applied") from exc


async def audit_trail(sessions: SessionMaker, candidate_id: uuid.UUID) -> list[AuditEvent]:
    async with sessions() as s:
        rows = await s.execute(
            select(AuditEvent)
            .where(AuditEvent.candidate_id == candidate_id)
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        )
        return list(rows.scalars())
