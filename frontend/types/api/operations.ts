import type { UUID } from "./common";



export type OperationalMetricSample = {
  name: string;
  value: number;
  metric_type: "gauge";
  help: string;
  labels: Record<string, string>;
};

export type OperationalAlert = {
  key: string;
  severity: "warning" | "critical";
  metric_name: string;
  current_value: number;
  threshold: number;
  summary: string;
  route: string;
};

export type OperationalMetrics = {
  schema_version: string;
  generated_at: string;
  health: "healthy" | "degraded" | "critical";
  samples: OperationalMetricSample[];
  alerts: OperationalAlert[];
};

export type OperationalReliabilityPermission = {
  policy_version: string;
  can_audit: boolean;
  can_administer: boolean;
  auditor_roles: string[];
  administrator_roles: string[];
  identity_verified: boolean;
  signer_role: string | null;
};

export type OperationalReliabilityPolicy = {
  snapshot_enabled: boolean;
  snapshot_interval_seconds: number;
  snapshot_retention_days: number;
  slo_window_seconds: number;
  slo_short_window_seconds: number;
  slo_min_samples: number;
  identity_slo_target: number;
  worker_slo_target: number;
  slo_warning_burn_rate: number;
  slo_critical_burn_rate: number;
  incident_escalation_seconds: number;
  paging_enabled: boolean;
  paging_destination: string | null;
  paging_transport: string;
  paging_active_key_id: string | null;
  paging_tls_verified: boolean;
  paging_provider: string;
  paging_receipt_required: boolean;
  paging_secret_source:
    | "projected_file"
    | "environment_keyring"
    | "legacy_environment"
    | "unconfigured"
    | "invalid";
  paging_key_count: number;
};

export type OperationalReadinessCheck = {
  key: string;
  status: "passed" | "failed";
  summary: string;
  evidence: string | null;
};

export type OperationalStagingReadiness = {
  schema_version: string;
  ready: boolean;
  passed_count: number;
  failed_count: number;
  latest_receipt_delivery_id: UUID | null;
  checks: OperationalReadinessCheck[];
};

export type OperationalSnapshotSummary = {
  id: UUID;
  bucket_started_at: string;
  generated_at: string;
  expires_at: string;
  health: "healthy" | "degraded" | "critical";
  sample_count: number;
  alert_count: number;
  content_hash: string;
  worker_online: number;
  queue_depth: number;
  identity_retention_due: number;
  identity_inactive_provider_token: number;
};

export type OperationalSLOEvaluation = {
  id: UUID;
  snapshot_id: UUID;
  slo_key: string;
  scope: "identity" | "worker";
  status: "met" | "breached" | "insufficient";
  target_ratio: number;
  observed_ratio: number | null;
  error_budget_remaining_ratio: number | null;
  window_seconds: number;
  short_window_seconds: number;
  short_observed_ratio: number | null;
  burn_rate: number | null;
  short_burn_rate: number | null;
  burn_alert_level: "none" | "warning" | "critical";
  sample_count: number;
  good_sample_count: number;
  window_started_at: string;
  window_ended_at: string;
  evaluated_at: string;
  details_json: Record<string, unknown>;
  evaluation_hash: string;
};

export type OperationalAlertIncident = {
  id: UUID;
  alert_key: string;
  source_type: "derived_alert" | "slo" | "test";
  severity: "warning" | "critical";
  route: string;
  summary: string;
  metric_name: string | null;
  current_value: number | null;
  threshold: number | null;
  slo_evaluation_id: UUID | null;
  status: "open" | "resolved";
  opened_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  acknowledged_at: string | null;
  acknowledged_by_identity_json: Record<string, unknown> | null;
  assigned_to: string | null;
  escalation_level: number;
  occurrence_count: number;
  transition_version: number;
};

export type OperationalAlertIncidentAction = {
  id: UUID;
  incident_id: UUID;
  action_type: "acknowledged" | "assigned" | "note" | "escalated";
  reason: string;
  assignee: string | null;
  actor_identity_json: Record<string, unknown>;
  identity_verified: boolean;
  occurred_at: string;
  previous_action_hash: string | null;
  action_hash: string;
};

export type OperationalAlertDelivery = {
  id: UUID;
  incident_id: UUID;
  delivery_job_id: UUID | null;
  transition_type: "opened" | "resolved" | "test" | "escalated";
  transition_version: number;
  destination_fingerprint: string;
  signing_key_id: string;
  status: "queued" | "delivered" | "failed";
  payload_hash: string;
  requested_at: string;
  last_attempt_at: string | null;
  attempt_count: number;
  response_status: number | null;
  response_hash: string | null;
  provider_name: string | null;
  provider_event_id: string | null;
  provider_receipt_id: string | null;
  provider_accepted_at: string | null;
  error_message: string | null;
  delivered_at: string | null;
};

export type OperationalReliabilityOverview = {
  schema_version: string;
  generated_at: string;
  health: "healthy" | "degraded" | "critical";
  snapshot_count: number;
  open_incident_count: number;
  delivery_status_counts: Record<string, number>;
  latest_snapshot: OperationalSnapshotSummary | null;
  latest_slo_evaluations: OperationalSLOEvaluation[];
  snapshots: OperationalSnapshotSummary[];
  incidents: OperationalAlertIncident[];
  incident_actions: OperationalAlertIncidentAction[];
  deliveries: OperationalAlertDelivery[];
  policy: OperationalReliabilityPolicy;
  staging_readiness: OperationalStagingReadiness;
  permissions: OperationalReliabilityPermission;
};

export type IsolationPolicy = {
  policy_id: string;
  policy_version: string;
  display_name: string;
  workload_kinds: Array<"tool" | "rag">;
  network_mode: "none" | "internal_allowlist";
  allowed_network_hosts: string[];
  credential_mode: "none" | "environment_allowlist";
  allowed_secret_envs: string[];
  filesystem_mode: "ephemeral" | "read_only";
  read_only_paths: string[];
  writable_paths: string[];
  allowed_tools: string[];
  subprocess_allowed: boolean;
  max_execution_seconds: number;
  max_output_bytes: number;
};

export type IsolationPolicyRegistry = {
  registry_version: string;
  policy_count: number;
  policies: IsolationPolicy[];
};
