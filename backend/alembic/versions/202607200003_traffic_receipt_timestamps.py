"""Align Agent traffic receipt timestamps with the ORM model.

Revision ID: 202607200003
Revises: 202607200002
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607200003"
down_revision: str | None = "202607200002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_traffic_receipts",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column(
        "agent_traffic_receipts",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_traffic_receipts", "updated_at")
    op.drop_column("agent_traffic_receipts", "created_at")
