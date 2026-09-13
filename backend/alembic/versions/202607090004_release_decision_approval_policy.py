"""release decision approval policy

Revision ID: 202607090004
Revises: 202607090003
Create Date: 2026-07-09 00:00:03.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202607090004"
down_revision: str | None = "202607090003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "release_decisions",
        sa.Column(
            "approval_policy_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("release_decisions", "approval_policy_json", server_default=None)


def downgrade() -> None:
    op.drop_column("release_decisions", "approval_policy_json")
