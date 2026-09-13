"""Add durable operational SLO and paging delivery state.

Revision ID: 202607270002
Revises: 202607270001
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607270002"
down_revision: str | None = "202607270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_metric_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bucket_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("health", sa.String(length=20), nullable=False),
        sa.Column("schema_version", sa.String(length=100), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("alert_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("collected_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "health IN ('healthy', 'degraded', 'critical')",
            name="ck_operational_metric_snapshots_health",
        ),
        sa.CheckConstraint(
            "sample_count >= 0 AND alert_count >= 0",
            name="ck_operational_metric_snapshots_counts",
        ),
        sa.CheckConstraint(
            "expires_at > generated_at",
            name="ck_operational_metric_snapshots_expiry",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket_started_at"),
        sa.UniqueConstraint("content_hash"),
    )
    for name, column in (
        ("ix_operational_metric_snapshots_bucket_started_at", "bucket_started_at"),
        ("ix_operational_metric_snapshots_generated_at", "generated_at"),
        ("ix_operational_metric_snapshots_expires_at", "expires_at"),
        ("ix_operational_metric_snapshots_health", "health"),
        ("ix_operational_metric_snapshots_content_hash", "content_hash"),
    ):
        op.create_index(name, "operational_metric_snapshots", [column])

    op.create_table(
        "operational_metric_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.String(length=180), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("labels_json", sa.JSON(), nullable=False),
        sa.Column("labels_hash", sa.String(length=64), nullable=False),
        sa.Column("help_text", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["operational_metric_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "snapshot_id",
            "metric_name",
            "labels_hash",
            name="uq_operational_metric_points_snapshot_metric_labels",
        ),
    )
    for name, column in (
        ("ix_operational_metric_points_snapshot_id", "snapshot_id"),
        ("ix_operational_metric_points_metric_name", "metric_name"),
        ("ix_operational_metric_points_recorded_at", "recorded_at"),
    ):
        op.create_index(name, "operational_metric_points", [column])

    op.create_table(
        "operational_slo_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slo_key", sa.String(length=120), nullable=False),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("target_ratio", sa.Float(), nullable=False),
        sa.Column("observed_ratio", sa.Float(), nullable=True),
        sa.Column("error_budget_remaining_ratio", sa.Float(), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("good_sample_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("evaluation_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope IN ('identity', 'worker')",
            name="ck_operational_slo_evaluations_scope",
        ),
        sa.CheckConstraint(
            "status IN ('met', 'breached', 'insufficient')",
            name="ck_operational_slo_evaluations_status",
        ),
        sa.CheckConstraint(
            "target_ratio >= 0 AND target_ratio <= 1 "
            "AND (observed_ratio IS NULL OR "
            "(observed_ratio >= 0 AND observed_ratio <= 1)) "
            "AND (error_budget_remaining_ratio IS NULL OR "
            "(error_budget_remaining_ratio >= 0 "
            "AND error_budget_remaining_ratio <= 1))",
            name="ck_operational_slo_evaluations_ratios",
        ),
        sa.CheckConstraint(
            "window_seconds > 0 AND sample_count >= 0 "
            "AND good_sample_count >= 0 AND good_sample_count <= sample_count",
            name="ck_operational_slo_evaluations_counts",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["operational_metric_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("evaluation_hash"),
        sa.UniqueConstraint(
            "snapshot_id",
            "slo_key",
            name="uq_operational_slo_evaluations_snapshot_key",
        ),
    )
    for name, column in (
        ("ix_operational_slo_evaluations_snapshot_id", "snapshot_id"),
        ("ix_operational_slo_evaluations_slo_key", "slo_key"),
        ("ix_operational_slo_evaluations_scope", "scope"),
        ("ix_operational_slo_evaluations_status", "status"),
        ("ix_operational_slo_evaluations_evaluated_at", "evaluated_at"),
        ("ix_operational_slo_evaluations_evaluation_hash", "evaluation_hash"),
    ):
        op.create_index(name, "operational_slo_evaluations", [column])

    op.create_table(
        "operational_alert_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_key", sa.String(length=180), nullable=True),
        sa.Column("alert_key", sa.String(length=180), nullable=False),
        sa.Column("source_type", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("route", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("metric_name", sa.String(length=180), nullable=True),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column(
            "slo_evaluation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("transition_version", sa.Integer(), nullable=False),
        sa.Column("latest_context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('derived_alert', 'slo', 'test')",
            name="ck_operational_alert_incidents_source",
        ),
        sa.CheckConstraint(
            "severity IN ('warning', 'critical')",
            name="ck_operational_alert_incidents_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved')",
            name="ck_operational_alert_incidents_status",
        ),
        sa.CheckConstraint(
            "occurrence_count > 0 AND transition_version > 0",
            name="ck_operational_alert_incidents_counts",
        ),
        sa.CheckConstraint(
            "(status = 'open' AND active_key IS NOT NULL "
            "AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND active_key IS NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_operational_alert_incidents_lifecycle",
        ),
        sa.ForeignKeyConstraint(
            ["slo_evaluation_id"],
            ["operational_slo_evaluations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("active_key"),
    )
    for name, column in (
        ("ix_operational_alert_incidents_active_key", "active_key"),
        ("ix_operational_alert_incidents_alert_key", "alert_key"),
        ("ix_operational_alert_incidents_source_type", "source_type"),
        ("ix_operational_alert_incidents_severity", "severity"),
        ("ix_operational_alert_incidents_metric_name", "metric_name"),
        ("ix_operational_alert_incidents_slo_evaluation_id", "slo_evaluation_id"),
        ("ix_operational_alert_incidents_status", "status"),
        ("ix_operational_alert_incidents_opened_at", "opened_at"),
        ("ix_operational_alert_incidents_last_seen_at", "last_seen_at"),
        ("ix_operational_alert_incidents_resolved_at", "resolved_at"),
    ):
        op.create_index(name, "operational_alert_incidents", [column])

    op.create_table(
        "operational_alert_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "delivery_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("transition_type", sa.String(length=20), nullable=False),
        sa.Column("transition_version", sa.Integer(), nullable=False),
        sa.Column("destination_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "transition_type IN ('opened', 'resolved', 'test')",
            name="ck_operational_alert_deliveries_transition",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'delivered', 'failed')",
            name="ck_operational_alert_deliveries_status",
        ),
        sa.CheckConstraint(
            "transition_version > 0 AND attempt_count >= 0",
            name="ck_operational_alert_deliveries_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["delivery_job_id"],
            ["agent_execution_jobs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["operational_alert_incidents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("delivery_job_id"),
        sa.UniqueConstraint("payload_hash"),
        sa.UniqueConstraint(
            "incident_id",
            "transition_type",
            "transition_version",
            name="uq_operational_alert_deliveries_transition",
        ),
    )
    for name, column in (
        ("ix_operational_alert_deliveries_incident_id", "incident_id"),
        ("ix_operational_alert_deliveries_delivery_job_id", "delivery_job_id"),
        ("ix_operational_alert_deliveries_transition_type", "transition_type"),
        ("ix_operational_alert_deliveries_status", "status"),
        ("ix_operational_alert_deliveries_payload_hash", "payload_hash"),
        ("ix_operational_alert_deliveries_requested_at", "requested_at"),
        ("ix_operational_alert_deliveries_last_attempt_at", "last_attempt_at"),
        ("ix_operational_alert_deliveries_delivered_at", "delivered_at"),
    ):
        op.create_index(name, "operational_alert_deliveries", [column])

    op.drop_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
        "'traffic_evidence_import', 'model_validation_campaign', "
        "'trust_source_sync', 'oidc_session_cleanup', "
        "'operational_observability_cycle', 'operational_alert_delivery')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
        "'traffic_evidence_import', 'model_validation_campaign', "
        "'trust_source_sync', 'oidc_session_cleanup')",
    )
    op.drop_table("operational_alert_deliveries")
    op.drop_table("operational_alert_incidents")
    op.drop_table("operational_slo_evaluations")
    op.drop_table("operational_metric_points")
    op.drop_table("operational_metric_snapshots")
