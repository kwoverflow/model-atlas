"""Add signed supply-chain attestations and production evidence receipts.

Revision ID: 202607200004
Revises: 202607200003
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607200004"
down_revision: str | None = "202607200003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_supply_chain_attestations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "model_artifact_attestation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("statement_id", sa.String(length=200), nullable=False),
        sa.Column("statement_type", sa.String(length=200), nullable=False),
        sa.Column("predicate_type", sa.String(length=300), nullable=False),
        sa.Column("publisher", sa.String(length=240), nullable=False),
        sa.Column("publisher_key_id", sa.String(length=200), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=30), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("subject_digest", sa.String(length=80), nullable=False),
        sa.Column("sbom_format", sa.String(length=80), nullable=False),
        sa.Column("sbom_version", sa.String(length=40), nullable=False),
        sa.Column("sbom_digest", sa.String(length=64), nullable=False),
        sa.Column("sbom_json", sa.JSON(), nullable=False),
        sa.Column("statement_json", sa.JSON(), nullable=False),
        sa.Column("statement_jws", sa.Text(), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("attestation_hash", sa.String(length=64), nullable=False),
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
            "signature_algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_model_supply_chain_attestations_algorithm",
        ),
        sa.CheckConstraint(
            "sbom_format IN ('CycloneDX')",
            name="ck_model_supply_chain_attestations_sbom_format",
        ),
        sa.ForeignKeyConstraint(
            ["model_artifact_attestation_id"],
            ["model_artifact_attestations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "statement_id",
            name="uq_model_supply_chain_attestations_statement_id",
        ),
        sa.UniqueConstraint(
            "attestation_hash",
            name="uq_model_supply_chain_attestations_hash",
        ),
    )
    for name, column in (
        ("ix_supply_chain_runtime_attestation", "model_artifact_attestation_id"),
        ("ix_supply_chain_statement_id", "statement_id"),
        ("ix_supply_chain_publisher", "publisher"),
        ("ix_supply_chain_publisher_key", "publisher_key_id"),
        ("ix_supply_chain_subject_digest", "subject_digest"),
        ("ix_supply_chain_sbom_digest", "sbom_digest"),
        ("ix_supply_chain_signature_verified", "signature_verified"),
        ("ix_supply_chain_verified_at", "verified_at"),
        ("ix_supply_chain_identity_verified", "identity_verified"),
        ("ix_supply_chain_attestation_hash", "attestation_hash"),
    ):
        op.create_index(name, "model_supply_chain_attestations", [column])

    op.create_table(
        "model_supply_chain_attestation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "supply_chain_attestation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
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
            "action_type IN ('revoked')",
            name="ck_model_supply_chain_actions_type",
        ),
        sa.ForeignKeyConstraint(
            ["supply_chain_attestation_id"],
            ["model_supply_chain_attestations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "supply_chain_attestation_id",
            "action_type",
            name="uq_model_supply_chain_actions_attestation_type",
        ),
        sa.UniqueConstraint(
            "action_hash",
            name="uq_model_supply_chain_actions_hash",
        ),
    )
    for name, column in (
        ("ix_supply_chain_action_attestation", "supply_chain_attestation_id"),
        ("ix_supply_chain_action_type", "action_type"),
        ("ix_supply_chain_action_identity", "identity_verified"),
        ("ix_supply_chain_action_occurred", "occurred_at"),
        ("ix_supply_chain_action_hash", "action_hash"),
    ):
        op.create_index(name, "model_supply_chain_attestation_actions", [column])

    op.create_table(
        "production_evidence_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("benchmark_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "model_artifact_attestation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "supply_chain_attestation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("capture_id", sa.String(length=200), nullable=False),
        sa.Column("issuer", sa.String(length=240), nullable=False),
        sa.Column("key_id", sa.String(length=200), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=30), nullable=False),
        sa.Column("key_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("subject_digest", sa.String(length=80), nullable=False),
        sa.Column("source_environment_json", sa.JSON(), nullable=False),
        sa.Column("capture_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capture_ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("metric_count", sa.Integer(), nullable=False),
        sa.Column("statement_json", sa.JSON(), nullable=False),
        sa.Column("statement_jws", sa.Text(), nullable=False),
        sa.Column("signature_verified", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_by_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("receipt_hash", sa.String(length=64), nullable=False),
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
            "signature_algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_production_evidence_receipts_algorithm",
        ),
        sa.CheckConstraint(
            "capture_ended_at >= capture_started_at",
            name="ck_production_evidence_receipts_capture_window",
        ),
        sa.CheckConstraint(
            "result_count >= 0 AND metric_count >= 0",
            name="ck_production_evidence_receipts_counts_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["benchmark_run_id"],
            ["benchmark_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_artifact_attestation_id"],
            ["model_artifact_attestations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["supply_chain_attestation_id"],
            ["model_supply_chain_attestations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "capture_id",
            name="uq_production_evidence_receipts_capture_id",
        ),
        sa.UniqueConstraint(
            "receipt_hash",
            name="uq_production_evidence_receipts_hash",
        ),
    )
    for name, column in (
        ("ix_production_receipt_run", "benchmark_run_id"),
        ("ix_production_receipt_runtime_attestation", "model_artifact_attestation_id"),
        ("ix_production_receipt_supply_chain", "supply_chain_attestation_id"),
        ("ix_production_receipt_capture_id", "capture_id"),
        ("ix_production_receipt_issuer", "issuer"),
        ("ix_production_receipt_key", "key_id"),
        ("ix_production_receipt_subject_digest", "subject_digest"),
        ("ix_production_receipt_signature", "signature_verified"),
        ("ix_production_receipt_verified_at", "verified_at"),
        ("ix_production_receipt_identity", "identity_verified"),
        ("ix_production_receipt_hash", "receipt_hash"),
    ):
        op.create_index(name, "production_evidence_receipts", [column])


def downgrade() -> None:
    op.drop_table("production_evidence_receipts")
    op.drop_table("model_supply_chain_attestation_actions")
    op.drop_table("model_supply_chain_attestations")
