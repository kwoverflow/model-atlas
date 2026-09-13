"""Add append-only reviewed judge label decisions.

Revision ID: 202607200002
Revises: 202607200001
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607200002"
down_revision: str | None = "202607200001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "judge_label_review_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_case_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decision_type", sa.String(length=40), nullable=False),
        sa.Column("candidate_label_hash", sa.String(length=64), nullable=True),
        sa.Column("prior_scores_json", sa.JSON(), nullable=False),
        sa.Column("applied_scores_json", sa.JSON(), nullable=True),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("reviewer_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("criticality", sa.String(length=40), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "decision_type IN ('approved_candidate', 'overridden', 'rejected')",
            name="ck_judge_label_review_decisions_type",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_result_id"],
            ["benchmark_results.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_case_id"],
            ["evaluation_cases.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "review_hash",
            name="uq_judge_label_review_decisions_review_hash",
        ),
    )
    for column in (
        "benchmark_result_id",
        "evaluation_case_id",
        "decision_type",
        "candidate_label_hash",
        "applied",
        "identity_verified",
        "criticality",
        "reviewed_at",
        "review_hash",
    ):
        op.create_index(
            f"ix_judge_label_review_decisions_{column}",
            "judge_label_review_decisions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("judge_label_review_decisions")
