"""Add stale release operational actions and replacement links.

Revision ID: 202607170003
Revises: 202607170002
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607170003"
down_revision: str | None = "202607170002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "release_decisions",
        sa.Column(
            "replaces_release_decision_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_release_decisions_replaces",
        "release_decisions",
        "release_decisions",
        ["replaces_release_decision_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_release_decisions_replaces_release_decision_id",
        "release_decisions",
        ["replaces_release_decision_id"],
    )
    op.create_table(
        "release_decision_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "release_decision_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("dedupe_key", sa.String(length=240), nullable=False),
        sa.Column("actor_identity_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "source_gate_evaluation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "replacement_release_decision_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
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
            "action_type IN ('stale_detected', 'review_requested', "
            "'acknowledged', 'revoked', 'replaced')",
            name="ck_release_decision_actions_type",
        ),
        sa.ForeignKeyConstraint(
            ["release_decision_id"],
            ["release_decisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_gate_evaluation_id"],
            ["gate_evaluations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["replacement_release_decision_id"],
            ["release_decisions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    for column in (
        "release_decision_id",
        "action_type",
        "source_gate_evaluation_id",
        "replacement_release_decision_id",
        "occurred_at",
    ):
        op.create_index(
            f"ix_release_decision_actions_{column}",
            "release_decision_actions",
            [column],
        )


def downgrade() -> None:
    op.drop_table("release_decision_actions")
    op.drop_index(
        "ix_release_decisions_replaces_release_decision_id",
        table_name="release_decisions",
    )
    op.drop_constraint(
        "fk_release_decisions_replaces",
        "release_decisions",
        type_="foreignkey",
    )
    op.drop_column("release_decisions", "replaces_release_decision_id")
