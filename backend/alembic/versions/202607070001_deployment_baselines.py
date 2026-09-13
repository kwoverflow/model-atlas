"""deployment baselines

Revision ID: 202607070001
Revises: 202607060002
Create Date: 2026-07-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607070001"
down_revision: str | None = "202607060002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "deployment_baselines",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("deployment_configuration_id", uuid_type, nullable=False),
        sa.Column("evaluation_suite_id", uuid_type, nullable=False),
        sa.Column("acceptance_policy_id", uuid_type, nullable=False),
        sa.Column("gate_evaluation_id", uuid_type, nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_by", sa.String(length=120), nullable=True),
        sa.Column("promotion_reason", sa.Text(), nullable=True),
        sa.Column("baseline_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_baseline_id", uuid_type, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'archived')",
            name="ck_deployment_baselines_status",
        ),
        sa.ForeignKeyConstraint(
            ["acceptance_policy_id"],
            ["acceptance_policies.id"],
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
            ["superseded_by_baseline_id"],
            ["deployment_baselines.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deployment_baselines_acceptance_policy_id"),
        "deployment_baselines",
        ["acceptance_policy_id"],
    )
    op.create_index(
        op.f("ix_deployment_baselines_baseline_hash"),
        "deployment_baselines",
        ["baseline_hash"],
    )
    op.create_index(
        op.f("ix_deployment_baselines_deployment_configuration_id"),
        "deployment_baselines",
        ["deployment_configuration_id"],
    )
    op.create_index(
        op.f("ix_deployment_baselines_evaluation_suite_id"),
        "deployment_baselines",
        ["evaluation_suite_id"],
    )
    op.create_index(
        op.f("ix_deployment_baselines_gate_evaluation_id"),
        "deployment_baselines",
        ["gate_evaluation_id"],
    )
    op.create_index(
        op.f("ix_deployment_baselines_status"),
        "deployment_baselines",
        ["status"],
    )
    op.create_index(
        op.f("ix_deployment_baselines_superseded_by_baseline_id"),
        "deployment_baselines",
        ["superseded_by_baseline_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_deployment_baselines_superseded_by_baseline_id"),
        table_name="deployment_baselines",
    )
    op.drop_index(op.f("ix_deployment_baselines_status"), table_name="deployment_baselines")
    op.drop_index(
        op.f("ix_deployment_baselines_gate_evaluation_id"),
        table_name="deployment_baselines",
    )
    op.drop_index(
        op.f("ix_deployment_baselines_evaluation_suite_id"),
        table_name="deployment_baselines",
    )
    op.drop_index(
        op.f("ix_deployment_baselines_deployment_configuration_id"),
        table_name="deployment_baselines",
    )
    op.drop_index(
        op.f("ix_deployment_baselines_baseline_hash"),
        table_name="deployment_baselines",
    )
    op.drop_index(
        op.f("ix_deployment_baselines_acceptance_policy_id"),
        table_name="deployment_baselines",
    )
    op.drop_table("deployment_baselines")
