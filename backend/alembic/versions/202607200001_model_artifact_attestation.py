"""Add verified model artifact manifest attestations.

Revision ID: 202607200001
Revises: 202607170004
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607200001"
down_revision: str | None = "202607170004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_artifact_attestations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_artifact_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("manifest_version", sa.String(length=80), nullable=False),
        sa.Column("runtime_provider", sa.String(length=80), nullable=False),
        sa.Column("runtime_model_name", sa.String(length=200), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("digest_algorithm", sa.String(length=20), nullable=False),
        sa.Column("digest_value", sa.String(length=80), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("verification_method", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attested_by_identity_json", sa.JSON(), nullable=False),
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
            "digest_algorithm IN ('sha256')",
            name="ck_model_artifact_attestations_digest_algorithm",
        ),
        sa.CheckConstraint(
            "status IN ('verified', 'revoked')",
            name="ck_model_artifact_attestations_status",
        ),
        sa.ForeignKeyConstraint(
            ["model_artifact_id"],
            ["model_artifacts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attestation_hash",
            name="uq_model_artifact_attestations_attestation_hash",
        ),
        sa.UniqueConstraint(
            "model_artifact_id",
            "digest_value",
            name="uq_model_artifact_attestations_artifact_digest",
        ),
    )
    for column in (
        "model_artifact_id",
        "runtime_model_name",
        "digest_value",
        "manifest_hash",
        "status",
        "attested_at",
        "identity_verified",
        "attestation_hash",
    ):
        op.create_index(
            f"ix_model_artifact_attestations_{column}",
            "model_artifact_attestations",
            [column],
        )


def downgrade() -> None:
    op.drop_table("model_artifact_attestations")
