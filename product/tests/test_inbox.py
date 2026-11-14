"""Phase 5B: connected inbox. Rules, ingestion (once per message), job matching, the
recruiter's job pick, duplicates, provider failures, the Gmail sign in checks and token
encryption (phase 5B design sections 4 to 9)."""

from __future__ import annotations

import asyncio
import base64
import json
import smtplib
import uuid
from collections.abc import AsyncIterator
from email.message import EmailMessage
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import func, select, text

from app.agents.job_matcher import Fit, MatcherOutput, choose
from app.config import Settings
from app.db.models import (
    Candidate,
    InboxAttachment,
    InboxMessage,
    JobMatch,
    Mailbox,
    OAuthState,
    OutboundEmail,
)
from app.db.session import SessionMaker
from app.inbox import oauth
from app.inbox.crypto import decrypt_token, encrypt_token
from app.inbox.providers import (
    GMAIL_SCOPE,
    Attachment,
    FakeMailbox,
    MailpitMailbox,
    RawEmail,
)
from app.inbox.rules import OpenJob, guess_contact, match_rules, redact_subject, sender_kind
from app.integrations.email import LogSender
from tests.phase1_helpers import score_json
from tests.test_parse_step import AUTH, EMAIL, NAME, PHONE, PROFILE, Env, cv_docx, make_env

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SCORE = score_json()
KEY = base64.urlsafe_b64encode(b"test-only-key-32-bytes-long-abcd").decode()  # tests only


def matcher_json(job_id: str, fit: float) -> str:
    return json.dumps(
        {"fits": [{"job_id": job_id, "fit": fit, "reason": "analyst work"}], "none_fit": fit < 0.5}
    )


def email(
    mid: str,
    subject: str,
    *,
    sender: tuple[str, str] = (NAME, EMAIL),
    to: list[str] | None = None,
    files: list[Attachment] | None = None,
) -> RawEmail:
    return RawEmail(
        id=mid,
        subject=subject,
        sender_name=sender[0],
        sender_address=sender[1],
        to=to or ["careers@northwind.example"],
        received_at=None,
        attachments=[Attachment("cv.docx", DOCX, cv_docx())] if files is None else files,
    )


# ---- rules (no database) ------------------------------------------------------------------

J1, J2, J3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
JOBS = [
    OpenJob(J1, "Data Analyst", "DA-0042", True),
    OpenJob(J2, "Registered Nurse, Surgical Ward", "RN-0017", True),
    OpenJob(J3, "Site Supervisor (Construction)", "SS-0008", False),
]


@pytest.mark.parametrize(
    ("subject", "to", "kind", "want", "route"),
    [
        ("Application DA-0042", [], "direct", J1, "job_code"),
        ("Fwd: re: application da-0042 attached", [], "direct", J1, "job_code"),
        ("CV attached", ["careers+rn-0017@northwind.example"], "direct", J2, "plus_address"),
        ("Application for Data Analyst from Jane Doe", [], "seek", J1, "seek_subject"),
        ("New application: Registered Nurse, Surgical Ward", [], "indeed", J2, "indeed_subject"),
        ("Application SS-0008", [], "direct", None, None),  # closed job
        ("Application for Site Supervisor (Construction)", [], "seek", None, None),  # closed
        ("Hello, keen on analyst roles", [], "direct", None, None),
        ("Application ZZ-9999", [], "direct", None, None),  # unknown code
    ],
)
def test_match_rules(subject: str, to: list[str], kind: str, want: Any, route: Any) -> None:
    m = match_rules(subject, to, kind, JOBS)
    assert (m.job_id, m.route) == (want, route), m.detail


def test_same_title_twice_is_not_a_rule_match() -> None:
    twin = [*JOBS, OpenJob(uuid.uuid4(), "Data Analyst", "DA-0050", True)]
    m = match_rules("Application for Data Analyst", [], "seek", twin)
    assert m.job_id is None and "more than one" in m.detail


def test_sender_kind_subject_redaction_and_contact() -> None:
    assert sender_kind("noreply@seek.com.au") == "seek"
    assert sender_kind("apply@indeedemail.com") == "indeed"
    assert sender_kind(EMAIL) == "direct"
    red = redact_subject(f"Application for Data Analyst from {NAME} ({EMAIL}, {PHONE})", [NAME])
    for gone in [NAME, "Zephyrine", EMAIL, PHONE]:
        assert gone not in red
    assert red.startswith("Application for Data Analyst")
    assert redact_subject("Application for Data Analyst from Jane Doe", []).endswith("[name]")
    # direct: the sender; Seek: the subject's name and the CV's address, never Seek's own
    assert guess_contact(
        kind="direct", sender_name=NAME, sender_address=EMAIL, subject="x", cv_text=""
    ) == (NAME, EMAIL)
    n, e = guess_contact(
        kind="seek",
        sender_name="SEEK",
        sender_address="noreply@seek.com.au",
        subject="Application for Data Analyst from Jane Doe",
        cv_text="noreply@seek.com.au\njane@example.test",
    )
    assert (n, e) == ("Jane Doe", "jane@example.test")


def test_choose_needs_a_clear_winner() -> None:
    def out(*fits: float) -> MatcherOutput:
        return MatcherOutput(
            fits=[
                Fit(job_id=str(j), fit=f, reason="r") for j, f in zip([J1, J2], fits, strict=False)
            ],
            none_fit=False,
        )

    assert choose(out(0.92, 0.3), threshold=0.8, gap=0.3).job_id == J1
    assert choose(out(0.92, 0.75), threshold=0.8, gap=0.3).job_id is None  # too close
    assert choose(out(0.7, 0.1), threshold=0.8, gap=0.3).job_id is None  # not sure enough
    assert (
        choose(
            MatcherOutput(fits=[Fit(job_id=str(J1), fit=0.95, reason="r")], none_fit=True),
            threshold=0.8,
            gap=0.3,
        ).job_id
        is None
    )


def test_tokens_are_encrypted_and_tamper_evident(settings: Settings) -> None:
    s = settings.model_copy(update={"inbox_token_key": SecretStr(KEY)})
    ct = encrypt_token(s, "1//refresh-token-value")
    assert b"refresh-token-value" not in ct
    assert decrypt_token(s, ct) == "1//refresh-token-value"
    with pytest.raises(Exception, match="cannot be read"):
        decrypt_token(s, ct[:-4] + b"AAAA")


# ---- ingestion (database) -----------------------------------------------------------------


@pytest.fixture
async def inbox(
    sessions: SessionMaker, settings: Settings
) -> AsyncIterator[tuple[Env, FakeMailbox, uuid.UUID]]:
    async for env in make_env(sessions, settings, [PROFILE, SCORE]):
        fake = FakeMailbox()
        env.p.mailboxes = lambda _mb, f=fake: f
        async with sessions() as s, s.begin():
            mb = Mailbox(
                provider="fake",
                address="careers@northwind.example",
                label="Applications",
                status="active",
                scopes=["read"],
                connected_by="test",
            )
            s.add(mb)
            await s.flush()
            mid = mb.id
        yield env, fake, mid


async def code_of(env: Env) -> str:
    async with env.p.sessions() as s:
        from app.db.models import Job

        job = await s.get(Job, uuid.UUID(env.job_id))
        assert job is not None and job.code
        return job.code


async def inbox_candidates(env: Env) -> list[Candidate]:
    async with env.p.sessions() as s:
        return list(
            (await s.execute(select(Candidate).where(Candidate.source == "inbox"))).scalars()
        )


@pytest.mark.integration
async def test_an_emailed_cv_with_a_job_code_is_ingested_scored_and_acknowledged(
    inbox: Any,
) -> None:
    env, fake, mid = inbox
    code = await code_of(env)
    fake.add("Applications", email("m1", f"Application {code} from {NAME}"))
    fake.add("Personal", email("m2", "Dinner on Friday?"))  # another label: never listed
    assert await env.p.poll_inbox(mid) == "polled"
    await env.p.drain()
    [cand] = await inbox_candidates(env)
    assert str(cand.job_id) == env.job_id and cand.state == "SCORED"
    assert cand.email == EMAIL and cand.consent_basis == "inbox_notice"
    async with env.p.sessions() as s:
        msgs = list((await s.execute(select(InboxMessage))).scalars())
        ack = (
            await s.execute(select(OutboundEmail).where(OutboundEmail.kind == "acknowledgement"))
        ).scalar_one()
    assert [(m.status, m.match_route) for m in msgs] == [("ingested", "job_code")]
    assert NAME not in msgs[0].subject_redacted and "Zephyrine" not in msgs[0].subject_redacted
    assert ack.status == "sent" and fake.fetches == 1
    sender = env.p.email
    assert isinstance(sender, LogSender)
    text_sent = sender.sent[0].text
    assert text_sent.startswith("Hi Zephyrine,") and "delete your application and data" in text_sent
    audit = (await env.state(str(cand.id)))["audit"]
    assert audit[0]["transition_id"] == "T24" and audit[0]["actor_type"] == "system"


@pytest.mark.integration
async def test_a_message_is_processed_once(inbox: Any) -> None:
    env, fake, mid = inbox
    fake.add("Applications", email("m1", f"Application {await code_of(env)}"))
    await env.p.poll_inbox(mid)
    await env.p.poll_inbox(mid)  # listed again: the unique key keeps one row
    async with env.p.sessions() as s:
        [msg_id] = list((await s.execute(select(InboxMessage.id))).scalars())
    # the same message processed twice at once, and again afterwards
    await asyncio.gather(env.p.process_inbox_message(msg_id), env.p.process_inbox_message(msg_id))
    await env.p.process_inbox_message(msg_id)
    assert len(await inbox_candidates(env)) == 1
    assert fake.fetches == 1


@pytest.mark.integration
async def test_no_cv_is_skipped_and_nothing_is_stored(inbox: Any) -> None:
    env, fake, mid = inbox
    fake.add(
        "Applications",
        email("m1", "Our newsletter", files=[Attachment("photo.jpg", "image/jpeg", b"\xff\xd8xx")]),
    )
    fake.add(
        "Applications",
        email("m2", "Invoice", files=[Attachment("invoice.pdf", "application/pdf", b"not a pdf")]),
    )
    await env.p.poll_inbox(mid)
    await env.p.drain()
    async with env.p.sessions() as s:
        statuses = sorted(m.status for m in (await s.execute(select(InboxMessage))).scalars())
    assert statuses == ["not_a_cv", "not_a_cv"]
    assert await inbox_candidates(env) == [] and env.storage.objects == {}


@pytest.mark.integration
async def test_no_job_in_the_email_the_matcher_picks_when_sure(
    sessions: SessionMaker, settings: Settings
) -> None:
    async for env in make_env(sessions, settings, [PROFILE]):
        env.provider._script.extend([matcher_json(env.job_id, 0.94), SCORE])
        fake = FakeMailbox()
        env.p.mailboxes = lambda _mb, f=fake: f
        async with sessions() as s, s.begin():
            mb = Mailbox(
                provider="fake",
                address="a@b.example",
                label="Applications",
                status="active",
                scopes=[],
                connected_by="t",
            )
            s.add(mb)
            await s.flush()
            mid = mb.id
        fake.add("Applications", email("m1", "CV attached, keen on analyst roles"))
        await env.p.poll_inbox(mid)
        await env.p.drain()
        [cand] = await inbox_candidates(env)
        assert cand.state == "SCORED" and str(cand.job_id) == env.job_id
        async with sessions() as s:
            m = (await s.execute(select(JobMatch))).scalar_one()
        assert m.outcome == "auto_matched" and m.prompt_version == "v2"
        sent = json.dumps(env.provider.calls[2]["messages"])  # rubric, parse, then the matcher
        for needle in [NAME, "Zephyrine", EMAIL, PHONE, "570 156", "keen on analyst roles"]:
            assert needle not in sent, needle


@pytest.mark.integration
async def test_unsure_goes_to_needs_a_job_and_the_recruiter_picks(
    sessions: SessionMaker, settings: Settings
) -> None:
    async for env in make_env(sessions, settings, [PROFILE]):
        env.provider._script.extend([matcher_json(env.job_id, 0.6), SCORE])
        fake = FakeMailbox()
        env.p.mailboxes = lambda _mb, f=fake: f
        async with sessions() as s, s.begin():
            mb = Mailbox(
                provider="fake",
                address="a@b.example",
                label="Applications",
                status="active",
                scopes=[],
                connected_by="t",
            )
            s.add(mb)
            await s.flush()
            mid = mb.id
        fake.add("Applications", email("m1", "CV attached"))
        await env.p.poll_inbox(mid)
        await env.p.drain()
        [cand] = await inbox_candidates(env)
        assert cand.state == "NEEDS_REVIEW" and cand.job_id is None
        cid = str(cand.id)
        state = await env.state(cid)
        assert "needs a job" in state["audit"][-1]["reason"]
        stale = await env.c.post(
            f"/candidates/{cid}/pick-job",
            json={"job_id": env.job_id, "expected_version": 1},
            headers=AUTH,
        )
        assert stale.status_code == 409
        r = await env.c.post(
            f"/candidates/{cid}/pick-job",
            json={"job_id": env.job_id, "expected_version": state["state_version"]},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
        await env.p.drain()
        assert (await env.state(cid))["state"] == "SCORED"
        again = await env.c.post(
            f"/candidates/{cid}/pick-job",
            json={"job_id": env.job_id, "expected_version": 99},
            headers=AUTH,
        )
        assert again.status_code == 409
        page = (await env.c.get("/inbox", headers=AUTH)).json()
        assert page["messages"][0]["attachments"][0]["match"]


@pytest.mark.integration
async def test_same_person_same_job_is_a_duplicate(inbox: Any) -> None:
    env, fake, mid = inbox
    code = await code_of(env)
    fake.add("Applications", email("m1", f"Application {code}"))
    await env.p.poll_inbox(mid)
    await env.p.drain()
    fake.add("Applications", email("m2", f"Re: Application {code}"))
    await env.p.poll_inbox(mid)
    await env.p.drain()
    assert len(await inbox_candidates(env)) == 1
    async with env.p.sessions() as s:
        outcomes = sorted(a.outcome for a in (await s.execute(select(InboxAttachment))).scalars())
    assert outcomes == ["duplicate", "ingested"]


@pytest.mark.integration
async def test_revoked_access_needs_reconnect_and_errors_are_counted(inbox: Any) -> None:
    env, fake, mid = inbox
    fake.fail_next = 2
    assert await env.p.poll_inbox(mid) == "error"
    assert await env.p.poll_inbox(mid) == "error"
    async with env.p.sessions() as s:
        mb = await s.get(Mailbox, mid)
        assert mb is not None and mb.failures == 2 and mb.last_error
    fake.fail_auth = True
    assert await env.p.poll_inbox(mid) == "auth_error"
    async with env.p.sessions() as s:
        mb = await s.get(Mailbox, mid)
        assert mb is not None and mb.status == "needs_reconnect"
    assert await env.p.poll_inbox(mid) == "skipped"  # nothing read until reconnected


@pytest.mark.integration
async def test_two_pollers_at_once_one_runs(inbox: Any) -> None:
    env, fake, mid = inbox
    fake.add("Applications", email("m1", f"Application {await code_of(env)}"))
    results = await asyncio.gather(*(env.p.poll_inbox(mid) for _ in range(5)))
    assert results.count("polled") == 1 and results.count("skipped") == 4


@pytest.mark.integration
async def test_label_rules_and_disconnect_deletes_the_token(
    inbox: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    env, _fake, mid = inbox
    r = await env.c.put(f"/inbox/mailboxes/{mid}", json={"label": "INBOX"}, headers=AUTH)
    assert r.status_code == 422  # never the whole mailbox
    revoked: list[str] = []

    async def fake_revoke(token: str, transport: Any = None) -> bool:
        revoked.append(token)
        return True

    monkeypatch.setattr("app.api.inbox_api.revoke", fake_revoke)
    s2 = env.p.settings.model_copy(update={"inbox_token_key": SecretStr(KEY)})
    async with env.p.sessions() as s, s.begin():
        mb = await s.get(Mailbox, mid)
        assert mb is not None
        mb.provider, mb.token_ciphertext = "gmail", encrypt_token(s2, "1//refresh")
    monkeypatch.setattr(env.p.settings, "inbox_token_key", s2.inbox_token_key)
    r = await env.c.post(f"/inbox/mailboxes/{mid}/disconnect", headers=AUTH)
    assert r.status_code == 200 and r.json()["revoked"] is True and revoked == ["1//refresh"]
    async with env.p.sessions() as s:
        raw = (
            await s.execute(
                text("SELECT token_ciphertext, status FROM mailboxes WHERE id = :i"), {"i": mid}
            )
        ).one()
    assert raw.token_ciphertext is None and raw.status == "disconnected"


# ---- Gmail sign in (recorded responses) ---------------------------------------------------


def google(
    scope: str = GMAIL_SCOPE, refresh: str | None = "1//refresh", seen: list[str] | None = None
) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(f"{req.method} {req.url.path}")
        if req.url.path == "/token":
            body = {"access_token": "ya29.access", "scope": scope, "expires_in": 3600}
            if refresh:
                body["refresh_token"] = refresh
            return httpx.Response(200, json=body)
        if req.url.path.endswith("/profile"):
            return httpx.Response(200, json={"emailAddress": "careers@northwind.example"})
        if req.url.path == "/revoke":
            return httpx.Response(200)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.integration
async def test_gmail_sign_in_checks(sessions: SessionMaker, settings: Settings) -> None:
    s = settings.model_copy(
        update={
            "google_client_id": "cid",
            "google_client_secret": SecretStr("secret"),
            "inbox_token_key": SecretStr(KEY),
        }
    )
    url = await oauth.start_gmail(sessions, s, "recruiter-a")
    assert "scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.readonly" in url
    assert "code_challenge_method=S256" in url and "access_type=offline" in url
    state = url.split("state=")[1].split("&")[0]

    with pytest.raises(oauth.ConnectRefused, match="not one we started"):
        await oauth.finish_gmail(
            sessions, s, actor_id="recruiter-a", code="c", state="x" * 20, transport=google()
        )
    with pytest.raises(oauth.ConnectRefused, match="someone else"):
        await oauth.finish_gmail(
            sessions, s, actor_id="recruiter-b", code="c", state=state, transport=google()
        )

    state2 = (await oauth.start_gmail(sessions, s, "recruiter-a")).split("state=")[1].split("&")[0]
    seen: list[str] = []
    with pytest.raises(oauth.ConnectRefused, match="only read only"):
        await oauth.finish_gmail(
            sessions,
            s,
            actor_id="recruiter-a",
            code="c",
            state=state2,
            transport=google(
                scope=f"{GMAIL_SCOPE} https://www.googleapis.com/auth/gmail.send", seen=seen
            ),
        )
    assert "POST /revoke" in seen  # a wider grant is revoked at once

    state3 = (await oauth.start_gmail(sessions, s, "recruiter-a")).split("state=")[1].split("&")[0]
    mb = await oauth.finish_gmail(
        sessions, s, actor_id="recruiter-a", code="c", state=state3, transport=google()
    )
    assert mb.status == "needs_label" and mb.scopes == [GMAIL_SCOPE]
    with pytest.raises(oauth.ConnectRefused, match="already used"):
        await oauth.finish_gmail(
            sessions, s, actor_id="recruiter-a", code="c", state=state3, transport=google()
        )
    async with sessions() as db:
        raw = (
            await db.execute(
                text("SELECT token_ciphertext FROM mailboxes WHERE id = :i"), {"i": mb.id}
            )
        ).scalar_one()
        used = (
            await db.execute(
                select(func.count()).select_from(OAuthState).where(OAuthState.used_at.is_not(None))
            )
        ).scalar_one()
    assert b"1//refresh" not in raw and decrypt_token(s, raw) == "1//refresh"
    assert used == 2  # the foreign attempt was refused before the state was spent


async def test_gmail_not_configured_is_refused(sessions: SessionMaker, settings: Settings) -> None:
    with pytest.raises(oauth.ConnectRefused, match="not set up"):
        await oauth.start_gmail(sessions, settings.model_copy(update={"google_client_id": ""}), "r")


# ---- Mailpit, the real container ------------------------------------------------------------


def _mailpit_up(url: str) -> bool:
    try:
        return httpx.get(f"{url}/api/v1/info", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.integration
async def test_mailpit_provider_lists_by_tag_and_downloads_cvs(settings: Settings) -> None:
    if not _mailpit_up(settings.mailpit_api_url):
        pytest.skip("Mailpit is not running (make up)")
    tag = f"Applications-{uuid.uuid4().hex[:8]}"
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = (
        f"{NAME} <{EMAIL}>",
        "careers+da-0042@northwind.example",
        "CV for the analyst job",
    )
    msg["X-Tags"] = tag
    msg.set_content("Please find my CV attached.")
    msg.add_attachment(
        cv_docx(),
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="cv.docx",
    )
    msg.add_attachment(b"\xff\xd8xx", maintype="image", subtype="jpeg", filename="photo.jpg")
    with smtplib.SMTP(settings.mailpit_smtp_host, settings.mailpit_smtp_port, timeout=5) as smtp:
        smtp.send_message(msg)
    box = MailpitMailbox(settings.mailpit_api_url)
    ids: list[str] = []
    for _ in range(20):
        ids, _cp = await box.list_new(tag, None, 10)
        if ids:
            break
        await asyncio.sleep(0.2)
    assert len(ids) == 1
    raw = await box.fetch(ids[0], settings.cv_max_bytes)
    assert raw.sender_address == EMAIL and "careers+da-0042@northwind.example" in raw.to
    assert [a.name for a in raw.attachments] == ["cv.docx"] and raw.attachments[0].data.startswith(
        b"PK"
    )
    assert any("photo.jpg" in s for s in raw.skipped)
