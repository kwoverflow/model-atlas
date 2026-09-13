"""Add remote evidence trust sources and sync history.

Revision ID: 202607210001
Revises: 202607200005
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607210001"
down_revision: str | None = "202607200005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_trust_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("source_kind", sa.String(length=40), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("issuer", sa.String(length=240), nullable=False),
        sa.Column("trust_tier", sa.String(length=40), nullable=False),
        sa.Column("endpoint_url", sa.String(length=500), nullable=False),
        sa.Column("allowed_algorithms_json", sa.JSON(), nullable=False),
        sa.Column("allow_insecure_http", sa.Boolean(), nullable=False),
        sa.Column("freshness_seconds", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "source_kind IN ('jwks')",
            name="ck_evidence_trust_sources_kind",
        ),
        sa.CheckConstraint(
            "purpose IN ('model_publisher', 'production_collector', 'transparency_log')",
            name="ck_evidence_trust_sources_purpose",
        ),
        sa.CheckConstraint(
            "trust_tier IN ('development', 'internal_ca', 'external')",
            name="ck_evidence_trust_sources_tier",
        ),
        sa.CheckConstraint(
            "freshness_seconds >= 60 AND freshness_seconds <= 604800",
            name="ck_evidence_trust_sources_freshness",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_evidence_trust_sources_name"),
        sa.UniqueConstraint(
            "purpose",
            "issuer",
            "endpoint_url",
            name="uq_evidence_trust_sources_purpose_issuer_endpoint",
        ),
        sa.UniqueConstraint(
            "configuration_hash",
            name="uq_evidence_trust_sources_configuration_hash",
        ),
    )
    for name, column in (
        ("ix_evidence_trust_sources_name", "name"),
        ("ix_evidence_trust_sources_kind", "source_kind"),
        ("ix_evidence_trust_sources_purpose", "purpose"),
        ("ix_evidence_trust_sources_issuer", "issuer"),
        ("ix_evidence_trust_sources_tier", "trust_tier"),
        ("ix_evidence_trust_sources_enabled", "enabled"),
        ("ix_evidence_trust_sources_registered", "registered_at"),
        ("ix_evidence_trust_sources_identity", "identity_verified"),
        ("ix_evidence_trust_sources_config_hash", "configuration_hash"),
    ):
        op.create_index(name, "evidence_trust_sources", [column])

    op.create_table(
        "evidence_trust_source_syncs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trust_source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("key_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("unchanged_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("observed_keys_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("actor_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("sync_hash", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
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
            "mode IN ('preview', 'apply')",
            name="ck_evidence_trust_source_syncs_mode",
        ),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_evidence_trust_source_syncs_status",
        ),
        sa.CheckConstraint(
            "key_count >= 0 AND candidate_count >= 0 AND imported_count >= 0 "
            "AND unchanged_count >= 0 AND rejected_count >= 0",
            name="ck_evidence_trust_source_syncs_counts",
        ),
        sa.ForeignKeyConstraint(
            ["trust_source_id"],
            ["evidence_trust_sources.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sync_hash", name="uq_evidence_trust_source_syncs_hash"),
    )
    for name, column in (
        ("ix_evidence_trust_source_syncs_source", "trust_source_id"),
        ("ix_evidence_trust_source_syncs_mode", "mode"),
        ("ix_evidence_trust_source_syncs_status", "status"),
        ("ix_evidence_trust_source_syncs_fetched", "fetched_at"),
        ("ix_evidence_trust_source_syncs_completed", "completed_at"),
        ("ix_evidence_trust_source_syncs_payload", "payload_hash"),
        ("ix_evidence_trust_source_syncs_error", "error_code"),
        ("ix_evidence_trust_source_syncs_identity", "identity_verified"),
        ("ix_evidence_trust_source_syncs_hash", "sync_hash"),
    ):
        op.create_index(name, "evidence_trust_source_syncs", [column])

    op.add_column(
        "evidence_trust_roots",
        sa.Column("trust_source_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "evidence_trust_roots",
        sa.Column("trust_source_sync_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_evidence_trust_roots_source",
        "evidence_trust_roots",
        "evidence_trust_sources",
        ["trust_source_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evidence_trust_roots_source_sync",
        "evidence_trust_roots",
        "evidence_trust_source_syncs",
        ["trust_source_sync_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_evidence_trust_roots_source",
        "evidence_trust_roots",
        ["trust_source_id"],
    )
    op.create_index(
        "ix_evidence_trust_roots_source_sync",
        "evidence_trust_roots",
        ["trust_source_sync_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_trust_roots_source_sync",
        table_name="evidence_trust_roots",
    )
    op.drop_index(
        "ix_evidence_trust_roots_source",
        table_name="evidence_trust_roots",
    )
    op.drop_constraint(
        "fk_evidence_trust_roots_source_sync",
        "evidence_trust_roots",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_evidence_trust_roots_source",
        "evidence_trust_roots",
        type_="foreignkey",
    )
    op.drop_column("evidence_trust_roots", "trust_source_sync_id")
    op.drop_column("evidence_trust_roots", "trust_source_id")
    op.drop_table("evidence_trust_source_syncs")
    op.drop_table("evidence_trust_sources")
