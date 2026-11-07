"""The intake adapter: one path for every application source.

Order (phase 1 design section 4): job open, consent, answers, CV checks, duplicate check,
store the CV, then create the candidate and answers in one transaction (deleting the CV
if that fails), then start the pipeline. Every refusal happens before anything is stored.
Nothing here logs or traces personal data: only ids and outcomes.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import Answer, Candidate, Job, ScreeningQuestion
from app.domain.jobs import JobState
from app.domain.notice import NOTICE_VERSION
from app.domain.questions import coerce_answer
from app.domain.states import ActorType, CandidateState
from app.intake.files import CVRejected, check_cv
from app.integrations.storage import Storage, StorageError, delete_with_retry, new_cv_key
from app.workflow.machine import Snapshot, add_created_audit
from app.workflow.pipeline import Pipeline

log = logging.getLogger(__name__)

Source = Literal["apply_page", "bulk_upload"]


@dataclass
class Application:
    job_id: uuid.UUID
    source: Source
    full_name: str
    email: str
    phone: str | None
    cv_bytes: bytes
    cv_filename: str
    answers: dict[str, Any] = field(default_factory=dict)
    candidate_consented: bool = False
    recruiter_attested: bool = False
    attested_by: str | None = None
    original_platform: str | None = None


class IntakeRefused(Exception):
    """Validation failed; `errors` maps a field to a message the applicant can act on."""

    def __init__(self, errors: dict[str, str], status: int = 422) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors
        self.status = status


@dataclass(frozen=True)
class IntakeResult:
    status: Literal["created", "duplicate"]
    candidate_id: uuid.UUID


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _valid_email(email: str) -> bool:
    e = email.strip()
    if len(e) > 320 or " " in e or e.count("@") != 1:
        return False
    local, domain = e.split("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


async def submit(
    pipeline: Pipeline, storage: Storage, app: Application, *, cv_max_bytes: int
) -> IntakeResult:
    sessions = pipeline.sessions
    errors: dict[str, str] = {}

    # 1. job open, and its questions
    async with sessions() as s:
        job = await s.get(Job, app.job_id)
        if job is None or job.state != JobState.OPEN:
            raise IntakeRefused({"job": "this job is not open for applications"}, status=404)
        qs = list(
            (
                await s.execute(
                    select(ScreeningQuestion)
                    .where(ScreeningQuestion.job_id == app.job_id)
                    .order_by(ScreeningQuestion.position)
                )
            ).scalars()
        )

    # 2. consent
    if app.source == "apply_page" and not app.candidate_consented:
        errors["consent"] = "please read the notice and tick the box to agree"
    if app.source == "bulk_upload" and not (app.recruiter_attested and app.original_platform):
        errors["consent"] = "confirm the candidate consented and name the platform they applied on"

    # contact details
    name = " ".join(app.full_name.split())
    if not 2 <= len(name) <= 200:
        errors["full_name"] = "enter your full name"
    if not _valid_email(app.email):
        errors["email"] = "enter a valid email address"
    phone = (app.phone or "").strip() or None
    if phone is not None and (len(phone) > 40 or sum(ch.isdigit() for ch in phone) < 8):
        errors["phone"] = "enter a valid phone number"

    # 3. answers
    values: dict[uuid.UUID, Any] = {}
    for q in qs:
        raw = app.answers.get(q.key)
        try:
            value = coerce_answer(q.answer_type, q.choices, raw)
        except ValueError as exc:
            errors[f"q_{q.key}"] = str(exc)
            continue
        if value is None and q.required and app.source == "apply_page":
            errors[f"q_{q.key}"] = "this question is required"
            continue
        if value is not None:
            values[q.id] = value

    # 4. CV
    try:
        cv = check_cv(app.cv_bytes, app.cv_filename, cv_max_bytes)
    except CVRejected as exc:
        errors["cv"] = str(exc)

    if errors:
        log.info("intake refused for job %s: %s", app.job_id, sorted(errors))
        raise IntakeRefused(errors)

    # 5. duplicate
    email_n = normalise_email(app.email)
    async with sessions() as s:
        existing = (
            await s.execute(
                select(Candidate.id).where(
                    Candidate.job_id == app.job_id,
                    Candidate.email_normalised == email_n,
                    Candidate.erased_at.is_(None),
                )
            )
        ).scalar_one_or_none()
    if existing is not None:
        log.info("intake duplicate for job %s -> candidate %s", app.job_id, existing)
        return IntakeResult("duplicate", existing)

    # 6. store the CV (encrypted at rest by the storage backend)
    cid = uuid.uuid4()
    key = new_cv_key(cid)
    try:
        await storage.put(key, cv.data, cv.media_type)
    except StorageError as exc:
        log.warning("intake storage failure for job %s: %s", app.job_id, exc)
        raise IntakeRefused(
            {"cv": "we could not save your CV just now, please try again later"}, status=503
        ) from exc

    # 7. candidate + answers + audit in one transaction
    now = datetime.now(UTC)
    try:
        async with sessions() as s, s.begin():
            count = (
                await s.execute(
                    select(func.count())
                    .select_from(Candidate)
                    .where(Candidate.job_id == app.job_id)
                )
            ).scalar_one()
            cand = Candidate(
                id=cid,
                state=CandidateState.APPLIED,
                state_version=1,
                display_label=f"Applicant {int(count) + 1}",
                job_id=app.job_id,
                source=app.source,
                full_name=name,
                email=app.email.strip(),
                email_normalised=email_n,
                phone=phone,
                consent_at=now,
                consent_notice_version=NOTICE_VERSION if app.source == "apply_page" else None,
                consent_basis="candidate" if app.source == "apply_page" else "recruiter_attested",
                cv_object_key=key,
                cv_original_name=cv.original_name,
                cv_media_type=cv.media_type,
                cv_size_bytes=len(cv.data),
                cv_sha256=hashlib.sha256(cv.data).hexdigest(),
            )
            s.add(cand)
            await s.flush()
            for qid, value in values.items():
                s.add(Answer(candidate_id=cid, question_id=qid, value=value))
            actor = (
                app.attested_by if app.source == "bulk_upload" and app.attested_by else "applicant"
            )
            reason = (
                "applied via the apply page"
                if app.source == "apply_page"
                else "bulk upload by recruiter "
                f"(consent attested, platform: {app.original_platform})"
            )
            add_created_audit(
                s,
                cand,
                actor_type=ActorType.RECRUITER
                if app.source == "bulk_upload"
                else ActorType.CANDIDATE,
                actor_id=actor,
                reason=reason,
            )
    except IntegrityError:
        await delete_with_retry(storage, key)
        async with sessions() as s:
            existing = (
                await s.execute(
                    select(Candidate.id).where(
                        Candidate.job_id == app.job_id,
                        Candidate.email_normalised == email_n,
                        Candidate.erased_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if existing is not None:
            return IntakeResult("duplicate", existing)
        raise
    except Exception:
        await delete_with_retry(storage, key)  # no orphan CV
        raise

    # 8. start the pipeline
    await pipeline.schedule(Snapshot.of(cand))
    log.info("intake created candidate %s for job %s via %s", cid, app.job_id, app.source)
    return IntakeResult("created", cid)
