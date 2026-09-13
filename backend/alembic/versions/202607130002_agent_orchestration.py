"""Add append-only agent revisions, gate staleness, and durable jobs.

Revision ID: 202607130002
Revises: 202607130001
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607130002"
down_revision: str | None = "202607130001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "benchmark_runs",
        sa.Column("parent_benchmark_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "benchmark_runs",
        sa.Column("root_benchmark_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "benchmark_runs",
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "benchmark_runs",
        sa.Column("revision_reason", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "benchmark_runs",
        sa.Column("evidence_revision_hash", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_benchmark_runs_parent_revision",
        "benchmark_runs",
        "benchmark_runs",
        ["parent_benchmark_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_benchmark_runs_root_revision",
        "benchmark_runs",
        "benchmark_runs",
        ["root_benchmark_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_benchmark_runs_revision_number_positive",
        "benchmark_runs",
        "revision_number > 0",
    )
    for column in (
        "parent_benchmark_run_id",
        "root_benchmark_run_id",
        "evidence_revision_hash",
    ):
        op.create_index(f"ix_benchmark_runs_{column}", "benchmark_runs", [column])

    op.add_column(
        "benchmark_results",
        sa.Column("parent_benchmark_result_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "benchmark_results",
        sa.Column("root_benchmark_result_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "benchmark_results",
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "benchmark_results",
        sa.Column("evidence_revision_hash", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_benchmark_results_parent_revision",
        "benchmark_results",
        "benchmark_results",
        ["parent_benchmark_result_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_benchmark_results_root_revision",
        "benchmark_results",
        "benchmark_results",
        ["root_benchmark_result_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_benchmark_results_revision_number_positive",
        "benchmark_results",
        "revision_number > 0",
    )
    for column in (
        "parent_benchmark_result_id",
        "root_benchmark_result_id",
        "evidence_revision_hash",
    ):
        op.create_index(f"ix_benchmark_results_{column}", "benchmark_results", [column])

    op.add_column(
        "agent_approval_checkpoints",
        sa.Column("transition_benchmark_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "agent_approval_checkpoints",
        sa.Column("transition_benchmark_result_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_checkpoints_transition_run",
        "agent_approval_checkpoints",
        "benchmark_runs",
        ["transition_benchmark_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_agent_checkpoints_transition_result",
        "agent_approval_checkpoints",
        "benchmark_results",
        ["transition_benchmark_result_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_approval_checkpoints_transition_benchmark_run_id",
        "agent_approval_checkpoints",
        ["transition_benchmark_run_id"],
    )
    op.create_index(
        "ix_agent_approval_checkpoints_transition_benchmark_result_id",
        "agent_approval_checkpoints",
        ["transition_benchmark_result_id"],
    )

    op.drop_constraint(
        "ck_gate_evaluations_status",
        "gate_evaluations",
        type_="check",
    )
    op.add_column(
        "gate_evaluations",
        sa.Column("evidence_revision_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "gate_evaluations",
        sa.Column("stale_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "gate_evaluations",
        sa.Column("stale_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "gate_evaluations",
        sa.Column(
            "superseded_by_gate_evaluation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_gate_evaluations_superseded_by",
        "gate_evaluations",
        "gate_evaluations",
        ["superseded_by_gate_evaluation_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_gate_evaluations_status",
        "gate_evaluations",
        "status IN ('draft', 'completed', 'failed', 'stale')",
    )
    for column in (
        "evidence_revision_hash",
        "stale_at",
        "superseded_by_gate_evaluation_id",
    ):
        op.create_index(f"ix_gate_evaluations_{column}", "gate_evaluations", [column])

    op.create_table(
        "agent_execution_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="queued"),
        sa.Column("dedupe_key", sa.String(length=240), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("requested_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("benchmark_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("benchmark_result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("checkpoint_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("lease_owner", sa.String(length=160), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
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
            "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
            "'traffic_evidence_import')",
            name="ck_agent_execution_jobs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'leased', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_agent_execution_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0",
            name="ck_agent_execution_jobs_attempts",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_run_id"], ["benchmark_runs.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_result_id"], ["benchmark_results.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_record_id"],
            ["agent_approval_checkpoints.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
        sa.UniqueConstraint("lease_token"),
    )
    for column in (
        "job_type",
        "status",
        "benchmark_run_id",
        "benchmark_result_id",
        "checkpoint_record_id",
        "available_at",
        "lease_owner",
        "lease_expires_at",
    ):
        op.create_index(f"ix_agent_execution_jobs_{column}", "agent_execution_jobs", [column])


def downgrade() -> None:
    op.drop_table("agent_execution_jobs")

    for column in (
        "superseded_by_gate_evaluation_id",
        "stale_at",
        "evidence_revision_hash",
    ):
        op.drop_index(f"ix_gate_evaluations_{column}", table_name="gate_evaluations")
    op.drop_constraint("ck_gate_evaluations_status", "gate_evaluations", type_="check")
    op.drop_constraint(
        "fk_gate_evaluations_superseded_by",
        "gate_evaluations",
        type_="foreignkey",
    )
    op.drop_column("gate_evaluations", "superseded_by_gate_evaluation_id")
    op.drop_column("gate_evaluations", "stale_reason")
    op.drop_column("gate_evaluations", "stale_at")
    op.drop_column("gate_evaluations", "evidence_revision_hash")
    op.create_check_constraint(
        "ck_gate_evaluations_status",
        "gate_evaluations",
        "status IN ('draft', 'completed', 'failed')",
    )

    op.drop_index(
        "ix_agent_approval_checkpoints_transition_benchmark_result_id",
        table_name="agent_approval_checkpoints",
    )
    op.drop_index(
        "ix_agent_approval_checkpoints_transition_benchmark_run_id",
        table_name="agent_approval_checkpoints",
    )
    op.drop_constraint(
        "fk_agent_checkpoints_transition_result",
        "agent_approval_checkpoints",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_agent_checkpoints_transition_run",
        "agent_approval_checkpoints",
        type_="foreignkey",
    )
    op.drop_column("agent_approval_checkpoints", "transition_benchmark_result_id")
    op.drop_column("agent_approval_checkpoints", "transition_benchmark_run_id")

    for column in (
        "evidence_revision_hash",
        "root_benchmark_result_id",
        "parent_benchmark_result_id",
    ):
        op.drop_index(f"ix_benchmark_results_{column}", table_name="benchmark_results")
    op.drop_constraint(
        "ck_benchmark_results_revision_number_positive",
        "benchmark_results",
        type_="check",
    )
    op.drop_constraint(
        "fk_benchmark_results_root_revision",
        "benchmark_results",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_benchmark_results_parent_revision",
        "benchmark_results",
        type_="foreignkey",
    )
    op.drop_column("benchmark_results", "evidence_revision_hash")
    op.drop_column("benchmark_results", "revision_number")
    op.drop_column("benchmark_results", "root_benchmark_result_id")
    op.drop_column("benchmark_results", "parent_benchmark_result_id")

    for column in (
        "evidence_revision_hash",
        "root_benchmark_run_id",
        "parent_benchmark_run_id",
    ):
        op.drop_index(f"ix_benchmark_runs_{column}", table_name="benchmark_runs")
    op.drop_constraint(
        "ck_benchmark_runs_revision_number_positive",
        "benchmark_runs",
        type_="check",
    )
    op.drop_constraint(
        "fk_benchmark_runs_root_revision",
        "benchmark_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_benchmark_runs_parent_revision",
        "benchmark_runs",
        type_="foreignkey",
    )
    op.drop_column("benchmark_runs", "evidence_revision_hash")
    op.drop_column("benchmark_runs", "revision_reason")
    op.drop_column("benchmark_runs", "revision_number")
    op.drop_column("benchmark_runs", "root_benchmark_run_id")
    op.drop_column("benchmark_runs", "parent_benchmark_run_id")
