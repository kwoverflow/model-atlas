import type { UUID } from "./common";



export type ModelSupplyChainAttestation = {
  id: UUID;
  model_artifact_attestation_id: UUID;
  publisher_trust_root_id: UUID | null;
  publisher_trust_tier: "development" | "internal_ca" | "external";
  schema_version: string;
  statement_id: string;
  statement_type: string;
  predicate_type: string;
  publisher: string;
  publisher_key_id: string;
  signature_algorithm: string;
  key_fingerprint: string;
  subject_digest: string;
  sbom_format: "CycloneDX";
  sbom_version: string;
  sbom_digest: string;
  sbom_json: Record<string, unknown>;
  statement_json: Record<string, unknown>;
  signature_verified: boolean;
  verified_at: string;
  verified_by_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  attestation_hash: string;
  status: "verified" | "revoked";
  revocation_count: number;
  latest_revocation_at: string | null;
  publisher_trust_status:
    | "unmanaged"
    | "scheduled"
    | "active"
    | "retired"
    | "revoked"
    | "expired";
  transparency_status: "missing" | "development" | "verified" | "invalidated";
  production_eligible: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductionEvidenceReceipt = {
  id: UUID;
  benchmark_run_id: UUID;
  model_artifact_attestation_id: UUID;
  supply_chain_attestation_id: UUID;
  collector_trust_root_id: UUID | null;
  collector_trust_tier: "development" | "internal_ca" | "external";
  schema_version: string;
  capture_id: string;
  issuer: string;
  key_id: string;
  signature_algorithm: string;
  key_fingerprint: string;
  subject_digest: string;
  source_environment_json: Record<string, unknown>;
  capture_started_at: string;
  capture_ended_at: string;
  result_count: number;
  metric_count: number;
  statement_json: Record<string, unknown>;
  signature_verified: boolean;
  verified_at: string;
  verified_by_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  receipt_hash: string;
  collector_trust_status:
    | "unmanaged"
    | "scheduled"
    | "active"
    | "retired"
    | "revoked"
    | "expired";
  supply_chain_production_eligible: boolean;
  production_eligible: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type SupplyChainOverview = {
  schema_version: string;
  publisher_trust_configured: boolean;
  production_evidence_trust_configured: boolean;
  verified_attestation_count: number;
  revoked_attestation_count: number;
  production_receipt_count: number;
  managed_attestation_count: number;
  production_eligible_attestation_count: number;
  transparency_proof_count: number;
  production_eligible_receipt_count: number;
  unverified_production_run_count: number;
};

export type TrustRootStatus = "scheduled" | "active" | "retired" | "revoked" | "expired";

export type TrustSourceStatus =
  | "unsynced"
  | "healthy"
  | "degraded"
  | "stale"
  | "failed"
  | "disabled";

export type EvidenceTrustRoot = {
  id: UUID;
  name: string;
  purpose: "model_publisher" | "production_collector" | "transparency_log";
  issuer: string;
  key_id: string;
  algorithm: "RS256" | "ES256" | "EdDSA";
  key_fingerprint: string;
  public_key_jwk_json: Record<string, unknown>;
  trust_tier: "development" | "internal_ca" | "external";
  source_type: "development" | "internal_ca" | "external_registry" | "transparency_log";
  source_uri: string | null;
  valid_from: string;
  valid_until: string | null;
  supersedes_trust_root_id: UUID | null;
  trust_source_id: UUID | null;
  trust_source_sync_id: UUID | null;
  registered_at: string;
  registered_by_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  registration_hash: string;
  notes: string | null;
  status: TrustRootStatus;
  production_eligible: boolean;
  action_count: number;
  latest_action_type: "rotated" | "retired" | "revoked" | null;
  latest_action_at: string | null;
  trust_source_status: TrustSourceStatus | null;
  source_key_current: boolean | null;
  created_at: string;
  updated_at: string;
};

export type EvidenceTrustSource = {
  id: UUID;
  name: string;
  source_kind: "jwks";
  purpose: "model_publisher" | "production_collector" | "transparency_log";
  issuer: string;
  trust_tier: "development" | "internal_ca" | "external";
  endpoint_url: string;
  allowed_algorithms_json: Array<"RS256" | "ES256" | "EdDSA">;
  allow_insecure_http: boolean;
  freshness_seconds: number;
  enabled: boolean;
  registered_at: string;
  registered_by_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  configuration_hash: string;
  notes: string | null;
  status: TrustSourceStatus;
  production_eligible: boolean;
  latest_attempt_at: string | null;
  latest_attempt_status: "succeeded" | "failed" | null;
  last_successful_apply_at: string | null;
  next_sync_due_at: string | null;
  current_key_count: number;
  created_at: string;
  updated_at: string;
};

export type EvidenceTrustSourceSchedule = {
  id: UUID;
  trust_source_id: UUID;
  enabled: boolean;
  interval_seconds: number;
  jitter_seconds: number;
  max_attempts: number;
  retry_base_seconds: number;
  retry_max_seconds: number;
  retry_jitter_seconds: number;
  next_run_at: string;
  last_enqueued_at: string | null;
  last_completed_at: string | null;
  last_job_id: UUID | null;
  last_sync_id: UUID | null;
  run_sequence: number;
  consecutive_failures: number;
  lease_owner: string | null;
  lease_expires_at: string | null;
  policy_hash: string;
  configured_by_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  status: "disabled" | "scheduled" | "due" | "leased" | "retrying" | "failed";
  last_job_status: string | null;
  created_at: string;
  updated_at: string;
};

export type EvidenceTrustSourceSync = {
  id: UUID;
  trust_source_id: UUID;
  mode: "preview" | "apply";
  status: "succeeded" | "failed";
  trigger: "manual" | "scheduled";
  schedule_id: UUID | null;
  job_id: UUID | null;
  attempt_number: number;
  scheduled_for: string | null;
  http_status: number | null;
  fetched_at: string;
  completed_at: string;
  payload_hash: string | null;
  key_count: number;
  candidate_count: number;
  imported_count: number;
  unchanged_count: number;
  rejected_count: number;
  observed_keys_json: Array<Record<string, unknown>>;
  error_code: string | null;
  error_message: string | null;
  actor_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  sync_hash: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type TransparencyProof = {
  id: UUID;
  supply_chain_attestation_id: UUID;
  log_trust_root_id: UUID;
  schema_version: string;
  proof_id: string;
  log_id: string;
  log_index: number;
  tree_size: number;
  integrated_at: string;
  leaf_hash: string;
  root_hash: string;
  entry_json: Record<string, unknown>;
  inclusion_path_json: string[];
  checkpoint_json: Record<string, unknown>;
  signature_algorithm: string;
  key_id: string;
  key_fingerprint: string;
  signature_verified: boolean;
  verified_at: string;
  verified_by_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  proof_hash: string;
  notes: string | null;
  trust_root_status: TrustRootStatus;
  production_eligible: boolean;
  created_at: string;
  updated_at: string;
};

export type TrustRegistryOverview = {
  schema_version: string;
  trust_source_count: number;
  healthy_source_count: number;
  degraded_source_count: number;
  stale_source_count: number;
  failed_source_count: number;
  unsynced_source_count: number;
  automatic_schedule_count: number;
  automatic_schedule_enabled_count: number;
  automatic_schedule_due_count: number;
  automatic_schedule_retrying_count: number;
  automatic_schedule_failed_count: number;
  active_root_count: number;
  production_eligible_root_count: number;
  retired_root_count: number;
  revoked_root_count: number;
  expired_root_count: number;
  scheduled_root_count: number;
  transparency_proof_count: number;
  production_eligible_proof_count: number;
  managed_attestation_count: number;
  production_eligible_attestation_count: number;
  production_tier_attestation_pending_count: number;
};
