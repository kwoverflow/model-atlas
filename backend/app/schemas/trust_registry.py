from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

TrustPurpose = Literal[
    "model_publisher",
    "production_collector",
    "transparency_log",
]
TrustTier = Literal["development", "internal_ca", "external"]
TrustRootStatus = Literal["scheduled", "active", "retired", "revoked", "expired"]
TrustRootActionType = Literal["rotated", "retired", "revoked"]
TrustSourceStatus = Literal[
    "unsynced",
    "healthy",
    "degraded",
    "stale",
    "failed",
    "disabled",
]
TrustSourceSyncMode = Literal["preview", "apply"]
TrustSourceSyncStatus = Literal["succeeded", "failed"]
TrustSourceSyncTrigger = Literal["manual", "scheduled"]
TrustSourceScheduleStatus = Literal[
    "disabled",
    "scheduled",
    "due",
    "leased",
    "retrying",
    "failed",
]
SigningAlgorithm = Literal["RS256", "ES256", "EdDSA"]


class EvidenceTrustRootCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    purpose: TrustPurpose
    issuer: str = Field(min_length=1, max_length=240)
    key_id: str = Field(min_length=1, max_length=200)
    algorithm: SigningAlgorithm
    public_key_jwk_json: dict[str, Any]
    trust_tier: TrustTier
    source_type: Literal[
        "development",
        "internal_ca",
        "external_registry",
        "transparency_log",
    ]
    source_uri: str | None = Field(default=None, max_length=500)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    supersedes_trust_root_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=2000)


class EvidenceTrustRootRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    purpose: TrustPurpose
    issuer: str
    key_id: str
    algorithm: str
    key_fingerprint: str
    public_key_jwk_json: dict[str, Any]
    trust_tier: TrustTier
    source_type: str
    source_uri: str | None
    valid_from: datetime
    valid_until: datetime | None
    supersedes_trust_root_id: UUID | None
    trust_source_id: UUID | None
    trust_source_sync_id: UUID | None
    registered_at: datetime
    registered_by_identity_json: dict[str, Any]
    identity_verified: bool
    registration_hash: str
    notes: str | None
    status: TrustRootStatus
    production_eligible: bool
    action_count: int
    latest_action_type: TrustRootActionType | None = None
    latest_action_at: datetime | None = None
    trust_source_status: TrustSourceStatus | None = None
    source_key_current: bool | None = None
    created_at: datetime
    updated_at: datetime


class EvidenceTrustRootCreateRead(BaseModel):
    schema_version: str
    created: bool
    trust_root: EvidenceTrustRootRead


class EvidenceTrustRootActionCreate(BaseModel):
    action_type: Literal["retired", "revoked"]
    reason: str = Field(min_length=1, max_length=4000)
    ticket_reference: str | None = Field(default=None, max_length=200)


class EvidenceTrustRootActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trust_root_id: UUID
    action_type: TrustRootActionType
    reason: str
    ticket_reference: str | None
    actor_identity_json: dict[str, Any]
    identity_verified: bool
    occurred_at: datetime
    action_hash: str
    created_at: datetime
    updated_at: datetime


class EvidenceTrustSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    source_kind: Literal["jwks"] = "jwks"
    purpose: TrustPurpose
    issuer: str = Field(min_length=1, max_length=240)
    trust_tier: TrustTier
    endpoint_url: str = Field(min_length=1, max_length=500)
    allowed_algorithms: list[SigningAlgorithm] = Field(min_length=1, max_length=3)
    allow_insecure_http: bool = False
    freshness_seconds: int = Field(default=3600, ge=60, le=604_800)
    enabled: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class EvidenceTrustSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    source_kind: Literal["jwks"]
    purpose: TrustPurpose
    issuer: str
    trust_tier: TrustTier
    endpoint_url: str
    allowed_algorithms_json: list[SigningAlgorithm]
    allow_insecure_http: bool
    freshness_seconds: int
    enabled: bool
    registered_at: datetime
    registered_by_identity_json: dict[str, Any]
    identity_verified: bool
    configuration_hash: str
    notes: str | None
    status: TrustSourceStatus
    production_eligible: bool
    latest_attempt_at: datetime | None = None
    latest_attempt_status: TrustSourceSyncStatus | None = None
    last_successful_apply_at: datetime | None = None
    next_sync_due_at: datetime | None = None
    current_key_count: int
    created_at: datetime
    updated_at: datetime


class EvidenceTrustSourceCreateRead(BaseModel):
    schema_version: str
    created: bool
    trust_source: EvidenceTrustSourceRead


class EvidenceTrustSourceSyncCreate(BaseModel):
    mode: TrustSourceSyncMode
    notes: str | None = Field(default=None, max_length=2000)


class EvidenceTrustSourceSyncRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trust_source_id: UUID
    mode: TrustSourceSyncMode
    status: TrustSourceSyncStatus
    trigger: TrustSourceSyncTrigger
    schedule_id: UUID | None
    job_id: UUID | None
    attempt_number: int
    scheduled_for: datetime | None
    http_status: int | None
    fetched_at: datetime
    completed_at: datetime
    payload_hash: str | None
    key_count: int
    candidate_count: int
    imported_count: int
    unchanged_count: int
    rejected_count: int
    observed_keys_json: list[dict[str, Any]]
    error_code: str | None
    error_message: str | None
    actor_identity_json: dict[str, Any]
    identity_verified: bool
    sync_hash: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class EvidenceTrustSourceSyncCreateRead(BaseModel):
    schema_version: str
    sync: EvidenceTrustSourceSyncRead
    trust_source: EvidenceTrustSourceRead


class EvidenceTrustSourceScheduleUpsert(BaseModel):
    enabled: bool = True
    interval_seconds: int = Field(default=3600, ge=60, le=604_800)
    jitter_seconds: int = Field(default=60, ge=0, le=86_400)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    retry_max_seconds: int = Field(default=300, ge=1, le=3600)
    retry_jitter_seconds: int = Field(default=2, ge=0, le=3600)
    run_immediately: bool = True

    @model_validator(mode="after")
    def validate_policy_bounds(self) -> EvidenceTrustSourceScheduleUpsert:
        if self.jitter_seconds >= self.interval_seconds:
            raise ValueError("jitter_seconds must be less than interval_seconds")
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("retry_max_seconds must be at least retry_base_seconds")
        if self.retry_jitter_seconds > self.retry_max_seconds:
            raise ValueError("retry_jitter_seconds cannot exceed retry_max_seconds")
        return self


class EvidenceTrustSourceScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    trust_source_id: UUID
    enabled: bool
    interval_seconds: int
    jitter_seconds: int
    max_attempts: int
    retry_base_seconds: int
    retry_max_seconds: int
    retry_jitter_seconds: int
    next_run_at: datetime
    last_enqueued_at: datetime | None
    last_completed_at: datetime | None
    last_job_id: UUID | None
    last_sync_id: UUID | None
    run_sequence: int
    consecutive_failures: int
    lease_owner: str | None
    lease_expires_at: datetime | None
    policy_hash: str
    configured_by_identity_json: dict[str, Any]
    identity_verified: bool
    status: TrustSourceScheduleStatus
    last_job_status: str | None
    created_at: datetime
    updated_at: datetime


class TransparencyProofCreate(BaseModel):
    supply_chain_attestation_id: UUID
    signed_checkpoint_jws: str = Field(min_length=1, max_length=262_144)
    entry_json: dict[str, Any]
    log_index: int = Field(ge=0)
    inclusion_path: list[str] = Field(default_factory=list, max_length=128)
    notes: str | None = Field(default=None, max_length=2000)


class TransparencyProofRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supply_chain_attestation_id: UUID
    log_trust_root_id: UUID
    schema_version: str
    proof_id: str
    log_id: str
    log_index: int
    tree_size: int
    integrated_at: datetime
    leaf_hash: str
    root_hash: str
    entry_json: dict[str, Any]
    inclusion_path_json: list[str]
    checkpoint_json: dict[str, Any]
    signature_algorithm: str
    key_id: str
    key_fingerprint: str
    signature_verified: bool
    verified_at: datetime
    verified_by_identity_json: dict[str, Any]
    identity_verified: bool
    proof_hash: str
    notes: str | None
    trust_root_status: TrustRootStatus
    production_eligible: bool
    created_at: datetime
    updated_at: datetime


class TransparencyProofCreateRead(BaseModel):
    schema_version: str
    created: bool
    proof: TransparencyProofRead


class TrustRegistryOverviewRead(BaseModel):
    schema_version: str
    trust_source_count: int
    healthy_source_count: int
    degraded_source_count: int
    stale_source_count: int
    failed_source_count: int
    unsynced_source_count: int
    automatic_schedule_count: int
    automatic_schedule_enabled_count: int
    automatic_schedule_due_count: int
    automatic_schedule_retrying_count: int
    automatic_schedule_failed_count: int
    active_root_count: int
    production_eligible_root_count: int
    retired_root_count: int
    revoked_root_count: int
    expired_root_count: int
    scheduled_root_count: int
    transparency_proof_count: int
    production_eligible_proof_count: int
    managed_attestation_count: int
    production_eligible_attestation_count: int
    production_tier_attestation_pending_count: int
