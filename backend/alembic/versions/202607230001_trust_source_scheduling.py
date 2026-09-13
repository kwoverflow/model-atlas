"""Add scheduled trust-source synchronization policy and lineage.

Revision ID: 202607230001
Revises: 202607220001
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607230001"
down_revision: str | None = "202607220001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_trust_source_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trust_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("jitter_seconds", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_base_seconds", sa.Integer(), nullable=False),
        sa.Column("retry_max_seconds", sa.Integer(), nullable=False),
        sa.Column("retry_jitter_seconds", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_sync_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_token_hash", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("configured_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
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
            "interval_seconds >= 60 AND interval_seconds <= 604800",
            name="ck_evidence_trust_source_schedules_interval",
        ),
        sa.CheckConstraint(
            "jitter_seconds >= 0 AND jitter_seconds < interval_seconds",
            name="ck_evidence_trust_source_schedules_jitter",
        ),
        sa.CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 10",
            name="ck_evidence_trust_source_schedules_attempts",
        ),
        sa.CheckConstraint(
            "retry_base_seconds >= 1 AND retry_base_seconds <= retry_max_seconds "
            "AND retry_max_seconds <= 3600 AND retry_jitter_seconds >= 0 "
            "AND retry_jitter_seconds <= retry_max_seconds",
            name="ck_evidence_trust_source_schedules_retry",
        ),
        sa.CheckConstraint(
            "run_sequence >= 0 AND consecutive_failures >= 0",
            name="ck_evidence_trust_source_schedules_counts",
        ),
        sa.CheckConstraint(
            "(lease_token_hash IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL) "
            "OR (lease_token_hash IS NOT NULL AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_evidence_trust_source_schedules_lease",
        ),
        sa.ForeignKeyConstraint(
            ["trust_source_id"], ["evidence_trust_sources.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["last_job_id"], ["agent_execution_jobs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lease_token_hash"),
        sa.UniqueConstraint("trust_source_id"),
    )
    for name, column in (
        ("ix_evidence_trust_source_schedules_source", "trust_source_id"),
        ("ix_evidence_trust_source_schedules_enabled", "enabled"),
        ("ix_evidence_trust_source_schedules_next_run", "next_run_at"),
        ("ix_evidence_trust_source_schedules_last_enqueued", "last_enqueued_at"),
        ("ix_evidence_trust_source_schedules_last_completed", "last_completed_at"),
        ("ix_evidence_trust_source_schedules_last_job", "last_job_id"),
        ("ix_evidence_trust_source_schedules_last_sync", "last_sync_id"),
        ("ix_evidence_trust_source_schedules_lease_owner", "lease_owner"),
        ("ix_evidence_trust_source_schedules_lease_expires", "lease_expires_at"),
        ("ix_evidence_trust_source_schedules_policy_hash", "policy_hash"),
        ("ix_evidence_trust_source_schedules_identity", "identity_verified"),
    ):
        op.create_index(name, "evidence_trust_source_schedules", [column])

    op.add_column(
        "evidence_trust_source_syncs",
        sa.Column("trigger", sa.String(length=20), nullable=False, server_default="manual"),
    )
    op.add_column(
        "evidence_trust_source_syncs",
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence_trust_source_syncs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence_trust_source_syncs",
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "evidence_trust_source_syncs",
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_evidence_trust_source_syncs_schedule",
        "evidence_trust_source_syncs",
        "evidence_trust_source_schedules",
        ["schedule_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_trust_source_syncs_job",
        "evidence_trust_source_syncs",
        "agent_execution_jobs",
        ["job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_evidence_trust_source_syncs_trigger",
        "evidence_trust_source_syncs",
        "trigger IN ('manual', 'scheduled')",
    )
    op.drop_constraint(
        "ck_evidence_trust_source_syncs_counts",
        "evidence_trust_source_syncs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_trust_source_syncs_counts",
        "evidence_trust_source_syncs",
        "key_count >= 0 AND candidate_count >= 0 AND imported_count >= 0 "
        "AND unchanged_count >= 0 AND rejected_count >= 0 AND attempt_number > 0",
    )
    for name, column in (
        ("ix_evidence_trust_source_syncs_trigger", "trigger"),
        ("ix_evidence_trust_source_syncs_schedule", "schedule_id"),
        ("ix_evidence_trust_source_syncs_job", "job_id"),
        ("ix_evidence_trust_source_syncs_scheduled_for", "scheduled_for"),
    ):
        op.create_index(name, "evidence_trust_source_syncs", [column])

    op.drop_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
        "'traffic_evidence_import', 'model_validation_campaign', 'trust_source_sync')",
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
        "'traffic_evidence_import', 'model_validation_campaign')",
    )

    for name in (
        "ix_evidence_trust_source_syncs_scheduled_for",
        "ix_evidence_trust_source_syncs_job",
        "ix_evidence_trust_source_syncs_schedule",
        "ix_evidence_trust_source_syncs_trigger",
    ):
        op.drop_index(name, table_name="evidence_trust_source_syncs")
    op.drop_constraint(
        "ck_evidence_trust_source_syncs_counts",
        "evidence_trust_source_syncs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_evidence_trust_source_syncs_counts",
        "evidence_trust_source_syncs",
        "key_count >= 0 AND candidate_count >= 0 AND imported_count >= 0 "
        "AND unchanged_count >= 0 AND rejected_count >= 0",
    )
    op.drop_constraint(
        "ck_evidence_trust_source_syncs_trigger",
        "evidence_trust_source_syncs",
        type_="check",
    )
    op.drop_constraint(
        "fk_evidence_trust_source_syncs_job",
        "evidence_trust_source_syncs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_evidence_trust_source_syncs_schedule",
        "evidence_trust_source_syncs",
        type_="foreignkey",
    )
    for column in ("scheduled_for", "attempt_number", "job_id", "schedule_id", "trigger"):
        op.drop_column("evidence_trust_source_syncs", column)
    op.drop_table("evidence_trust_source_schedules")
