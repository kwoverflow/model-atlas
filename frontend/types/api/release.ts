import type { EvidenceTrustSummary, ProductionReadiness, UUID } from "./common";

import type { GateEvaluation } from "./gate";



export type ReleaseReadinessStatus =
  | "READY"
  | "READY_TO_PROMOTE"
  | "NEEDS_REVIEW"
  | "BLOCKED"
  | "INSUFFICIENT_EVIDENCE";

export type ReleaseReadinessSnapshot = {
  schema_version: string;
  evidence_trust_version: string;
  generated_at: string;
  status: ReleaseReadinessStatus;
  production_readiness: ProductionReadiness;
  release_summary: string;
  deployment_configuration_id: UUID;
  evaluation_suite_id: UUID;
  acceptance_policy_id: UUID;
  readiness_reasons: string[];
  review_reasons: string[];
  next_actions: string[];
  evidence_trust: EvidenceTrustSummary;
  gate: {
    gate_evaluation_id: UUID;
    status: GateEvaluation["status"];
    verdict: GateEvaluation["verdict"];
    decision_hash: string;
    decision_summary: string;
    evaluated_at: string;
    passed_rule_count: number;
    failed_rule_count: number;
    insufficient_rule_count: number;
    critical_failure_count: number;
    benchmark_run_ids: UUID[];
    metric_count: number;
    result_count: number;
    source_distribution: Record<string, number>;
    evidence_revision_hash: string | null;
    stale_at: string | null;
    stale_reason: string | null;
    superseded_by_gate_evaluation_id: UUID | null;
  };
  baseline: {
    active_baseline_id: UUID | null;
    active_baseline_gate_evaluation_id: UUID | null;
    gate_is_active_baseline: boolean;
    baseline_status: "active_source" | "different_active_baseline" | "not_promoted";
    baseline_hash: string | null;
    promoted_at: string | null;
  };
  judge_calibration: {
    result_count: number;
    reviewed_count: number;
    candidate_label_count: number;
    heuristic_scored_count: number;
    heuristic_only_count: number;
    applied_label_count: number;
    human_reviewed_count: number;
    unlabeled_count: number;
    needs_review_count: number;
    applied_label_coverage_rate: number;
    critical_review_coverage_rate: number;
    average_quality_score: number | null;
    average_abs_quality_delta_vs_candidate: number | null;
  };
  prompt_regression: {
    prompt_version_count: number;
    baseline_prompt_version_id: UUID | null;
    risk_row_count: number;
    risk_flags: string[];
  };
  lineage: {
    event_count: number;
    lineage_count: number;
    latest_events: Array<{
      event_type: string;
      event_time: string;
      summary: string;
      status: string;
    }>;
  };
};

export type ReleaseDecisionType =
  | "APPROVE_RELEASE"
  | "REJECT_RELEASE"
  | "REQUEST_CHANGES";

export type ReleaseDecisionPolicyEvaluation = {
  policy_version: string;
  decision: ReleaseDecisionType;
  allowed: boolean;
  requires_verified_identity: boolean;
  allowed_roles: string[];
  signer_role: string | null;
  identity_verified: boolean;
  reasons: string[];
  [key: string]: unknown;
};

export type SnapshotDiffStatus = "added" | "removed" | "changed";

export type ReleaseSnapshotDiffItem = {
  path: string;
  status: SnapshotDiffStatus;
  frozen_present: boolean;
  current_present: boolean;
  frozen_value?: unknown;
  current_value?: unknown;
};

export type ReleaseSnapshotDiff = {
  release_decision_id: UUID;
  gate_evaluation_id: UUID;
  frozen_snapshot_hash: string;
  current_snapshot_hash: string;
  changed: boolean;
  diff_count: number;
  truncated: boolean;
  ignored_paths: string[];
  diffs: ReleaseSnapshotDiffItem[];
};

export type ReleaseDecision = {
  id: UUID;
  gate_evaluation_id: UUID;
  deployment_configuration_id: UUID;
  evaluation_suite_id: UUID;
  acceptance_policy_id: UUID;
  decision: ReleaseDecisionType;
  release_readiness_status: ReleaseReadinessStatus;
  decided_at: string;
  decided_by: string;
  signer_identity_json: {
    subject_id?: string | null;
    display_name?: string | null;
    role?: string | null;
    identity_provider?: string | null;
    auth_source?: string | null;
    identity_verified?: boolean | null;
    ticket_reference?: string | null;
    [key: string]: unknown;
  };
  identity_verified: boolean;
  signature_hash: string | null;
  signature_statement: string | null;
  approval_policy_json: ReleaseDecisionPolicyEvaluation;
  decision_reason: string;
  notes: string | null;
  snapshot_hash: string;
  snapshot_json: ReleaseReadinessSnapshot;
  decision_hash: string;
  replaces_release_decision_id: UUID | null;
  operational_status:
    | "active"
    | "needs_review"
    | "revoked"
    | "replaced"
    | "recorded";
  stale_warning: boolean;
  action_count: number;
  latest_action_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReleaseDecisionAction = {
  id: UUID;
  release_decision_id: UUID;
  action_type:
    | "stale_detected"
    | "review_requested"
    | "acknowledged"
    | "revoked"
    | "replaced";
  dedupe_key: string;
  actor_identity_json: Record<string, unknown>;
  reason: string;
  source_gate_evaluation_id: UUID | null;
  replacement_release_decision_id: UUID | null;
  metadata_json: Record<string, unknown>;
  occurred_at: string;
  created_at: string;
  updated_at: string;
};
