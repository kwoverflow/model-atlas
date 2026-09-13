from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.entities import (
    BenchmarkExecutionCreate,
    DeploymentConfigurationRead,
    ModelArtifactRead,
)
from app.schemas.evidence_trust import EvidenceTrustSummaryRead

ModelValidationStatus = Literal[
    "no_evidence",
    "fixture_only",
    "insufficient_real_evidence",
    "needs_calibration",
    "needs_attention",
    "validated",
]
ModelArtifactAttestationStatus = Literal[
    "missing",
    "verified",
    "digest_mismatch",
    "model_mismatch",
]
ModelSupplyChainStatus = Literal["missing", "verified", "revoked"]
ProductionCaptureStatus = Literal["not_applicable", "verified", "unverified"]


class ModelValidationCampaignCreate(BenchmarkExecutionCreate):
    adapter_name: Literal["mock", "openai_compatible"] = "openai_compatible"
    data_source: Literal[
        "local_authored",
        "production_captured",
        "external_benchmark",
        "synthetic_demo",
    ] = "local_authored"
    campaign_key: str | None = Field(default=None, min_length=1, max_length=120)


class ObservedRuntimeConfigurationCreate(BaseModel):
    source_deployment_configuration_id: UUID
    base_url: str = Field(min_length=1, max_length=500)
    model_name: str = Field(min_length=1, max_length=200)
    configuration_name: str | None = Field(default=None, min_length=1, max_length=180)
    notes: str | None = Field(default=None, max_length=2000)


class RuntimeModelManifestRead(BaseModel):
    manifest_version: str
    runtime_provider: str
    runtime_model_name: str
    source_uri: str
    digest_algorithm: Literal["sha256"]
    digest_value: str
    size_bytes: int
    modified_at: str | None = None
    details: dict[str, Any]
    manifest_hash: str


class ModelArtifactAttestationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_artifact_id: UUID
    manifest_version: str
    runtime_provider: str
    runtime_model_name: str
    source_uri: str
    digest_algorithm: str
    digest_value: str
    manifest_hash: str
    manifest_json: dict[str, Any]
    verification_method: str
    status: Literal["verified", "revoked"]
    attested_at: datetime
    attested_by_identity_json: dict[str, Any]
    identity_verified: bool
    attestation_hash: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class ObservedRuntimeConfigurationRead(BaseModel):
    schema_version: str
    manifest: RuntimeModelManifestRead
    model_artifact: ModelArtifactRead
    attestation: ModelArtifactAttestationRead
    deployment_configuration: DeploymentConfigurationRead
    model_created: bool
    artifact_created: bool
    attestation_created: bool
    configuration_created: bool


class ModelValidationCohortRead(BaseModel):
    data_source: str
    benchmark_run_ids: list[UUID]
    result_count: int
    metric_count: int
    adapter_names: list[str]
    model_names: list[str]
    actual_runtime_result_count: int
    average_quality_score: float | None = None
    exact_match_rate: float | None = None
    json_validity_rate: float | None = None
    tool_call_validity_rate: float | None = None
    average_groundedness_score: float | None = None
    average_faithfulness_score: float | None = None
    error_rate: float
    p50_end_to_end_latency_ms: float | None = None
    p95_end_to_end_latency_ms: float | None = None
    p50_tokens_per_second: float | None = None
    oom_rate: float | None = None
    reviewed_result_count: int
    review_coverage_rate: float
    trust_status: str


class ModelValidationComparisonRead(BaseModel):
    baseline_source: str
    candidate_source: str
    quality_delta: float | None = None
    p95_latency_delta_ms: float | None = None
    p50_throughput_delta: float | None = None
    error_rate_delta: float
    oom_rate_delta: float | None = None


class ModelValidationJudgeCalibrationRead(BaseModel):
    status: Literal["not_available", "calibrated", "needs_review"]
    candidate_label_count: int
    mean_abs_quality_delta: float | None = None
    max_abs_quality_delta: float | None = None
    within_tolerance_rate: float | None = None
    tolerance: float
    reviewed_label_count: int = 0
    critical_reviewed_count: int = 0
    reviewer_count: int = 0


class ModelValidationReportRead(BaseModel):
    schema_version: str
    generated_at: datetime
    deployment_configuration_id: UUID
    deployment_configuration_name: str
    configured_model_artifact_name: str
    observed_model_names: list[str]
    observed_model_digests: list[str]
    configuration_model_match: bool | None = None
    artifact_attestation_status: ModelArtifactAttestationStatus
    artifact_attestation_id: UUID | None = None
    configured_artifact_digest: str | None = None
    supply_chain_status: ModelSupplyChainStatus = "missing"
    supply_chain_attestation_id: UUID | None = None
    supply_chain_trust_tier: Literal[
        "unmanaged", "development", "internal_ca", "external"
    ] = "unmanaged"
    transparency_status: Literal[
        "missing", "development", "verified", "invalidated"
    ] = "missing"
    supply_chain_production_eligible: bool = False
    production_capture_status: ProductionCaptureStatus = "not_applicable"
    verified_production_run_count: int = 0
    verified_production_result_count: int = 0
    evaluation_suite_id: UUID
    evaluation_suite_name: str
    focus_benchmark_run_id: UUID | None = None
    status: ModelValidationStatus
    actual_runtime_validated: bool
    release_authorized: bool = False
    evidence_revision_hash: str
    selected_run_count: int
    result_count: int
    metric_count: int
    cohorts: list[ModelValidationCohortRead]
    comparisons: list[ModelValidationComparisonRead]
    judge_calibration: ModelValidationJudgeCalibrationRead
    evidence_trust: EvidenceTrustSummaryRead
    recommendations: list[str]
    limitations: list[str]
    report_hash: str
