"""Apply page, intake adapter, bulk upload, erasure, and personal data hygiene."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.api.main import create_app
from app.config import Settings
from app.db.models import Answer, AuditEvent, Candidate
from app.db.session import SessionMaker
from app.integrations.storage import MemoryStorage
from app.llm.client import LLMClient
from app.llm.providers import FakeProvider
from app.observability.tracing import RecordingTracer
from app.workflow.dispatch import InlineDispatcher
from app.workflow.pipeline import Pipeline
from tests.conftest import TEST_TOKEN
from tests.phase1_helpers import JOB, PDF, RUBRIC_JSON, answers, docx

pytestmark = pytest.mark.integration
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}

SENTINEL_NAME = "Zephyrine Quoll-Whitcombe"
SENTINEL_EMAIL = "zephyrine.quoll@example.test"
SENTINEL_PHONE = "0491 570 156"
SENTINEL_CV = b"%PDF-1.7\nSENTINEL-CV-CONTENT-7731\n%%EOF\n"


class Env:
    def __init__(
        self,
        client: httpx.AsyncClient,
        pipeline: Pipeline,
        storage: MemoryStorage,
        tracer: RecordingTracer,
        job_id: str,
    ) -> None:
        self.c, self.p, self.storage, self.tracer, self.job_id = (
            client,
            pipeline,
            storage,
            tracer,
            job_id,
        )

    async def apply(
        self,
        *,
        name: str = "Alex Example",
        email: str = "alex@example.test",
        phone: str | None = "0400 000 000",
        consent: bool = True,
        cv: bytes = PDF,
        filename: str = "cv.pdf",
        **ans: str,
    ) -> httpx.Response:
        data = {"full_name": name, "email": email, **answers(**ans)}
        if phone:
            data["phone"] = phone
        if consent:
            data["consent"] = "yes"
        return await self.c.post(
            f"/apply/{self.job_id}", data=data, files={"cv": (filename, cv, "application/pdf")}
        )

    async def candidates(self) -> list[Candidate]:
        async with self.p.sessions() as s:
            return list(
                (await s.execute(select(Candidate).where(Candidate.job_id.is_not(None)))).scalars()
            )


@pytest.fixture
async def env(sessions: SessionMaker, settings: Settings) -> AsyncIterator[Env]:
    tracer = RecordingTracer()
    llm = LLMClient(FakeProvider([RUBRIC_JSON]), tracer, settings)
    p = Pipeline(sessions, InlineDispatcher(), tracer, settings, llm=llm)
    storage = MemoryStorage()
    app = create_app(settings, p, storage)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post("/jobs", json=JOB, headers=AUTH)
        job_id = r.json()["id"]
        await p.drain()
        r = await c.post(
            f"/jobs/{job_id}/approve", json={"version": 1, "reason": "ok"}, headers=AUTH
        )
        assert r.json()["state"] == "OPEN"
        yield Env(c, p, storage, tracer, job_id)


async def test_apply_page_shows_notice_questions_and_unticked_consent(env: Env) -> None:
    r = await env.c.get(f"/apply/{env.job_id}")
    assert r.status_code == 200
    html = r.text
    assert "Business Analyst" in html and "right to work in Australia" in html
    assert "AI assisted system" in html and "A person makes every decision" in html
    consent_tag = html.split('name="consent"')[1].split(">")[0]
    assert "checked" not in consent_tag  # consent is never pre-ticked
    assert "Notice version v1" in html


async def test_successful_application(env: Env) -> None:
    r = await env.apply()
    assert r.status_code == 201, r.text
    assert "your application is in" in r.text
    [cand] = await env.candidates()
    assert cand.state == "APPLIED" and str(cand.job_id) == env.job_id
    assert cand.display_label == "Applicant 1" and cand.consent_basis == "candidate"
    assert cand.consent_notice_version == "v1" and cand.cv_media_type == "application/pdf"
    assert cand.cv_object_key in env.storage.objects
    assert "alex" not in (cand.cv_object_key or "").lower()  # random key, no personal data
    head = await env.storage.head(cand.cv_object_key or "")
    assert head is not None and head.encrypted
    async with env.p.sessions() as s:
        n = (
            await s.execute(
                select(func.count()).select_from(Answer).where(Answer.candidate_id == cand.id)
            )
        ).scalar()
        [created] = (
            await s.execute(select(AuditEvent).where(AuditEvent.candidate_id == cand.id))
        ).scalars()
    assert n == 5 and created.transition_id == "T23" and created.actor_type == "candidate"
    await env.p.drain()  # the pipeline starts
    [cand] = await env.candidates()
    assert cand.state == "SCORED"


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"consent": False}, "consent"),
        ({"cv": b"MZ\x90\x00 this is an exe", "filename": "cv.pdf"}, "cv"),
        ({"cv": docx(macros=True), "filename": "cv.docm"}, "cv"),
        ({"cv": docx(macros=True), "filename": "cv.docx"}, "cv"),
        ({"cv": PDF, "filename": "cv.docx"}, "cv"),
        ({"cv": b""}, "cv"),
        ({"q_right_to_work": ""}, "q_right_to_work"),
        ({"q_notice_period": "next year"}, "q_notice_period"),
        ({"q_expected_salary": "lots"}, "q_expected_salary"),
        ({"email": "not-an-email"}, "email"),
        ({"name": "A"}, "full_name"),
    ],
)
async def test_bad_applications_refused_and_nothing_stored(
    env: Env, kwargs: dict[str, Any], field: str
) -> None:
    r = await env.apply(**kwargs)
    assert r.status_code == 422, r.text
    assert "Please fix the highlighted fields" in r.text
    assert await env.candidates() == []
    assert env.storage.objects == {}


async def test_oversize_cv_refused(env: Env, settings: Settings) -> None:
    big = b"%PDF-1.7\n" + b"0" * (settings.cv_max_bytes + 10)
    r = await env.apply(cv=big)
    assert r.status_code == 422 and "larger than" in r.text
    assert env.storage.objects == {}


async def test_docx_accepted(env: Env) -> None:
    r = await env.apply(cv=docx(), filename="My CV.docx")
    assert r.status_code == 201, r.text


async def test_duplicate_application_is_one_candidate(env: Env) -> None:
    assert (await env.apply(email="Sam@Example.test")).status_code == 201
    r = await env.apply(email="  sam@example.TEST ")
    assert r.status_code == 200 and "already have your application" in r.text
    assert len(await env.candidates()) == 1
    assert len(env.storage.objects) == 1


async def test_closed_or_missing_job_refused(env: Env) -> None:
    await env.c.post(f"/jobs/{env.job_id}/close", json={"reason": "filled"}, headers=AUTH)
    assert (await env.c.get(f"/apply/{env.job_id}")).status_code == 404
    assert (await env.apply()).status_code == 404
    assert await env.candidates() == []


async def test_storage_down_refuses_cleanly(env: Env) -> None:
    env.storage.fail_puts = True
    r = await env.apply()
    assert r.status_code == 503 and "try again later" in r.text
    assert await env.candidates() == []


async def test_database_failure_after_store_leaves_no_orphan(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.intake.service as svc

    def boom(*a: Any, **k: Any) -> None:
        raise RuntimeError("database write failed")

    monkeypatch.setattr(svc, "add_created_audit", boom)
    with pytest.raises(RuntimeError):
        await env.apply()
    assert env.storage.objects == {}
    assert await env.candidates() == []


async def test_bulk_upload(env: Env) -> None:
    meta = [
        {"filename": "a.pdf", "full_name": "Ana Bulk", "email": "ana@example.test"},
        {"filename": "b.docx", "full_name": "Ben Bulk", "email": "ben@example.test"},
    ]
    files = [
        ("files", ("a.pdf", PDF, "application/pdf")),
        ("files", ("b.docx", docx(), "x")),
        ("files", ("c.pdf", PDF, "application/pdf")),
    ]
    r = await env.c.post(
        f"/jobs/{env.job_id}/candidates/bulk",
        headers=AUTH,
        files=files,
        data={
            "metadata": json.dumps(meta),
            "original_platform": "Seek",
            "consent_attested": "true",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2
    assert [x["status"] for x in body["results"]] == ["created", "created", "refused"]
    cands = await env.candidates()
    assert {c.consent_basis for c in cands} == {"recruiter_attested"} and {
        c.source for c in cands
    } == {"bulk_upload"}


async def test_bulk_upload_needs_attestation_and_token(env: Env) -> None:
    meta = [{"filename": "a.pdf", "full_name": "Ana Bulk", "email": "ana@example.test"}]
    files = [("files", ("a.pdf", PDF, "application/pdf"))]
    r = await env.c.post(
        f"/jobs/{env.job_id}/candidates/bulk",
        headers=AUTH,
        files=files,
        data={
            "metadata": json.dumps(meta),
            "original_platform": "Seek",
            "consent_attested": "false",
        },
    )
    assert r.json()["results"][0]["status"] == "refused"
    r = await env.c.post(
        f"/jobs/{env.job_id}/candidates/bulk",
        files=files,
        data={
            "metadata": json.dumps(meta),
            "original_platform": "Seek",
            "consent_attested": "true",
        },
    )
    assert r.status_code == 401


async def test_erase_removes_personal_data_keeps_audit(env: Env) -> None:
    await env.apply(
        name=SENTINEL_NAME,
        email=SENTINEL_EMAIL,
        phone=SENTINEL_PHONE,
        q_current_role="Lead at Quoll Pty Ltd",
    )
    [cand] = await env.candidates()
    key = cand.cv_object_key
    r = await env.c.post(f"/candidates/{cand.id}/erase", headers=AUTH)
    assert r.status_code == 200 and r.json()["state"] == "WITHDRAWN"
    assert key not in env.storage.objects
    [cand] = await env.candidates()
    assert cand.erased_at and cand.full_name is None and cand.email is None and cand.phone is None
    assert cand.cv_object_key is None
    async with env.p.sessions() as s:
        values = [
            a.value
            for a in (
                await s.execute(select(Answer).where(Answer.candidate_id == cand.id))
            ).scalars()
        ]
        audit = list(
            (
                await s.execute(select(AuditEvent).where(AuditEvent.candidate_id == cand.id))
            ).scalars()
        )
    assert "Lead at Quoll Pty Ltd" not in values and True in values  # text cleared, yes/no kept
    assert [a.transition_id for a in audit][-1] == "T22"
    blob = " ".join(f"{a.reason} {a.actor_id}" for a in audit)
    assert SENTINEL_NAME not in blob and SENTINEL_EMAIL not in blob
    again = await env.c.post(f"/candidates/{cand.id}/erase", headers=AUTH)
    assert again.status_code == 200
    async with env.p.sessions() as s:
        n = (
            await s.execute(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.candidate_id == cand.id)
            )
        ).scalar()
    assert n == len(audit)  # second erase is a no-op
    assert (
        await env.apply(name=SENTINEL_NAME, email=SENTINEL_EMAIL)
    ).status_code == 201  # email released


async def test_erase_storage_failure_erases_nothing(env: Env) -> None:
    await env.apply()
    [cand] = await env.candidates()
    env.storage.fail_deletes = 5
    r = await env.c.post(f"/candidates/{cand.id}/erase", headers=AUTH)
    assert r.status_code == 503
    [cand] = await env.candidates()
    assert cand.erased_at is None and cand.email is not None


async def test_no_personal_data_in_traces_or_logs(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await env.apply(name=SENTINEL_NAME, email=SENTINEL_EMAIL, phone=SENTINEL_PHONE, cv=SENTINEL_CV)
    await env.apply(
        name=SENTINEL_NAME, email=SENTINEL_EMAIL, phone=SENTINEL_PHONE, cv=SENTINEL_CV
    )  # duplicate
    await env.apply(
        name=SENTINEL_NAME, email="bad", phone=SENTINEL_PHONE, cv=SENTINEL_CV
    )  # refused
    await env.p.drain()
    spans = json.dumps(
        [{"name": s.name, **{k: str(v) for k, v in s.fields.items()}} for s in env.tracer.spans]
    )
    logs = "\n".join(r.getMessage() for r in caplog.records)
    for needle in (
        SENTINEL_NAME,
        SENTINEL_EMAIL,
        SENTINEL_PHONE,
        "SENTINEL-CV-CONTENT-7731",
        "zephyrine",
    ):
        assert needle.lower() not in spans.lower(), needle
        assert needle.lower() not in logs.lower(), needle
    assert any(s.name.startswith("step:") for s in env.tracer.spans)  # tracing did run
