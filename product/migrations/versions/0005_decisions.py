"""decisions and access events

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("score_id", sa.Uuid(), nullable=True),
        sa.Column("recommended", sa.String(length=10), nullable=False),
        sa.Column("decision", sa.String(length=10), nullable=False),
        sa.Column("override", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="decisions_candidate_id_fkey"
        ),
        sa.ForeignKeyConstraint(["score_id"], ["scores.id"], name="decisions_score_id_fkey"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_candidate_id", "decisions", ["candidate_id"], unique=False)
    op.create_table(
        "access_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("what", sa.String(length=20), nullable=False),
        sa.Column("actor_id", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="access_events_candidate_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_access_events_candidate_id", "access_events", ["candidate_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_access_events_candidate_id", table_name="access_events")
    op.drop_table("access_events")
    op.drop_index("ix_decisions_candidate_id", table_name="decisions")
    op.drop_table("decisions")
