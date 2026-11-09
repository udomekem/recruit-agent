"""Tables.

Phase 0: candidates and the append-only candidate audit log.
Phase 1: jobs, job audit log, screening questions, rubric versions, answers, and the
candidate's intake fields (contact details, consent, CV reference, erasure).

States are stored as text and validated in the application (adding a state later does
not need an enum migration). CV files live in object storage, never in the database.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_return_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    work_arrangement: Mapped[str] = mapped_column(String(16), nullable=False)
    salary_min: Mapped[int] = mapped_column(Integer, nullable=False)
    salary_max: Mapped[int] = mapped_column(Integer, nullable=False)
    approved_rubric_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobAuditEvent(Base):
    __tablename__ = "job_audit_events"
    __table_args__ = (
        UniqueConstraint("job_id", "idempotency_key", name="uq_job_audit_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    transition_id: Mapped[str] = mapped_column(String(8), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class ScreeningQuestion(Base):
    __tablename__ = "screening_questions"
    __table_args__ = (UniqueConstraint("job_id", "key", name="uq_question_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(16), nullable=False)
    choices: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    standard: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    knockout_rule: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Rubric(Base):
    """Immutable: every edit is a new row with the next version number."""

    __tablename__ = "rubrics"
    __table_args__ = (UniqueConstraint("job_id", "version", name="uq_rubric_version"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # ai | recruiter
    criteria: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    prompt_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Candidate(Base):
    __tablename__ = "candidates"
    __table_args__ = (
        # one live application per job per email (erased rows release the email)
        Index(
            "uq_candidate_job_email",
            "job_id",
            "email_normalised",
            unique=True,
            postgresql_where=text("erased_at IS NULL AND email_normalised IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_return_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    screen_call_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    display_label: Mapped[str] = mapped_column(String(120), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id"), nullable=True, index=True
    )
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalised: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_notice_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    consent_basis: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cv_object_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cv_original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cv_media_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cv_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cv_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    erased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=utcnow
    )


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("candidate_id", "question_id", name="uq_answer"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("screening_questions.id"), nullable=False
    )
    value: Mapped[Any] = mapped_column(JSONB, nullable=True)


class CvParse(Base):
    """Phase 2. Holds only the redacted copy and the structured profile; the raw extracted
    text is never stored (it can be rebuilt from the encrypted CV). Erasure deletes rows."""

    __tablename__ = "cv_parses"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # parsed | no_text_layer | failed
    text_layer: Mapped[bool] = mapped_column(Boolean, nullable=False)
    redacted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    redaction_counts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    prompt_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Score(Base):
    """Phase 3. One row per candidate per rubric version (rule 11: versions stored).
    Total and band are computed by code; the model only judges each criterion.
    Erasure clears judgements, reasons and answer values; numbers and versions stay."""

    __tablename__ = "scores"
    __table_args__ = (UniqueConstraint("candidate_id", "rubric_id", name="uq_score_rubric"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id"), nullable=False)
    rubric_version: Mapped[int] = mapped_column(Integer, nullable=False)
    cv_parse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_parses.id", ondelete="SET NULL"), nullable=True
    )  # the parse is deleted on erasure
    judgements: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    answer_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    total: Mapped[float] = mapped_column(nullable=False)
    band: Mapped[str] = mapped_column(String(10), nullable=False)  # advance | maybe | reject
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    injection_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    prompt_id: Mapped[str] = mapped_column(String(60), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(nullable=True)
    attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    erased: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class Decision(Base):
    """Phase 4. A recruiter shortlist or reject, with the recommendation it was made
    against, for the agreement rate. Written in the same transaction as the move.
    Erasure clears the reason (a recruiter may have typed personal details)."""

    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    score_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scores.id"), nullable=True)
    recommended: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # advance|maybe|reject|none
    decision: Mapped[str] = mapped_column(String(10), nullable=False)  # shortlist | reject
    override: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AccessEvent(Base):
    """Phase 4. Who read a candidate's contact details, and when (Privacy Act). Holds no
    personal data itself, so erasure keeps it."""

    __tablename__ = "access_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    what: Mapped[str] = mapped_column(String(20), nullable=False)  # contact
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        UniqueConstraint("candidate_id", "idempotency_key", name="uq_audit_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id"), nullable=False, index=True
    )
    transition_id: Mapped[str] = mapped_column(String(8), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
