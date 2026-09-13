"""Add governed OIDC browser-session lifecycle management.

Revision ID: 202607270001
Revises: 202607230001
Create Date: 2026-07-27
"""

import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607270001"
down_revision: str | None = "202607230001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "oidc_browser_sessions",
        sa.Column("provider_session_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "oidc_browser_sessions",
        sa.Column("client_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "oidc_browser_sessions",
        sa.Column(
            "provider_token_purged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    for name, column in (
        ("ix_oidc_browser_sessions_provider_session_hash", "provider_session_hash"),
        ("ix_oidc_browser_sessions_client_fingerprint", "client_fingerprint"),
        ("ix_oidc_browser_sessions_provider_token_purged_at", "provider_token_purged_at"),
    ):
        op.create_index(name, "oidc_browser_sessions", [column])

    op.create_table(
        "oidc_browser_session_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=240), nullable=False),
        sa.Column("identity_provider", sa.String(length=500), nullable=False),
        sa.Column("provider_session_hash", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=True),
        sa.Column("actor_identity_json", sa.JSON(), nullable=False),
        sa.Column("identity_verified", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("previous_event_hash", sa.String(length=64), nullable=True),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('issued', 'migrated', 'revoked', "
            "'provider_token_purged', 'retention_deleted')",
            name="ck_oidc_browser_session_events_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_hash"),
    )
    for name, column in (
        ("ix_oidc_browser_session_events_session_id", "session_id"),
        ("ix_oidc_browser_session_events_session_hash", "session_hash"),
        ("ix_oidc_browser_session_events_subject_id", "subject_id"),
        (
            "ix_oidc_browser_session_events_provider_session_hash",
            "provider_session_hash",
        ),
        ("ix_oidc_browser_session_events_event_type", "event_type"),
        ("ix_oidc_browser_session_events_identity_verified", "identity_verified"),
        ("ix_oidc_browser_session_events_event_hash", "event_hash"),
        ("ix_oidc_browser_session_events_occurred_at", "occurred_at"),
    ):
        op.create_index(name, "oidc_browser_session_events", [column])

    connection = op.get_bind()
    sessions = list(
        connection.execute(
            sa.text(
                "SELECT id, session_hash, subject_id, identity_provider, "
                "provider_session_id, provider_id_token_ciphertext, "
                "authenticated_at, expires_at, revoked_at "
                "FROM oidc_browser_sessions"
            )
        ).mappings()
    )
    migrated_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    event_rows: list[dict[str, object]] = []
    for session in sessions:
        provider_session_id = session["provider_session_id"]
        provider_session_hash = (
            hashlib.sha256(str(provider_session_id).encode()).hexdigest()
            if provider_session_id
            else None
        )
        if provider_session_hash:
            connection.execute(
                sa.text(
                    "UPDATE oidc_browser_sessions "
                    "SET provider_session_hash = :provider_session_hash "
                    "WHERE id = :session_id"
                ),
                {
                    "provider_session_hash": provider_session_hash,
                    "session_id": session["id"],
                },
            )
        event_id = uuid.uuid4()
        metadata = {
            "source_revision": revision,
            "authenticated_at": session["authenticated_at"].isoformat(),
            "expires_at": session["expires_at"].isoformat(),
            "revoked_at": (
                session["revoked_at"].isoformat() if session["revoked_at"] else None
            ),
            "provider_token_state": (
                "retained"
                if session["provider_id_token_ciphertext"]
                else "not_available"
            ),
        }
        actor = {
            "subject_id": "alembic-202607270001",
            "display_name": "OIDC session lifecycle migration",
            "role": "System Migration",
            "identity_provider": "model-atlas",
            "auth_source": "database_migration",
            "identity_verified": True,
            "ticket_reference": None,
        }
        canonical = {
            "id": str(event_id),
            "session_id": str(session["id"]),
            "session_hash": session["session_hash"],
            "subject_id": session["subject_id"],
            "identity_provider": session["identity_provider"],
            "provider_session_hash": provider_session_hash,
            "event_type": "migrated",
            "reason": "session_lifecycle_baseline",
            "actor_identity_json": actor,
            "identity_verified": True,
            "metadata_json": metadata,
            "previous_event_hash": None,
            "occurred_at": migrated_at.isoformat(),
        }
        event_rows.append(
            {
                **canonical,
                "id": event_id,
                "session_id": session["id"],
                "occurred_at": migrated_at,
                "created_at": migrated_at,
                "event_hash": hashlib.sha256(
                    json.dumps(
                        canonical,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            }
        )
    if event_rows:
        event_table = sa.table(
            "oidc_browser_session_events",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("session_id", postgresql.UUID(as_uuid=True)),
            sa.column("session_hash", sa.String()),
            sa.column("subject_id", sa.String()),
            sa.column("identity_provider", sa.String()),
            sa.column("provider_session_hash", sa.String()),
            sa.column("event_type", sa.String()),
            sa.column("reason", sa.String()),
            sa.column("actor_identity_json", sa.JSON()),
            sa.column("identity_verified", sa.Boolean()),
            sa.column("metadata_json", sa.JSON()),
            sa.column("previous_event_hash", sa.String()),
            sa.column("event_hash", sa.String()),
            sa.column("occurred_at", sa.DateTime(timezone=True)),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(event_table, event_rows)

    op.drop_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
        "'traffic_evidence_import', 'model_validation_campaign', "
        "'trust_source_sync', 'oidc_session_cleanup')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_agent_execution_jobs_job_type",
        "agent_execution_jobs",
        "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
        "'traffic_evidence_import', 'model_validation_campaign', "
        "'trust_source_sync')",
    )
    op.drop_table("oidc_browser_session_events")
    for name in (
        "ix_oidc_browser_sessions_provider_token_purged_at",
        "ix_oidc_browser_sessions_client_fingerprint",
        "ix_oidc_browser_sessions_provider_session_hash",
    ):
        op.drop_index(name, table_name="oidc_browser_sessions")
    for column in (
        "provider_token_purged_at",
        "client_fingerprint",
        "provider_session_hash",
    ):
        op.drop_column("oidc_browser_sessions", column)
