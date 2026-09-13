"""benchmark execution logs

Revision ID: 202607060002
Revises: 202607060001
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607060002"
down_revision: str | None = "202607060001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "benchmark_execution_logs",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("benchmark_run_id", uuid_type, nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("level", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "level IN ('debug', 'info', 'warning', 'error')",
            name="ck_benchmark_execution_logs_level",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_run_id"],
            ["benchmark_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_benchmark_execution_logs_benchmark_run_id"),
        "benchmark_execution_logs",
        ["benchmark_run_id"],
    )
    op.create_index(
        op.f("ix_benchmark_execution_logs_event_type"),
        "benchmark_execution_logs",
        ["event_type"],
    )
    op.create_index(
        op.f("ix_benchmark_execution_logs_level"),
        "benchmark_execution_logs",
        ["level"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_benchmark_execution_logs_level"), table_name="benchmark_execution_logs")
    op.drop_index(
        op.f("ix_benchmark_execution_logs_event_type"),
        table_name="benchmark_execution_logs",
    )
    op.drop_index(
        op.f("ix_benchmark_execution_logs_benchmark_run_id"),
        table_name="benchmark_execution_logs",
    )
    op.drop_table("benchmark_execution_logs")
