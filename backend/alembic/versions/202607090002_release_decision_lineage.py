"""release decision lineage

Revision ID: 202607090002
Revises: 202607090001
Create Date: 2026-07-09 00:00:01.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607090002"
down_revision: str | None = "202607090001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("experiment_lineage_events", sa.Column("release_decision_id", uuid_type))
    op.create_foreign_key(
        "fk_experiment_lineage_events_release_decision_id",
        "experiment_lineage_events",
        "release_decisions",
        ["release_decision_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_experiment_lineage_events_release_decision_id"),
        "experiment_lineage_events",
        ["release_decision_id"],
    )
    op.drop_constraint(
        "ck_experiment_lineage_events_event_type",
        "experiment_lineage_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_experiment_lineage_events_primary_entity_type",
        "experiment_lineage_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_experiment_lineage_events_event_type",
        "experiment_lineage_events",
        "event_type IN ("
        "'prompt_version_created', "
        "'benchmark_run_created', "
        "'benchmark_run_completed', "
        "'benchmark_run_failed', "
        "'gate_evaluation_completed', "
        "'baseline_promoted', "
        "'baseline_superseded', "
        "'release_decision_signed'"
        ")",
    )
    op.create_check_constraint(
        "ck_experiment_lineage_events_primary_entity_type",
        "experiment_lineage_events",
        "primary_entity_type IN ("
        "'prompt_version', "
        "'benchmark_run', "
        "'gate_evaluation', "
        "'deployment_baseline', "
        "'release_decision'"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_experiment_lineage_events_primary_entity_type",
        "experiment_lineage_events",
        type_="check",
    )
    op.drop_constraint(
        "ck_experiment_lineage_events_event_type",
        "experiment_lineage_events",
        type_="check",
    )
    op.create_check_constraint(
        "ck_experiment_lineage_events_primary_entity_type",
        "experiment_lineage_events",
        "primary_entity_type IN ("
        "'prompt_version', "
        "'benchmark_run', "
        "'gate_evaluation', "
        "'deployment_baseline'"
        ")",
    )
    op.create_check_constraint(
        "ck_experiment_lineage_events_event_type",
        "experiment_lineage_events",
        "event_type IN ("
        "'prompt_version_created', "
        "'benchmark_run_created', "
        "'benchmark_run_completed', "
        "'benchmark_run_failed', "
        "'gate_evaluation_completed', "
        "'baseline_promoted', "
        "'baseline_superseded'"
        ")",
    )
    op.drop_index(
        op.f("ix_experiment_lineage_events_release_decision_id"),
        table_name="experiment_lineage_events",
    )
    op.drop_constraint(
        "fk_experiment_lineage_events_release_decision_id",
        "experiment_lineage_events",
        type_="foreignkey",
    )
    op.drop_column("experiment_lineage_events", "release_decision_id")
