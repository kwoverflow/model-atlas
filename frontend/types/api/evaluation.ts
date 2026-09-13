import type { AgentExecutionSummary, AgentExecutionTraceRecord } from "./agent";

import type { EvidenceTrustStatus, EvidenceTrustSummary, ProductionReadiness, UUID } from "./common";

import type { GateEvaluation } from "./gate";



export type OverviewResponse = {
  model_count: number;
  model_artifact_count: number;
  benchmark_task_count: number;
  benchmark_run_count: number;
  benchmark_result_count: number;
  latest_benchmark_run_timestamp: string | null;
  synthetic_record_count: number;
  latest_data_quality_warnings: Array<{
    code: string;
    message: string;
    count: number;
  }>;
};

export type ControlPlaneOverview = {
  mode: "empty" | "demo" | "production_evidence";
  latest_gate: {
    id: UUID;
    verdict: GateEvaluation["verdict"];
    evidence_trust_status: EvidenceTrustStatus;
    production_readiness: ProductionReadiness;
    decision_summary: string;
    created_at: string;
  } | null;
  release_ready_configuration_count: number;
  needs_review_count: number;
  production_evidence_result_count: number;
  local_authored_result_count: number;
  synthetic_evidence_result_count: number;
  unknown_evidence_result_count: number;
  failed_critical_case_count: number;
  active_baseline_count: number;
  next_actions: Array<{
    priority: "high" | "medium" | "low";
    kind: string;
    title: string;
    description: string;
    href: string;
  }>;
  workflow_steps: Array<{
    key: string;
    label: string;
    status: "complete" | "attention" | "not_started";
    href: string;
  }>;
  inventory: OverviewResponse;
  recent_runs: Array<{
    id: UUID;
    status: string;
    runtime_name: string;
    data_source: string;
    started_at: string;
  }>;
};

export type ReferenceMetricSet = {
  mean_quality_score: number | null;
  json_validity_rate: number | null;
  tool_selection_accuracy: number | null;
  tool_argument_validity_rate: number | null;
  tool_execution_success_rate: number | null;
  tool_sequence_success_rate: number | null;
  rag_retrieval_recall: number | null;
  rag_groundedness_score: number | null;
  rag_unsupported_claim_rate: number | null;
  agent_task_success_rate: number | null;
  task_completion_rate: number | null;
  critical_case_failure_rate: number | null;
  p95_end_to_end_latency_ms: number | null;
  oom_rate: number | null;
};

export type ReferenceConfiguration = {
  entry_name: string;
  enabled: boolean;
  status: "completed" | "not_run" | "disabled";
  deployment_configuration_id: UUID | null;
  configuration_hash: string | null;
  model_artifact_id: UUID | null;
  model_name: string | null;
  model_digest: string | null;
  digest_status: "observed" | "missing" | "not_run";
  runtime_name: string | null;
  runtime_version: string | null;
  context_length: number;
  prompt_bundle: string;
  generation_config: Record<string, unknown>;
  concurrency: number;
  latest_run_id: UUID | null;
  latest_run_started_at: string | null;
  latest_run_completed_at: string | null;
  data_source: string | null;
  completed_case_count: number;
  result_count: number;
  metric_count: number;
  minimum_trials_per_case: number;
  maximum_trials_per_case: number;
  error_count: number;
  timeout_count: number;
  oom_count: number;
  critical_failure_count: number;
  human_reviewed_count: number;
  metrics: ReferenceMetricSet;
  gate_evaluation_id: UUID | null;
  gate_verdict: string;
};

export type ReferenceMetricComparisonRow = {
  entry_name: string;
  deployment_configuration_id: UUID | null;
  benchmark_run_id: UUID | null;
  model_name: string | null;
  prompt_bundle: string;
  metrics: ReferenceMetricSet;
  delta_from_baseline: Record<string, number | null>;
};

export type ReferenceCriticalFailure = {
  benchmark_result_id: UUID;
  benchmark_run_id: UUID;
  deployment_configuration_id: UUID;
  entry_name: string;
  evaluation_case_id: UUID;
  external_case_id: string;
  title: string;
  category: string;
  criticality: string;
  sample_id: string;
  failure_reason: string;
  expected_contract_summary: string;
  observed_output_summary: string;
  quality_score: number | null;
  groundedness_score: number | null;
  faithfulness_score: number | null;
  evidence_source: string;
  review_status: string;
  benchmark_execution_href: string;
  judge_review_href: string;
  gate_detail_href: string | null;
};

export type ReferenceReviewPriority = "P0" | "P1" | "P2";

export type ReferenceReviewCandidateAssessment = {
  schema_version: string;
  source: "deterministic_failure_triage";
  candidate_label: string;
  quality_score: number | null;
  groundedness_score: number | null;
  faithfulness_score: number | null;
  confidence: "high" | "medium";
  basis: string[];
  assessment_hash: string;
  applied: false;
  human_reviewed: false;
};

export type ReferenceOutputReviewPlan = {
  schema_version: string;
  generated_at: string;
  plan_hash: string;
  comparison_hash: string;
  status: "empty" | "ready_for_human_review";
  total_failure_count: number;
  cluster_count: number;
  target_review_count: number;
  selected_result_count: number;
  selected_unique_case_count: number;
  selected_category_count: number;
  selected_configuration_count: number;
  currently_human_reviewed_count: number;
  remaining_human_review_target: number;
  priority_counts: Record<ReferenceReviewPriority, number>;
  clusters: Array<{
    cluster_key: string;
    external_case_id: string;
    title: string;
    category: string;
    failure_reason: string;
    priority: ReferenceReviewPriority;
    priority_reasons: string[];
    occurrence_count: number;
    configuration_count: number;
    configuration_names: string[];
    unreviewed_count: number;
    mean_quality_score: number | null;
    minimum_quality_score: number | null;
    representative_result_id: UUID;
    representative_review_href: string;
  }>;
  selected_items: Array<{
    rank: number;
    cluster_key: string;
    priority: ReferenceReviewPriority;
    priority_reasons: string[];
    failure: ReferenceCriticalFailure;
    candidate_assessment: ReferenceReviewCandidateAssessment;
  }>;
  limitations: string[];
};

export type ReferenceWorkloadOverview = {
  schema_version: string;
  generated_at: string;
  workload: {
    id: UUID | null;
    name: string;
    slug: string;
    version: string;
    description: string;
    domain: string;
    primary_language: string;
    local_only_required: boolean;
    evaluation_suite_id: UUID | null;
    evaluation_suite_name: string;
    evaluation_suite_status: string;
    evaluation_suite_hash: string | null;
  };
  manifest: {
    schema_version: string;
    manifest_hash: string;
    file_count: number;
    total_bytes: number;
    source_paths: string[];
  };
  corpus: {
    corpus_id: string;
    corpus_version: string;
    corpus_hash: string;
    chunking_version: string;
    chunk_count: number;
  };
  case_coverage: {
    case_count: number;
    active_case_count: number;
    approved_case_count: number;
    approved_critical_case_count: number;
    critical_case_count: number;
    draft_case_count: number;
    rejected_case_count: number;
    category_counts: Record<string, number>;
    critical_category_counts: Record<string, number>;
    source_review_coverage_rate: number;
  };
  review_coverage: {
    result_count: number;
    human_reviewed_count: number;
    applied_judge_label_count: number;
    critical_result_count: number;
    critical_reviewed_count: number;
    human_review_coverage_rate: number;
    critical_review_coverage_rate: number;
    target_review_count: number;
    remaining_to_target: number;
  };
  evaluation_status: "COMPLETE" | "INCOMPLETE";
  configuration_matrix: ReferenceConfiguration[];
  latest_runs: Array<{
    id: UUID;
    entry_name: string;
    deployment_configuration_id: UUID;
    status: string;
    data_source: string;
    result_count: number;
    started_at: string;
    completed_at: string | null;
    benchmark_execution_href: string;
  }>;
  metric_comparison: ReferenceMetricComparisonRow[];
  comparison_hash: string;
  critical_failure_count: number;
  critical_failures: ReferenceCriticalFailure[];
  gate_outcomes: Array<{
    entry_name: string;
    deployment_configuration_id: UUID | null;
    gate_evaluation_id: UUID | null;
    verdict: string;
    evidence_trust_status: string;
    release_readiness: string;
    production_readiness: string;
    decision_summary: string;
    gate_detail_href: string | null;
  }>;
  gate_verdict: string;
  evidence_trust: EvidenceTrustSummary;
  actual_runtime_result_count: number;
  production_captured_result_count: number;
  production_readiness: "not_production_ready" | "production_ready";
  portfolio_completion: {
    status: "incomplete" | "ready";
    checks: Array<{
      key: string;
      label: string;
      passed: boolean;
      observed: number | string;
      required: number | string;
      href: string | null;
    }>;
    next_actions: Array<{
      priority: "high" | "medium" | "low";
      title: string;
      description: string;
      href: string;
    }>;
  };
  reproduction_commands: string[];
  limitations: string[];
};

export type BenchmarkTask = {
  id: UUID;
  name: string;
  category: string;
  description: string;
  task_type: string;
  language: string;
  input_format: string;
  expected_output_format: string;
  scoring_method: string;
  dataset_version: string;
  is_active: boolean;
};

export type BenchmarkRun = {
  id: UUID;
  hardware_profile_id: UUID;
  model_artifact_id: UUID;
  benchmark_task_id: UUID;
  prompt_version_id: UUID;
  deployment_configuration_id: UUID | null;
  evaluation_suite_id: UUID | null;
  parent_benchmark_run_id: UUID | null;
  root_benchmark_run_id: UUID | null;
  revision_number: number;
  revision_reason: string | null;
  evidence_revision_hash: string | null;
  runtime_name: string;
  runtime_version: string | null;
  runtime_config_json: Record<string, unknown>;
  dataset_version: string;
  seed: number | null;
  started_at: string;
  completed_at: string | null;
  status: string;
  failure_reason: string | null;
  data_source: string;
};

export type PromptVersion = {
  id: UUID;
  name: string;
  benchmark_task_id: UUID;
  system_prompt: string;
  user_template: string;
  output_schema: Record<string, unknown> | null;
  prompt_hash: string;
  version_label: string;
  is_active: boolean;
  notes: string | null;
};

export type BenchmarkExecutionRead = {
  benchmark_run: BenchmarkRun;
  result_count: number;
  metric_count: number;
  log_count: number;
  tool_execution_summary: ToolExecutionSummary;
  rag_evaluation_summary: RagEvaluationSummary;
  runtime_reliability_summary: RuntimeReliabilitySummary;
  agent_execution_summary: AgentExecutionSummary;
};

export type ToolExecutionSummary = {
  schema_version: string;
  tool_case_count: number;
  call_count: number;
  successful_call_count: number;
  failed_call_count: number;
  retried_call_count: number;
  recovered_call_count: number;
  multi_step_case_count: number;
  invalid_call_case_count: number;
  selection_accuracy: number | null;
  argument_validity_rate: number | null;
  execution_success_rate: number | null;
  sequence_success_rate: number | null;
  retry_recovery_rate: number | null;
};

export type ToolDescriptor = {
  tool_id: string;
  tool_version: string;
  display_name: string;
  description: string;
  argument_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  capabilities: string[];
  side_effect_mode: "none" | "simulated";
  default_max_attempts: number;
};

export type ToolRegistry = {
  registry_id: string;
  registry_version: string;
  tool_count: number;
  tools: ToolDescriptor[];
};

export type ToolExecutionAttempt = {
  attempt_number: number;
  status: "success" | "failed";
  retryable: boolean;
  duration_ms: number;
  error_type: string | null;
  message: string | null;
};

export type ToolExecutionStep = {
  step_index: number;
  call_id: string;
  expected_tool_name: string | null;
  tool_name: string;
  arguments: Record<string, unknown>;
  selection_valid: boolean;
  arguments_valid: boolean;
  validation_errors: string[];
  execution_status: "success" | "failed" | "skipped";
  attempt_count: number;
  retry_count: number;
  recovered: boolean;
  output_valid: boolean;
  output_validation_errors: string[];
  output: Record<string, unknown> | null;
  error_type: string | null;
  error_message: string | null;
  duration_ms: number;
  attempts: ToolExecutionAttempt[];
};

export type ToolExecutionTrace = {
  schema_version: string;
  registry_id: string;
  registry_version: string;
  external_case_id: string;
  parse_valid: boolean;
  parse_error: string | null;
  call_valid: boolean;
  status: "success" | "partial_failure" | "failed" | "invalid_call";
  successful: boolean;
  sequence_match: boolean;
  expected_tool_sequence: string[];
  actual_tool_sequence: string[];
  selection_accuracy: number | null;
  argument_validity_rate: number | null;
  execution_success_rate: number | null;
  retry_recovery_rate: number | null;
  total_duration_ms: number;
  steps: ToolExecutionStep[];
};

export type ToolExecutionTraceRecord = {
  benchmark_result_id: UUID;
  evaluation_case_id: UUID | null;
  sample_id: string;
  case_title: string | null;
  criticality: string | null;
  trace: ToolExecutionTrace;
};

export type RagEvaluationSummary = {
  schema_version: string;
  rag_case_count: number;
  successful_case_count: number;
  failed_case_count: number;
  retrieval_empty_case_count: number;
  average_retrieval_recall: number | null;
  average_citation_precision: number | null;
  average_citation_recall: number | null;
  average_groundedness_score: number | null;
  average_unsupported_claim_rate: number | null;
  average_evidence_selection_recall: number | null;
  retrieval_contract_satisfied_count: number;
  citation_contract_satisfied_count: number;
  evidence_selection_contract_satisfied_count: number;
  alternative_evidence_match_count: number;
  low_confidence_selection_count: number;
  semantic_contract_case_count: number;
  semantic_contract_successful_case_count: number;
  required_fact_contract_satisfied_count: number;
  alternative_required_fact_match_count: number;
  bounded_answer_contract_case_count: number;
  bounded_answer_contract_satisfied_count: number;
  refusal_case_count: number;
  successful_refusal_case_count: number;
  average_required_fact_coverage: number | null;
  forbidden_claim_violation_count: number;
  corpus_versions: string[];
  retriever_versions: string[];
};

export type RagChunk = {
  chunk_id: string;
  document_id: string;
  title: string;
  text: string;
  metadata: Record<string, unknown>;
};

export type RagCorpusSummary = {
  corpus_id: string;
  corpus_version: string;
  display_name: string;
  description: string;
  language: string;
  chunk_count: number;
  document_count: number;
  corpus_hash: string;
};

export type RagCorpusRegistry = {
  registry_id: string;
  registry_version: string;
  corpus_count: number;
  corpora: RagCorpusSummary[];
};

export type RetrieverDescriptor = {
  retriever_id: string;
  retriever_version: string;
  display_name: string;
  capabilities: string[];
  input_schema_version: string;
  output_schema_version: string;
};

export type RetrievedChunk = {
  rank: number;
  chunk_id: string;
  document_id: string;
  title: string;
  text: string;
  score: number;
};

export type RagRetrievalTrace = {
  schema_version: string;
  registry_version: string;
  corpus_id: string;
  corpus_version: string;
  corpus_hash: string;
  retriever_id: string;
  retriever_version: string;
  query: string;
  top_k: number;
  min_score: number;
  evidence_contract_version?: string;
  expected_relevant_chunk_ids: string[];
  acceptable_evidence_groups?: string[][];
  retrieved_chunks: RetrievedChunk[];
  relevant_retrieved_chunk_ids: string[];
  matched_acceptable_chunk_ids?: string[];
  retrieval_recall: number;
  retrieval_contract_satisfied?: boolean;
  satisfied_evidence_group_index?: number | null;
  retrieval_latency_ms: number;
  status: "success" | "empty" | "invalid_config";
  errors: string[];
  evidence_selection?: {
    schema_version: string;
    selector_id: string;
    selector_version: string;
    candidate_count: number;
    selected_count: number;
    selected_chunk_ids: string[];
    confidence: "high" | "medium" | "low" | "none";
    abstain_recommended: boolean;
    applied_to_generation?: boolean;
    selections: Array<{
      selection_rank: number;
      source_rank: number;
      chunk_id: string;
      document_id: string;
      title: string;
      text: string;
      claim: string;
      score: number;
      confidence: "high" | "medium" | "low";
      query_coverage: number;
      boundary_signal: boolean;
    }>;
  };
  selected_relevant_chunk_ids: string[];
  selected_acceptable_chunk_ids?: string[];
  evidence_selection_recall: number;
  evidence_selection_contract_satisfied?: boolean;
  satisfied_selection_group_index?: number | null;
};

export type RagEvaluationTrace = {
  schema_version: string;
  status: "success" | "failed";
  successful: boolean;
  output_valid: boolean;
  output_error: string | null;
  answer: string;
  citations: string[];
  claims: string[];
  invalid_citation_ids: string[];
  correct_citation_ids: string[];
  citation_precision: number;
  citation_recall: number;
  citation_contract_satisfied?: boolean;
  satisfied_citation_group_index?: number | null;
  groundedness_score: number;
  unsupported_claim_count: number;
  unsupported_claim_rate: number;
  claim_support_scores: number[];
  semantic_contract_declared: boolean;
  semantic_contract_version?: string;
  semantic_contract_satisfied: boolean;
  must_refuse: boolean | null;
  refusal_detected: boolean;
  refusal_requirement_satisfied: boolean;
  required_facts: string[];
  acceptable_required_fact_groups?: string[][];
  required_fact_group_results?: Array<Array<{
    expectation: string;
    matched: boolean;
    score: number;
    matched_text: string;
    negated: boolean;
    threshold: number;
  }>>;
  required_fact_results: Array<{
    expectation: string;
    matched: boolean;
    score: number;
    matched_text: string;
    negated: boolean;
    threshold: number;
  }>;
  required_fact_coverage: number;
  required_fact_contract_satisfied?: boolean;
  matched_required_facts?: string[];
  satisfied_required_fact_group_index?: number | null;
  forbidden_claims: string[];
  forbidden_claim_results: Array<{
    expectation: string;
    matched: boolean;
    score: number;
    matched_text: string;
    negated: boolean;
    threshold: number;
  }>;
  forbidden_claim_violation_count: number;
  answer_contract_version?: string | null;
  answer_contract_strategy?: string | null;
  answer_contract_applied?: boolean;
  answer_contract_satisfied?: boolean;
  retrieval: RagRetrievalTrace;
};

export type RagEvaluationTraceRecord = {
  benchmark_result_id: UUID;
  evaluation_case_id: UUID | null;
  sample_id: string;
  case_title: string | null;
  criticality: string | null;
  trace: RagEvaluationTrace;
};

export type RuntimeReliabilitySummary = {
  schema_version: string;
  reliability_case_count: number;
  trial_count: number;
  expected_trial_count: number;
  success_count: number;
  timeout_count: number;
  oom_count: number;
  error_count: number;
  success_rate: number | null;
  timeout_rate: number | null;
  oom_rate: number | null;
  error_rate: number | null;
  p50_end_to_end_latency_ms: number | null;
  p95_end_to_end_latency_ms: number | null;
  p99_end_to_end_latency_ms: number | null;
  p50_ttft_ms: number | null;
  p95_ttft_ms: number | null;
  mean_tokens_per_second: number | null;
  latency_variation_coefficient: number | null;
  trial_coverage_rate: number | null;
  minimum_trials_per_case: number;
  maximum_trials_per_case: number;
  context_stress_trial_count: number;
  context_stress_success_rate: number | null;
  trace_versions: string[];
};

export type RuntimeReliabilityTrace = {
  schema_version: string;
  benchmark_run_id: UUID | null;
  external_case_id: string;
  trial_index: number;
  total_trials: number;
  concurrency: number;
  case_timeout_ms: number;
  status: "success" | "timeout" | "oom" | "error";
  successful: boolean;
  within_timeout: boolean;
  ttft_ms: number;
  end_to_end_latency_ms: number;
  tokens_per_second: number;
  prompt_tokens: number;
  completion_tokens: number;
  gpu_vram_used_mb: number | null;
  peak_memory_mb: number | null;
  oom_occurred: boolean;
  error_type: string | null;
  error_message: string | null;
  seed: number | null;
  context_tokens: number;
  context_window_tokens: number;
  context_utilization_ratio: number;
  context_stress: boolean;
};

export type RuntimeReliabilityTraceRecord = {
  benchmark_result_id: UUID;
  evaluation_case_id: UUID | null;
  sample_id: string;
  case_title: string | null;
  criticality: string | null;
  trace: RuntimeReliabilityTrace;
};

export type RuntimeReliabilityRun = {
  benchmark_run_id: UUID;
  deployment_configuration_id: UUID | null;
  runtime_name: string;
  runtime_version: string | null;
  dataset_version: string;
  summary: RuntimeReliabilitySummary;
};

export type RuntimeReliabilityComparison = {
  schema_version: string;
  left: RuntimeReliabilityRun;
  right: RuntimeReliabilityRun;
  right_minus_left: Record<string, number | null>;
  winner: "left" | "right" | "tie" | "insufficient_evidence";
  recommended_benchmark_run_id: UUID | null;
  reason: string;
};

export type BenchmarkExecutionDetail = {
  benchmark_run: BenchmarkRun;
  result_count: number;
  metric_count: number;
  log_count: number;
  tool_execution_summary: ToolExecutionSummary;
  tool_traces: ToolExecutionTraceRecord[];
  rag_evaluation_summary: RagEvaluationSummary;
  rag_traces: RagEvaluationTraceRecord[];
  runtime_reliability_summary: RuntimeReliabilitySummary;
  reliability_traces: RuntimeReliabilityTraceRecord[];
  agent_execution_summary: AgentExecutionSummary;
  agent_traces: AgentExecutionTraceRecord[];
};

export type RuntimeHealthRead = {
  adapter_name: string;
  healthy: boolean;
  message: string;
  details: Record<string, unknown>;
};

export type JudgeLabelScoreSource =
  | "applied_judge_label"
  | "human_reviewed"
  | "candidate_judge_label"
  | "heuristic"
  | "raw_label"
  | "unlabeled";

export type JudgeLabelReviewRow = {
  benchmark_result_id: UUID;
  benchmark_run_id: UUID;
  evaluation_case_id: UUID | null;
  sample_id: string;
  external_case_id: string | null;
  title: string | null;
  category: string | null;
  criticality: string | null;
  quality_score: number | null;
  groundedness_score: number | null;
  faithfulness_score: number | null;
  human_label: string | null;
  data_source: string;
  score_source: JudgeLabelScoreSource;
  candidate_judge_labels: Record<string, unknown> | null;
  judge_label_metadata: Record<string, unknown> | null;
  scorer_metadata: Record<string, unknown> | null;
  quality_delta_vs_candidate: number | null;
  needs_review: boolean;
};

export type JudgeLabelReviewResponse = {
  benchmark_run_id: UUID | null;
  benchmark_result_id: UUID | null;
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
  critical_result_count: number;
  critical_reviewed_count: number;
  critical_review_coverage_rate: number;
  average_quality_score: number | null;
  average_abs_quality_delta_vs_candidate: number | null;
  rows: JudgeLabelReviewRow[];
};

export type JudgeLabelImportSummary = {
  benchmark_run_id: string;
  label_count: number;
  matched_label_count: number;
  missing_result_count: number;
  applied: boolean;
  quality_label_count: number;
  average_abs_quality_delta: number | null;
  import_format_version: string;
};

export type PromptRegressionMetric = {
  value: number | null;
  sample_size: number;
  delta_vs_baseline: number | null;
};

export type PromptRegressionRow = {
  prompt_version_id: UUID;
  prompt_name: string;
  version_label: string;
  prompt_hash: string;
  benchmark_run_ids: UUID[];
  run_count: number;
  result_count: number;
  metric_count: number;
  data_sources: string[];
  is_baseline_prompt: boolean;
  mean_quality_score: PromptRegressionMetric;
  groundedness_score: PromptRegressionMetric;
  faithfulness_score: PromptRegressionMetric;
  json_validity_rate: PromptRegressionMetric;
  tool_call_validity_rate: PromptRegressionMetric;
  critical_case_failure_rate: PromptRegressionMetric;
  p95_end_to_end_latency_ms: PromptRegressionMetric;
  p95_ttft_ms: PromptRegressionMetric;
  mean_tokens_per_second: PromptRegressionMetric;
  oom_rate: PromptRegressionMetric;
  risk_flags: string[];
};

export type PromptRegressionReport = {
  deployment_configuration_id: UUID | null;
  evaluation_suite_id: UUID | null;
  acceptance_policy_id: UUID | null;
  baseline_gate_evaluation_id: UUID | null;
  baseline_prompt_version_id: UUID | null;
  row_count: number;
  rows: PromptRegressionRow[];
};

export type ExperimentLineageEventType =
  | "prompt_version_created"
  | "benchmark_run_created"
  | "benchmark_run_completed"
  | "benchmark_run_failed"
  | "gate_evaluation_completed"
  | "baseline_promoted"
  | "baseline_superseded"
  | "release_decision_signed";

export type ExperimentLineageEvent = {
  id: UUID;
  event_type: ExperimentLineageEventType;
  primary_entity_type:
    | "prompt_version"
    | "benchmark_run"
    | "gate_evaluation"
    | "deployment_baseline"
    | "release_decision";
  primary_entity_id: UUID;
  event_time: string;
  lineage_key: string;
  deployment_configuration_id: UUID | null;
  evaluation_suite_id: UUID | null;
  acceptance_policy_id: UUID | null;
  prompt_version_id: UUID | null;
  benchmark_run_id: UUID | null;
  gate_evaluation_id: UUID | null;
  deployment_baseline_id: UUID | null;
  release_decision_id: UUID | null;
  status: "recorded" | "superseded" | "failed";
  summary: string;
  metadata_json: Record<string, unknown> | null;
  data_source: string;
  created_at: string;
  updated_at: string;
};

export type ExperimentLineageReport = {
  event_count: number;
  lineage_count: number;
  benchmark_run_event_count: number;
  gate_event_count: number;
  baseline_event_count: number;
  release_decision_event_count: number;
  events: ExperimentLineageEvent[];
};

export type ModelComparisonRow = {
  model_artifact_id: UUID;
  model_name: string;
  artifact_name: string;
  benchmark_task_id: UUID;
  benchmark_task_name: string;
  average_quality_score: number | null;
  average_ttft_ms: number | null;
  average_end_to_end_latency_ms: number | null;
  average_tokens_per_second: number | null;
  average_vram_usage_mb: number | null;
  json_validity_rate: number | null;
  tool_call_validity_rate: number | null;
  benchmark_coverage_count: number;
};

export type RecommendationWeights = {
  quality: number;
  latency: number;
  throughput: number;
  vram_efficiency: number;
};

export type RecommendationRequest = {
  hardware_profile_id: UUID | null;
  benchmark_task_id: UUID | null;
  require_text: boolean;
  require_vision: boolean;
  require_tool_calling: boolean;
  require_structured_output: boolean;
  commercial_use_required: boolean;
  min_context_length: number | null;
  top_k: number;
  weights: RecommendationWeights;
};

export type EligibilityIssue = {
  artifact_name: string;
  reason_code: string;
  message: string;
};

export type RecommendationCandidate = {
  rank: number;
  model_id: UUID;
  model_name: string;
  provider: string;
  family: string;
  artifact_id: UUID;
  artifact_name: string;
  format: string;
  quantization: string | null;
  precision: string | null;
  recommended_vram_gb: number | null;
  context_limit: number;
  runtime_compatibility: string[];
  average_quality_score: number | null;
  average_ttft_ms: number | null;
  average_end_to_end_latency_ms: number | null;
  average_tokens_per_second: number | null;
  average_vram_usage_mb: number | null;
  json_validity_rate: number | null;
  tool_call_validity_rate: number | null;
  benchmark_coverage_count: number;
  quality_component: number;
  latency_component: number;
  throughput_component: number;
  vram_efficiency_component: number;
  raw_recommendation_score: number;
  evidence_confidence: number;
  confidence_penalty: number;
  recommendation_score: number;
  pareto_optimal: boolean;
  rationale: string[];
};

export type RecommendationReport = {
  hardware_profile_id: UUID;
  hardware_profile_name: string;
  benchmark_task_id: UUID | null;
  benchmark_task_name: string | null;
  request: RecommendationRequest;
  candidate_count: number;
  eligible_count: number;
  recommended_candidate: RecommendationCandidate | null;
  candidates: RecommendationCandidate[];
  pareto_frontier: RecommendationCandidate[];
  excluded: EligibilityIssue[];
  decision_summary: string;
};

export type RecommendationScenarioCreate = {
  name: string;
  description: string | null;
  request: RecommendationRequest;
};

export type RecommendationScenarioUpdate = {
  name?: string;
  description?: string | null;
  request?: RecommendationRequest;
};

export type RecommendationScenarioRead = RecommendationScenarioCreate & {
  id: UUID;
  created_at: string;
  updated_at: string;
};

export type WorkloadProfile = {
  id: UUID;
  name: string;
  slug: string;
  description: string;
  domain: string;
  primary_language: string;
  local_only_required: boolean;
  data_classification: string;
  expected_output_modes_json: string[];
  risk_notes: string | null;
  is_active: boolean;
};

export type EvaluationSuite = {
  id: UUID;
  workload_profile_id: UUID;
  name: string;
  version_label: string;
  description: string;
  suite_hash: string;
  status: "draft" | "completed" | "failed" | "stale";
  dataset_source: string;
  is_synthetic: boolean;
};

export type EvaluationCase = {
  id: UUID;
  evaluation_suite_id: UUID;
  external_case_id: string;
  category: string;
  title: string;
  criticality: "critical" | "standard" | "exploratory";
  weight: number;
  is_active: boolean;
  data_source: string;
};

export type MetricDefinition = {
  id: UUID;
  key: string;
  display_name: string;
  domain: string;
  aggregation: string;
  direction: string;
  unit: string | null;
  description: string;
  calculation_version: string;
  is_active: boolean;
};

export type DeploymentConfiguration = {
  id: UUID;
  name: string;
  workload_profile_id: UUID;
  hardware_profile_id: UUID;
  model_artifact_id: UUID;
  runtime_name: string;
  runtime_version: string | null;
  runtime_config_json: Record<string, unknown>;
  context_length: number;
  generation_config_json: Record<string, unknown>;
  prompt_bundle_json: Record<string, unknown>;
  output_schema_version: string | null;
  tool_schema_version: string | null;
  retrieval_config_json: Record<string, unknown> | null;
  concurrency_target: number;
  configuration_hash: string;
  status: string;
  notes: string | null;
};
