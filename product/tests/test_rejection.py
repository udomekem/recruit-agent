"""Phase 5: rejection drafts, hard rule checks, edits, one click send and idempotent
delivery (phase 5 design sections 2 to 8)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.db.models import OutboundEmail, RejectionDraft
from app.db.session import SessionMaker
from app.integrations.email import LogSender, MailpitSender, ResendSender, make_sender
from app.rejection.checks import run_checks
from app.rejection.compose import (
    NAME_PLACEHOLDER,
    assemble_body,
    full_text,
    reason_sources,
    template_parts,
)
from tests.phase1_helpers import RUBRIC, score_json
from tests.test_parse_step import AUTH, EMAIL, NAME, PHONE, PROFILE, Env, cv_docx, make_env

WEAK = score_json()  # 43.3 reject: ba_experience partly met, stakeholders and insurance not met
STRONG = score_json(ba_experience="met", stakeholders="met")  # advance

OPENING = (
    "Thank you for applying for this role with Northwind Talent and for the time you gave "
    "to your application. We have decided not to take your application further this time."
)
REASONS = [
    (
        "criterion:stakeholders",
        "This role works closely with senior leaders every week, so we were looking for "
        "someone who has managed those relationships directly.",
    ),
    (
        "criterion:insurance",
        "The team works on insurance products, so insurance industry experience is part of it.",
    ),
    (
        "criterion:ba_experience",
        "The role also asks for three years in business analysis; your analyst work is "
        "close, but business analysis is the core of this job.",
    ),
]
CLOSING = "We are grateful for your interest and wish you every success with your next step."
GOOD_BODY = assemble_body(OPENING, [s for _i, s in REASONS], CLOSING)


def writer_json(reasons: list[tuple[str, str]] | None = None, **over: str) -> str:
    return json.dumps(
        {
            "opening": over.get("opening", OPENING),
            "reasons": [
                {"source_id": i, "sentence": s}
                for i, s in (REASONS if reasons is None else reasons)
            ],
            "closing": over.get("closing", CLOSING),
        }
    )


# ---- checks (no database) ---------------------------------------------------------------


def _failed(body: str, **kw: Any) -> set[str]:
    results = run_checks(
        body,
        reason_ids=kw.get("reason_ids", ["criterion:stakeholders"]),
        allowed_ids=kw.get("allowed_ids", ["criterion:stakeholders", "criterion:ba_experience"]),
        cv_text=kw.get("cv_text", "Senior Data Analyst, Molonglo Analytics. SQL, Tableau, Python."),
    )
    return {r.rule for r in results if not r.passed}


def test_good_body_passes_every_rule() -> None:
    assert _failed(GOOD_BODY) == set()


@pytest.mark.parametrize(
    "extra,rule",
    [
        ("We could see a career gap between roles.", "H2"),
        ("As a new mum you may find the hours hard.", "H2"),
        ("The hours may not suit your young children.", "H2"),
        ("Your accent was hard to follow on the form.", "H2"),
        ("The commute from your suburb is long.", "H2"),
        ("Your stakeholder experience was poor.", "H3"),
        ("Unfortunately, you were overqualified.", "H3"),
        ("You scored 42 out of 100.", "H4"),
        ("You were ranked below the shortlist threshold.", "H4"),
        ("See https://evil.example.com for details.", "H6"),
        ("Write to hr@northwind.example instead.", "H6"),
        ("Call 0491 570 156 to talk.", "H6"),
        ("We would like to offer you the role.", "H7"),
        ("Congratulations, you are hired.", "H7"),
    ],
)
def test_each_rule_catches_its_case(extra: str, rule: str) -> None:
    assert rule in _failed(f"{GOOD_BODY} {extra}")


def test_invented_reason_and_copied_text_and_length() -> None:
    assert "H1" in _failed(GOOD_BODY, reason_ids=["criterion:insurance"])
    assert "H1" in _failed(GOOD_BODY, reason_ids=["criterion:stakeholders"] * 2)
    cv = "I led a team of twelve analysts across three states for the federal health department"
    copied = f"{GOOD_BODY} You led a team of twelve analysts across three states for us."
    assert "H5" in _failed(copied, cv_text=cv)
    assert "H8" in _failed("Thank you for applying. We will not progress your application.")
    assert "H8" in _failed(" ".join([GOOD_BODY] * 4))


def test_keeping_the_cv_and_future_roles_are_allowed() -> None:
    body = GOOD_BODY + " We will keep your CV on file and contact you about future roles."
    results = run_checks(body, reason_ids=None, allowed_ids=[], cv_text="")
    assert next(r for r in results if r.rule == "H7").passed


def test_recruiter_edit_skips_only_h1() -> None:
    results = run_checks(GOOD_BODY, reason_ids=None, allowed_ids=[], cv_text="")
    assert all(r.passed for r in results)
    assert results[0].detail == "not checked on a recruiter edit"


def test_template_passes_the_checks_and_preview_hides_the_name() -> None:
    opening, closing = template_parts("Business Analyst", "Northwind Talent (demo)")
    body = assemble_body(opening, [], closing)
    assert all(r.passed for r in run_checks(body, reason_ids=[], allowed_ids=[], cv_text=""))
    preview = full_text(body, first_name=None, company="Northwind", reply_to="c@n.example")
    assert preview.startswith(f"Hi {NAME_PLACEHOLDER},")
    assert "reply to this email or contact c@n.example" in preview
    assert "delete your application and data" in preview
    sent = full_text(body, first_name="Zephyrine", company="Northwind", reply_to="c@n.example")
    assert sent.startswith("Hi Zephyrine,") and sent.endswith("Northwind Recruitment")
    assert full_text(body, first_name="", company="N", reply_to="r").startswith("Hi,")


def test_answer_sources_never_carry_the_salary_figures() -> None:
    answers = [
        {
            "key": "expected_salary",
            "outcome": "flag",
            "note": "$140,000 is above the band maximum $120,000",
        }
    ]
    (src,) = reason_sources([], [], answers, {}, location="Sydney", arrangement="hybrid")
    assert "$" not in str(src.for_model()) and src.status == "not_met"


def test_reason_sources_order_answers_then_not_met_then_partly() -> None:
    criteria = RUBRIC["criteria"]
    judgements = [
        {"criterion_id": "ba_experience", "verdict": "partly_met", "reason": "close"},
        {"criterion_id": "sql", "verdict": "met", "reason": "yes"},
        {"criterion_id": "stakeholders", "verdict": "not_met", "reason": "no"},
        {"criterion_id": "insurance", "verdict": "not_met", "reason": "no"},
    ]
    answers = [
        {"key": "expected_salary", "outcome": "flag", "note": "above band"},
        {"key": "right_to_work", "outcome": "fail", "note": "answered no, required yes"},
        {"key": "notice_period", "outcome": "not_scored", "note": ""},
    ]
    ids = [
        s.id
        for s in reason_sources(
            criteria, judgements, answers, {}, location="Sydney", arrangement="hybrid"
        )
    ]
    assert ids[:2] == ["answer:right_to_work", "answer:expected_salary"]
    assert ids == ["answer:right_to_work", "answer:expected_salary", "criterion:stakeholders"]
    no_answers = [
        s.id
        for s in reason_sources(
            criteria, judgements, [], {}, location="Sydney", arrangement="hybrid"
        )
    ]
    # not met before partly met; must haves first, then weight; at most three
    assert no_answers == [
        "criterion:stakeholders",
        "criterion:insurance",
        "criterion:ba_experience",
    ]
    assert "criterion:sql" not in ids and len(ids) <= 5


# ---- providers --------------------------------------------------------------------------


def test_real_provider_only_when_switched_on_and_keyed() -> None:
    base: dict[str, Any] = {"_env_file": None}
    assert isinstance(make_sender(Settings(**base)), LogSender)
    off = Settings(**base, email_provider="resend", resend_api_key="re_test")  # type: ignore[arg-type]
    assert isinstance(make_sender(off), LogSender)  # EMAIL_SENDING_ENABLED is false
    no_key = Settings(**base, email_provider="resend", email_sending_enabled=True)
    assert isinstance(make_sender(no_key), LogSender)
    on = Settings(
        **base,
        email_provider="resend",
        email_sending_enabled=True,
        resend_api_key="re_test",  # type: ignore[arg-type]
    )
    assert isinstance(make_sender(on), ResendSender)
    assert isinstance(make_sender(Settings(**base, email_provider="mailpit")), MailpitSender)


async def test_resend_sends_the_idempotency_key() -> None:
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"id": "re_123"})

    from app.integrations.email import OutgoingEmail

    sender = ResendSender("re_test", transport=httpx.MockTransport(handle))
    msg = OutgoingEmail("a@b.example", "f@n.example", "r@n.example", "s", "t", "<k@n.example>")
    assert await sender.send(msg) == "re_123"
    assert await sender.send(msg) == "re_123"
    assert [r.headers["Idempotency-Key"] for r in seen] == ["k@n.example", "k@n.example"]


# ---- end to end through the API (fake model, log sender) --------------------------------


@pytest.fixture
async def env(sessions: SessionMaker, settings: Settings) -> AsyncIterator[Env]:
    async for e in make_env(sessions, settings, [PROFILE, WEAK, writer_json()]):
        yield e


async def _v(env: Env, cid: str) -> int:
    return int((await env.state(cid))["state_version"])


async def reject(env: Env, cid: str, reason: str = "Agrees with the recommendation") -> None:
    r = await env.c.post(
        f"/candidates/{cid}/reject",
        json={"reason": reason, "expected_version": await _v(env, cid)},
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    await env.p.drain_without_delivery()  # type: ignore[attr-defined]


async def send(env: Env, cid: str) -> httpx.Response:
    return await env.c.post(
        f"/candidates/{cid}/send-rejection",
        json={"expected_version": await _v(env, cid)},
        headers=AUTH,
    )


async def rejection(env: Env, cid: str) -> dict[str, Any]:
    r = await env.c.get(f"/candidates/{cid}/rejection", headers=AUTH)
    assert r.status_code == 200
    return r.json()  # type: ignore[no-any-return]


def sent(env: Env) -> list[Any]:
    sender = env.p.email
    assert isinstance(sender, LogSender)
    return sender.sent


async def scored(env: Env) -> str:
    cid = await env.apply(cv_docx())
    await env.p.drain()
    assert (await env.state(cid))["state"] == "SCORED"
    return cid


@pytest.fixture(autouse=True)
def _drain_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    """`drain_without_delivery`: run queued jobs but leave email delivery jobs queued, so
    tests can look between Send and delivery."""
    from app.workflow.dispatch import DeliveryJob, InlineDispatcher
    from app.workflow.pipeline import Pipeline

    async def drain_without_delivery(self: Pipeline) -> int:
        assert isinstance(self.dispatcher, InlineDispatcher)
        held = [j for j in self.dispatcher.queue if isinstance(j, DeliveryJob)]
        self.dispatcher.queue = [j for j in self.dispatcher.queue if not isinstance(j, DeliveryJob)]
        n = await self.drain()
        self.dispatcher.queue = held + [
            j for j in self.dispatcher.queue if isinstance(j, DeliveryJob)
        ]
        return n

    monkeypatch.setattr(Pipeline, "drain_without_delivery", drain_without_delivery, raising=False)


@pytest.mark.integration
async def test_reject_drafts_an_email_with_only_missed_requirements(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    assert (await env.state(cid))["state"] == "REJECTION_DRAFTED"
    d = (await rejection(env, cid))["draft"]
    assert d["source"] == "agent" and d["version"] == 1 and not d["needs_edit"]
    assert [r["source_id"] for r in d["reasons"]] == [i for i, _s in REASONS]
    assert all(c["passed"] for c in d["checks"]) and len(d["checks"]) == 8
    assert d["preview"].startswith(f"Hi {NAME_PLACEHOLDER},")
    page = json.dumps(await rejection(env, cid))
    for personal in [NAME, "Zephyrine", EMAIL, PHONE]:
        assert personal not in page  # blind review holds on the draft too
    # What the writer was sent: no name, contact details, CV text, score or band.
    call = env.provider.calls[-1]
    sent_text = json.dumps(call["messages"])  # the system prompt is fixed text
    for never in [
        NAME,
        "Zephyrine",
        EMAIL,
        PHONE,
        "Molonglo",
        "SQL, Tableau",
        "43.3",
        '"band"',
        '"reject"',
    ]:
        assert never not in sent_text, never
    assert "<untrusted_data" in sent_text and "Stakeholder management" in sent_text
    assert any(e["transition_id"] == "T7" for e in (await env.state(cid))["audit"])


@pytest.mark.integration
async def test_drafts_failing_the_checks_fall_back_to_the_template(
    sessions: SessionMaker, settings: Settings
) -> None:
    bad = writer_json(closing="Congratulations, you are hired.")
    async for env in make_env(sessions, settings, [PROFILE, WEAK, bad, bad, bad]):
        cid = await scored(env)
        await reject(env, cid)
        d = (await rejection(env, cid))["draft"]
        assert d["source"] == "template" and d["needs_edit"] and d["reasons"] == []
        assert "failed the checks" in d["fallback_reason"]
        assert all(c["passed"] for c in d["checks"])
        assert len(env.provider.calls) == 3 + 3  # rubric, parse, score; three writer attempts


@pytest.mark.integration
async def test_override_of_an_advance_gets_the_template_without_a_model_call(
    sessions: SessionMaker, settings: Settings
) -> None:
    async for env in make_env(sessions, settings, [PROFILE, STRONG]):
        cid = await scored(env)
        await reject(env, cid, "Not the right domain background for this team")
        d = (await rejection(env, cid))["draft"]
        assert d["source"] == "template" and "overrode" in d["fallback_reason"]
        assert len(env.provider.calls) == 3  # rubric, parse and score only


@pytest.mark.integration
async def test_edit_runs_the_checks_and_adds_a_version(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    bad = await env.c.put(
        f"/candidates/{cid}/rejection",
        json={
            "body": GOOD_BODY + " Hours may be hard with your young children.",
            "expected_draft_version": 1,
        },
        headers=AUTH,
    )
    assert bad.status_code == 422 and bad.json()["error"] == "draft_refused"
    assert any(c["rule"] == "H2" and not c["passed"] for c in bad.json()["checks"])
    assert (await rejection(env, cid))["versions"] == 1  # not saved
    edited = GOOD_BODY.replace("every success", "the very best")
    ok = await env.c.put(
        f"/candidates/{cid}/rejection",
        json={"body": edited, "expected_draft_version": 1},
        headers=AUTH,
    )
    assert ok.status_code == 200 and ok.json()["draft"]["source"] == "recruiter"
    stale = await env.c.put(
        f"/candidates/{cid}/rejection",
        json={"body": edited, "expected_draft_version": 1},
        headers=AUTH,
    )
    assert stale.status_code == 409
    got = await rejection(env, cid)
    assert got["versions"] == 2 and got["draft"]["body"] == edited
    assert any(e["transition_id"] == "EDIT" for e in (await env.state(cid))["audit"])


@pytest.mark.integration
async def test_send_queues_one_email_and_delivers_it_once(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    r = await send(env, cid)
    assert r.status_code == 200 and r.json()["state"] == "REJECTION_SENT"
    assert (await rejection(env, cid))["outbox"]["status"] == "queued"
    assert sent(env) == []  # Send only queues; delivery is the worker's job
    await env.p.drain()
    [msg] = sent(env)
    assert msg.to == EMAIL and msg.text.startswith("Hi Zephyrine,")
    assert "business analysis is the core of this job" in msg.text
    assert msg.subject.startswith("Your application for")
    out = (await rejection(env, cid))["outbox"]
    assert out["status"] == "sent" and out["attempts"] == 1 and out["sent_at"]
    audit = (await env.state(cid))["audit"]
    ids = [e["transition_id"] for e in audit]
    assert "T8" in ids and "EMAIL" in ids  # order is by wall clock (known gap: WSL clock steps)
    # Delivering the same outbox row again sends nothing.
    oid = uuid_of(out["id"])
    assert await env.p.deliver_email(oid) == "sent"
    assert len(sent(env)) == 1


def uuid_of(s: str) -> Any:
    import uuid

    return uuid.UUID(s)


@pytest.mark.integration
async def test_twenty_concurrent_sends_make_one_email(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    v = await _v(env, cid)
    results = await asyncio.gather(
        *[
            env.c.post(
                f"/candidates/{cid}/send-rejection", json={"expected_version": v}, headers=AUTH
            )
            for _ in range(20)
        ]
    )
    codes = sorted(r.status_code for r in results)
    assert codes.count(200) == 1 and set(codes) == {200, 409}
    await env.p.drain()
    async with env.p.sessions() as s:
        n = (await s.execute(select(func.count()).select_from(OutboundEmail))).scalar_one()
    assert n == 1 and len(sent(env)) == 1


@pytest.mark.integration
async def test_crash_after_provider_accepted_does_not_send_twice(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    oid = uuid_of((await send(env, cid)).json()["outbox_id"])
    await env.p.drain()
    assert len(sent(env)) == 1
    # Simulate the worker dying after the provider accepted, before the row was marked.
    async with env.p.sessions() as s, s.begin():
        row = await s.get(OutboundEmail, oid)
        assert row is not None
        row.status, row.sent_at = "sending", None
    assert await env.p.deliver_email(oid, 1) == "sent"
    assert len(sent(env)) == 1  # found as already delivered, not sent again


@pytest.mark.integration
async def test_failed_delivery_retries_then_lists_as_not_delivered(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    sender = env.p.email
    assert isinstance(sender, LogSender)
    sender.fail_times = 99
    await send(env, cid)
    await env.p.drain()
    out = (await rejection(env, cid))["outbox"]
    assert out["status"] == "failed" and out["attempts"] == 5
    q = (await env.c.get("/rejections/queue", headers=AUTH)).json()
    assert [u["id"] for u in q["undelivered"]] == [cid]
    assert (await env.state(cid))["state"] == "REJECTION_SENT"  # state never changes
    sender.fail_times = 0
    r = await env.c.post(f"/candidates/{cid}/rejection/retry-delivery", headers=AUTH)
    assert r.status_code == 202
    await env.p.drain()
    assert (await rejection(env, cid))["outbox"]["status"] == "sent" and len(sent(env)) == 1


@pytest.mark.integration
async def test_erasure_before_send_refuses_and_after_send_cancels(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    await send(env, cid)  # queued, not delivered yet
    r = await env.c.post(
        f"/candidates/{cid}/erase", json={"reason": "candidate asked"}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    await env.p.drain()
    assert sent(env) == []
    got = await rejection(env, cid)
    assert got["outbox"]["status"] == "cancelled"
    assert got["draft"]["body"] == "" and got["draft"]["erased"]
    async with env.p.sessions() as s:
        bodies = (await s.execute(select(RejectionDraft.body))).scalars().all()
    assert set(bodies) == {""}


@pytest.mark.integration
async def test_erased_before_send_is_refused(env: Env) -> None:
    cid = await scored(env)
    await reject(env, cid)
    await env.c.post(f"/candidates/{cid}/erase", json={"reason": "candidate asked"}, headers=AUTH)
    # erasure moves a non terminal candidate to WITHDRAWN, so Send is refused outright
    assert (await send(env, cid)).status_code in (409, 410)
    assert sent(env) == []


@pytest.mark.integration
async def test_queue_lists_drafts_needing_a_look_first(
    sessions: SessionMaker, settings: Settings
) -> None:
    async for env in make_env(sessions, settings, [PROFILE, STRONG]):
        cid = await scored(env)
        await reject(env, cid, "Not the right domain background for this team")
        q = (await env.c.get("/rejections/queue", headers=AUTH)).json()
        assert q["drafts"][0]["id"] == cid and q["drafts"][0]["needs_edit"]


def _mailpit_up() -> bool:
    try:
        return httpx.get("http://localhost:8025/api/v1/info", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.skipif(not _mailpit_up(), reason="Mailpit not running (make up)")
async def test_mailpit_delivers_and_finds_the_exact_message_id() -> None:
    import uuid

    from app.integrations.email import OutgoingEmail

    m = MailpitSender("localhost", 1025, "http://localhost:8025")
    mid = f"<rejection.{uuid.uuid4()}@northwind.example>"
    other = f"<rejection.{uuid.uuid4()}@northwind.example>"
    assert not await m.already_delivered(mid)
    await m.send(
        OutgoingEmail(
            "probe@example.test",
            "N <c@northwind.example>",
            "c@northwind.example",
            "probe",
            "body",
            mid,
        )
    )
    await asyncio.sleep(0.5)
    assert await m.already_delivered(mid)
    assert not await m.already_delivered(other)  # the search is loose; the check is exact
    async with httpx.AsyncClient() as c:  # tidy: remove the probe message
        found = (
            await c.get(
                "http://localhost:8025/api/v1/search",
                params={"query": f"message-id:{mid.strip('<>')}"},
            )
        ).json()
        ids = [x["ID"] for x in found["messages"] if x["MessageID"].strip("<>") == mid.strip("<>")]
        await c.request("DELETE", "http://localhost:8025/api/v1/messages", json={"IDs": ids})
