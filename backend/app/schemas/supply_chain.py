from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SupplyChainAttestationStatus = Literal["verified", "revoked"]


class ModelSupplyChainAttestationCreate(BaseModel):
    model_artifact_attestation_id: UUID
    signed_statement_jws: str = Field(min_length=1, max_length=262_144)
    sbom_json: dict[str, Any]
    notes: str | None = Field(default=None, max_length=2000)


class ModelSupplyChainAttestationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_artifact_attestation_id: UUID
    publisher_trust_root_id: UUID | None
    publisher_trust_tier: Literal["development", "internal_ca", "external"]
    schema_version: str
    statement_id: str
    statement_type: str
    predicate_type: str
    publisher: str
    publisher_key_id: str
    signature_algorithm: str
    key_fingerprint: str
    subject_digest: str
    sbom_format: str
    sbom_version: str
    sbom_digest: str
    sbom_json: dict[str, Any]
    statement_json: dict[str, Any]
    signature_verified: bool
    verified_at: datetime
    verified_by_identity_json: dict[str, Any]
    identity_verified: bool
    attestation_hash: str
    status: SupplyChainAttestationStatus
    revocation_count: int
    latest_revocation_at: datetime | None = None
    publisher_trust_status: Literal[
        "unmanaged", "scheduled", "active", "retired", "revoked", "expired"
    ]
    transparency_status: Literal["missing", "development", "verified", "invalidated"]
    production_eligible: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ModelSupplyChainAttestationCreateRead(BaseModel):
    schema_version: str
    created: bool
    attestation: ModelSupplyChainAttestationRead


class SupplyChainRevocationCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)
    ticket_reference: str | None = Field(default=None, max_length=200)


class SupplyChainRevocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supply_chain_attestation_id: UUID
    action_type: Literal["revoked"]
    reason: str
    ticket_reference: str | None
    actor_identity_json: dict[str, Any]
    identity_verified: bool
    occurred_at: datetime
    action_hash: str
    created_at: datetime
    updated_at: datetime


class ProductionEvidenceReceiptCreate(BaseModel):
    signed_statement_jws: str = Field(min_length=1, max_length=262_144)
    notes: str | None = Field(default=None, max_length=2000)


class ProductionEvidenceReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    benchmark_run_id: UUID
    model_artifact_attestation_id: UUID
    supply_chain_attestation_id: UUID
    collector_trust_root_id: UUID | None
    collector_trust_tier: Literal["development", "internal_ca", "external"]
    schema_version: str
    capture_id: str
    issuer: str
    key_id: str
    signature_algorithm: str
    key_fingerprint: str
    subject_digest: str
    source_environment_json: dict[str, Any]
    capture_started_at: datetime
    capture_ended_at: datetime
    result_count: int
    metric_count: int
    statement_json: dict[str, Any]
    signature_verified: bool
    verified_at: datetime
    verified_by_identity_json: dict[str, Any]
    identity_verified: bool
    receipt_hash: str
    collector_trust_status: Literal[
        "unmanaged", "scheduled", "active", "retired", "revoked", "expired"
    ]
    supply_chain_production_eligible: bool
    production_eligible: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ProductionEvidenceReceiptCreateRead(BaseModel):
    schema_version: str
    created: bool
    receipt: ProductionEvidenceReceiptRead


class SupplyChainOverviewRead(BaseModel):
    schema_version: str
    publisher_trust_configured: bool
    production_evidence_trust_configured: bool
    verified_attestation_count: int
    revoked_attestation_count: int
    production_receipt_count: int
    managed_attestation_count: int
    production_eligible_attestation_count: int
    transparency_proof_count: int
    production_eligible_receipt_count: int
    unverified_production_run_count: int
