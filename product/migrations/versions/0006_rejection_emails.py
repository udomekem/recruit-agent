"""rejection drafts and the email outbox

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rejection_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("score_id", sa.Uuid(), nullable=True),
        sa.Column("opening", sa.Text(), nullable=False),
        sa.Column("closing", sa.Text(), nullable=False),
        sa.Column("reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("needs_edit", sa.Boolean(), nullable=False),
        sa.Column("prompt_id", sa.String(length=60), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("erased", sa.Boolean(), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="rejection_drafts_candidate_id_fkey"
        ),
        sa.ForeignKeyConstraint(["score_id"], ["scores.id"], name="rejection_drafts_score_id_fkey"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "version", name="uq_draft_version"),
    )
    op.create_index(
        "ix_rejection_drafts_candidate_id", "rejection_drafts", ["candidate_id"], unique=False
    )
    op.create_table(
        "outbound_emails",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("draft_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("message_id", sa.String(length=250), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("provider", sa.String(length=10), nullable=False),
        sa.Column("provider_message_id", sa.String(length=200), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="outbound_emails_candidate_id_fkey"
        ),
        sa.ForeignKeyConstraint(
            ["draft_id"], ["rejection_drafts.id"], name="outbound_emails_draft_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="outbound_emails_idempotency_key_key"),
        sa.UniqueConstraint("message_id", name="outbound_emails_message_id_key"),
    )
    op.create_index(
        "ix_outbound_emails_candidate_id", "outbound_emails", ["candidate_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_outbound_emails_candidate_id", table_name="outbound_emails")
    op.drop_table("outbound_emails")
    op.drop_index("ix_rejection_drafts_candidate_id", table_name="rejection_drafts")
    op.drop_table("rejection_drafts")
