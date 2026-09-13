"""Add isolated scenario reports and self-reported input study attempts."""

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID

revision = "202609100001"
down_revision = "202609090001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "request_scenario_runs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_request_scenario_runs_owner_key", "request_scenario_runs", ["owner_key"])
    op.create_table(
        "request_study_attempts",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("scenario_json", sa.JSON(), nullable=False),
        sa.Column("actor_json", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("correction_count", sa.Integer(), nullable=False),
        sa.Column("answer_json", sa.JSON()),
        sa.Column("answer_hash", sa.String(64)),
        sa.Column("result_json", sa.JSON()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_request_study_attempts_owner_key", "request_study_attempts", ["owner_key"])


def downgrade():
    op.drop_table("request_study_attempts")
    op.drop_table("request_scenario_runs")
