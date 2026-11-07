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
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent, Candidate
from app.db.session import SessionMaker
from app.domain.states import TERMINAL, ActorType, CandidateState, find_transition


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


def add_created_audit(
    s: AsyncSession,
    cand: Candidate,
    *,
    actor_type: ActorType,
    actor_id: str,
    reason: str,
    trace_id: str | None = None,
) -> None:
    """Write the creation audit row (T1 recruiter, T23 candidate) in the caller's
    transaction. The candidate row must already be added to the session."""
    t = find_transition(None, CandidateState.APPLIED, actor_type)
    if t is None:
        raise TransitionRefused(f"{actor_type} may not create a candidate")
    s.add(
        AuditEvent(
            candidate_id=cand.id,
            transition_id=t.id,
            from_state=None,
            to_state=CandidateState.APPLIED,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
            idempotency_key=idempotency_key(cand.id, t.id, 0),
            trace_id=trace_id,
        )
    )


async def create_candidate(
    sessions: SessionMaker, *, display_label: str, actor_id: str, trace_id: str | None = None
) -> Snapshot:
    """Test and demo candidates with no job (phase 0 path; refused in production)."""
    cid = uuid.uuid4()
    async with sessions() as s, s.begin():
        cand = Candidate(
            id=cid, state=CandidateState.APPLIED, state_version=1, display_label=display_label
        )
        s.add(cand)
        await s.flush()
        add_created_audit(
            s,
            cand,
            actor_type=ActorType.RECRUITER,
            actor_id=actor_id,
            reason="candidate created",
            trace_id=trace_id,
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
    extra: Callable[[AsyncSession, Candidate], None] | None = None,
) -> Snapshot:
    """`extra` adds rows in the same transaction as the move (e.g. the CV parse result),
    so a candidate is never PARSED without its parse, or the reverse."""
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
            if extra is not None:
                extra(s, cand)
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


class ErasureIncomplete(Exception):
    """The CV object could not be deleted; personal fields are kept so nothing is half
    erased, and the caller reports it for review."""


async def erase_personal_data(
    sessions: SessionMaker, storage: object, candidate_id: uuid.UUID, *, actor_id: str
) -> Snapshot:
    """Delete the CV object and clear contact details and text answers (design section 2).
    A non terminal candidate also moves to WITHDRAWN. The audit row holds no personal data.
    Repeating it is a no-op."""
    from app.db.models import Answer
    from app.integrations.storage import Storage, delete_with_retry

    store: Storage = storage  # type: ignore[assignment]
    async with sessions() as s:
        cand = await s.get(Candidate, candidate_id)
        if cand is None:
            raise CandidateNotFound(str(candidate_id))
        if cand.erased_at is not None:
            return Snapshot.of(cand)
        key = cand.cv_object_key
    if key and not await delete_with_retry(store, key):
        raise ErasureIncomplete("the CV file could not be deleted; nothing was erased")

    from datetime import UTC, datetime

    async with sessions() as s, s.begin():
        cand = (
            await s.execute(select(Candidate).where(Candidate.id == candidate_id).with_for_update())
        ).scalar_one()
        if cand.erased_at is not None:
            return Snapshot.of(cand)
        current = CandidateState(cand.state)
        from_version = cand.state_version
        to = CandidateState.WITHDRAWN if current not in TERMINAL else current
        tid = "T22" if to != current else "ERASE"
        s.add(
            AuditEvent(
                candidate_id=cand.id,
                transition_id=tid,
                from_state=current,
                to_state=to,
                actor_type=ActorType.RECRUITER,
                actor_id=actor_id,
                reason="personal data erased on request",
                idempotency_key=idempotency_key(cand.id, "ERASE", from_version),
            )
        )
        cand.full_name = cand.email = cand.email_normalised = cand.phone = None
        cand.cv_object_key = cand.cv_original_name = cand.cv_sha256 = None
        cand.erased_at = datetime.now(UTC)
        cand.state = to
        cand.state_version = from_version + 1
        cand.review_return_state = None
        from sqlalchemy import delete as sql_delete

        from app.db.models import CvParse

        await s.execute(sql_delete(CvParse).where(CvParse.candidate_id == cand.id))
        answers = (await s.execute(select(Answer).where(Answer.candidate_id == cand.id))).scalars()
        for a in answers:
            if isinstance(a.value, str):
                a.value = None
        await s.flush()
        return Snapshot.of(cand)
