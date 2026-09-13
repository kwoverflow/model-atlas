from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

BrowserSessionStatus = Literal["active", "expired", "revoked"]
BrowserSessionProviderTokenState = Literal["retained", "purged", "not_available"]


class BrowserSessionPermissionRead(BaseModel):
    policy_version: str
    can_audit: bool
    can_administer: bool
    auditor_roles: list[str]
    administrator_roles: list[str]
    identity_verified: bool
    signer_role: str | None


class BrowserSessionRetentionPolicyRead(BaseModel):
    retention_days: int
    cleanup_enabled: bool
    cleanup_interval_seconds: int
    cleanup_batch_size: int
    provider_token_policy: str


class OIDCBrowserSessionRead(BaseModel):
    id: UUID
    session_fingerprint: str
    subject_id: str
    display_name: str
    role: str | None
    identity_provider: str
    provider_session_hash: str | None
    client_fingerprint: str | None
    authenticated_at: dt.datetime
    expires_at: dt.datetime
    last_seen_at: dt.datetime
    revoked_at: dt.datetime | None
    revocation_reason: str | None
    provider_token_state: BrowserSessionProviderTokenState
    provider_token_purged_at: dt.datetime | None
    status: BrowserSessionStatus
    current_session: bool


class OIDCBrowserSessionEventRead(BaseModel):
    id: UUID
    session_id: UUID
    session_fingerprint: str
    subject_id: str
    identity_provider: str
    provider_session_hash: str | None
    event_type: str
    reason: str | None
    actor_identity_json: dict[str, Any]
    identity_verified: bool
    metadata_json: dict[str, Any]
    previous_event_hash: str | None
    event_hash: str
    occurred_at: dt.datetime
    created_at: dt.datetime


class BrowserSessionOverviewRead(BaseModel):
    schema_version: str
    generated_at: dt.datetime
    health: Literal["healthy", "attention"]
    active_count: int
    expired_count: int
    revoked_count: int
    retention_due_count: int
    inactive_provider_token_count: int
    audit_event_count: int
    last_cleanup_job_id: UUID | None
    last_cleanup_job_status: str | None
    last_cleanup_completed_at: dt.datetime | None
    policy: BrowserSessionRetentionPolicyRead
    permissions: BrowserSessionPermissionRead


class BrowserSessionRevokeCreate(BaseModel):
    reason: str = Field(min_length=8, max_length=160)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 8:
            raise ValueError("reason must contain at least 8 non-whitespace characters")
        return normalized


class BrowserSessionBulkActionRead(BaseModel):
    action: Literal["session", "subject", "provider_session"]
    matched_count: int
    revoked_count: int
    already_inactive_count: int
    current_session_preserved: bool
    event_ids: list[UUID]


class BrowserSessionCleanupRequest(BaseModel):
    reason: str = Field(
        default="Operator requested retention cleanup",
        min_length=8,
        max_length=160,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return BrowserSessionRevokeCreate.normalize_reason(value)
