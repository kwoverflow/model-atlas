import type { ModelValidationReport } from "./catalog";

import type { UUID } from "./common";



export type OperationalMemoryRecord = {
  memory_id: string;
  memory_version: string;
  title: string;
  tags: string[];
  data_classification: string;
  content_hash: string;
};

export type OperationalMemoryRegistry = {
  registry_id: string;
  registry_version: string;
  record_count: number;
  records: OperationalMemoryRecord[];
};

export type AgentApprovalCheckpointStatus =
  | "pending"
  | "approved"
  | "denied"
  | "revoked"
  | "expired"
  | "resumed";

export type AgentCheckpointPolicy = {
  policy_version: string;
  checkpoint_id: string;
  allowed_roles: string[];
  resume_roles: string[];
  requires_verified_identity: boolean;
  separation_of_duties: boolean;
  expires_in_seconds: number;
};

export type AgentApprovalCheckpoint = {
  id: UUID;
  benchmark_run_id: UUID;
  benchmark_result_id: UUID;
  checkpoint_id: string;
  status: AgentApprovalCheckpointStatus;
  requested_by_subject_id: string;
  requested_by_identity_json: Record<string, unknown>;
  request_snapshot_json: {
    external_case_id?: string | null;
    sample_id?: string | null;
    guarded_actions?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  approval_policy_json: AgentCheckpointPolicy;
  request_hash: string;
  expires_at: string;
  decision: "approved" | "denied" | null;
  decision_reason: string | null;
  decided_at: string | null;
  approver_identity_json: Record<string, unknown> | null;
  identity_verified: boolean;
  decision_hash: string | null;
  revoked_at: string | null;
  revocation_reason: string | null;
  revoked_by_identity_json: Record<string, unknown> | null;
  revocation_hash: string | null;
  resumed_at: string | null;
  resumed_by_identity_json: Record<string, unknown> | null;
  resume_hash: string | null;
  transition_benchmark_run_id: UUID | null;
  transition_benchmark_result_id: UUID | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type AgentRuntimeDescriptor = {
  runtime_id: string;
  runtime_version: string;
  trace_schema_version: string;
  context_schema_version: string;
  observation_schema_version: string;
  recovery_policy_version: string;
  approval_policy_version: string;
  live_replan_callback_version: string;
  allowed_actions: string[];
  limits: Record<string, number>;
  tool_registry_version: string;
  memory_registry_version: string;
  corpus_version: string;
  retriever_version: string;
  memory_write_mode: "task_local_simulated";
  approval_decision_mode: "external_request_only";
};

export type AgentObservation = {
  schema_version: string;
  status: string;
  successful: boolean;
  error_type: string | null;
  policy_violation_count: number;
  output_digest: string | null;
};

export type AgentExecutionStep = {
  step_index: number;
  action: string;
  expected_action: string | null;
  status: string;
  successful: boolean;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error_type: string | null;
  error_message: string | null;
  policy_violations: string[];
  recovered: boolean;
  retry_count: number;
  memory_provenance_valid: boolean;
  approval_provenance_valid: boolean;
  recovered_by_replan: boolean;
  phase: "plan" | "recovery";
  parent_step_index: number | null;
  observation: AgentObservation | null;
  duration_ms: number;
};

export type AgentReplan = {
  replan_index: number;
  trigger_step_index: number;
  trigger_error_type: string | null;
  observation: AgentObservation | null;
  strategy: string;
  expected_action_sequence: string[];
  actual_action_sequence: string[];
  sequence_match: boolean;
  recovery_step_indices: number[];
  status: string;
  successful: boolean;
  policy_version: string;
  source: "predeclared_plan" | "live_callback";
  model_call: Record<string, unknown> | null;
};

export type AgentExecutionTrace = {
  schema_version: string;
  context_version: string;
  runtime_version: string | null;
  observation_schema_version: string | null;
  recovery_policy_version: string | null;
  approval_policy_version: string | null;
  memory_registry_version: string;
  tool_registry_version: string;
  corpus_version: string;
  retriever_version: string;
  external_case_id: string;
  parse_valid: boolean;
  parse_error: string | null;
  plan_valid: boolean;
  status:
    | "success"
    | "partial_failure"
    | "failed"
    | "invalid_plan"
    | "limit_exceeded"
    | "pending_approval"
    | "approval_denied";
  successful: boolean;
  step_limit: number;
  execution_step_limit: number | null;
  replan_limit: number;
  step_count: number;
  expected_action_sequence: string[];
  actual_action_sequence: string[];
  sequence_match: boolean;
  successful_step_count: number;
  failed_step_count: number;
  step_success_rate: number | null;
  tool_call_count: number;
  retrieval_count: number;
  memory_read_count: number;
  memory_write_count: number;
  retried_tool_count: number;
  recovered_tool_count: number;
  policy_violation_count: number;
  final_response_present: boolean;
  memory_provenance_count: number;
  memory_action_count: number;
  observation_count: number;
  replan_count: number;
  successful_replan_count: number;
  recovery_step_count: number;
  successful_recovery_step_count: number;
  recovery_sequence_match: boolean | null;
  unrecovered_failure_count: number;
  approval_checkpoint_count: number;
  approved_checkpoint_count: number;
  denied_checkpoint_count: number;
  pending_checkpoint_count: number;
  approval_provenance_count: number;
  halt_reason: string | null;
  total_duration_ms: number;
  live_replan_count: number;
  live_replan_model_call_count: number;
  live_replan_prompt_tokens: number;
  live_replan_completion_tokens: number;
  live_replan_latency_ms: number;
  live_replan_estimated_cost_usd: number;
  replans: AgentReplan[];
  steps: AgentExecutionStep[];
};

export type AgentExecutionTraceRecord = {
  benchmark_result_id: UUID;
  evaluation_case_id: UUID | null;
  sample_id: string;
  case_title: string | null;
  criticality: string | null;
  trace: AgentExecutionTrace;
};

export type AgentExecutionSummary = {
  schema_version: string;
  agent_case_count: number;
  successful_case_count: number;
  failed_case_count: number;
  total_step_count: number;
  successful_step_count: number;
  failed_step_count: number;
  task_success_rate: number | null;
  plan_validity_rate: number | null;
  step_success_rate: number | null;
  action_sequence_accuracy: number | null;
  policy_violation_rate: number | null;
  final_response_rate: number | null;
  memory_provenance_rate: number | null;
  retried_tool_count: number;
  recovered_tool_count: number;
  tool_retry_recovery_rate: number | null;
  replan_case_count: number;
  replan_count: number;
  successful_replan_count: number;
  replan_success_rate: number | null;
  live_replan_count: number;
  live_replan_model_call_count: number;
  live_replan_prompt_tokens: number;
  live_replan_completion_tokens: number;
  live_replan_latency_ms: number;
  live_replan_estimated_cost_usd: number;
  recovery_step_count: number;
  successful_recovery_step_count: number;
  recovery_step_success_rate: number | null;
  approval_checkpoint_count: number;
  approved_checkpoint_count: number;
  denied_checkpoint_count: number;
  pending_checkpoint_count: number;
  approval_compliance_rate: number | null;
  approval_provenance_rate: number | null;
  pending_approval_rate: number | null;
  observation_coverage_rate: number | null;
  unrecovered_failure_rate: number | null;
  halted_case_count: number;
  average_steps_per_case: number | null;
  memory_registry_versions: string[];
  tool_registry_versions: string[];
  corpus_versions: string[];
  retriever_versions: string[];
  observation_versions: string[];
  recovery_policy_versions: string[];
  approval_policy_versions: string[];
  trace_versions: string[];
};

export type AgentReplay = {
  benchmark_result_id: UUID;
  benchmark_run_id: UUID;
  evaluation_case_id: UUID;
  version_compatible: boolean;
  deterministic_match: boolean;
  original_signature: string;
  replay_signature: string;
  changed_paths: string[];
  original_trace: AgentExecutionTrace;
  replay_trace: AgentExecutionTrace;
};

export type AgentCheckpointResume = {
  checkpoint: AgentApprovalCheckpoint;
  benchmark_run_id: UUID;
  benchmark_result_id: UUID;
  parent_benchmark_run_id: UUID;
  parent_benchmark_result_id: UUID;
  result_revision: number;
  trace: AgentExecutionTrace;
  summary: AgentExecutionSummary;
};

export type AgentExecutionJobStatus =
  | "queued"
  | "leased"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type AgentExecutionJob = {
  id: UUID;
  job_type:
    | "resume_checkpoint"
    | "checkpoint_reconciliation"
    | "traffic_evidence_import"
    | "model_validation_campaign"
    | "trust_source_sync"
    | "oidc_session_cleanup"
    | "operational_observability_cycle"
    | "operational_alert_delivery";
  status: AgentExecutionJobStatus;
  dedupe_key: string;
  payload_json: Record<string, unknown>;
  requested_by_identity_json: Record<string, unknown>;
  benchmark_run_id: UUID | null;
  benchmark_result_id: UUID | null;
  checkpoint_record_id: UUID | null;
  priority: number;
  available_at: string;
  lease_owner: string | null;
  lease_expires_at: string | null;
  last_heartbeat_at: string | null;
  heartbeat_count: number;
  attempt_count: number;
  max_attempts: number;
  started_at: string | null;
  completed_at: string | null;
  last_error: string | null;
  result_json: {
    benchmark_run_id?: UUID;
    benchmark_result_id?: UUID;
    result_revision?: number;
    trace_status?: string;
    report?: ModelValidationReport;
    [key: string]: unknown;
  } | null;
  dead_lettered_at: string | null;
  dead_letter_reason: string | null;
  requeue_count: number;
  last_requeued_at: string | null;
  last_requeued_by_identity_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AgentWorkerState = {
  worker_id: string;
  status: "online" | "offline" | "stopped";
  started_at: string;
  last_seen_at: string;
  current_job_id: UUID | null;
  processed_count: number;
  completed_count: number;
  failed_count: number;
  metadata_json: Record<string, unknown>;
};

export type AgentJobOverview = {
  schema_version: string;
  generated_at: string;
  health: "healthy" | "degraded" | "blocked" | "idle";
  total_job_count: number;
  status_counts: Record<string, number>;
  job_type_counts: Record<string, number>;
  queue_depth: number;
  retrying_count: number;
  active_lease_count: number;
  expired_lease_count: number;
  dead_letter_count: number;
  oldest_queued_age_seconds: number | null;
  completed_last_24h: number;
  failed_last_24h: number;
  success_rate_last_24h: number | null;
  average_queue_latency_ms: number | null;
  average_execution_duration_ms: number | null;
  online_worker_count: number;
  workers: AgentWorkerState[];
};

export type AgentTrafficSourceStatus = {
  schema_version: string;
  source_system: string;
  health: "active" | "stale" | "never_seen";
  batch_count: number;
  replay_count: number;
  last_received_at: string | null;
  last_job_id: UUID | null;
  collector_versions: string[];
  observed_key_ids: string[];
  configured_key_ids: string[];
};
