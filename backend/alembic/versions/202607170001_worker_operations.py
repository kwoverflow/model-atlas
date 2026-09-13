"""Add Agent worker operations and dead-letter metadata.

Revision ID: 202607170001
Revises: 202607130002
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607170001"
down_revision: str | None = "202607130002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_agent_execution_jobs_attempts",
        "agent_execution_jobs",
        type_="check",
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column(
            "heartbeat_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column("dead_lettered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column("dead_letter_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column(
            "requeue_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column("last_requeued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_execution_jobs",
        sa.Column("last_requeued_by_identity_json", sa.JSON(), nullable=True),
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_attempts",
        "agent_execution_jobs",
        "attempt_count >= 0 AND max_attempts > 0 AND heartbeat_count >= 0 "
        "AND requeue_count >= 0",
    )
    op.create_index(
        "ix_agent_execution_jobs_last_heartbeat_at",
        "agent_execution_jobs",
        ["last_heartbeat_at"],
    )
    op.create_index(
        "ix_agent_execution_jobs_dead_lettered_at",
        "agent_execution_jobs",
        ["dead_lettered_at"],
    )

    op.create_table(
        "agent_worker_states",
        sa.Column("worker_id", sa.String(length=160), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            nullable=False,
            server_default="online",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("current_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "processed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "failed_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
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
            "status IN ('online', 'stopped')",
            name="ck_agent_worker_states_status",
        ),
        sa.CheckConstraint(
            "processed_count >= 0 AND completed_count >= 0 AND failed_count >= 0",
            name="ck_agent_worker_states_counts",
        ),
        sa.ForeignKeyConstraint(
            ["current_job_id"],
            ["agent_execution_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    for column in ("status", "last_seen_at", "current_job_id"):
        op.create_index(
            f"ix_agent_worker_states_{column}",
            "agent_worker_states",
            [column],
        )


def downgrade() -> None:
    op.drop_table("agent_worker_states")
    op.drop_index(
        "ix_agent_execution_jobs_dead_lettered_at",
        table_name="agent_execution_jobs",
    )
    op.drop_index(
        "ix_agent_execution_jobs_last_heartbeat_at",
        table_name="agent_execution_jobs",
    )
    op.drop_constraint(
        "ck_agent_execution_jobs_attempts",
        "agent_execution_jobs",
        type_="check",
    )
    for column in (
        "last_requeued_by_identity_json",
        "last_requeued_at",
        "requeue_count",
        "dead_letter_reason",
        "dead_lettered_at",
        "heartbeat_count",
        "last_heartbeat_at",
    ):
        op.drop_column("agent_execution_jobs", column)
    op.create_check_constraint(
        "ck_agent_execution_jobs_attempts",
        "agent_execution_jobs",
        "attempt_count >= 0 AND max_attempts > 0",
    )
