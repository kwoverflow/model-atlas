import type { EvidenceTrustStatus, EvidenceTrustSummary, ProductionReadiness, UUID } from "./common";



export type AcceptancePolicy = {
  id: UUID;
  workload_profile_id: UUID;
  name: string;
  version_label: string;
  description: string;
  policy_hash: string;
  allow_conditional: boolean;
  is_active: boolean;
};

export type AcceptancePolicyRule = {
  id: UUID;
  acceptance_policy_id: UUID;
  metric_definition_id: UUID;
  rule_name: string;
  operator: string;
  threshold_value: number;
  severity: "blocker" | "warning";
  minimum_sample_size: number | null;
  required: boolean;
  enabled: boolean;
  message_on_fail: string;
};

export type DeploymentBaseline = {
  id: UUID;
  deployment_configuration_id: UUID;
  evaluation_suite_id: UUID;
  acceptance_policy_id: UUID;
  gate_evaluation_id: UUID;
  promoted_at: string;
  promoted_by: string | null;
  promotion_reason: string | null;
  baseline_hash: string;
  status: "active" | "superseded" | "archived";
  superseded_at: string | null;
  superseded_by_baseline_id: UUID | null;
  notes: string | null;
};

export type GateRuleResult = {
  id: UUID;
  gate_evaluation_id: UUID;
  acceptance_policy_rule_id: UUID;
  metric_value: number | null;
  sample_size: number;
  status: "pass" | "fail" | "insufficient";
  severity: "blocker" | "warning";
  details_json: Record<string, unknown> | null;
};

export type GateEvaluation = {
  id: UUID;
  deployment_configuration_id: UUID;
  evaluation_suite_id: UUID;
  acceptance_policy_id: UUID;
  baseline_gate_evaluation_id: UUID | null;
  status: string;
  verdict: "APPROVED" | "CONDITIONAL" | "BLOCKED" | "INSUFFICIENT_EVIDENCE";
  evidence_snapshot_json: Record<string, unknown>;
  scorecard_json: {
    metrics?: Record<string, { value: number | null; sample_size: number }>;
    rule_results?: Array<{
      rule_id: string;
      rule_name: string;
      metric_key: string;
      metric_value: number | null;
      sample_size: number;
      status: string;
      severity: string;
      details: Record<string, unknown>;
    }>;
    critical_case_outcomes?: Array<{
      case_id: string;
      external_case_id: string;
      title: string;
      category: string;
      benchmark_run_id: string;
      sample_id: string;
      status: string;
      quality_score: number | null;
      error_type: string | null;
      data_source: string;
      tool_execution_status?: string | null;
      rag_evaluation_status?: string | null;
      runtime_reliability_status?: string | null;
      agent_execution_status?: string | null;
      agent_halt_reason?: string | null;
      agent_replan_count?: number;
      agent_pending_approval_count?: number;
    }>;
    baseline_comparison?: {
      baseline_gate_evaluation_id: string | null;
      quality_regression_vs_baseline: number | null;
      latency_regression_vs_baseline: number | null;
    };
    next_actions?: string[];
    evidence_trust?: EvidenceTrustSummary;
    decision_explanation?: {
      summary: string;
      verdict: string;
      blockers: Array<{
        code: string;
        title: string;
        detail: string;
        severity: string;
        sample_ids?: string[];
      }>;
      warnings: Array<{
        code: string;
        title: string;
        detail: string;
        severity: string;
      }>;
      next_actions: Array<{
        code: string;
        title: string;
        description: string;
        href: string;
      }>;
    };
    synthetic_data_warning?: string | null;
  };
  decision_summary: string;
  decision_hash: string;
  evidence_revision_hash: string | null;
  stale_at: string | null;
  stale_reason: string | null;
  superseded_by_gate_evaluation_id: UUID | null;
  evaluated_at: string;
  rule_results: GateRuleResult[];
};

export type GatePreflightResponse = {
  configuration: {
    id: UUID;
    name: string;
    artifact_name: string;
    runtime_name: string;
    hardware_name: string;
    context_length: number;
    prompt_version: string | null;
  };
  suite: {
    id: UUID;
    name: string;
    version_label: string;
    active_case_count: number;
    critical_case_count: number;
  };
  policy: {
    id: UUID;
    name: string;
    version_label: string;
    rule_count: number;
    blocking_rule_count: number;
    warning_rule_count: number;
  };
  evidence: {
    completed_run_count: number;
    result_count: number;
    metric_count: number;
    source_distribution: Record<string, number>;
    score_distribution: Record<string, number>;
    heuristic_only_count: number;
    applied_judge_label_count: number;
    human_reviewed_count: number;
    applied_judge_label_rate: number;
    critical_review_coverage_rate: number;
    trust_status: EvidenceTrustStatus;
    production_readiness: ProductionReadiness;
  };
  baseline: {
    source: "explicit" | "active_scope_baseline";
    gate_evaluation_id: UUID;
    verdict: string;
  } | null;
  expected_outcome_constraints: string[];
  blocking_preconditions: string[];
  warnings: string[];
  can_evaluate: boolean;
};
