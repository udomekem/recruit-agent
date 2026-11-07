"""Jobs, screening questions and rubrics through the API, with a scripted fake model."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.api.main import create_app
from app.config import Settings
from app.db.session import SessionMaker
from app.integrations.storage import MemoryStorage
from app.llm.client import LLMClient
from app.llm.providers import FakeProvider, ProviderResponse
from app.observability.tracing import RecordingTracer
from app.workflow.dispatch import InlineDispatcher
from app.workflow.pipeline import Pipeline
from tests.conftest import TEST_TOKEN
from tests.phase1_helpers import JOB, RUBRIC, RUBRIC_JSON

pytestmark = pytest.mark.integration
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}


def make_pipeline(sessions: SessionMaker, settings: Settings, script: list[Any] | None) -> Pipeline:
    tracer = RecordingTracer()
    llm = None
    if script is not None:
        llm = LLMClient(FakeProvider(script), tracer, settings)
        llm._backoff_scale = 0.0
    return Pipeline(sessions, InlineDispatcher(), tracer, settings, llm=llm)


async def client_for(settings: Settings, pipeline: Pipeline) -> httpx.AsyncClient:
    app = create_app(settings, pipeline, MemoryStorage())
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def ok(
    sessions: SessionMaker, settings: Settings
) -> AsyncIterator[tuple[httpx.AsyncClient, Pipeline]]:
    p = make_pipeline(sessions, settings, [RUBRIC_JSON])
    async with await client_for(settings, p) as c:
        yield c, p


async def _create(c: httpx.AsyncClient, **over: Any) -> dict[str, Any]:
    r = await c.post("/jobs", json={**JOB, **over}, headers=AUTH)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def _detail(c: httpx.AsyncClient, jid: str) -> dict[str, Any]:
    r = await c.get(f"/jobs/{jid}", headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def test_create_job_builds_rubric_and_adds_standard_questions(ok: Any) -> None:
    c, p = ok
    job = await _create(c)
    assert job["state"] == "DRAFT"
    await p.drain()
    d = await _detail(c, job["id"])
    assert d["state"] == "RUBRIC_READY"
    assert [q["key"] for q in d["questions"]] == [
        "right_to_work",
        "expected_salary",
        "notice_period",
        "location_fit",
        "current_role",
    ]
    assert d["questions"][0]["knockout_rule"]["hard_fail"] is True
    assert len(d["rubrics"]) == 1 and d["rubrics"][0]["source"] == "ai"
    assert d["rubrics"][0]["prompt_version"] == "v1" and d["rubrics"][0]["model"]
    assert [a["transition_id"] for a in d["audit"]] == ["J1", "J2"]


async def test_judgement_tier_uses_fallback_and_medium_effort(
    sessions: SessionMaker, settings: Settings
) -> None:
    p = make_pipeline(sessions, settings, [RUBRIC_JSON])
    async with await client_for(settings, p) as c:
        await _create(c)
        await p.drain()
    assert p.llm is not None
    call = p.llm.provider.calls[0]  # type: ignore[attr-defined]
    assert call["fallback"] is True and call["effort"] == "medium"
    assert call["model"] == "claude-sonnet-5-5"


async def test_approve_opens_job_and_locks_rubric(ok: Any) -> None:
    c, p = ok
    job = await _create(c)
    await p.drain()
    r = await c.post(
        f"/jobs/{job['id']}/approve", json={"version": 1, "reason": "looks right"}, headers=AUTH
    )
    assert r.status_code == 200 and r.json()["state"] == "OPEN"
    assert r.json()["approved_rubric_version"] == 1
    edit = await c.post(
        f"/jobs/{job['id']}/rubric", json={**RUBRIC, "reason": "tweak"}, headers=AUTH
    )
    assert edit.status_code == 409  # no rubric change while open
    d = await _detail(c, job["id"])
    assert d["rubrics"][0]["approved_by"] == "recruiter-dev"


async def test_edit_makes_new_version_and_old_version_cannot_be_approved(ok: Any) -> None:
    c, p = ok
    job = await _create(c)
    await p.drain()
    r = await c.post(
        f"/jobs/{job['id']}/rubric", json={**RUBRIC, "reason": "reweight"}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    stale = await c.post(
        f"/jobs/{job['id']}/approve", json={"version": 1, "reason": "x"}, headers=AUTH
    )
    assert stale.status_code == 409
    good = await c.post(
        f"/jobs/{job['id']}/approve", json={"version": 2, "reason": "x"}, headers=AUTH
    )
    assert good.status_code == 200
    d = await _detail(c, job["id"])
    assert [r["version"] for r in d["rubrics"]] == [1, 2]
    assert d["rubrics"][1]["source"] == "recruiter"
    assert [a["transition_id"] for a in d["audit"]] == ["J1", "J2", "J4", "J6"]


async def test_invalid_model_output_moves_job_to_review(
    sessions: SessionMaker, settings: Settings
) -> None:
    bad = json.dumps(
        {**RUBRIC, "criteria": [{**RUBRIC["criteria"][0], "evidence": "made up quote"}]}
    )
    p = make_pipeline(sessions, settings, [bad, bad, bad])
    async with await client_for(settings, p) as c:
        job = await _create(c)
        await p.drain()
        d = await _detail(c, job["id"])
    assert d["state"] == "NEEDS_REVIEW"
    assert d["audit"][-1]["transition_id"] == "J3"
    assert "exact quote from the ad" in d["audit"][-1]["reason"]


async def test_refusal_moves_job_to_review(sessions: SessionMaker, settings: Settings) -> None:
    p = make_pipeline(
        sessions, settings, [ProviderResponse(None, "refusal", 10, 0, "claude-sonnet-5-5")]
    )
    async with await client_for(settings, p) as c:
        job = await _create(c)
        await p.drain()
        assert (await _detail(c, job["id"]))["state"] == "NEEDS_REVIEW"


async def test_no_model_configured_moves_job_to_review(
    sessions: SessionMaker, settings: Settings
) -> None:
    p = make_pipeline(sessions, settings, None)
    async with await client_for(settings, p) as c:
        job = await _create(c)
        await p.drain()
        d = await _detail(c, job["id"])
    assert d["state"] == "NEEDS_REVIEW" and "not set" in d["audit"][-1]["reason"]


async def test_review_then_supply_rubric_by_hand(
    sessions: SessionMaker, settings: Settings
) -> None:
    p = make_pipeline(sessions, settings, None)
    async with await client_for(settings, p) as c:
        job = await _create(c)
        await p.drain()
        r = await c.post(
            f"/jobs/{job['id']}/rubric", json={**RUBRIC, "reason": "wrote it myself"}, headers=AUTH
        )
        assert r.status_code == 200 and r.json()["state"] == "RUBRIC_READY"
        d = await _detail(c, job["id"])
    assert d["audit"][-1]["transition_id"] == "J11"


async def test_retry_build_after_review(sessions: SessionMaker, settings: Settings) -> None:
    bad = "not json"
    p = make_pipeline(sessions, settings, [bad, bad, bad, RUBRIC_JSON])
    async with await client_for(settings, p) as c:
        job = await _create(c)
        await p.drain()
        r = await c.post(
            f"/jobs/{job['id']}/retry-build", json={"reason": "try again"}, headers=AUTH
        )
        assert r.status_code == 200
        await p.drain()
        assert (await _detail(c, job["id"]))["state"] == "RUBRIC_READY"


async def test_description_edit_rebuilds(sessions: SessionMaker, settings: Settings) -> None:
    p = make_pipeline(sessions, settings, [RUBRIC_JSON, RUBRIC_JSON])
    async with await client_for(settings, p) as c:
        job = await _create(c)
        await p.drain()
        r = await c.put(
            f"/jobs/{job['id']}/description",
            json={
                "description": JOB["description"] + "\nAlso: Agile teams welcome.",
                "reason": "added",
            },
            headers=AUTH,
        )
        assert r.status_code == 200 and r.json()["state"] == "DRAFT"
        await p.drain()
        d = await _detail(c, job["id"])
    assert d["state"] == "RUBRIC_READY" and [r["version"] for r in d["rubrics"]] == [1, 2]


async def test_close_reopen_and_revise(ok: Any) -> None:
    c, p = ok
    job = await _create(c)
    await p.drain()
    await c.post(f"/jobs/{job['id']}/approve", json={"version": 1, "reason": "ok"}, headers=AUTH)
    assert (
        await c.post(f"/jobs/{job['id']}/close", json={"reason": "filled"}, headers=AUTH)
    ).json()["state"] == "CLOSED"
    assert (
        await c.post(f"/jobs/{job['id']}/reopen", json={"reason": "again"}, headers=AUTH)
    ).json()["state"] == "OPEN"
    await c.post(f"/jobs/{job['id']}/close", json={"reason": "pause"}, headers=AUTH)
    r = await c.post(f"/jobs/{job['id']}/rubric", json={**RUBRIC, "reason": "revise"}, headers=AUTH)
    assert r.json()["state"] == "RUBRIC_READY"


async def test_protected_wording_refused_in_custom_question_and_recruiter_rubric(ok: Any) -> None:
    c, p = ok
    q = {"key": "age_q", "prompt": "Are you under 30?", "answer_type": "yes_no"}
    r = await c.post("/jobs", json={**JOB, "questions": [q]}, headers=AUTH)
    assert r.status_code == 422
    job = await _create(c)
    await p.drain()
    bad = {
        **RUBRIC,
        "criteria": [{**RUBRIC["criteria"][0], "text": "Young and energetic"}],
        "reason": "x",
    }
    r = await c.post(f"/jobs/{job['id']}/rubric", json=bad, headers=AUTH)
    assert r.status_code == 422 and "protected" in r.json()["detail"]


async def test_illegal_job_moves_refused(ok: Any) -> None:
    c, p = ok
    job = await _create(c)
    r = await c.post(
        f"/jobs/{job['id']}/approve", json={"version": 1, "reason": "too early"}, headers=AUTH
    )
    assert r.status_code == 409  # DRAFT cannot open
    r = await c.post(f"/jobs/{uuid.uuid4()}/close", json={"reason": "x"}, headers=AUTH)
    assert r.status_code == 404


async def test_job_validation(ok: Any) -> None:
    c, _ = ok
    assert (
        await c.post("/jobs", json={**JOB, "description": "too short"}, headers=AUTH)
    ).status_code == 422
    assert (
        await c.post("/jobs", json={**JOB, "salary_min": 200000}, headers=AUTH)
    ).status_code == 422
