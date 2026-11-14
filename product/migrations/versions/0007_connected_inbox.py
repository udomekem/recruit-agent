"""connected inbox: mailboxes, messages, attachments, job matches; job codes; outbox kind

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("code", sa.String(length=20), nullable=True))
    op.create_unique_constraint("uq_jobs_code", "jobs", ["code"])
    # Backfill: initials of the title plus a number, e.g. DA-0042.
    op.execute(
        """
        WITH numbered AS (
            SELECT id, title, row_number() OVER (ORDER BY created_at, id) AS n FROM jobs
        )
        UPDATE jobs SET code = (
            SELECT upper(coalesce(
                nullif(left(regexp_replace(initcap(numbered.title), '[^A-Z]', '', 'g'), 2), ''),
                'JB'))
                || '-' || lpad(numbered.n::text, 4, '0')
            FROM numbered WHERE numbered.id = jobs.id
        )
        """
    )

    op.add_column(
        "outbound_emails",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="rejection"),
    )
    op.alter_column("outbound_emails", "draft_id", nullable=True)

    op.create_table(
        "mailboxes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(length=10), nullable=False),
        sa.Column("address", sa.String(length=320), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("checkpoint", sa.String(length=200), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("connected_by", sa.String(length=120), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "mailbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mailbox_id", sa.Uuid(), sa.ForeignKey("mailboxes.id"), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_mailbox_events_mailbox_id", "mailbox_events", ["mailbox_id"])
    op.create_table(
        "oauth_states",
        sa.Column("state", sa.String(length=64), primary_key=True),
        sa.Column("provider", sa.String(length=10), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "inbox_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("mailbox_id", sa.Uuid(), sa.ForeignKey("mailboxes.id"), nullable=False),
        sa.Column("provider_message_id", sa.String(length=200), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subject_redacted", sa.String(length=300), nullable=False),
        sa.Column("sender_kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("match_route", sa.String(length=20), nullable=True),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("mailbox_id", "provider_message_id", name="uq_inbox_message"),
    )
    op.create_index("ix_inbox_messages_mailbox_id", "inbox_messages", ["mailbox_id"])
    op.create_table(
        "inbox_attachments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("inbox_messages.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=True),
        sa.UniqueConstraint("message_id", "position", name="uq_inbox_attachment"),
    )
    op.create_index("ix_inbox_attachments_message_id", "inbox_attachments", ["message_id"])
    op.create_index("ix_inbox_attachments_candidate_id", "inbox_attachments", ["candidate_id"])
    op.create_table(
        "job_matches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("candidate_id", sa.Uuid(), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("fits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("chosen_job_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("prompt_id", sa.String(length=60), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column("model", sa.String(length=60), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_matches_candidate_id", "job_matches", ["candidate_id"])


def downgrade() -> None:
    op.drop_table("job_matches")
    op.drop_table("inbox_attachments")
    op.drop_table("inbox_messages")
    op.drop_table("oauth_states")
    op.drop_table("mailbox_events")
    op.drop_table("mailboxes")
    op.alter_column("outbound_emails", "draft_id", nullable=False)
    op.drop_column("outbound_emails", "kind")
    op.drop_constraint("uq_jobs_code", "jobs", type_="unique")
    op.drop_column("jobs", "code")
