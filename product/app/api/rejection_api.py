"""Rejection email endpoints (phase 5 design sections 3 and 6).

- GET  /candidates/{id}/rejection: the latest draft, the preview as it will read (with
  "[first name]", never the name or address: blind review), the version count and the
  delivery status.
- PUT  /candidates/{id}/rejection: a recruiter edit; checks run first (422 with results).
- POST /candidates/{id}/send-rejection: the move to REJECTION_SENT plus the outbox row in
  one transaction, then the delivery job is queued.
- POST /candidates/{id}/rejection/retry-delivery: for an email that was not delivered.
- GET  /rejections/queue: drafts to send (needs a look first) and emails not delivered.
"""

import time
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.config import Settings
from app.db.models import Candidate, Job, OutboundEmail, RejectionDraft
from app.domain.states import ActorType, CandidateState
from app.rejection.compose import full_text
from app.rejection.outbox import (
    CandidateErased,
    DraftRefused,
    SendRefused,
    edit_draft,
    latest_draft,
    latest_outbox,
    requeue_failed,
    send_extra,
)
from app.workflow.machine import TransitionRefused, apply_transition, get_candidate

S = CandidateState


class EditDraft(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    expected_draft_version: int


class Send(BaseModel):
    reason: str = Field(default="rejection email sent", min_length=1, max_length=2000)
    expected_version: int | None = None


def _draft(d: RejectionDraft, settings: Settings) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "version": d.version,
        "source": d.source,
        "reasons": d.reasons,
        "body": d.body,
        "preview": full_text(
            d.body,
            first_name=None,
            company=settings.company_name,
            reply_to=settings.email_reply_to,
        ),
        "checks": d.checks,
        "fallback_reason": d.fallback_reason,
        "needs_edit": d.needs_edit,
        "prompt": f"{d.prompt_id}-{d.prompt_version}" if d.prompt_id else None,
        "model": d.model,
        "actor_id": d.actor_id,
        "erased": d.erased,
        "created_at": d.created_at.isoformat(),
    }


def _outbox(o: OutboundEmail) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "status": o.status,
        "provider": o.provider,
        "subject": o.subject,
        "attempts": o.attempts,
        "last_error": o.last_error,
        "actor_id": o.actor_id,
        "queued_at": o.queued_at.isoformat(),
        "sent_at": o.sent_at.isoformat() if o.sent_at else None,
    }


def register(app: FastAPI, cfg: Settings, Recruiter: Any, Pl: Any) -> None:  # noqa: N803
    @app.exception_handler(DraftRefused)
    async def _draft_refused(_: Request, exc: DraftRefused) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "draft_refused",
                "detail": str(exc),
                "checks": [r.as_dict() for r in exc.results],
            },
        )

    @app.exception_handler(SendRefused)
    async def _send_refused(_: Request, exc: SendRefused) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "send_refused", "detail": str(exc)})

    @app.exception_handler(CandidateErased)
    async def _erased(_: Request, exc: CandidateErased) -> JSONResponse:
        return JSONResponse(status_code=410, content={"error": "erased", "detail": str(exc)})

    @app.get("/candidates/{candidate_id}/rejection")
    async def get_rejection(candidate_id: uuid.UUID, _: Recruiter, p: Pl) -> JSONResponse:
        await get_candidate(p.sessions, candidate_id)  # 404 when unknown
        async with p.sessions() as s:
            draft = await latest_draft(s, candidate_id)
            versions = (
                await s.execute(
                    select(func.count())
                    .select_from(RejectionDraft)
                    .where(RejectionDraft.candidate_id == candidate_id)
                )
            ).scalar_one()
            out = await latest_outbox(s, candidate_id)
        return JSONResponse(
            content={
                "draft": _draft(draft, cfg) if draft is not None else None,
                "versions": versions,
                "outbox": _outbox(out) if out is not None else None,
            }
        )

    @app.put("/candidates/{candidate_id}/rejection")
    async def put_rejection(
        candidate_id: uuid.UUID, body: EditDraft, actor: Recruiter, p: Pl
    ) -> JSONResponse:
        row = await edit_draft(
            p.sessions,
            candidate_id,
            body=body.body,
            expected_draft_version=body.expected_draft_version,
            actor_id=actor,
        )
        return JSONResponse(content={"draft": _draft(row, cfg)})

    @app.post("/candidates/{candidate_id}/send-rejection")
    async def send_rejection(
        candidate_id: uuid.UUID, body: Send, actor: Recruiter, p: Pl
    ) -> JSONResponse:
        current = await get_candidate(p.sessions, candidate_id)
        if current.state != S.REJECTION_DRAFTED:
            raise TransitionRefused(f"send is only possible from a draft (now {current.state})")
        hook, outbox_id = await send_extra(
            p.sessions, candidate_id, actor_id=actor, settings=cfg, provider=p.email.name
        )
        moved = await apply_transition(
            p.sessions,
            candidate_id=candidate_id,
            to_state=S.REJECTION_SENT,
            actor_type=ActorType.RECRUITER,
            actor_id=actor,
            reason=f"{body.reason} (queued for delivery)",
            expected_state=current.state,
            expected_version=body.expected_version
            if body.expected_version is not None
            else current.state_version,
            extra=hook,
        )
        if outbox_id is not None:
            await p.queue_delivery(outbox_id)
        return JSONResponse(
            content={
                "id": str(moved.id),
                "state": moved.state.value,
                "state_version": moved.state_version,
                "outbox_id": str(outbox_id) if outbox_id else None,
            }
        )

    @app.post("/candidates/{candidate_id}/rejection/retry-delivery")
    async def retry_delivery(candidate_id: uuid.UUID, actor: Recruiter, p: Pl) -> JSONResponse:
        outbox_id = await requeue_failed(p.sessions, candidate_id, actor_id=actor)
        # a new job id (the first run of attempt 0 is still remembered by the queue)
        await p.queue_delivery(outbox_id, attempt=int(time.time()))
        return JSONResponse(status_code=202, content={"outbox_id": str(outbox_id)})

    @app.get("/rejections/queue")
    async def rejection_queue(_: Recruiter, p: Pl) -> JSONResponse:
        async with p.sessions() as s:
            drafts = (
                await s.execute(
                    select(Candidate, Job.title)
                    .outerjoin(Job, Job.id == Candidate.job_id)
                    .where(Candidate.state == S.REJECTION_DRAFTED.value)
                    .order_by(Candidate.updated_at)
                )
            ).all()
            draft_rows = []
            for c, title in drafts:
                d = await latest_draft(s, c.id)
                draft_rows.append(
                    {
                        "id": str(c.id),
                        "label": c.display_label,
                        "job_id": str(c.job_id) if c.job_id else None,
                        "job_title": title,
                        "state_version": c.state_version,
                        "source": d.source if d else None,
                        "needs_edit": bool(d.needs_edit) if d else False,
                        "fallback_reason": d.fallback_reason if d else None,
                    }
                )
            draft_rows.sort(key=lambda r: not r["needs_edit"])
            failed = (
                await s.execute(
                    select(OutboundEmail, Candidate, Job.title)
                    .join(Candidate, Candidate.id == OutboundEmail.candidate_id)
                    .outerjoin(Job, Job.id == Candidate.job_id)
                    .where(OutboundEmail.status == "failed")
                    .order_by(OutboundEmail.queued_at)
                )
            ).all()
        return JSONResponse(
            content={
                "drafts": draft_rows,
                "undelivered": [
                    {
                        "id": str(c.id),
                        "label": c.display_label,
                        "job_title": title,
                        "attempts": o.attempts,
                        "last_error": o.last_error,
                    }
                    for o, c, title in failed
                ],
            }
        )

    _ = (get_rejection, put_rejection, send_rejection, retry_delivery, rejection_queue)
