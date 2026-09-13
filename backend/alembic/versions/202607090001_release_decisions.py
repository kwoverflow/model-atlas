"""release decisions

Revision ID: 202607090001
Revises: 202607080001
Create Date: 2026-07-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607090001"
down_revision: str | None = "202607080001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "release_decisions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("gate_evaluation_id", uuid_type, nullable=False),
        sa.Column("deployment_configuration_id", uuid_type, nullable=False),
        sa.Column("evaluation_suite_id", uuid_type, nullable=False),
        sa.Column("acceptance_policy_id", uuid_type, nullable=False),
        sa.Column("decision", sa.String(length=40), nullable=False),
        sa.Column("release_readiness_status", sa.String(length=40), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(length=120), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=128), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("decision_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('APPROVE_RELEASE', 'REJECT_RELEASE', 'REQUEST_CHANGES')",
            name="ck_release_decisions_decision",
        ),
        sa.CheckConstraint(
            "release_readiness_status IN ("
            "'READY', "
            "'READY_TO_PROMOTE', "
            "'NEEDS_REVIEW', "
            "'BLOCKED', "
            "'INSUFFICIENT_EVIDENCE'"
            ")",
            name="ck_release_decisions_readiness_status",
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
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_hash", name="uq_release_decisions_decision_hash"),
    )
    for column_name in (
        "acceptance_policy_id",
        "decision",
        "decision_hash",
        "deployment_configuration_id",
        "evaluation_suite_id",
        "gate_evaluation_id",
        "release_readiness_status",
        "snapshot_hash",
    ):
        op.create_index(
            op.f(f"ix_release_decisions_{column_name}"),
            "release_decisions",
            [column_name],
        )


def downgrade() -> None:
    for column_name in (
        "snapshot_hash",
        "release_readiness_status",
        "gate_evaluation_id",
        "evaluation_suite_id",
        "deployment_configuration_id",
        "decision_hash",
        "decision",
        "acceptance_policy_id",
    ):
        op.drop_index(op.f(f"ix_release_decisions_{column_name}"), table_name="release_decisions")
    op.drop_table("release_decisions")
