"""scores

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_id", sa.Uuid(), nullable=False),
        sa.Column("rubric_version", sa.Integer(), nullable=False),
        sa.Column("cv_parse_id", sa.Uuid(), nullable=True),
        sa.Column("judgements", JSON, nullable=False),
        sa.Column("answer_results", JSON, nullable=False),
        sa.Column("total", sa.Double(), nullable=False),
        sa.Column("band", sa.String(length=10), nullable=False),
        sa.Column("reasons", JSON, nullable=False),
        sa.Column("flags", JSON, nullable=False),
        sa.Column("injection_suspected", sa.Boolean(), nullable=False),
        sa.Column("prompt_id", sa.String(length=60), nullable=False),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("cost_usd", sa.Double(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("erased", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"], ["candidates.id"], name="scores_candidate_id_fkey"
        ),
        sa.ForeignKeyConstraint(["rubric_id"], ["rubrics.id"], name="scores_rubric_id_fkey"),
        sa.ForeignKeyConstraint(
            ["cv_parse_id"], ["cv_parses.id"], name="scores_cv_parse_id_fkey", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "rubric_id", name="uq_score_rubric"),
    )
    op.create_index("ix_scores_candidate_id", "scores", ["candidate_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scores_candidate_id", table_name="scores")
    op.drop_table("scores")
