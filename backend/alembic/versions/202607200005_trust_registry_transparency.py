"""Add managed evidence trust roots and transparency proofs.

Revision ID: 202607200005
Revises: 202607200004
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607200005"
down_revision: str | None = "202607200004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evidence_trust_roots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("purpose", sa.String(length=40), nullable=False),
        sa.Column("issuer", sa.String(length=240), nullable=False),
        sa.Column("key_id", sa.String(length=200), nullable=False),
        sa.Column("algorithm", sa.String(length=30), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("public_key_jwk_json", sa.JSON(), nullable=False),
        sa.Column("trust_tier", sa.String(length=40), nullable=False),
        sa.Column("source_type", sa.String(length=60), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "supersedes_trust_root_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("registered_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("registration_hash", sa.String(length=64), nullable=False),
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
            "purpose IN ('model_publisher', 'production_collector', 'transparency_log')",
            name="ck_evidence_trust_roots_purpose",
        ),
        sa.CheckConstraint(
            "algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_evidence_trust_roots_algorithm",
        ),
        sa.CheckConstraint(
            "trust_tier IN ('development', 'internal_ca', 'external')",
            name="ck_evidence_trust_roots_tier",
        ),
        sa.CheckConstraint(
            "source_type IN "
            "('development', 'internal_ca', 'external_registry', 'transparency_log')",
            name="ck_evidence_trust_roots_source_type",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_evidence_trust_roots_validity",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_trust_root_id"],
            ["evidence_trust_roots.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "purpose",
            "issuer",
            "key_id",
            name="uq_evidence_trust_roots_purpose_issuer_key",
        ),
        sa.UniqueConstraint(
            "registration_hash",
            name="uq_evidence_trust_roots_registration_hash",
        ),
    )
    for name, column in (
        ("ix_evidence_trust_roots_purpose", "purpose"),
        ("ix_evidence_trust_roots_issuer", "issuer"),
        ("ix_evidence_trust_roots_key_id", "key_id"),
        ("ix_evidence_trust_roots_fingerprint", "key_fingerprint"),
        ("ix_evidence_trust_roots_tier", "trust_tier"),
        ("ix_evidence_trust_roots_valid_from", "valid_from"),
        ("ix_evidence_trust_roots_valid_until", "valid_until"),
        ("ix_evidence_trust_roots_supersedes", "supersedes_trust_root_id"),
        ("ix_evidence_trust_roots_registered_at", "registered_at"),
        ("ix_evidence_trust_roots_identity", "identity_verified"),
        ("ix_evidence_trust_roots_registration_hash", "registration_hash"),
    ):
        op.create_index(name, "evidence_trust_roots", [column])

    op.create_table(
        "evidence_trust_root_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trust_root_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("ticket_reference", sa.String(length=200), nullable=True),
        sa.Column("actor_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action_hash", sa.String(length=64), nullable=False),
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
            "action_type IN ('rotated', 'retired', 'revoked')",
            name="ck_evidence_trust_root_actions_type",
        ),
        sa.ForeignKeyConstraint(
            ["trust_root_id"],
            ["evidence_trust_roots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "trust_root_id",
            "action_type",
            name="uq_evidence_trust_root_actions_root_type",
        ),
        sa.UniqueConstraint(
            "action_hash",
            name="uq_evidence_trust_root_actions_hash",
        ),
    )
    for name, column in (
        ("ix_evidence_trust_root_actions_root", "trust_root_id"),
        ("ix_evidence_trust_root_actions_type", "action_type"),
        ("ix_evidence_trust_root_actions_identity", "identity_verified"),
        ("ix_evidence_trust_root_actions_occurred", "occurred_at"),
        ("ix_evidence_trust_root_actions_hash", "action_hash"),
    ):
        op.create_index(name, "evidence_trust_root_actions", [column])

    op.add_column(
        "model_supply_chain_attestations",
        sa.Column(
            "publisher_trust_root_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "model_supply_chain_attestations",
        sa.Column(
            "publisher_trust_tier",
            sa.String(length=40),
            nullable=False,
            server_default="development",
        ),
    )
    op.create_foreign_key(
        "fk_supply_chain_attestations_publisher_trust_root",
        "model_supply_chain_attestations",
        "evidence_trust_roots",
        ["publisher_trust_root_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_model_supply_chain_attestations_trust_tier",
        "model_supply_chain_attestations",
        "publisher_trust_tier IN ('development', 'internal_ca', 'external')",
    )
    op.create_index(
        "ix_supply_chain_publisher_trust_root",
        "model_supply_chain_attestations",
        ["publisher_trust_root_id"],
    )
    op.create_index(
        "ix_supply_chain_publisher_trust_tier",
        "model_supply_chain_attestations",
        ["publisher_trust_tier"],
    )

    op.add_column(
        "production_evidence_receipts",
        sa.Column(
            "collector_trust_root_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "production_evidence_receipts",
        sa.Column(
            "collector_trust_tier",
            sa.String(length=40),
            nullable=False,
            server_default="development",
        ),
    )
    op.create_foreign_key(
        "fk_production_receipts_collector_trust_root",
        "production_evidence_receipts",
        "evidence_trust_roots",
        ["collector_trust_root_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_production_evidence_receipts_trust_tier",
        "production_evidence_receipts",
        "collector_trust_tier IN ('development', 'internal_ca', 'external')",
    )
    op.create_index(
        "ix_production_receipt_collector_trust_root",
        "production_evidence_receipts",
        ["collector_trust_root_id"],
    )
    op.create_index(
        "ix_production_receipt_collector_trust_tier",
        "production_evidence_receipts",
        ["collector_trust_tier"],
    )

    op.create_table(
        "supply_chain_transparency_proofs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "supply_chain_attestation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("log_trust_root_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("proof_id", sa.String(length=200), nullable=False),
        sa.Column("log_id", sa.String(length=240), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("tree_size", sa.Integer(), nullable=False),
        sa.Column("integrated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leaf_hash", sa.String(length=64), nullable=False),
        sa.Column("root_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_json", sa.JSON(), nullable=False),
        sa.Column("inclusion_path_json", sa.JSON(), nullable=False),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("checkpoint_jws", sa.Text(), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=30), nullable=False),
        sa.Column("key_id", sa.String(length=200), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("proof_hash", sa.String(length=64), nullable=False),
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
            "log_index >= 0 AND tree_size > 0 AND log_index < tree_size",
            name="ck_supply_chain_transparency_position",
        ),
        sa.CheckConstraint(
            "signature_algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_supply_chain_transparency_algorithm",
        ),
        sa.ForeignKeyConstraint(
            ["supply_chain_attestation_id"],
            ["model_supply_chain_attestations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["log_trust_root_id"],
            ["evidence_trust_roots.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proof_id", name="uq_supply_chain_transparency_proof_id"),
        sa.UniqueConstraint("proof_hash", name="uq_supply_chain_transparency_proof_hash"),
        sa.UniqueConstraint(
            "supply_chain_attestation_id",
            "log_id",
            "log_index",
            name="uq_supply_chain_transparency_log_entry",
        ),
    )
    for name, column in (
        ("ix_supply_chain_transparency_attestation", "supply_chain_attestation_id"),
        ("ix_supply_chain_transparency_trust_root", "log_trust_root_id"),
        ("ix_supply_chain_transparency_proof_id", "proof_id"),
        ("ix_supply_chain_transparency_log_id", "log_id"),
        ("ix_supply_chain_transparency_integrated_at", "integrated_at"),
        ("ix_supply_chain_transparency_signature", "signature_verified"),
        ("ix_supply_chain_transparency_verified_at", "verified_at"),
        ("ix_supply_chain_transparency_identity", "identity_verified"),
        ("ix_supply_chain_transparency_proof_hash", "proof_hash"),
    ):
        op.create_index(name, "supply_chain_transparency_proofs", [column])


def downgrade() -> None:
    op.drop_table("supply_chain_transparency_proofs")

    op.drop_index(
        "ix_production_receipt_collector_trust_tier",
        table_name="production_evidence_receipts",
    )
    op.drop_index(
        "ix_production_receipt_collector_trust_root",
        table_name="production_evidence_receipts",
    )
    op.drop_constraint(
        "ck_production_evidence_receipts_trust_tier",
        "production_evidence_receipts",
        type_="check",
    )
    op.drop_constraint(
        "fk_production_receipts_collector_trust_root",
        "production_evidence_receipts",
        type_="foreignkey",
    )
    op.drop_column("production_evidence_receipts", "collector_trust_tier")
    op.drop_column("production_evidence_receipts", "collector_trust_root_id")

    op.drop_index(
        "ix_supply_chain_publisher_trust_tier",
        table_name="model_supply_chain_attestations",
    )
    op.drop_index(
        "ix_supply_chain_publisher_trust_root",
        table_name="model_supply_chain_attestations",
    )
    op.drop_constraint(
        "ck_model_supply_chain_attestations_trust_tier",
        "model_supply_chain_attestations",
        type_="check",
    )
    op.drop_constraint(
        "fk_supply_chain_attestations_publisher_trust_root",
        "model_supply_chain_attestations",
        type_="foreignkey",
    )
    op.drop_column("model_supply_chain_attestations", "publisher_trust_tier")
    op.drop_column("model_supply_chain_attestations", "publisher_trust_root_id")

    op.drop_table("evidence_trust_root_actions")
    op.drop_table("evidence_trust_roots")
