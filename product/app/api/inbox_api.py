"""Connected inbox endpoints (phase 5B design sections 5 and 6).

- GET  /inbox: mailboxes, recent messages (redacted subjects only) and what can be connected
- POST /inbox/mailpit: connect the local test inbox (not in production)
- POST /inbox/gmail/start: the Google sign in address (state and PKCE stored)
- POST /inbox/gmail/callback: finish the sign in (the dashboard passes the code and state)
- GET  /inbox/mailboxes/{id}/labels: labels to choose from
- PUT  /inbox/mailboxes/{id}: choose the label, pause or resume
- POST /inbox/mailboxes/{id}/poll: check now
- POST /inbox/mailboxes/{id}/disconnect: revoke and delete the token, stop reading
- POST /candidates/{id}/pick-job: the recruiter picks the job for a "needs a job" candidate
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.config import Settings
from app.db.models import (
    Candidate,
    InboxAttachment,
    InboxMessage,
    Job,
    JobMatch,
    Mailbox,
    MailboxEvent,
)
from app.domain.jobs import JobState
from app.domain.states import ActorType, CandidateState
from app.inbox.crypto import decrypt_token
from app.inbox.oauth import ConnectRefused, finish_gmail, gmail_configured, revoke, start_gmail
from app.inbox.providers import ProviderError
from app.workflow.dispatch import InboxPollJob
from app.workflow.machine import StaleTransition, TransitionRefused, apply_transition

S = CandidateState


class Callback(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    state: str = Field(min_length=10, max_length=64)


class MailpitConnect(BaseModel):
    label: str = Field(default="Applications", min_length=1, max_length=200)


class MailboxUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "paused"] | None = None


class PickJob(BaseModel):
    job_id: uuid.UUID
    expected_version: int


def _mailbox(m: Mailbox) -> dict[str, Any]:
    return {
        "id": str(m.id),
        "provider": m.provider,
        "address": m.address,
        "label": m.label,
        "status": m.status,
        "last_polled_at": m.last_polled_at.isoformat() if m.last_polled_at else None,
        "last_error": m.last_error,
        "connected_by": m.connected_by,
        "connected_at": m.connected_at.isoformat(),
    }


def register(app: FastAPI, cfg: Settings, Recruiter: Any, Pl: Any) -> None:  # noqa: N803
    @app.exception_handler(ConnectRefused)
    async def _refused(_: Request, exc: ConnectRefused) -> JSONResponse:
        return JSONResponse(
            status_code=400, content={"error": "connect_refused", "detail": str(exc)}
        )

    @app.get("/inbox")
    async def inbox(_: Recruiter, p: Pl) -> JSONResponse:
        async with p.sessions() as s:
            boxes = list(
                (
                    await s.execute(
                        select(Mailbox)
                        .where(Mailbox.status != "disconnected")
                        .order_by(Mailbox.connected_at)
                    )
                ).scalars()
            )
            msgs = list(
                (
                    await s.execute(
                        select(InboxMessage)
                        .where(InboxMessage.mailbox_id.in_([b.id for b in boxes]))
                        .order_by(InboxMessage.created_at.desc())
                        .limit(100)
                    )
                ).scalars()
            )
            atts = list(
                (
                    await s.execute(
                        select(InboxAttachment, Candidate, Job.title)
                        .outerjoin(Candidate, Candidate.id == InboxAttachment.candidate_id)
                        .outerjoin(Job, Job.id == Candidate.job_id)
                        .where(InboxAttachment.message_id.in_([m.id for m in msgs]))
                    )
                ).all()
            )
            matches = {
                r.candidate_id: r
                for r in (
                    await s.execute(
                        select(JobMatch)
                        .where(
                            JobMatch.candidate_id.in_([c.id for _, c, _ in atts if c is not None])
                        )
                        .order_by(JobMatch.created_at)
                    )
                ).scalars()
            }
            open_jobs = [
                {"id": str(j.id), "title": j.title, "code": j.code}
                for j in (
                    await s.execute(
                        select(Job).where(Job.state == JobState.OPEN).order_by(Job.title)
                    )
                ).scalars()
            ]
        by_msg: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for a, c, title in atts:
            m = matches.get(c.id) if c is not None else None
            by_msg.setdefault(a.message_id, []).append(
                {
                    "outcome": a.outcome,
                    "note": a.note,
                    "candidate_id": str(c.id) if c else None,
                    "label": c.display_label if c else None,
                    "state": c.state if c else None,
                    "state_version": c.state_version if c else None,
                    "job_title": title,
                    "needs_job": bool(c and c.state == S.NEEDS_REVIEW and c.job_id is None),
                    "suggested": [f["job_id"] for f in sorted(m.fits, key=lambda f: -f["fit"])[:2]]
                    if m
                    else [],
                    "match": m.reason if m else None,
                }
            )
        return JSONResponse(
            content={
                "mailboxes": [_mailbox(b) for b in boxes],
                "messages": [
                    {
                        "id": str(m.id),
                        "mailbox_id": str(m.mailbox_id),
                        "subject": m.subject_redacted,
                        "sender_kind": m.sender_kind,
                        "status": m.status,
                        "route": m.match_route,
                        "detail": m.detail,
                        "received_at": (m.received_at or m.created_at).isoformat(),
                        "attachments": by_msg.get(m.id, []),
                    }
                    for m in msgs
                ],
                "open_jobs": open_jobs,
                "can_connect": {
                    "gmail": gmail_configured(cfg),
                    "mailpit": cfg.environment != "production",
                },
            }
        )

    @app.post("/inbox/mailpit")
    async def connect_mailpit(body: MailpitConnect, actor: Recruiter, p: Pl) -> JSONResponse:
        if cfg.environment == "production":
            raise HTTPException(403, "the test inbox is not available in production")
        async with p.sessions() as s, s.begin():
            existing = (
                await s.execute(
                    select(Mailbox).where(
                        Mailbox.provider == "mailpit", Mailbox.status != "disconnected"
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return JSONResponse(content=_mailbox(existing))
            mb = Mailbox(
                provider="mailpit",
                address="test inbox (Mailpit)",
                label=body.label,
                status="active",
                scopes=["read"],
                connected_by=actor,
            )
            s.add(mb)
            await s.flush()
            s.add(
                MailboxEvent(
                    mailbox_id=mb.id,
                    kind="connect",
                    actor_id=actor,
                    detail=f"mailpit, tag {body.label}",
                )
            )
            out = _mailbox(mb)
        await p.dispatcher.enqueue(InboxPollJob(uuid.UUID(out["id"]), 0))
        return JSONResponse(content=out)

    @app.post("/inbox/gmail/start")
    async def gmail_start(actor: Recruiter, p: Pl) -> JSONResponse:
        return JSONResponse(content={"url": await start_gmail(p.sessions, cfg, actor)})

    @app.post("/inbox/gmail/callback")
    async def gmail_callback(body: Callback, actor: Recruiter, p: Pl) -> JSONResponse:
        mb = await finish_gmail(p.sessions, cfg, actor_id=actor, code=body.code, state=body.state)
        return JSONResponse(content=_mailbox(mb))

    async def _get(p: Any, mailbox_id: uuid.UUID) -> Mailbox:
        async with p.sessions() as s:
            mb: Mailbox | None = await s.get(Mailbox, mailbox_id)
        if mb is None or mb.status == "disconnected":
            raise HTTPException(404, "no such inbox")
        return mb

    @app.get("/inbox/mailboxes/{mailbox_id}/labels")
    async def labels(mailbox_id: uuid.UUID, _: Recruiter, p: Pl) -> JSONResponse:
        mb = await _get(p, mailbox_id)
        try:
            names = await p.mailboxes(mb).labels()
        except ProviderError as exc:
            raise HTTPException(502, f"could not read the labels: {exc}") from exc
        return JSONResponse(content={"labels": names})

    @app.put("/inbox/mailboxes/{mailbox_id}")
    async def update_mailbox(
        mailbox_id: uuid.UUID, body: MailboxUpdate, actor: Recruiter, p: Pl
    ) -> JSONResponse:
        async with p.sessions() as s, s.begin():
            mb = await s.get(Mailbox, mailbox_id, with_for_update=True)
            if mb is None or mb.status == "disconnected":
                raise HTTPException(404, "no such inbox")
            if mb.status == "needs_reconnect":
                raise HTTPException(409, "reconnect this inbox first")
            if body.label is not None:
                if body.label.strip().upper() in ("INBOX", "ALL", "ALL MAIL", "[GMAIL]/ALL MAIL"):
                    raise HTTPException(422, "choose a label for applications, not the whole inbox")
                mb.label = body.label.strip()
                mb.checkpoint = None
                s.add(MailboxEvent(mailbox_id=mb.id, kind="label", actor_id=actor, detail=mb.label))
                if mb.status == "needs_label":
                    mb.status = "active"
            if body.status is not None and mb.label:
                mb.status = body.status
                s.add(
                    MailboxEvent(
                        mailbox_id=mb.id,
                        kind="pause" if body.status == "paused" else "resume",
                        actor_id=actor,
                    )
                )
            out = _mailbox(mb)
        if out["status"] == "active":
            await p.dispatcher.enqueue(InboxPollJob(mailbox_id, 0))
        return JSONResponse(content=out)

    @app.post("/inbox/mailboxes/{mailbox_id}/poll")
    async def poll_now(mailbox_id: uuid.UUID, _: Recruiter, p: Pl) -> JSONResponse:
        mb = await _get(p, mailbox_id)
        if mb.status != "active":
            raise HTTPException(409, "this inbox is not active")
        await p.dispatcher.enqueue(InboxPollJob(mailbox_id, int(uuid.uuid4().int % 10**9)))
        return JSONResponse(status_code=202, content={"queued": True})

    @app.post("/inbox/mailboxes/{mailbox_id}/disconnect")
    async def disconnect(mailbox_id: uuid.UUID, actor: Recruiter, p: Pl) -> JSONResponse:
        async with p.sessions() as s, s.begin():
            mb = await s.get(Mailbox, mailbox_id, with_for_update=True)
            if mb is None or mb.status == "disconnected":
                raise HTTPException(404, "no such inbox")
            token = None
            if mb.token_ciphertext is not None:
                try:
                    token = decrypt_token(cfg, mb.token_ciphertext)
                except Exception:  # noqa: BLE001 (deleted below either way)
                    token = None
            mb.token_ciphertext = None
            mb.status = "disconnected"
            mb.disconnected_at = datetime.now(UTC)
            provider = mb.provider
        revoked = await revoke(token) if token and provider == "gmail" else False
        async with p.sessions() as s, s.begin():
            s.add(
                MailboxEvent(
                    mailbox_id=mailbox_id,
                    kind="disconnect",
                    actor_id=actor,
                    detail="token deleted"
                    + (
                        "; revoked at Google"
                        if revoked
                        else (
                            "" if provider != "gmail" else "; revoke failed, token deleted anyway"
                        )
                    ),
                )
            )
        return JSONResponse(content={"status": "disconnected", "revoked": revoked})

    @app.post("/candidates/{candidate_id}/pick-job")
    async def pick_job(
        candidate_id: uuid.UUID, body: PickJob, actor: Recruiter, p: Pl
    ) -> JSONResponse:
        async with p.sessions() as s:
            cand = await s.get(Candidate, candidate_id)
            job = await s.get(Job, body.job_id)
        if cand is None:
            raise HTTPException(404, "no such candidate")
        if job is None or job.state != JobState.OPEN:
            raise HTTPException(422, "pick an open job")
        if (
            cand.state != S.NEEDS_REVIEW
            or cand.review_return_state != S.PARSED
            or cand.job_id is not None
        ):
            raise HTTPException(409, "this candidate is not waiting for a job")
        jid, title = job.id, job.title

        def set_job(_s: object, c: Candidate) -> None:
            c.job_id = jid

        try:
            moved = await apply_transition(
                p.sessions,
                candidate_id=candidate_id,
                to_state=S.PARSED,
                actor_type=ActorType.RECRUITER,
                actor_id=actor,
                reason=f"job picked: {title}",
                expected_state=S.NEEDS_REVIEW,
                expected_version=body.expected_version,
                extra=set_job,
            )
        except StaleTransition as exc:
            raise HTTPException(409, "this candidate changed since you opened it") from exc
        except TransitionRefused as exc:
            raise HTTPException(409, str(exc)) from exc
        await p.schedule(moved)
        return JSONResponse(
            content={"id": str(moved.id), "state": moved.state.value, "job_id": str(jid)}
        )

    _ = (
        inbox,
        connect_mailpit,
        gmail_start,
        gmail_callback,
        labels,
        update_mailbox,
        poll_now,
        disconnect,
        pick_job,
    )
