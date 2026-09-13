"""add staging paging provider receipts

Revision ID: 202608040001
Revises: 202608030001
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "202608040001"
down_revision: str | None = "202608030001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operational_alert_deliveries",
        sa.Column("provider_name", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "operational_alert_deliveries",
        sa.Column("provider_event_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "operational_alert_deliveries",
        sa.Column("provider_receipt_id", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "operational_alert_deliveries",
        sa.Column(
            "provider_accepted_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_operational_alert_deliveries_provider_name",
        "operational_alert_deliveries",
        ["provider_name"],
    )
    op.create_index(
        "ix_operational_alert_deliveries_provider_event_id",
        "operational_alert_deliveries",
        ["provider_event_id"],
    )
    op.create_index(
        "ix_operational_alert_deliveries_provider_receipt_id",
        "operational_alert_deliveries",
        ["provider_receipt_id"],
    )
    op.create_index(
        "ix_operational_alert_deliveries_provider_accepted_at",
        "operational_alert_deliveries",
        ["provider_accepted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_alert_deliveries_provider_accepted_at",
        table_name="operational_alert_deliveries",
    )
    op.drop_index(
        "ix_operational_alert_deliveries_provider_receipt_id",
        table_name="operational_alert_deliveries",
    )
    op.drop_index(
        "ix_operational_alert_deliveries_provider_event_id",
        table_name="operational_alert_deliveries",
    )
    op.drop_index(
        "ix_operational_alert_deliveries_provider_name",
        table_name="operational_alert_deliveries",
    )
    op.drop_column("operational_alert_deliveries", "provider_accepted_at")
    op.drop_column("operational_alert_deliveries", "provider_receipt_id")
    op.drop_column("operational_alert_deliveries", "provider_event_id")
    op.drop_column("operational_alert_deliveries", "provider_name")
