"""Recruiter edits, Send and delivery (phase 5 design sections 3 and 7).

- Edit: a new draft version; the checks (H2 to H8) run first and a failing edit is not
  saved. An audit row ("EDIT", no state move) records who and when.
- Send: the move to REJECTION_SENT and one outbox row in the same transaction. The row's
  idempotency key is unique per candidate rejection, so a double click, a second tab or
  a retried request can never create a second email.
- Delivery: the worker sets the row to `sending` before calling the provider. A job that
  finds a row already `sending` (a crash between the provider accepting it and the row
  being marked sent) asks the provider whether that Message-ID was delivered before
  sending again. Failures are retried with backoff, then the row is `failed` and shows in
  the "not delivered" list. The candidate's state never changes after Send.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import (
    AuditEvent,
    Candidate,
    CvParse,
    Job,
    OutboundEmail,
    RejectionDraft,
)
from app.db.session import SessionMaker
from app.domain.notice import acknowledgement_text
from app.domain.states import ActorType, CandidateState
from app.integrations.email import EmailError, EmailSender, OutgoingEmail
from app.rejection.checks import CheckResult, all_passed, failures, run_checks
from app.rejection.compose import first_name_of, full_text, subject

S = CandidateState


class DraftRefused(ValueError):
    """An edit failed the checks (422). Carries the results for the dashboard."""

    def __init__(self, results: list[CheckResult]) -> None:
        self.results = results
        super().__init__("; ".join(f"{r.rule}: {r.detail}" for r in failures(results)))


class SendRefused(Exception):
    """Send not possible now (409): no draft, a failing draft, or a stale draft version."""


class CandidateErased(Exception):
    """The candidate's personal data was erased (410)."""


def idempotency_key(candidate_id: uuid.UUID) -> str:
    return f"{candidate_id}:rejection"


def message_id(candidate_id: uuid.UUID, sender: str) -> str:
    addr = parseaddr(sender)[1]
    domain = addr.split("@", 1)[1] if "@" in addr else "recruit-agent.local"
    return f"<rejection.{candidate_id}@{domain}>"


async def latest_draft(s: AsyncSession, candidate_id: uuid.UUID) -> RejectionDraft | None:
    return (
        await s.execute(
            select(RejectionDraft)
            .where(RejectionDraft.candidate_id == candidate_id)
            .order_by(RejectionDraft.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def latest_outbox(
    s: AsyncSession, candidate_id: uuid.UUID, kind: str | None = "rejection"
) -> OutboundEmail | None:
    q = select(OutboundEmail).where(OutboundEmail.candidate_id == candidate_id)
    if kind is not None:
        q = q.where(OutboundEmail.kind == kind)
    return (
        await s.execute(q.order_by(OutboundEmail.queued_at.desc()).limit(1))
    ).scalar_one_or_none()


async def _cv_text(s: AsyncSession, candidate_id: uuid.UUID) -> str:
    parse = (
        await s.execute(
            select(CvParse)
            .where(CvParse.candidate_id == candidate_id, CvParse.status == "parsed")
            .order_by(CvParse.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return (parse.redacted_text or "") if parse is not None else ""


def _note(
    cand: Candidate, kind: str, reason: str, actor_type: ActorType, actor_id: str, key: str
) -> AuditEvent:
    return AuditEvent(
        candidate_id=cand.id,
        transition_id=kind,
        from_state=cand.state,
        to_state=cand.state,
        actor_type=actor_type,
        actor_id=actor_id,
        reason=reason,
        idempotency_key=key,
    )


async def edit_draft(
    sessions: SessionMaker,
    candidate_id: uuid.UUID,
    *,
    body: str,
    expected_draft_version: int,
    actor_id: str,
) -> RejectionDraft:
    async with sessions() as s, s.begin():
        cand = (
            await s.execute(select(Candidate).where(Candidate.id == candidate_id).with_for_update())
        ).scalar_one_or_none()
        if cand is None:
            from app.workflow.machine import CandidateNotFound

            raise CandidateNotFound(str(candidate_id))
        if cand.erased_at is not None:
            raise CandidateErased("this candidate's data was erased")
        if cand.state != S.REJECTION_DRAFTED.value:
            raise SendRefused(f"the draft can only be edited before sending (now {cand.state})")
        current = await latest_draft(s, candidate_id)
        if current is None:
            raise SendRefused("there is no draft yet")
        if current.version != expected_draft_version:
            raise SendRefused("the draft changed since you opened it")
        results = run_checks(
            body,
            reason_ids=None,
            allowed_ids=[],
            cv_text=await _cv_text(s, candidate_id),
        )
        if not all_passed(results):
            raise DraftRefused(results)
        row = RejectionDraft(
            candidate_id=candidate_id,
            version=current.version + 1,
            source="recruiter",
            score_id=current.score_id,
            opening="",
            closing="",
            reasons=current.reasons,
            body=body.strip(),
            checks=[r.as_dict() for r in results],
            fallback_reason=None,
            needs_edit=False,
            actor_id=actor_id,
        )
        s.add(row)
        s.add(
            _note(
                cand,
                "EDIT",
                f"rejection draft edited (version {row.version})",
                ActorType.RECRUITER,
                actor_id,
                f"{candidate_id}:EDIT:v{row.version}",
            )
        )
    return row


async def send_extra(
    sessions: SessionMaker,
    candidate_id: uuid.UUID,
    *,
    actor_id: str,
    settings: Settings,
    provider: str,
) -> tuple[Callable[[AsyncSession, Candidate], None], uuid.UUID | None]:
    """Check the draft now (before anything moves) and return the hook that writes the
    outbox row in the move's transaction, with the new row's id. Phase 0 test candidates
    (no job, no contact details, stub draft) move without an email: (no-op, None)."""
    async with sessions() as s:
        cand = await s.get(Candidate, candidate_id)
        if cand is not None and cand.erased_at is not None:
            raise CandidateErased("this candidate's data was erased")
        draft = await latest_draft(s, candidate_id)
        if (
            draft is None
            and cand is not None
            and cand.job_id is None
            and settings.environment != "production"
        ):
            return (lambda _s, _c: None), None
        if draft is None:
            raise SendRefused("there is no draft to send yet")
        if not all_passed(draft.checks):
            raise SendRefused("the latest draft fails a check; edit it first")
        job = await s.get(Job, cand.job_id) if cand is not None and cand.job_id else None
        title = job.title if job is not None else "the role"
        draft_id = draft.id
    outbox_id = uuid.uuid4()
    row: dict[str, Any] = {
        "id": outbox_id,
        "candidate_id": candidate_id,
        "draft_id": draft_id,
        "idempotency_key": idempotency_key(candidate_id),
        "message_id": message_id(candidate_id, settings.email_from),
        "subject": subject(title, settings.company_name),
        "status": "queued",
        "provider": provider,
        "attempts": 0,
        "actor_id": actor_id,
    }

    def add(s: AsyncSession, _c: Candidate) -> None:
        s.add(OutboundEmail(**row))

    return add, outbox_id


@dataclass(frozen=True)
class Delivery:
    status: str  # sent | retry | failed | cancelled | missing
    retry_in: int = 0
    attempts: int = 0


async def _mark(sessions: SessionMaker, outbox_id: uuid.UUID, **values: Any) -> None:
    async with sessions() as s, s.begin():
        row = await s.get(OutboundEmail, outbox_id)
        if row is not None:
            for k, v in values.items():
                setattr(row, k, v)


async def _audit(sessions: SessionMaker, candidate_id: uuid.UUID, reason: str, key: str) -> None:
    from sqlalchemy.exc import IntegrityError

    try:
        async with sessions() as s, s.begin():
            cand = await s.get(Candidate, candidate_id)
            if cand is not None:
                s.add(_note(cand, "EMAIL", reason, ActorType.SYSTEM, "worker:deliver_email", key))
    except IntegrityError:
        pass  # already recorded by an earlier run of the same job


async def deliver(
    sessions: SessionMaker, sender: EmailSender, outbox_id: uuid.UUID, *, settings: Settings
) -> Delivery:
    # Claim the row: queued (or a crashed `sending`) to `sending`, under a row lock.
    async with sessions() as s, s.begin():
        row = (
            await s.execute(
                select(OutboundEmail).where(OutboundEmail.id == outbox_id).with_for_update()
            )
        ).scalar_one_or_none()
        if row is None:
            return Delivery("missing")
        if row.status in ("sent", "cancelled", "failed"):
            return Delivery(row.status, attempts=row.attempts)
        cand = await s.get(Candidate, row.candidate_id)
        if cand is None or cand.erased_at is not None:
            row.status = "cancelled"
            row.last_error = "candidate erased before delivery"
            return Delivery("cancelled", attempts=row.attempts)
        crashed = row.status == "sending"
        if row.kind == "acknowledgement":
            job = await s.get(Job, cand.job_id) if cand.job_id else None
            text = acknowledgement_text(
                first_name=first_name_of(cand.full_name),
                company=settings.company_name,
                job_title=job.title if job else None,
                reply_to=settings.email_reply_to,
            )
        else:
            draft = await s.get(RejectionDraft, row.draft_id) if row.draft_id else None
            text = full_text(
                draft.body if draft is not None else "",
                first_name=first_name_of(cand.full_name),
                company=settings.company_name,
                reply_to=settings.email_reply_to,
            )
        kind = row.kind
        msg = OutgoingEmail(
            to=cand.email or "",
            sender=settings.email_from,
            reply_to=settings.email_reply_to,
            subject=row.subject,
            text=text,
            message_id=row.message_id,
        )
        candidate_id, mid = row.candidate_id, row.message_id
        row.status = "sending"
        row.attempts += 1
        attempt = row.attempts

    if not msg.to:
        await _mark(sessions, outbox_id, status="failed", last_error="no email address")
        await _audit(
            sessions, candidate_id, "email not delivered: no email address", f"{outbox_id}:failed"
        )
        return Delivery("failed", attempts=attempt)

    try:
        if crashed and await sender.already_delivered(mid):
            provider_id = "found after restart"
        else:
            provider_id = await sender.send(msg)
    except EmailError as exc:
        error = str(exc)[:500]
        if attempt >= settings.email_delivery_max_attempts:
            await _mark(sessions, outbox_id, status="failed", last_error=error)
            await _audit(
                sessions,
                candidate_id,
                f"email not delivered after {attempt} attempts: {error}",
                f"{outbox_id}:failed:{attempt}",
            )
            return Delivery("failed", attempts=attempt)
        await _mark(sessions, outbox_id, status="queued", last_error=error)
        return Delivery(
            "retry",
            retry_in=settings.email_retry_base_seconds * 2 ** (attempt - 1),
            attempts=attempt,
        )

    await _mark(
        sessions,
        outbox_id,
        status="sent",
        provider_message_id=provider_id[:200],
        sent_at=datetime.now(UTC),
        last_error=None,
    )
    await _audit(
        sessions,
        candidate_id,
        f"{kind} email delivered ({sender.name}, attempt {attempt})",
        f"{outbox_id}:sent",
    )
    return Delivery("sent", attempts=attempt)


async def requeue_failed(
    sessions: SessionMaker, candidate_id: uuid.UUID, *, actor_id: str
) -> uuid.UUID:
    """Retry delivery for a `failed` email (the "not delivered" list)."""
    async with sessions() as s, s.begin():
        cand = await s.get(Candidate, candidate_id)
        if cand is None:
            from app.workflow.machine import CandidateNotFound

            raise CandidateNotFound(str(candidate_id))
        if cand.erased_at is not None:
            raise CandidateErased("this candidate's data was erased")
        row = (
            await s.execute(
                select(OutboundEmail)
                .where(OutboundEmail.candidate_id == candidate_id, OutboundEmail.status == "failed")
                .order_by(OutboundEmail.queued_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            raise SendRefused("only an email that was not delivered can be retried")
        row.status = "queued"
        row.attempts = 0
        s.add(
            _note(
                cand,
                "EMAIL",
                "delivery retry requested",
                ActorType.RECRUITER,
                actor_id,
                f"{row.id}:retry:{uuid.uuid4().hex}",
            )
        )
        return row.id


async def cancel_on_erasure(s: AsyncSession, candidate_id: uuid.UUID) -> None:
    """Called inside the erasure transaction: clear draft text, cancel unsent email."""
    from sqlalchemy import update as sql_update

    await s.execute(
        sql_update(RejectionDraft)
        .where(RejectionDraft.candidate_id == candidate_id)
        .values(opening="", closing="", reasons=[], body="", erased=True)
    )
    await s.execute(
        sql_update(OutboundEmail)
        .where(
            OutboundEmail.candidate_id == candidate_id,
            OutboundEmail.status.in_(["queued", "sending", "failed"]),
        )
        .values(status="cancelled", last_error="candidate erased before delivery")
    )
