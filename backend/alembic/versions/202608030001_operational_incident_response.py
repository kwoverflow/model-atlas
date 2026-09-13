"""Add multi-window SLO and operational incident response state.

Revision ID: 202608030001
Revises: 202607270002
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202608030001"
down_revision: str | None = "202607270002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "operational_slo_evaluations",
        sa.Column(
            "short_window_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("300"),
        ),
    )
    op.add_column(
        "operational_slo_evaluations",
        sa.Column("short_observed_ratio", sa.Float(), nullable=True),
    )
    op.add_column(
        "operational_slo_evaluations",
        sa.Column("burn_rate", sa.Float(), nullable=True),
    )
    op.add_column(
        "operational_slo_evaluations",
        sa.Column("short_burn_rate", sa.Float(), nullable=True),
    )
    op.add_column(
        "operational_slo_evaluations",
        sa.Column(
            "burn_alert_level",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )
    op.drop_constraint(
        "ck_operational_slo_evaluations_ratios",
        "operational_slo_evaluations",
        type_="check",
    )
    op.drop_constraint(
        "ck_operational_slo_evaluations_counts",
        "operational_slo_evaluations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_slo_evaluations_burn_alert_level",
        "operational_slo_evaluations",
        "burn_alert_level IN ('none', 'warning', 'critical')",
    )
    op.create_check_constraint(
        "ck_operational_slo_evaluations_ratios",
        "operational_slo_evaluations",
        "target_ratio >= 0 AND target_ratio <= 1 "
        "AND (observed_ratio IS NULL OR "
        "(observed_ratio >= 0 AND observed_ratio <= 1)) "
        "AND (short_observed_ratio IS NULL OR "
        "(short_observed_ratio >= 0 AND short_observed_ratio <= 1)) "
        "AND (error_budget_remaining_ratio IS NULL OR "
        "(error_budget_remaining_ratio >= 0 "
        "AND error_budget_remaining_ratio <= 1)) "
        "AND (burn_rate IS NULL OR burn_rate >= 0) "
        "AND (short_burn_rate IS NULL OR short_burn_rate >= 0)",
    )
    op.create_check_constraint(
        "ck_operational_slo_evaluations_counts",
        "operational_slo_evaluations",
        "window_seconds > 0 AND short_window_seconds > 0 "
        "AND short_window_seconds <= window_seconds AND sample_count >= 0 "
        "AND good_sample_count >= 0 AND good_sample_count <= sample_count",
    )
    op.create_index(
        "ix_operational_slo_evaluations_burn_alert_level",
        "operational_slo_evaluations",
        ["burn_alert_level"],
    )
    op.alter_column(
        "operational_slo_evaluations",
        "short_window_seconds",
        server_default=None,
    )
    op.alter_column(
        "operational_slo_evaluations",
        "burn_alert_level",
        server_default=None,
    )

    op.add_column(
        "operational_alert_incidents",
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "operational_alert_incidents",
        sa.Column("acknowledged_by_identity_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "operational_alert_incidents",
        sa.Column("assigned_to", sa.String(length=160), nullable=True),
    )
    op.add_column(
        "operational_alert_incidents",
        sa.Column(
            "escalation_level",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.drop_constraint(
        "ck_operational_alert_incidents_counts",
        "operational_alert_incidents",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_alert_incidents_counts",
        "operational_alert_incidents",
        "occurrence_count > 0 AND transition_version > 0 "
        "AND escalation_level >= 0 AND escalation_level <= 3",
    )
    for name, column in (
        ("ix_operational_alert_incidents_acknowledged_at", "acknowledged_at"),
        ("ix_operational_alert_incidents_assigned_to", "assigned_to"),
    ):
        op.create_index(name, "operational_alert_incidents", [column])
    op.alter_column(
        "operational_alert_incidents",
        "escalation_level",
        server_default=None,
    )

    op.create_table(
        "operational_alert_incident_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("assignee", sa.String(length=160), nullable=True),
        sa.Column("actor_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_action_hash", sa.String(length=64), nullable=True),
        sa.Column("action_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_type IN ('acknowledged', 'assigned', 'note', 'escalated')",
            name="ck_operational_alert_incident_actions_type",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["operational_alert_incidents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("action_hash"),
    )
    for name, column in (
        ("ix_operational_alert_incident_actions_incident_id", "incident_id"),
        ("ix_operational_alert_incident_actions_action_type", "action_type"),
        ("ix_operational_alert_incident_actions_occurred_at", "occurred_at"),
        ("ix_operational_alert_incident_actions_action_hash", "action_hash"),
    ):
        op.create_index(name, "operational_alert_incident_actions", [column])

    op.add_column(
        "operational_alert_deliveries",
        sa.Column(
            "signing_key_id",
            sa.String(length=120),
            nullable=False,
            server_default=sa.text("'legacy'"),
        ),
    )
    op.drop_constraint(
        "ck_operational_alert_deliveries_transition",
        "operational_alert_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_alert_deliveries_transition",
        "operational_alert_deliveries",
        "transition_type IN ('opened', 'resolved', 'test', 'escalated')",
    )
    op.alter_column(
        "operational_alert_deliveries",
        "signing_key_id",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_operational_alert_deliveries_transition",
        "operational_alert_deliveries",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_alert_deliveries_transition",
        "operational_alert_deliveries",
        "transition_type IN ('opened', 'resolved', 'test')",
    )
    op.drop_column("operational_alert_deliveries", "signing_key_id")

    op.drop_table("operational_alert_incident_actions")
    for name in (
        "ix_operational_alert_incidents_assigned_to",
        "ix_operational_alert_incidents_acknowledged_at",
    ):
        op.drop_index(name, table_name="operational_alert_incidents")
    op.drop_constraint(
        "ck_operational_alert_incidents_counts",
        "operational_alert_incidents",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_alert_incidents_counts",
        "operational_alert_incidents",
        "occurrence_count > 0 AND transition_version > 0",
    )
    for column in (
        "escalation_level",
        "assigned_to",
        "acknowledged_by_identity_json",
        "acknowledged_at",
    ):
        op.drop_column("operational_alert_incidents", column)

    op.drop_index(
        "ix_operational_slo_evaluations_burn_alert_level",
        table_name="operational_slo_evaluations",
    )
    op.drop_constraint(
        "ck_operational_slo_evaluations_burn_alert_level",
        "operational_slo_evaluations",
        type_="check",
    )
    op.drop_constraint(
        "ck_operational_slo_evaluations_ratios",
        "operational_slo_evaluations",
        type_="check",
    )
    op.drop_constraint(
        "ck_operational_slo_evaluations_counts",
        "operational_slo_evaluations",
        type_="check",
    )
    op.create_check_constraint(
        "ck_operational_slo_evaluations_ratios",
        "operational_slo_evaluations",
        "target_ratio >= 0 AND target_ratio <= 1 "
        "AND (observed_ratio IS NULL OR "
        "(observed_ratio >= 0 AND observed_ratio <= 1)) "
        "AND (error_budget_remaining_ratio IS NULL OR "
        "(error_budget_remaining_ratio >= 0 "
        "AND error_budget_remaining_ratio <= 1))",
    )
    op.create_check_constraint(
        "ck_operational_slo_evaluations_counts",
        "operational_slo_evaluations",
        "window_seconds > 0 AND sample_count >= 0 "
        "AND good_sample_count >= 0 AND good_sample_count <= sample_count",
    )
    for column in (
        "burn_alert_level",
        "short_burn_rate",
        "burn_rate",
        "short_observed_ratio",
        "short_window_seconds",
    ):
        op.drop_column("operational_slo_evaluations", column)
