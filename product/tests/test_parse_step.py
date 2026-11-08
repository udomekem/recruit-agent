"""The real parse step end to end: apply with a CV, the pipeline parses it with a scripted
model, the redacted copy and profile are stored, and no personal data reaches the model
call, traces or logs."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.api.main import create_app
from app.config import Settings
from app.db.models import CvParse
from app.db.session import SessionMaker
from app.integrations.storage import MemoryStorage
from app.llm.client import LLMClient
from app.llm.providers import FakeProvider
from app.observability.tracing import RecordingTracer
from app.workflow.dispatch import InlineDispatcher
from app.workflow.pipeline import Pipeline
from tests.conftest import TEST_TOKEN
from tests.phase1_helpers import JOB, RUBRIC_JSON, SCORE_JSON, answers

pytestmark = pytest.mark.integration
AUTH = {"Authorization": f"Bearer {TEST_TOKEN}"}
NAME, EMAIL, PHONE = "Zephyrine Quoll-Whitcombe", "zephyrine.quoll@example.test", "0491 570 156"


def cv_docx(extra: str = "") -> bytes:
    from docx import Document

    d = Document()
    for line in [
        NAME,
        "Senior Data Analyst",
        "14 Banksia Road, Toowong QLD 4066",
        f"Phone: {PHONE} | Email: {EMAIL}",
        "Gender: Female",
        "Profile",
        "Analyst with eight years in government data. Proud mum of three.",
        "Experience",
        "Senior Data Analyst, Molonglo Analytics",
        "Mar 2021 to Present",
        "Skills",
        "SQL, Tableau, Python",
        extra,  # before Referees: that section is removed by redaction
        "Referees",
        "Desmond Varga, 0491 570 299",
    ]:
        if line:
            d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


PROFILE = json.dumps(
    {
        "headline": "Senior Data Analyst",
        "summary": None,
        "work_history": [
            {
                "title": "Senior Data Analyst",
                "employer": "Molonglo Analytics",
                "start": "2021-03",
                "end": "present",
                "highlights": [],
            }
        ],
        "education": [],
        "skills": ["SQL", "Tableau", "Python"],
        "certifications": [],
        "licences": [],
        # "Proud mum of three." is removed by code before the model, so the model's span is a
        # statement code does not know about.
        "personal_spans": [
            {"text": "Analyst with eight years in government data.", "kind": "other_personal"}
        ],
    }
)


class Env:
    def __init__(
        self,
        c: httpx.AsyncClient,
        p: Pipeline,
        provider: FakeProvider,
        storage: MemoryStorage,
        tracer: RecordingTracer,
        job_id: str,
    ) -> None:
        self.c, self.p, self.provider, self.storage, self.tracer, self.job_id = (
            c,
            p,
            provider,
            storage,
            tracer,
            job_id,
        )

    async def apply(self, cv: bytes, filename: str = "cv.docx", **ans: str) -> str:
        data = {
            "full_name": NAME,
            "email": EMAIL,
            "phone": PHONE,
            "consent": "yes",
            **answers(**ans),
        }
        r = await self.c.post(f"/apply/{self.job_id}", data=data, files={"cv": (filename, cv, "x")})
        assert r.status_code == 201, r.text
        async with self.p.sessions() as s:
            from app.db.models import Candidate

            cid = (
                await s.execute(select(Candidate.id).where(Candidate.job_id.is_not(None)))
            ).scalar_one()
        return str(cid)

    async def state(self, cid: str) -> dict[str, Any]:
        return (await self.c.get(f"/candidates/{cid}", headers=AUTH)).json()  # type: ignore[no-any-return]


async def make_env(
    sessions: SessionMaker, settings: Settings, script: list[Any]
) -> AsyncIterator[Env]:
    tracer = RecordingTracer()
    provider = FakeProvider([RUBRIC_JSON, *script])
    llm = LLMClient(provider, tracer, settings)
    llm._backoff_scale = 0.0
    storage = MemoryStorage()
    p = Pipeline(sessions, InlineDispatcher(), tracer, settings, llm=llm, storage=storage)
    app = create_app(settings, p, storage)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        job = (await c.post("/jobs", json=JOB, headers=AUTH)).json()
        await p.drain()
        await c.post(
            f"/jobs/{job['id']}/approve", json={"version": 1, "reason": "ok"}, headers=AUTH
        )
        yield Env(c, p, provider, storage, tracer, job["id"])


@pytest.fixture
async def env(sessions: SessionMaker, settings: Settings) -> AsyncIterator[Env]:
    async for e in make_env(sessions, settings, [PROFILE, SCORE_JSON]):
        yield e


async def test_parse_stores_redacted_copy_and_profile(env: Env) -> None:
    cid = await env.apply(cv_docx())
    await env.p.drain()
    assert (await env.state(cid))["state"] == "SCORED"  # parsed, then scored, for real
    r = await env.c.get(f"/candidates/{cid}/parse", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    text = body["redacted_text"]
    for gone in [
        NAME,
        "Zephyrine",
        "Quoll-Whitcombe",
        EMAIL,
        PHONE,
        "Banksia Road",
        "Toowong",
        "4066",
        "Female",
        "Proud mum of three",
        "Desmond Varga",
        "0491 570 299",
    ]:
        assert gone not in text, gone
    for kept in [
        "Senior Data Analyst",
        "Molonglo Analytics",
        "Mar 2021 to Present",
        "SQL, Tableau, Python",
    ]:
        assert kept in text, kept
    assert body["profile"]["work_history"][0]["employer"] == "Molonglo Analytics"
    assert "personal_spans" not in body["profile"]
    assert body["prompt_version"] == "v2" and body["status"] == "parsed"
    assert body["redaction_counts"]["[NAME]"] >= 1
    audit = (await env.state(cid))["audit"]
    assert audit[1]["to_state"] == "PARSED" and "roles" in audit[1]["reason"]


async def test_model_never_receives_the_applicants_identifiers(env: Env) -> None:
    await env.apply(cv_docx())
    await env.p.drain()
    sent = json.dumps(env.provider.calls[1]["messages"])  # calls[0] is the rubric build
    for needle in [NAME, "Zephyrine", "Quoll", EMAIL, PHONE, "570 156", "Banksia", "Desmond Varga"]:
        assert needle not in sent, needle


async def test_scanned_cv_goes_to_review_without_a_model_call(env: Env) -> None:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(10, 10, 300, 300)
    c.save()
    cid = await env.apply(buf.getvalue(), filename="scan.pdf")
    await env.p.drain()
    st = await env.state(cid)
    assert st["state"] == "NEEDS_REVIEW" and "no text layer" in st["audit"][-1]["reason"]
    assert len(env.provider.calls) == 1  # only the rubric build


async def test_invalid_parser_output_goes_to_review_without_personal_data(
    sessions: SessionMaker, settings: Settings
) -> None:
    bad = json.dumps({**json.loads(PROFILE), "skills": ["Neurosurgery"]})
    async for e in make_env(sessions, settings, [bad, bad, bad]):
        cid = await e.apply(cv_docx())
        await e.p.drain()
        st = await e.state(cid)
        assert st["state"] == "NEEDS_REVIEW"
        reason = st["audit"][-1]["reason"]
        assert reason == "cv parser failed: LLMOutputInvalid"
        async with e.p.sessions() as s:
            row = (await s.execute(select(CvParse))).scalar_one()
        assert row.status == "failed" and row.redacted_text is None


async def test_erase_deletes_parse(env: Env) -> None:
    cid = await env.apply(cv_docx())
    await env.p.drain()
    assert (await env.c.post(f"/candidates/{cid}/erase", headers=AUTH)).status_code == 200
    async with env.p.sessions() as s:
        assert (await s.execute(select(func.count()).select_from(CvParse))).scalar() == 0
    assert (await env.c.get(f"/candidates/{cid}/parse", headers=AUTH)).status_code == 404


async def test_no_personal_data_in_traces_or_logs(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    await env.apply(cv_docx(extra="SENTINEL-CV-LINE-4471"))
    await env.p.drain()
    spans = json.dumps(
        [{"n": s.name, **{k: str(v) for k, v in s.fields.items()}} for s in env.tracer.spans]
    )
    logs = "\n".join(r.getMessage() for r in caplog.records)
    for needle in [NAME, EMAIL, PHONE, "Molonglo", "Proud mum", "SENTINEL-CV-LINE-4471", "Tableau"]:
        assert needle.lower() not in spans.lower(), needle
        assert needle.lower() not in logs.lower(), needle
    parse_spans = [s for s in env.tracer.spans if s.name == "step:parse"]
    assert parse_spans and parse_spans[0].fields["outcome"] == "parsed"
