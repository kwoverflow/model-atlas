export type UUID = string;

export type EvidenceTrustStatus =
  | "synthetic_only"
  | "needs_judge_review"
  | "local_demo_ready"
  | "production_evidence_ready"
  | "unknown";

export type ProductionReadiness =
  | "production_ready"
  | "not_production_ready"
  | "unknown";

export type EvidenceTrustSummary = {
  source_distribution: Record<string, number>;
  score_distribution: Record<string, number>;
  total_result_count: number;
  synthetic_demo_count: number;
  local_authored_count: number;
  production_captured_count: number;
  unverified_production_captured_count: number;
  external_benchmark_count: number;
  unknown_source_count: number;
  heuristic_only_count: number;
  candidate_judge_label_count: number;
  applied_judge_label_count: number;
  human_reviewed_count: number;
  unknown_score_count: number;
  critical_result_count: number;
  critical_reviewed_count: number;
  applied_judge_label_rate: number;
  critical_review_coverage_rate: number;
  trust_status: EvidenceTrustStatus;
  production_readiness: ProductionReadiness;
  reasons: string[];
  limitations: string[];
};
