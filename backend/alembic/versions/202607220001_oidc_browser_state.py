"""Add shared OIDC browser sessions and provider document cache.

Revision ID: 202607220001
Revises: 202607210001
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607220001"
down_revision: str | None = "202607210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oidc_browser_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=240), nullable=False),
        sa.Column("display_name", sa.String(length=240), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("identity_provider", sa.String(length=500), nullable=False),
        sa.Column("provider_session_id", sa.String(length=240), nullable=True),
        sa.Column("provider_id_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=80), nullable=True),
        sa.Column("logout_initiated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "expires_at > authenticated_at",
            name="ck_oidc_browser_sessions_expiry",
        ),
        sa.CheckConstraint(
            "revocation_reason IS NULL OR revoked_at IS NOT NULL",
            name="ck_oidc_browser_sessions_revocation",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_hash"),
        sa.UniqueConstraint("token_hash"),
    )
    for name, column in (
        ("ix_oidc_browser_sessions_token_hash", "token_hash"),
        ("ix_oidc_browser_sessions_session_hash", "session_hash"),
        ("ix_oidc_browser_sessions_subject_id", "subject_id"),
        ("ix_oidc_browser_sessions_provider_session_id", "provider_session_id"),
        ("ix_oidc_browser_sessions_authenticated_at", "authenticated_at"),
        ("ix_oidc_browser_sessions_expires_at", "expires_at"),
        ("ix_oidc_browser_sessions_last_seen_at", "last_seen_at"),
        ("ix_oidc_browser_sessions_revoked_at", "revoked_at"),
    ):
        op.create_index(name, "oidc_browser_sessions", [column])

    op.create_table(
        "oidc_cache_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("document_type", sa.String(length=20), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_count", sa.Integer(), nullable=False),
        sa.Column("refreshed_by", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "document_type IN ('discovery', 'jwks')",
            name="ck_oidc_cache_entries_type",
        ),
        sa.CheckConstraint(
            "expires_at > fetched_at",
            name="ck_oidc_cache_entries_expiry",
        ),
        sa.CheckConstraint(
            "refresh_count > 0",
            name="ck_oidc_cache_entries_refresh_count",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cache_key"),
    )
    for name, column in (
        ("ix_oidc_cache_entries_cache_key", "cache_key"),
        ("ix_oidc_cache_entries_document_type", "document_type"),
        ("ix_oidc_cache_entries_content_hash", "content_hash"),
        ("ix_oidc_cache_entries_fetched_at", "fetched_at"),
        ("ix_oidc_cache_entries_expires_at", "expires_at"),
    ):
        op.create_index(name, "oidc_cache_entries", [column])


def downgrade() -> None:
    op.drop_table("oidc_cache_entries")
    op.drop_table("oidc_browser_sessions")
