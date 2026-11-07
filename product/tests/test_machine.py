"""State machine against a real Postgres: refusals, staleness, idempotency, audit."""

import asyncio

import pytest
from sqlalchemy import func, select

from app.db.models import AuditEvent
from app.db.session import SessionMaker
from app.domain.states import ActorType, CandidateState
from app.workflow.machine import (
    StaleTransition,
    TransitionRefused,
    apply_transition,
    audit_trail,
    create_candidate,
    get_candidate,
)

S = CandidateState
pytestmark = pytest.mark.integration


async def _audit_count(sessions: SessionMaker) -> int:
    async with sessions() as s:
        return int((await s.execute(select(func.count()).select_from(AuditEvent))).scalar_one())


async def test_illegal_transition_is_refused_and_writes_nothing(sessions: SessionMaker) -> None:
    c = await create_candidate(sessions, display_label="Test candidate 1", actor_id="t")
    before = await _audit_count(sessions)
    with pytest.raises(TransitionRefused):
        await apply_transition(
            sessions,
            candidate_id=c.id,
            to_state=S.ADVANCED,
            actor_type=ActorType.RECRUITER,
            actor_id="t",
            reason="skip ahead",
        )
    after = await get_candidate(sessions, c.id)
    assert after.state == S.APPLIED and after.state_version == c.state_version
    assert await _audit_count(sessions) == before


async def test_same_job_twice_moves_once(sessions: SessionMaker) -> None:
    c = await create_candidate(sessions, display_label="Test candidate 2", actor_id="t")
    kwargs = dict(
        candidate_id=c.id,
        to_state=S.PARSED,
        actor_type=ActorType.SYSTEM,
        actor_id="worker",
        reason="stub parse",
        expected_state=S.APPLIED,
        expected_version=c.state_version,
    )
    await apply_transition(sessions, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(StaleTransition):
        await apply_transition(sessions, **kwargs)  # type: ignore[arg-type]
    trail = await audit_trail(sessions, c.id)
    assert [e.to_state for e in trail] == [S.APPLIED, S.PARSED]


async def test_concurrent_recruiter_clicks_first_wins(sessions: SessionMaker) -> None:
    c = await create_candidate(sessions, display_label="Test candidate 3", actor_id="t")
    for to in (S.PARSED, S.SCORED):
        c = await apply_transition(
            sessions,
            candidate_id=c.id,
            to_state=to,
            actor_type=ActorType.SYSTEM,
            actor_id="worker",
            reason="stub",
        )

    async def click(actor: str) -> str:
        try:
            await apply_transition(
                sessions,
                candidate_id=c.id,
                to_state=S.SHORTLISTED,
                actor_type=ActorType.RECRUITER,
                actor_id=actor,
                reason="shortlist",
                expected_state=S.SCORED,
                expected_version=c.state_version,
            )
            return "moved"
        except StaleTransition:
            return "already moved"

    results = await asyncio.gather(click("r1"), click("r2"))
    assert sorted(results) == ["already moved", "moved"]
    trail = await audit_trail(sessions, c.id)
    assert sum(1 for e in trail if e.to_state == S.SHORTLISTED) == 1


async def test_audit_row_has_every_field(sessions: SessionMaker) -> None:
    c = await create_candidate(sessions, display_label="Test candidate 4", actor_id="r1")
    await apply_transition(
        sessions,
        candidate_id=c.id,
        to_state=S.WITHDRAWN,
        actor_type=ActorType.RECRUITER,
        actor_id="r1",
        reason="candidate took another offer",
        trace_id="abc",
    )
    trail = await audit_trail(sessions, c.id)
    last = trail[-1]
    assert (last.from_state, last.to_state, last.actor_type, last.actor_id) == (
        S.APPLIED,
        S.WITHDRAWN,
        "recruiter",
        "r1",
    )
    assert last.reason and last.occurred_at and last.idempotency_key and last.trace_id == "abc"
    assert last.transition_id == "T22"


async def test_reason_is_required(sessions: SessionMaker) -> None:
    c = await create_candidate(sessions, display_label="Test candidate 5", actor_id="t")
    with pytest.raises(ValueError):
        await apply_transition(
            sessions,
            candidate_id=c.id,
            to_state=S.PARSED,
            actor_type=ActorType.SYSTEM,
            actor_id="worker",
            reason="  ",
        )


async def test_needs_review_saves_and_clears_return_state(sessions: SessionMaker) -> None:
    c = await create_candidate(sessions, display_label="Test candidate 6", actor_id="t")
    c = await apply_transition(
        sessions,
        candidate_id=c.id,
        to_state=S.NEEDS_REVIEW,
        actor_type=ActorType.SYSTEM,
        actor_id="worker",
        reason="parse failed",
    )
    assert c.review_return_state == S.APPLIED
    c = await apply_transition(
        sessions,
        candidate_id=c.id,
        to_state=S.APPLIED,
        actor_type=ActorType.RECRUITER,
        actor_id="r1",
        reason="retry",
    )
    assert c.state == S.APPLIED and c.review_return_state is None
