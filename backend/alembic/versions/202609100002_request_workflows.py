"""Add separately attributed end-to-end request workflow attempts."""

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID

revision = "202609100002"
down_revision = "202609100001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "request_workflow_attempts",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("scenario_json", sa.JSON(), nullable=False),
        sa.Column("actor_json", sa.JSON(), nullable=False),
        sa.Column("request_id", GUID(), sa.ForeignKey("structured_requests.id"), unique=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("help_count", sa.Integer(), nullable=False),
        sa.Column("help_events_json", sa.JSON(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("result_json", sa.JSON()),
        sa.Column("submission_hash", sa.String(64)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_request_workflow_attempts_owner_key", "request_workflow_attempts", ["owner_key"]
    )


def downgrade():
    op.drop_table("request_workflow_attempts")
