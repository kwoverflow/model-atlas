"""Allow p99 metric aggregation for runtime reliability evidence.

Revision ID: 202607110001
Revises: 202607090004
Create Date: 2026-07-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202607110001"
down_revision: str | None = "202607090004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("metric_definitions") as batch_op:
        batch_op.drop_constraint(
            "ck_metric_definitions_aggregation",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_metric_definitions_aggregation",
            "aggregation IN ('mean', 'rate', 'p50', 'p95', 'p99', 'max', 'min', 'count')",
        )


def downgrade() -> None:
    with op.batch_alter_table("metric_definitions") as batch_op:
        batch_op.drop_constraint(
            "ck_metric_definitions_aggregation",
            type_="check",
        )
        batch_op.create_check_constraint(
            "ck_metric_definitions_aggregation",
            "aggregation IN ('mean', 'rate', 'p50', 'p95', 'max', 'min', 'count')",
        )
