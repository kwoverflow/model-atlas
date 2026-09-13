"""experiment lineage events

Revision ID: 202607080001
Revises: 202607070001
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607080001"
down_revision: str | None = "202607070001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "experiment_lineage_events",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("primary_entity_type", sa.String(length=80), nullable=False),
        sa.Column("primary_entity_id", uuid_type, nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lineage_key", sa.String(length=500), nullable=False),
        sa.Column("deployment_configuration_id", uuid_type, nullable=True),
        sa.Column("evaluation_suite_id", uuid_type, nullable=True),
        sa.Column("acceptance_policy_id", uuid_type, nullable=True),
        sa.Column("prompt_version_id", uuid_type, nullable=True),
        sa.Column("benchmark_run_id", uuid_type, nullable=True),
        sa.Column("gate_evaluation_id", uuid_type, nullable=True),
        sa.Column("deployment_baseline_id", uuid_type, nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("data_source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ("
            "'prompt_version_created', "
            "'benchmark_run_created', "
            "'benchmark_run_completed', "
            "'benchmark_run_failed', "
            "'gate_evaluation_completed', "
            "'baseline_promoted', "
            "'baseline_superseded'"
            ")",
            name="ck_experiment_lineage_events_event_type",
        ),
        sa.CheckConstraint(
            "primary_entity_type IN ("
            "'prompt_version', "
            "'benchmark_run', "
            "'gate_evaluation', "
            "'deployment_baseline'"
            ")",
            name="ck_experiment_lineage_events_primary_entity_type",
        ),
        sa.CheckConstraint(
            "status IN ('recorded', 'superseded', 'failed')",
            name="ck_experiment_lineage_events_status",
        ),
        sa.ForeignKeyConstraint(
            ["acceptance_policy_id"],
            ["acceptance_policies.id"],
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_run_id"],
            ["benchmark_runs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["deployment_baseline_id"],
            ["deployment_baselines.id"],
        ),
        sa.ForeignKeyConstraint(
            ["deployment_configuration_id"],
            ["deployment_configurations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_suite_id"],
            ["evaluation_suites.id"],
        ),
        sa.ForeignKeyConstraint(
            ["gate_evaluation_id"],
            ["gate_evaluations.id"],
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_type",
            "primary_entity_id",
            name="uq_experiment_lineage_events_type_entity",
        ),
    )
    for column_name in (
        "acceptance_policy_id",
        "benchmark_run_id",
        "deployment_baseline_id",
        "deployment_configuration_id",
        "evaluation_suite_id",
        "event_type",
        "gate_evaluation_id",
        "lineage_key",
        "primary_entity_id",
        "primary_entity_type",
        "prompt_version_id",
        "status",
    ):
        op.create_index(
            op.f(f"ix_experiment_lineage_events_{column_name}"),
            "experiment_lineage_events",
            [column_name],
        )


def downgrade() -> None:
    for column_name in (
        "status",
        "prompt_version_id",
        "primary_entity_type",
        "primary_entity_id",
        "lineage_key",
        "gate_evaluation_id",
        "event_type",
        "evaluation_suite_id",
        "deployment_configuration_id",
        "deployment_baseline_id",
        "benchmark_run_id",
        "acceptance_policy_id",
    ):
        op.drop_index(
            op.f(f"ix_experiment_lineage_events_{column_name}"),
            table_name="experiment_lineage_events",
        )
    op.drop_table("experiment_lineage_events")
