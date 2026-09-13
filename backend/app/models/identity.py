from __future__ import annotations

from app.models.base import (
    GUID,
    JSON,
    Any,
    Base,
    Boolean,
    CheckConstraint,
    Integer,
    Mapped,
    String,
    Text,
    TimestampMixin,
    UTCDateTime,
    dt,
    mapped_column,
    utcnow,
    uuid,
)


class OIDCBrowserSession(TimestampMixin, Base):
    __tablename__ = "oidc_browser_sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    subject_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(240), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120))
    identity_provider: Mapped[str] = mapped_column(String(500), nullable=False)
    provider_session_id: Mapped[str | None] = mapped_column(String(240), index=True)
    provider_session_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    client_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    provider_id_token_ciphertext: Mapped[str | None] = mapped_column(Text)
    provider_token_purged_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    authenticated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(80))
    logout_initiated_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (
        CheckConstraint(
            "expires_at > authenticated_at",
            name="ck_oidc_browser_sessions_expiry",
        ),
        CheckConstraint(
            "revocation_reason IS NULL OR revoked_at IS NOT NULL",
            name="ck_oidc_browser_sessions_revocation",
        ),
    )

class OIDCBrowserSessionEvent(Base):
    __tablename__ = "oidc_browser_session_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    session_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    identity_provider: Mapped[str] = mapped_column(String(500), nullable=False)
    provider_session_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(160))
    actor_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    identity_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    previous_event_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('issued', 'migrated', 'revoked', "
            "'provider_token_purged', 'retention_deleted')",
            name="ck_oidc_browser_session_events_type",
        ),
    )

class OIDCCacheEntry(TimestampMixin, Base):
    __tablename__ = "oidc_cache_entries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fetched_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    refresh_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    refreshed_by: Mapped[str] = mapped_column(String(160), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "document_type IN ('discovery', 'jwks')",
            name="ck_oidc_cache_entries_type",
        ),
        CheckConstraint(
            "expires_at > fetched_at",
            name="ck_oidc_cache_entries_expiry",
        ),
        CheckConstraint(
            "refresh_count > 0",
            name="ck_oidc_cache_entries_refresh_count",
        ),
    )
