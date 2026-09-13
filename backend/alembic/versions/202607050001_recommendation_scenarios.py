"""recommendation scenarios

Revision ID: 202607050001
Revises: 202607040001
Create Date: 2026-07-05 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607050001"
down_revision: str | None = "202607040001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "recommendation_scenarios",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendation_scenarios_name"),
        "recommendation_scenarios",
        ["name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_recommendation_scenarios_name"),
        table_name="recommendation_scenarios",
    )
    op.drop_table("recommendation_scenarios")
