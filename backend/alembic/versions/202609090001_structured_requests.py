"""Add isolated structured request lab records, not official evaluation evidence."""

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID

revision = "202609090001"
down_revision = "202608040001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "structured_requests",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("owner_key", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("draft_json", sa.JSON(), nullable=False),
        sa.Column("contract_hash", sa.String(64), nullable=False),
        sa.Column("tool_contract_hash", sa.String(64), nullable=False),
        sa.Column("confirmation_json", sa.JSON()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("executed_check_id", GUID()),
        sa.Column("events_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_structured_request_revision"),
        sa.CheckConstraint(
            "status IN ('draft', 'confirmed', 'revoked')", name="ck_structured_request_status"
        ),
    )
    op.create_index("ix_structured_requests_owner_key", "structured_requests", ["owner_key"])
    op.create_table(
        "structured_request_checks",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("request_id", GUID(), sa.ForeignKey("structured_requests.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("contract_hash", sa.String(64), nullable=False),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("proposal_hash", sa.String(64), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("generation_json", sa.JSON()),
        sa.Column("verdict_json", sa.JSON(), nullable=False),
        sa.Column("execution_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_structured_request_checks_request_id", "structured_request_checks", ["request_id"]
    )


def downgrade():
    op.drop_table("structured_request_checks")
    op.drop_table("structured_requests")
