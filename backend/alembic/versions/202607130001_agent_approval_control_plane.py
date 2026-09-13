"""Add persistent agent approval control-plane checkpoints.

Revision ID: 202607130001
Revises: 202607110001
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607130001"
down_revision: str | None = "202607110001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_approval_checkpoints",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "benchmark_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "benchmark_result_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("checkpoint_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requested_by_subject_id", sa.String(length=160), nullable=False),
        sa.Column("requested_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("request_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("approval_policy_json", sa.JSON(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approver_identity_json", sa.JSON(), nullable=True),
        sa.Column(
            "identity_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("decision_hash", sa.String(length=64), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("revoked_by_identity_json", sa.JSON(), nullable=True),
        sa.Column("revocation_hash", sa.String(length=64), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_by_identity_json", sa.JSON(), nullable=True),
        sa.Column("resume_hash", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
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
            "status IN ('pending', 'approved', 'denied', 'revoked', 'expired', 'resumed')",
            name="ck_agent_approval_checkpoints_status",
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('approved', 'denied')",
            name="ck_agent_approval_checkpoints_decision",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_agent_approval_checkpoints_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_result_id"],
            ["benchmark_results.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_run_id"],
            ["benchmark_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "benchmark_result_id",
            "checkpoint_id",
            name="uq_agent_approval_checkpoint_result_key",
        ),
    )
    op.create_index(
        "ix_agent_approval_checkpoints_benchmark_result_id",
        "agent_approval_checkpoints",
        ["benchmark_result_id"],
    )
    op.create_index(
        "ix_agent_approval_checkpoints_benchmark_run_id",
        "agent_approval_checkpoints",
        ["benchmark_run_id"],
    )
    op.create_index(
        "ix_agent_approval_checkpoints_checkpoint_id",
        "agent_approval_checkpoints",
        ["checkpoint_id"],
    )
    op.create_index(
        "ix_agent_approval_checkpoints_expires_at",
        "agent_approval_checkpoints",
        ["expires_at"],
    )
    op.create_index(
        "ix_agent_approval_checkpoints_requested_by_subject_id",
        "agent_approval_checkpoints",
        ["requested_by_subject_id"],
    )
    op.create_index(
        "ix_agent_approval_checkpoints_status",
        "agent_approval_checkpoints",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_approval_checkpoints_status",
        table_name="agent_approval_checkpoints",
    )
    op.drop_index(
        "ix_agent_approval_checkpoints_requested_by_subject_id",
        table_name="agent_approval_checkpoints",
    )
    op.drop_index(
        "ix_agent_approval_checkpoints_expires_at",
        table_name="agent_approval_checkpoints",
    )
    op.drop_index(
        "ix_agent_approval_checkpoints_checkpoint_id",
        table_name="agent_approval_checkpoints",
    )
    op.drop_index(
        "ix_agent_approval_checkpoints_benchmark_run_id",
        table_name="agent_approval_checkpoints",
    )
    op.drop_index(
        "ix_agent_approval_checkpoints_benchmark_result_id",
        table_name="agent_approval_checkpoints",
    )
    op.drop_table("agent_approval_checkpoints")
