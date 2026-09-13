"""Add signed Agent traffic receipt tracking.

Revision ID: 202607170002
Revises: 202607170001
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607170002"
down_revision: str | None = "202607170001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_traffic_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_system", sa.String(length=160), nullable=False),
        sa.Column("batch_id", sa.String(length=200), nullable=False),
        sa.Column("nonce", sa.String(length=160), nullable=False),
        sa.Column("signature_version", sa.String(length=60), nullable=False),
        sa.Column("signature_hash", sa.String(length=64), nullable=False),
        sa.Column("key_id", sa.String(length=120), nullable=False),
        sa.Column("collector_version", sa.String(length=120), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
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
        sa.Column(
            "replay_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "replay_count >= 0",
            name="ck_agent_traffic_receipts_replay_count",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["agent_execution_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_system",
            "batch_id",
            name="uq_agent_traffic_receipts_source_batch",
        ),
        sa.UniqueConstraint(
            "source_system",
            "nonce",
            name="uq_agent_traffic_receipts_source_nonce",
        ),
    )
    for column in (
        "source_system",
        "batch_id",
        "nonce",
        "key_id",
        "job_id",
    ):
        op.create_index(
            f"ix_agent_traffic_receipts_{column}",
            "agent_traffic_receipts",
            [column],
        )


def downgrade() -> None:
    op.drop_table("agent_traffic_receipts")
