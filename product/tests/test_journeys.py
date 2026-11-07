"""End to end journeys through the recruiter API and stub pipeline (in-process worker).

Covers the phase 0 done criteria: full journeys, decision points the worker never passes,
NEEDS_REVIEW on failure, duplicate jobs, audit completeness, and tracing fields.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.api.main import create_app
from app.config import Settings
from app.domain.states import CandidateState
from app.observability.tracing import REQUIRED_SPAN_FIELDS, RecordingTracer
from app.workflow.dispatch import InlineDispatcher
from app.workflow.machine import audit_trail
from app.workflow.pipeline import Pipeline
from app.workflow.steps import StubBehaviour
from tests.conftest import TEST_TOKEN

S = CandidateState
pytestmark = pytest.mark.integration
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
async def client(settings: Settings, pipeline: Pipeline) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, pipeline)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create(client: httpx.AsyncClient, label: str = "Test candidate") -> uuid.UUID:
    r = await client.post("/candidates", json={"display_label": label}, headers=AUTH)
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


async def _decide(client: httpx.AsyncClient, cid: uuid.UUID, action: str) -> httpx.Response:
    return await client.post(
        f"/candidates/{cid}/{action}", json={"reason": f"test {action}"}, headers=AUTH
    )


async def _state(client: httpx.AsyncClient, cid: uuid.UUID) -> dict[str, Any]:
    r = await client.get(f"/candidates/{cid}", headers=AUTH)
    assert r.status_code == 200
    return r.json()  # type: ignore[no-any-return]


async def test_full_journey_to_interview_booked(
    client: httpx.AsyncClient, pipeline: Pipeline
) -> None:
    cid = await _create(client, "Test candidate booked")
    await pipeline.drain()
    assert (await _state(client, cid))["state"] == S.SCORED  # waits for the recruiter

    assert (await _decide(client, cid, "shortlist")).status_code == 200
    await pipeline.drain()
    assert (await _state(client, cid))["state"] == S.SCREEN_SCORED  # waits again

    assert (await _decide(client, cid, "advance")).status_code == 200
    await pipeline.drain()
    detail = await _state(client, cid)
    assert detail["state"] == S.INTERVIEW_BOOKED
    assert [a["to_state"] for a in detail["audit"]] == [
        "APPLIED",
        "PARSED",
        "SCORED",
        "SHORTLISTED",
        "SCREEN_CALL_QUEUED",
        "SCREEN_CALL_DONE",
        "SCREEN_SCORED",
        "ADVANCED",
        "BOOKING_CALL_QUEUED",
        "BOOKING_CALL_DONE",
        "INTERVIEW_BOOKED",
    ]


async def test_rejection_journey_waits_for_send(
    client: httpx.AsyncClient, pipeline: Pipeline
) -> None:
    cid = await _create(client, "Test candidate rejected")
    await pipeline.drain()
    await _decide(client, cid, "reject")
    await pipeline.drain()
    assert (await _state(client, cid))["state"] == S.REJECTION_DRAFTED  # never auto sent
    await _decide(client, cid, "send-rejection")
    await pipeline.drain()
    assert (await _state(client, cid))["state"] == S.REJECTION_SENT


async def test_worker_never_passes_a_decision_point(
    pipeline: Pipeline, client: httpx.AsyncClient
) -> None:
    """Even if a job is forced at a decision point, nothing moves."""
    cid = await _create(client)
    await pipeline.drain()
    c = await _state(client, cid)
    for _ in range(3):
        assert await pipeline.advance(cid, S(c["state"]), c["state_version"]) is None
    assert (await _state(client, cid))["state"] == S.SCORED


async def test_failed_step_goes_to_review_then_resolves(
    client: httpx.AsyncClient, pipeline: Pipeline, behaviour: StubBehaviour, settings: Settings
) -> None:
    behaviour.failing_steps.add("parse")
    cid = await _create(client, "Test candidate failing parse")
    await pipeline.drain()
    detail = await _state(client, cid)
    assert detail["state"] == S.NEEDS_REVIEW
    assert detail["review_return_state"] == S.APPLIED
    last = detail["audit"][-1]
    assert last["transition_id"] == "T19"
    assert f"failed after {settings.step_max_attempts} attempts" in last["reason"]

    behaviour.failing_steps.clear()
    assert (await _decide(client, cid, "resolve-retry")).status_code == 200
    await pipeline.drain()
    assert (await _state(client, cid))["state"] == S.SCORED


async def test_unanswered_calls_retry_then_review(
    client: httpx.AsyncClient, pipeline: Pipeline, behaviour: StubBehaviour
) -> None:
    behaviour.unanswered_calls = 10
    cid = await _create(client, "Test candidate no answer")
    await pipeline.drain()
    await _decide(client, cid, "shortlist")
    await pipeline.drain()
    detail = await _state(client, cid)
    assert detail["state"] == S.NEEDS_REVIEW
    assert detail["screen_call_attempts"] == 3
    assert detail["audit"][-1]["reason"] == "no answer after 3 attempts"
    assert sum(1 for a in detail["audit"] if a["to_state"] == "NO_ANSWER") == 3


async def test_answer_on_second_try(
    client: httpx.AsyncClient, pipeline: Pipeline, behaviour: StubBehaviour
) -> None:
    behaviour.unanswered_calls = 1
    cid = await _create(client)
    await pipeline.drain()
    await _decide(client, cid, "shortlist")
    await pipeline.drain()
    assert (await _state(client, cid))["state"] == S.SCREEN_SCORED


async def test_withdraw_from_review(
    client: httpx.AsyncClient, pipeline: Pipeline, behaviour: StubBehaviour
) -> None:
    behaviour.failing_steps.add("score")
    cid = await _create(client)
    await pipeline.drain()
    assert (await _decide(client, cid, "withdraw")).status_code == 200
    assert (await _state(client, cid))["state"] == S.WITHDRAWN
    # terminal: nothing else allowed
    assert (await _decide(client, cid, "resolve-retry")).status_code == 409


async def test_duplicate_job_advances_once(client: httpx.AsyncClient, pipeline: Pipeline) -> None:
    cid = await _create(client)
    dispatcher = pipeline.dispatcher
    assert isinstance(dispatcher, InlineDispatcher)
    dispatcher.queue.append(dispatcher.queue[0])  # same job delivered twice
    await pipeline.drain()
    trail = await audit_trail(pipeline.sessions, cid)
    assert [e.to_state for e in trail] == ["APPLIED", "PARSED", "SCORED"]


async def test_illegal_decision_is_409_and_nothing_written(
    client: httpx.AsyncClient, pipeline: Pipeline
) -> None:
    cid = await _create(client)
    await pipeline.drain()
    r = await _decide(client, cid, "advance")  # SCORED -> ADVANCED is not in the table
    assert r.status_code == 409 and r.json()["error"] == "illegal_transition"
    assert len((await _state(client, cid))["audit"]) == 3


async def test_stale_expected_version_is_409(client: httpx.AsyncClient, pipeline: Pipeline) -> None:
    cid = await _create(client)
    await pipeline.drain()
    r = await client.post(
        f"/candidates/{cid}/shortlist",
        json={"reason": "late click", "expected_version": 1},
        headers=AUTH,
    )
    assert r.status_code == 409 and r.json()["error"] == "already_moved"


async def test_requests_without_token_are_refused(client: httpx.AsyncClient) -> None:
    assert (await client.post("/candidates", json={"display_label": "x"})).status_code == 401
    bad = {"Authorization": "Bearer wrong"}
    assert (
        await client.post("/candidates", json={"display_label": "x"}, headers=bad)
    ).status_code == 401


async def test_audit_rows_equal_transitions(client: httpx.AsyncClient, pipeline: Pipeline) -> None:
    cid = await _create(client)
    await pipeline.drain()
    await _decide(client, cid, "reject")
    await pipeline.drain()
    await _decide(client, cid, "send-rejection")
    detail = await _state(client, cid)
    assert detail["state_version"] == len(detail["audit"])  # one audit row per move
    for a in detail["audit"]:
        assert a["actor_type"] and a["actor_id"] and a["reason"] and a["occurred_at"]
        assert a["to_state"]
    assert detail["audit"][0]["from_state"] is None
    assert all(a["from_state"] for a in detail["audit"][1:])


async def test_every_step_span_has_required_fields(
    client: httpx.AsyncClient, pipeline: Pipeline, tracer: RecordingTracer
) -> None:
    cid = await _create(client)
    await pipeline.drain()
    await _decide(client, cid, "shortlist")
    await pipeline.drain()
    step_spans = [s for s in tracer.spans if s.kind != "event"]
    assert len(step_spans) >= 5
    for s in step_spans:
        missing = [f for f in REQUIRED_SPAN_FIELDS if f not in s.fields]
        assert not missing, (s.name, missing)
        assert s.fields["candidate_id"] == str(cid)
    # audit rows link to the trace that moved them
    trail = await audit_trail(pipeline.sessions, cid)
    assert all(e.trace_id for e in trail if e.actor_type == "system")


async def test_health_reports_database_and_redis(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok", "database": "ok", "redis": "ok"}
