import type { EvidenceTrustSummary, UUID } from "./common";

import type { DeploymentConfiguration } from "./evaluation";



export type HardwareProfile = {
  id: UUID;
  name: string;
  cpu_name: string;
  cpu_cores: number;
  ram_gb: number;
  gpu_name: string;
  gpu_vram_gb: number;
  gpu_count: number;
  os_name: string | null;
  cuda_version: string | null;
  driver_version: string | null;
  notes: string | null;
};

export type Model = {
  id: UUID;
  provider: string;
  family: string;
  name: string;
  display_name: string;
  parameter_count_b: number | null;
  architecture_type: string;
  supports_text: boolean;
  supports_vision: boolean;
  supports_tool_calling: boolean;
  supports_structured_output: boolean;
  context_length: number;
  license_name: string | null;
  commercial_use_allowed: boolean | null;
  primary_languages: string[];
  source_url: string | null;
  notes: string | null;
};

export type ModelArtifact = {
  id: UUID;
  model_id: UUID;
  artifact_name: string;
  format: string;
  quantization: string | null;
  precision: string | null;
  file_size_gb: number | null;
  minimum_vram_gb: number | null;
  recommended_vram_gb: number | null;
  context_limit: number;
  runtime_compatibility: string[];
  checksum: string | null;
  is_active: boolean;
  notes: string | null;
};

export type ModelValidationStatus =
  | "no_evidence"
  | "fixture_only"
  | "insufficient_real_evidence"
  | "needs_calibration"
  | "needs_attention"
  | "validated";

export type ModelValidationCohort = {
  data_source: string;
  benchmark_run_ids: UUID[];
  result_count: number;
  metric_count: number;
  adapter_names: string[];
  model_names: string[];
  actual_runtime_result_count: number;
  average_quality_score: number | null;
  exact_match_rate: number | null;
  json_validity_rate: number | null;
  tool_call_validity_rate: number | null;
  average_groundedness_score: number | null;
  average_faithfulness_score: number | null;
  error_rate: number;
  p50_end_to_end_latency_ms: number | null;
  p95_end_to_end_latency_ms: number | null;
  p50_tokens_per_second: number | null;
  oom_rate: number | null;
  reviewed_result_count: number;
  review_coverage_rate: number;
  trust_status: string;
};

export type ModelValidationComparison = {
  baseline_source: string;
  candidate_source: string;
  quality_delta: number | null;
  p95_latency_delta_ms: number | null;
  p50_throughput_delta: number | null;
  error_rate_delta: number;
  oom_rate_delta: number | null;
};

export type ModelValidationJudgeCalibration = {
  status: "not_available" | "calibrated" | "needs_review";
  candidate_label_count: number;
  mean_abs_quality_delta: number | null;
  max_abs_quality_delta: number | null;
  within_tolerance_rate: number | null;
  tolerance: number;
  reviewed_label_count: number;
  critical_reviewed_count: number;
  reviewer_count: number;
};

export type ModelValidationReport = {
  schema_version: string;
  generated_at: string;
  deployment_configuration_id: UUID;
  deployment_configuration_name: string;
  configured_model_artifact_name: string;
  observed_model_names: string[];
  observed_model_digests: string[];
  configuration_model_match: boolean | null;
  artifact_attestation_status:
    | "missing"
    | "verified"
    | "digest_mismatch"
    | "model_mismatch";
  artifact_attestation_id: UUID | null;
  configured_artifact_digest: string | null;
  supply_chain_status: "missing" | "verified" | "revoked";
  supply_chain_attestation_id: UUID | null;
  supply_chain_trust_tier: "unmanaged" | "development" | "internal_ca" | "external";
  transparency_status: "missing" | "development" | "verified" | "invalidated";
  supply_chain_production_eligible: boolean;
  production_capture_status: "not_applicable" | "verified" | "unverified";
  verified_production_run_count: number;
  verified_production_result_count: number;
  evaluation_suite_id: UUID;
  evaluation_suite_name: string;
  focus_benchmark_run_id: UUID | null;
  status: ModelValidationStatus;
  actual_runtime_validated: boolean;
  release_authorized: boolean;
  evidence_revision_hash: string;
  selected_run_count: number;
  result_count: number;
  metric_count: number;
  cohorts: ModelValidationCohort[];
  comparisons: ModelValidationComparison[];
  judge_calibration: ModelValidationJudgeCalibration;
  evidence_trust: EvidenceTrustSummary;
  recommendations: string[];
  limitations: string[];
  report_hash: string;
};

export type ObservedRuntimeConfiguration = {
  schema_version: string;
  manifest: {
    runtime_model_name: string;
    digest_value: string;
    size_bytes: number;
    manifest_hash: string;
  };
  model_artifact: ModelArtifact;
  attestation: {
    id: UUID;
    status: "verified" | "revoked";
    attestation_hash: string;
  };
  deployment_configuration: DeploymentConfiguration;
  model_created: boolean;
  artifact_created: boolean;
  attestation_created: boolean;
  configuration_created: boolean;
};

export type ModelArtifactAttestation = {
  id: UUID;
  model_artifact_id: UUID;
  runtime_model_name: string;
  digest_value: string;
  manifest_hash: string;
  status: "verified" | "revoked";
  attestation_hash: string;
  attested_at: string;
  identity_verified: boolean;
};
