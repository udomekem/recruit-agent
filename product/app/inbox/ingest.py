"""Poll a mailbox and ingest its CVs (phase 5B design sections 1, 7 and 8).

Poll: one poller per mailbox at a time (a lease on the row); new messages are recorded
under a unique (mailbox, provider message id) key before anything else, so a message is
processed once however often it is listed. Messages still `received` after a crash are
queued again by the next poll.

Process one message: fetch it, keep only PDF and Word attachments, redact the subject,
find the job with the code rules, then for each CV either link it to an existing
application (same email, same job, within the duplicate window) or store it and create
the candidate (T24) with the acknowledgement email in the same transaction. The email
body is never read or stored.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db.models import (
    AuditEvent,
    Candidate,
    InboxAttachment,
    InboxMessage,
    Job,
    Mailbox,
    MailboxEvent,
    OutboundEmail,
)
from app.db.session import SessionMaker
from app.domain.jobs import JobState
from app.domain.notice import NOTICE_VERSION
from app.domain.states import ActorType, CandidateState
from app.inbox.crypto import decrypt_token
from app.inbox.providers import (
    GmailMailbox,
    MailboxProvider,
    MailpitMailbox,
    ProviderAuthError,
    ProviderError,
)
from app.inbox.rules import OpenJob, guess_contact, match_rules, redact_subject, sender_kind
from app.intake.extract import extract
from app.intake.files import CVRejected, check_cv
from app.integrations.storage import Storage, delete_with_retry, new_cv_key
from app.workflow.machine import Snapshot, add_created_audit

log = logging.getLogger(__name__)

LEASE_SECONDS = 120
STUCK_AFTER = timedelta(minutes=5)
MAX_MESSAGE_ATTEMPTS = 3


def normalise_email(email: str) -> str:
    return email.strip().lower()  # as the intake adapter (not imported: it imports the pipeline)


ProviderFactory = Callable[[Mailbox], MailboxProvider]
Enqueue = Callable[[uuid.UUID], Awaitable[None]]


def make_provider(settings: Settings) -> ProviderFactory:
    def factory(mb: Mailbox) -> MailboxProvider:
        if mb.provider == "mailpit":
            return MailpitMailbox(settings.mailpit_api_url)
        if mb.provider == "gmail":
            if mb.token_ciphertext is None or settings.google_client_secret is None:
                raise ProviderAuthError("no stored access; reconnect the inbox")
            return GmailMailbox(
                decrypt_token(settings, mb.token_ciphertext),
                settings.google_client_id,
                settings.google_client_secret.get_secret_value(),
            )
        raise ProviderError(f"no provider {mb.provider!r} configured")

    return factory


async def mailbox_event(
    sessions: SessionMaker, mailbox_id: uuid.UUID, kind: str, actor_id: str, detail: str = ""
) -> None:
    async with sessions() as s, s.begin():
        s.add(
            MailboxEvent(mailbox_id=mailbox_id, kind=kind, actor_id=actor_id, detail=detail[:2000])
        )


# ---- poll ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PollResult:
    status: str  # polled | skipped | auth_error | error | limit
    new: int = 0
    requeued: int = 0


async def poll(
    sessions: SessionMaker,
    providers: ProviderFactory,
    enqueue: Enqueue,
    mailbox_id: uuid.UUID,
    *,
    settings: Settings,
) -> PollResult:
    now = datetime.now(UTC)
    async with sessions() as s, s.begin():
        got = (
            await s.execute(
                update(Mailbox)
                .where(
                    Mailbox.id == mailbox_id,
                    Mailbox.status == "active",
                    Mailbox.label.is_not(None),
                    (Mailbox.lease_until.is_(None)) | (Mailbox.lease_until < now),
                )
                .values(lease_until=now + timedelta(seconds=LEASE_SECONDS))
                .returning(Mailbox.id)
            )
        ).scalar_one_or_none()
    if got is None:
        return PollResult("skipped")  # paused, no label, or another poller holds it

    async with sessions() as s:
        mb = await s.get(Mailbox, mailbox_id)
        assert mb is not None
        label, checkpoint, provider_name = mb.label or "", mb.checkpoint, mb.provider
        today = (
            await s.execute(
                select(func.count())
                .select_from(InboxMessage)
                .where(
                    InboxMessage.mailbox_id == mailbox_id,
                    InboxMessage.created_at >= now - timedelta(days=1),
                )
            )
        ).scalar_one()
        stuck = list(
            (
                await s.execute(
                    select(InboxMessage.id).where(
                        InboxMessage.mailbox_id == mailbox_id,
                        InboxMessage.status.in_(["received", "working"]),
                        InboxMessage.attempts < MAX_MESSAGE_ATTEMPTS,
                        InboxMessage.created_at < now - STUCK_AFTER,
                    )
                )
            ).scalars()
        )

    async def release(**values: object) -> None:
        async with sessions() as s, s.begin():
            await s.execute(
                update(Mailbox).where(Mailbox.id == mailbox_id).values(lease_until=None, **values)
            )

    try:
        provider = providers(mb)
        limit = min(settings.inbox_max_per_poll, max(0, settings.inbox_max_per_day - int(today)))
        if limit == 0:
            await release(
                last_polled_at=now, last_error="daily limit reached; paused until tomorrow"
            )
            return PollResult("limit")
        ids, new_checkpoint = await provider.list_new(label, checkpoint, limit)
    except ProviderAuthError as exc:
        await release(status="needs_reconnect", last_error=str(exc)[:500])
        await mailbox_event(sessions, mailbox_id, "auth_error", "system", str(exc))
        return PollResult("auth_error")
    except ProviderError as exc:
        async with sessions() as s, s.begin():
            mb2 = await s.get(Mailbox, mailbox_id)
            assert mb2 is not None
            mb2.failures += 1
            mb2.last_error = str(exc)[:500]
            mb2.lease_until = None
            failures = mb2.failures
        if failures == 3:
            await mailbox_event(sessions, mailbox_id, "poll_error", "system", str(exc))
        return PollResult("error")

    new_ids: list[uuid.UUID] = []
    async with sessions() as s, s.begin():
        for pid in ids:
            row = (
                await s.execute(
                    pg_insert(InboxMessage)
                    .values(
                        id=uuid.uuid4(),
                        mailbox_id=mailbox_id,
                        provider_message_id=pid[:200],
                        subject_redacted="",
                        sender_kind="other",
                        status="received",
                        detail="",
                        attempts=0,
                        created_at=now,
                    )
                    .on_conflict_do_nothing(constraint="uq_inbox_message")
                    .returning(InboxMessage.id)
                )
            ).scalar_one_or_none()
            if row is not None:
                new_ids.append(row)
    if provider_name == "gmail":
        new_checkpoint = str(int((now - timedelta(days=1)).timestamp()))
    await release(last_polled_at=now, last_error=None, failures=0, checkpoint=new_checkpoint)
    if stuck:  # left by a crashed worker: claim again from the start
        async with sessions() as s, s.begin():
            await s.execute(
                update(InboxMessage).where(InboxMessage.id.in_(stuck)).values(status="received")
            )
    for mid in [*new_ids, *stuck]:
        await enqueue(mid)
    log.info("inbox poll %s: %d new, %d requeued", mailbox_id, len(new_ids), len(stuck))
    return PollResult("polled", len(new_ids), len(stuck))


# ---- process one message ----------------------------------------------------------------------


@dataclass(frozen=True)
class Created:
    candidate: Snapshot
    acknowledgement: uuid.UUID | None


async def _open_jobs(sessions: SessionMaker) -> list[OpenJob]:
    async with sessions() as s:
        rows = (await s.execute(select(Job.id, Job.title, Job.code, Job.state))).all()
    return [OpenJob(r.id, r.title, r.code, r.state == JobState.OPEN) for r in rows]


async def process_message(
    sessions: SessionMaker,
    storage: Storage,
    providers: ProviderFactory,
    message_id: uuid.UUID,
    *,
    settings: Settings,
    schedule: Callable[[Snapshot], Awaitable[None]],
    queue_email: Callable[[uuid.UUID], Awaitable[None]],
) -> str:
    async with sessions() as s, s.begin():
        msg = (
            await s.execute(
                select(InboxMessage).where(InboxMessage.id == message_id).with_for_update()
            )
        ).scalar_one_or_none()
        if msg is None:
            return "missing"
        if msg.status != "received":
            return msg.status  # done, or another worker has it: a repeat is a no-op
        mb = await s.get(Mailbox, msg.mailbox_id)
        if mb is None or mb.status == "disconnected":
            msg.status, msg.detail = "failed", "the inbox was disconnected"
            return "failed"
        msg.attempts += 1
        msg.status = "working"  # claimed: a second worker stops at the check above
        attempt, provider_id = msg.attempts, msg.provider_message_id
        mailbox = mb

    try:
        raw = await providers(mailbox).fetch(provider_id, settings.cv_max_bytes)
    except ProviderError as exc:
        return await _failed(sessions, message_id, attempt, str(exc))

    kind = sender_kind(raw.sender_address)
    jobs = await _open_jobs(sessions)
    rule = match_rules(raw.subject, raw.to, kind, jobs)

    cvs: list[tuple[int, str, bytes, str]] = []  # position, name, data, media type
    notes = list(raw.skipped)
    for pos, a in enumerate(raw.attachments):
        try:
            cv = check_cv(a.data, a.name, settings.cv_max_bytes)
        except CVRejected as exc:
            notes.append(f"{a.name}: {exc}")
            continue
        cvs.append((pos, cv.original_name, cv.data, cv.media_type))

    first_name_guess: str | None = None
    if not cvs:
        subject = redact_subject(raw.subject, [raw.sender_name])
        await _finish(
            sessions,
            message_id,
            "not_a_cv",
            kind,
            subject,
            None,
            "; ".join(notes) or "No CV attached",
            raw.received_at,
        )
        return "not_a_cv"

    outcomes: list[str] = []
    created: list[Created] = []
    for pos, name, data, media in cvs:
        text = (await extract(data, media)).text
        person, email = guess_contact(
            kind=kind,
            sender_name=raw.sender_name,
            sender_address=raw.sender_address,
            subject=raw.subject,
            cv_text=text,
        )
        first_name_guess = first_name_guess or person
        res = await _ingest_one(
            sessions,
            storage,
            settings,
            message_id=message_id,
            position=pos,
            original_name=name,
            data=data,
            media_type=media,
            job_id=rule.job_id,
            route=rule.route,
            person=person,
            email=email,
            mailbox=mailbox,
        )
        outcomes.append(res[0])
        if res[1] is not None:
            created.append(res[1])

    status = (
        "ingested"
        if "ingested" in outcomes
        else ("duplicate" if "duplicate" in outcomes else "ingested")
    )
    detail = rule.detail if rule.job_id else f"{rule.detail}; the AI matcher will suggest a job"
    if notes:
        detail += "; skipped: " + "; ".join(notes)
    subject = redact_subject(raw.subject, [raw.sender_name, first_name_guess])
    await _finish(sessions, message_id, status, kind, subject, rule.route, detail, raw.received_at)
    for c in created:
        await schedule(c.candidate)
        if c.acknowledgement is not None:
            await queue_email(c.acknowledgement)
    return status


async def _failed(sessions: SessionMaker, message_id: uuid.UUID, attempt: int, error: str) -> str:
    final = attempt >= MAX_MESSAGE_ATTEMPTS
    async with sessions() as s, s.begin():
        msg = await s.get(InboxMessage, message_id)
        assert msg is not None
        msg.last_error = error[:500]
        msg.status = "failed" if final else "received"
    if not final:
        raise ProviderError(error)  # the worker retries the job
    return "failed"


async def _finish(
    sessions: SessionMaker,
    message_id: uuid.UUID,
    status: str,
    kind: str,
    subject: str,
    route: str | None,
    detail: str,
    received_at: datetime | None,
) -> None:
    async with sessions() as s, s.begin():
        msg = await s.get(InboxMessage, message_id)
        assert msg is not None
        msg.status, msg.sender_kind, msg.subject_redacted = status, kind, subject[:300]
        msg.match_route, msg.detail, msg.received_at, msg.last_error = (
            route,
            detail[:2000],
            received_at,
            None,
        )


async def _ingest_one(
    sessions: SessionMaker,
    storage: Storage,
    settings: Settings,
    *,
    message_id: uuid.UUID,
    position: int,
    original_name: str,
    data: bytes,
    media_type: str,
    job_id: uuid.UUID | None,
    route: str | None,
    person: str | None,
    email: str | None,
    mailbox: Mailbox,
) -> tuple[str, Created | None]:
    async with sessions() as s:
        done = (
            await s.execute(
                select(InboxAttachment).where(
                    InboxAttachment.message_id == message_id, InboxAttachment.position == position
                )
            )
        ).scalar_one_or_none()
        if done is not None:
            return done.outcome, None
        email_n = normalise_email(email) if email else None
        existing = None
        if email_n and job_id:
            existing = (
                await s.execute(
                    select(Candidate.id).where(
                        Candidate.job_id == job_id,
                        Candidate.email_normalised == email_n,
                        Candidate.erased_at.is_(None),
                        Candidate.created_at
                        >= datetime.now(UTC) - timedelta(days=settings.inbox_duplicate_days),
                    )
                )
            ).scalar_one_or_none()

    if existing is not None:
        try:
            async with sessions() as s, s.begin():
                s.add(
                    InboxAttachment(
                        message_id=message_id,
                        position=position,
                        original_name=original_name,
                        media_type=media_type,
                        size_bytes=len(data),
                        outcome="duplicate",
                        note="same person and job already applied",
                        candidate_id=existing,
                    )
                )
                s.add(
                    AuditEvent(
                        candidate_id=existing,
                        transition_id="INBOX",
                        from_state=None,
                        to_state=(await s.get(Candidate, existing)).state,  # type: ignore[union-attr]
                        actor_type=ActorType.SYSTEM,
                        actor_id="inbox",
                        reason="another email with the same application arrived; not scored again",
                        idempotency_key=f"{existing}:inbox:{message_id}:{position}",
                    )
                )
        except IntegrityError:
            pass  # a concurrent run recorded it
        return "duplicate", None

    cid = uuid.uuid4()
    key = new_cv_key(cid)
    await storage.put(key, data, media_type)
    try:
        async with sessions() as s, s.begin():
            if job_id is not None:
                n = (
                    await s.execute(
                        select(func.count())
                        .select_from(Candidate)
                        .where(Candidate.job_id == job_id)
                    )
                ).scalar_one()
                label = f"Applicant {int(n) + 1}"
            else:
                n = (
                    await s.execute(
                        select(func.count())
                        .select_from(Candidate)
                        .where(Candidate.source == "inbox")
                    )
                ).scalar_one()
                label = f"Inbox applicant {int(n) + 1}"
            cand = Candidate(
                id=cid,
                state=CandidateState.APPLIED,
                state_version=1,
                display_label=label,
                job_id=job_id,
                source="inbox",
                full_name=person,
                email=email,
                email_normalised=normalise_email(email) if email else None,
                consent_at=None,
                consent_notice_version=NOTICE_VERSION if email else None,
                consent_basis="inbox_notice" if email else None,
                cv_object_key=key,
                cv_original_name=original_name,
                cv_media_type=media_type,
                cv_size_bytes=len(data),
                cv_sha256=hashlib.sha256(data).hexdigest(),
            )
            s.add(cand)
            await s.flush()
            s.add(
                InboxAttachment(
                    message_id=message_id,
                    position=position,
                    original_name=original_name,
                    media_type=media_type,
                    size_bytes=len(data),
                    outcome="ingested",
                    note="",
                    candidate_id=cid,
                )
            )
            add_created_audit(
                s,
                cand,
                actor_type=ActorType.SYSTEM,
                actor_id="inbox",
                reason=f"received at the connected inbox ({mailbox.provider})"
                + (f"; job from {route.replace('_', ' ')}" if route else "; job to be matched"),
            )
            ack: uuid.UUID | None = None
            if email:
                ack = uuid.uuid4()
                domain = settings.email_reply_to.split("@", 1)[-1] or "recruit-agent.local"
                s.add(
                    OutboundEmail(
                        id=ack,
                        candidate_id=cid,
                        kind="acknowledgement",
                        draft_id=None,
                        idempotency_key=f"{cid}:acknowledgement",
                        message_id=f"<acknowledgement.{cid}@{domain}>",
                        subject=f"We received your application ({settings.company_name})",
                        status="queued",
                        provider=settings.email_provider,
                        attempts=0,
                        actor_id="system",
                    )
                )
            await s.flush()
            snap = Snapshot.of(cand)
    except IntegrityError:
        await delete_with_retry(storage, key)
        return "ingested", None  # a concurrent run created it
    except Exception:
        await delete_with_retry(storage, key)
        raise
    return "ingested", Created(snap, ack)
