import type {
  AgentApprovalCheckpoint,
  AgentExecutionJob,
  AgentJobOverview,
  AgentTrafficSourceStatus,
  AgentRuntimeDescriptor,
  BenchmarkExecutionDetail,
  BenchmarkRun,
  BenchmarkTask,
  ControlPlaneOverview,
  AcceptancePolicy,
  AcceptancePolicyRule,
  DeploymentBaseline,
  DeploymentConfiguration,
  EvidenceTrustRoot,
  EvidenceTrustSource,
  EvidenceTrustSourceSchedule,
  EvidenceTrustSourceSync,
  EvaluationCase,
  EvaluationSuite,
  ExperimentLineageReport,
  GateEvaluation,
  HardwareProfile,
  IsolationPolicyRegistry,
  JudgeLabelReviewResponse,
  MetricDefinition,
  Model,
  ModelArtifact,
  ModelArtifactAttestation,
  ModelSupplyChainAttestation,
  ModelComparisonRow,
  ModelValidationReport,
  OperatorIdentity,
  OperationalMetrics,
  OperationalMemoryRegistry,
  OverviewResponse,
  PromptRegressionReport,
  PromptVersion,
  ProductionEvidenceReceipt,
  ReferenceOutputReviewPlan,
  ReferenceWorkloadOverview,
  RagCorpusRegistry,
  RecommendationReport,
  RecommendationScenarioRead,
  ReleaseDecision,
  ReleaseDecisionAction,
  ReleaseSnapshotDiff,
  ReleaseReadinessSnapshot,
  RuntimeReliabilityComparison,
  SupplyChainOverview,
  TransparencyProof,
  TrustRegistryOverview,
  ToolRegistry,
  RetrieverDescriptor,
  WorkloadProfile
} from "@/types/api";
import { SERVER_API_BASE_URL } from "@/lib/apiBase";

const emptyOverview: OverviewResponse = {
  model_count: 0,
  model_artifact_count: 0,
  benchmark_task_count: 0,
  benchmark_run_count: 0,
  benchmark_result_count: 0,
  latest_benchmark_run_timestamp: null,
  synthetic_record_count: 0,
  latest_data_quality_warnings: []
};

const emptyControlPlaneOverview: ControlPlaneOverview = {
  mode: "empty",
  latest_gate: null,
  release_ready_configuration_count: 0,
  needs_review_count: 0,
  production_evidence_result_count: 0,
  local_authored_result_count: 0,
  synthetic_evidence_result_count: 0,
  unknown_evidence_result_count: 0,
  failed_critical_case_count: 0,
  active_baseline_count: 0,
  next_actions: [
    {
      priority: "high",
      kind: "workload",
      title: "Define a workload",
      description: "Create the first versioned workload and evaluation suite.",
      href: "/workloads"
    },
    {
      priority: "high",
      kind: "configuration",
      title: "Configure a deployment",
      description: "Bind a model artifact, runtime, hardware, prompt, and workload.",
      href: "/deployments"
    }
  ],
  workflow_steps: [
    { key: "define_workload", label: "Define Workload", status: "not_started", href: "/workloads" },
    { key: "configure_deployment", label: "Configure Deployment", status: "not_started", href: "/deployments" },
    { key: "execute_evaluation", label: "Execute Evaluation", status: "not_started", href: "/benchmark-executions/new" },
    { key: "evaluate_gate", label: "Evaluate Gate", status: "not_started", href: "/deployment-gates/new" },
    { key: "review_evidence", label: "Review Evidence", status: "not_started", href: "/judge-labels" },
    { key: "sign_release", label: "Sign Release Decision", status: "not_started", href: "/release-decisions" }
  ],
  inventory: emptyOverview,
  recent_runs: []
};

export const emptyReferenceWorkloadOverview: ReferenceWorkloadOverview = {
  schema_version: "model-atlas-reference-workload-overview-v1",
  generated_at: new Date(0).toISOString(),
  workload: {
    id: null,
    name: "Model Atlas Korean Operator Assistant",
    slug: "model-atlas-operator-assistant-ko",
    version: "unavailable",
    description: "Reference workload data is unavailable.",
    domain: "ai_platform_operations",
    primary_language: "ko",
    local_only_required: true,
    evaluation_suite_id: null,
    evaluation_suite_name: "Reference evaluation suite",
    evaluation_suite_status: "unavailable",
    evaluation_suite_hash: null
  },
  manifest: {
    schema_version: "unavailable",
    manifest_hash: "",
    file_count: 0,
    total_bytes: 0,
    source_paths: []
  },
  corpus: {
    corpus_id: "unavailable",
    corpus_version: "unavailable",
    corpus_hash: "",
    chunking_version: "unavailable",
    chunk_count: 0
  },
  case_coverage: {
    case_count: 0,
    active_case_count: 0,
    approved_case_count: 0,
    approved_critical_case_count: 0,
    critical_case_count: 0,
    draft_case_count: 0,
    rejected_case_count: 0,
    category_counts: {},
    critical_category_counts: {},
    source_review_coverage_rate: 0
  },
  review_coverage: {
    result_count: 0,
    human_reviewed_count: 0,
    applied_judge_label_count: 0,
    critical_result_count: 0,
    critical_reviewed_count: 0,
    human_review_coverage_rate: 0,
    critical_review_coverage_rate: 0,
    target_review_count: 30,
    remaining_to_target: 30
  },
  evaluation_status: "INCOMPLETE",
  configuration_matrix: [],
  latest_runs: [],
  metric_comparison: [],
  comparison_hash: "",
  critical_failure_count: 0,
  critical_failures: [],
  gate_outcomes: [],
  gate_verdict: "NOT_EVALUATED",
  evidence_trust: {
    source_distribution: {},
    score_distribution: {},
    total_result_count: 0,
    synthetic_demo_count: 0,
    local_authored_count: 0,
    production_captured_count: 0,
    unverified_production_captured_count: 0,
    external_benchmark_count: 0,
    unknown_source_count: 0,
    heuristic_only_count: 0,
    candidate_judge_label_count: 0,
    applied_judge_label_count: 0,
    human_reviewed_count: 0,
    unknown_score_count: 0,
    critical_result_count: 0,
    critical_reviewed_count: 0,
    applied_judge_label_rate: 0,
    critical_review_coverage_rate: 0,
    trust_status: "unknown",
    production_readiness: "unknown",
    reasons: [],
    limitations: []
  },
  actual_runtime_result_count: 0,
  production_captured_result_count: 0,
  production_readiness: "not_production_ready",
  portfolio_completion: {
    status: "incomplete",
    checks: [],
    next_actions: []
  },
  reproduction_commands: [],
  limitations: ["Reference workload API is unavailable."]
};

const emptyRecommendationReport: RecommendationReport = {
  hardware_profile_id: "",
  hardware_profile_name: "No hardware profile",
  benchmark_task_id: null,
  benchmark_task_name: null,
  request: {
    hardware_profile_id: null,
    benchmark_task_id: null,
    require_text: true,
    require_vision: false,
    require_tool_calling: false,
    require_structured_output: false,
    commercial_use_required: false,
    min_context_length: null,
    top_k: 5,
    weights: {
      quality: 0.45,
      latency: 0.2,
      throughput: 0.2,
      vram_efficiency: 0.15
    }
  },
  candidate_count: 0,
  eligible_count: 0,
  recommended_candidate: null,
  candidates: [],
  pareto_frontier: [],
  excluded: [],
  decision_summary: "No recommendation report is available."
};

const emptyJudgeLabelReview: JudgeLabelReviewResponse = {
  benchmark_run_id: null,
  benchmark_result_id: null,
  result_count: 0,
  reviewed_count: 0,
  candidate_label_count: 0,
  heuristic_scored_count: 0,
  heuristic_only_count: 0,
  applied_label_count: 0,
  human_reviewed_count: 0,
  unlabeled_count: 0,
  needs_review_count: 0,
  applied_label_coverage_rate: 0,
  critical_result_count: 0,
  critical_reviewed_count: 0,
  critical_review_coverage_rate: 0,
  average_quality_score: null,
  average_abs_quality_delta_vs_candidate: null,
  rows: []
};

const emptyReferenceOutputReviewPlan: ReferenceOutputReviewPlan = {
  schema_version: "model-atlas-reference-output-review-plan-v1",
  generated_at: new Date(0).toISOString(),
  plan_hash: "unavailable",
  comparison_hash: "unavailable",
  status: "empty",
  total_failure_count: 0,
  cluster_count: 0,
  target_review_count: 30,
  selected_result_count: 0,
  selected_unique_case_count: 0,
  selected_category_count: 0,
  selected_configuration_count: 0,
  currently_human_reviewed_count: 0,
  remaining_human_review_target: 30,
  priority_counts: { P0: 0, P1: 0, P2: 0 },
  clusters: [],
  selected_items: [],
  limitations: ["The output review plan is unavailable."]
};

const emptyPromptRegressionReport: PromptRegressionReport = {
  deployment_configuration_id: null,
  evaluation_suite_id: null,
  acceptance_policy_id: null,
  baseline_gate_evaluation_id: null,
  baseline_prompt_version_id: null,
  row_count: 0,
  rows: []
};

const emptyToolRegistry: ToolRegistry = {
  registry_id: "model_atlas_local_tools",
  registry_version: "unavailable",
  tool_count: 0,
  tools: []
};

const emptyRagCorpusRegistry: RagCorpusRegistry = {
  registry_id: "model_atlas_local_rag_corpora",
  registry_version: "unavailable",
  corpus_count: 0,
  corpora: []
};

const emptyRetrieverDescriptor: RetrieverDescriptor = {
  retriever_id: "unavailable",
  retriever_version: "unavailable",
  display_name: "Retriever unavailable",
  capabilities: [],
  input_schema_version: "unavailable",
  output_schema_version: "unavailable"
};

const emptyAgentRuntime: AgentRuntimeDescriptor = {
  runtime_id: "model_atlas_bounded_agent",
  runtime_version: "unavailable",
  trace_schema_version: "unavailable",
  context_schema_version: "unavailable",
  observation_schema_version: "unavailable",
  recovery_policy_version: "unavailable",
  approval_policy_version: "unavailable",
  live_replan_callback_version: "unavailable",
  allowed_actions: [],
  limits: {},
  tool_registry_version: "unavailable",
  memory_registry_version: "unavailable",
  corpus_version: "unavailable",
  retriever_version: "unavailable",
  memory_write_mode: "task_local_simulated",
  approval_decision_mode: "external_request_only"
};

const emptyOperationalMemoryRegistry: OperationalMemoryRegistry = {
  registry_id: "model_atlas_operational_memory",
  registry_version: "unavailable",
  record_count: 0,
  records: []
};

const emptySupplyChainOverview: SupplyChainOverview = {
  schema_version: "model-supply-chain-overview-v2",
  publisher_trust_configured: false,
  production_evidence_trust_configured: false,
  verified_attestation_count: 0,
  revoked_attestation_count: 0,
  production_receipt_count: 0,
  managed_attestation_count: 0,
  production_eligible_attestation_count: 0,
  transparency_proof_count: 0,
  production_eligible_receipt_count: 0,
  unverified_production_run_count: 0
};

const emptyTrustRegistryOverview: TrustRegistryOverview = {
  schema_version: "model-atlas-trust-registry-overview-v3",
  trust_source_count: 0,
  healthy_source_count: 0,
  degraded_source_count: 0,
  stale_source_count: 0,
  failed_source_count: 0,
  unsynced_source_count: 0,
  automatic_schedule_count: 0,
  automatic_schedule_enabled_count: 0,
  automatic_schedule_due_count: 0,
  automatic_schedule_retrying_count: 0,
  automatic_schedule_failed_count: 0,
  active_root_count: 0,
  production_eligible_root_count: 0,
  retired_root_count: 0,
  revoked_root_count: 0,
  expired_root_count: 0,
  scheduled_root_count: 0,
  transparency_proof_count: 0,
  production_eligible_proof_count: 0,
  managed_attestation_count: 0,
  production_eligible_attestation_count: 0,
  production_tier_attestation_pending_count: 0
};

const emptyExperimentLineageReport: ExperimentLineageReport = {
  event_count: 0,
  lineage_count: 0,
  benchmark_run_event_count: 0,
  gate_event_count: 0,
  baseline_event_count: 0,
  release_decision_event_count: 0,
  events: []
};

const emptyOperatorIdentity: OperatorIdentity = {
  subject_id: "local-ui",
  display_name: "Local UI",
  role: null,
  identity_provider: "local-ui",
  auth_source: "none",
  identity_verified: false,
  ticket_reference: null,
  release_permissions: {
    policy_version: "release-approval-rbac-v1",
    decisions: {
      APPROVE_RELEASE: {
        policy_version: "release-approval-rbac-v1",
        decision: "APPROVE_RELEASE",
        allowed: false,
        requires_verified_identity: true,
        allowed_roles: ["Release Manager", "ML Ops Lead", "Model Governance", "Admin"],
        signer_role: null,
        identity_verified: false,
        reasons: ["APPROVE_RELEASE requires verified operator identity."]
      },
      REJECT_RELEASE: {
        policy_version: "release-approval-rbac-v1",
        decision: "REJECT_RELEASE",
        allowed: false,
        requires_verified_identity: true,
        allowed_roles: ["Release Manager", "ML Ops Lead", "Model Governance", "Admin"],
        signer_role: null,
        identity_verified: false,
        reasons: ["REJECT_RELEASE requires verified operator identity."]
      },
      REQUEST_CHANGES: {
        policy_version: "release-approval-rbac-v1",
        decision: "REQUEST_CHANGES",
        allowed: true,
        requires_verified_identity: false,
        allowed_roles: [
          "Release Manager",
          "ML Ops Lead",
          "Model Governance",
          "Admin",
          "ML Engineer",
          "QA Lead",
          "SRE Lead"
        ],
        signer_role: null,
        identity_verified: false,
        reasons: []
      }
    }
  },
  session_permissions: {
    policy_version: "oidc-session-administration-rbac-v1",
    can_audit: false,
    can_administer: false,
    auditor_roles: [],
    administrator_roles: [],
    identity_verified: false,
    signer_role: null
  }
};

const emptyAgentJobOverview: AgentJobOverview = {
  schema_version: "agent-job-operations-v1",
  generated_at: new Date(0).toISOString(),
  health: "idle",
  total_job_count: 0,
  status_counts: {},
  job_type_counts: {},
  queue_depth: 0,
  retrying_count: 0,
  active_lease_count: 0,
  expired_lease_count: 0,
  dead_letter_count: 0,
  oldest_queued_age_seconds: null,
  completed_last_24h: 0,
  failed_last_24h: 0,
  success_rate_last_24h: null,
  average_queue_latency_ms: null,
  average_execution_duration_ms: null,
  online_worker_count: 0,
  workers: []
};

const emptyOperationalMetrics: OperationalMetrics = {
  schema_version: "model-atlas-operational-metrics-v1",
  generated_at: new Date(0).toISOString(),
  health: "healthy",
  samples: [],
  alerts: []
};

const emptyIsolationPolicyRegistry: IsolationPolicyRegistry = {
  registry_version: "workload-isolation-registry-v1",
  policy_count: 0,
  policies: []
};

async function fetchJson<T>(path: string, fallback: T): Promise<T> {
  try {
    const response = await fetch(`${SERVER_API_BASE_URL}${path}`, { cache: "no-store" });
    if (!response.ok) {
      return fallback;
    }
    return (await response.json()) as T;
  } catch {
    return fallback;
  }
}

export const api = {
  overview: () => fetchJson<OverviewResponse>("/analytics/overview", emptyOverview),
  controlPlaneOverview: () =>
    fetchJson<ControlPlaneOverview>(
      "/analytics/control-plane-overview",
      emptyControlPlaneOverview
    ),
  referenceWorkloadOverview: () =>
    fetchJson<ReferenceWorkloadOverview>(
      "/reference-workload/overview",
      emptyReferenceWorkloadOverview
    ),
  referenceOutputReviewPlan: (targetCount = 30) =>
    fetchJson<ReferenceOutputReviewPlan>(
      `/reference-workload/output-review-plan?target_count=${targetCount}`,
      emptyReferenceOutputReviewPlan
    ),
  modelComparison: () => fetchJson<ModelComparisonRow[]>("/analytics/model-comparison", []),
  hardwareProfiles: () => fetchJson<HardwareProfile[]>("/hardware-profiles", []),
  models: () => fetchJson<Model[]>("/models", []),
  modelArtifacts: () => fetchJson<ModelArtifact[]>("/model-artifacts", []),
  benchmarkTasks: () => fetchJson<BenchmarkTask[]>("/benchmark-tasks", []),
  promptVersions: () => fetchJson<PromptVersion[]>("/prompt-versions", []),
  benchmarkRuns: () => fetchJson<BenchmarkRun[]>("/benchmark-runs?limit=50", []),
  benchmarkExecution: (id: string) =>
    fetchJson<BenchmarkExecutionDetail | null>(`/benchmark-executions/${id}`, null),
  agentApprovalCheckpoints: (benchmarkRunId: string) =>
    fetchJson<AgentApprovalCheckpoint[]>(
      `/agents/checkpoints?benchmark_run_id=${encodeURIComponent(benchmarkRunId)}&limit=500`,
      []
    ),
  agentJobs: () =>
    fetchJson<AgentExecutionJob[]>("/agents/jobs?limit=200", []),
  agentJobOverview: () =>
    fetchJson<AgentJobOverview>(
      "/agents/jobs/overview",
      emptyAgentJobOverview
    ),
  agentTrafficSources: () =>
    fetchJson<AgentTrafficSourceStatus[]>(
      "/agents/evidence/traffic-sources",
      []
    ),
  modelValidationReport: (params: URLSearchParams) =>
    fetchJson<ModelValidationReport | null>(
      `/model-validation/report?${params.toString()}`,
      null
    ),
  modelArtifactAttestations: () =>
    fetchJson<ModelArtifactAttestation[]>(
      "/model-validation/artifact-attestations?limit=500",
      []
    ),
  supplyChainOverview: () =>
    fetchJson<SupplyChainOverview>(
      "/supply-chain/overview",
      emptySupplyChainOverview
    ),
  modelSupplyChainAttestations: () =>
    fetchJson<ModelSupplyChainAttestation[]>(
      "/supply-chain/model-attestations?limit=500",
      []
    ),
  productionEvidenceReceipts: () =>
    fetchJson<ProductionEvidenceReceipt[]>(
      "/supply-chain/production-receipts?limit=500",
      []
    ),
  trustRegistryOverview: () =>
    fetchJson<TrustRegistryOverview>(
      "/trust-registry/overview",
      emptyTrustRegistryOverview
    ),
  evidenceTrustRoots: () =>
    fetchJson<EvidenceTrustRoot[]>("/trust-registry/roots?limit=500", []),
  evidenceTrustSources: () =>
    fetchJson<EvidenceTrustSource[]>("/trust-registry/sources?limit=500", []),
  evidenceTrustSourceSchedules: () =>
    fetchJson<EvidenceTrustSourceSchedule[]>(
      "/trust-registry/source-schedules?limit=500",
      []
    ),
  evidenceTrustSourceSyncs: () =>
    fetchJson<EvidenceTrustSourceSync[]>(
      "/trust-registry/source-syncs?limit=500",
      []
    ),
  transparencyProofs: () =>
    fetchJson<TransparencyProof[]>(
      "/trust-registry/transparency-proofs?limit=500",
      []
    ),
  runtimeReliabilityComparison: (leftRunId: string, rightRunId: string) =>
    fetchJson<RuntimeReliabilityComparison | null>(
      `/runtime-reliability/compare?left_run_id=${encodeURIComponent(leftRunId)}&right_run_id=${encodeURIComponent(rightRunId)}`,
      null
    ),
  toolRegistry: () =>
    fetchJson<ToolRegistry>("/benchmark-executions/tool-registry", emptyToolRegistry),
  ragCorpusRegistry: () =>
    fetchJson<RagCorpusRegistry>("/rag/corpora", emptyRagCorpusRegistry),
  ragRetriever: () =>
    fetchJson<RetrieverDescriptor>("/rag/retriever", emptyRetrieverDescriptor),
  agentRuntime: () =>
    fetchJson<AgentRuntimeDescriptor>("/agents/runtime", emptyAgentRuntime),
  operationalMemoryRegistry: () =>
    fetchJson<OperationalMemoryRegistry>(
      "/agents/memory-registry",
      emptyOperationalMemoryRegistry
    ),
  workloads: () => fetchJson<WorkloadProfile[]>("/workloads", []),
  evaluationSuites: () => fetchJson<EvaluationSuite[]>("/evaluation-suites", []),
  evaluationCases: () => fetchJson<EvaluationCase[]>("/evaluation-cases?limit=200", []),
  metricDefinitions: () => fetchJson<MetricDefinition[]>("/metric-definitions", []),
  acceptancePolicies: () => fetchJson<AcceptancePolicy[]>("/acceptance-policies", []),
  acceptancePolicyRules: () =>
    fetchJson<AcceptancePolicyRule[]>("/acceptance-policy-rules?limit=200", []),
  deploymentConfigurations: () =>
    fetchJson<DeploymentConfiguration[]>("/deployment-configurations", []),
  deploymentBaselines: (options?: { activeOnly?: boolean }) => {
    const activeOnly = options?.activeOnly ?? true;
    return fetchJson<DeploymentBaseline[]>(
      `/deployment-gates/baselines?active_only=${activeOnly}&limit=200`,
      []
    );
  },
  gateEvaluations: () => fetchJson<GateEvaluation[]>("/deployment-gates/evaluations", []),
  gateEvaluation: (id: string) =>
    fetchJson<GateEvaluation | null>(`/deployment-gates/evaluations/${id}`, null),
  judgeLabelReview: (options?: {
    benchmarkRunId?: string;
    benchmarkResultId?: string;
  }) => {
    const params = new URLSearchParams({ limit: "200" });
    if (options?.benchmarkRunId) {
      params.set("benchmark_run_id", options.benchmarkRunId);
    }
    if (options?.benchmarkResultId) {
      params.set("benchmark_result_id", options.benchmarkResultId);
    }
    return fetchJson<JudgeLabelReviewResponse>(
      `/judge-labels/review?${params.toString()}`,
      {
        ...emptyJudgeLabelReview,
        benchmark_run_id: options?.benchmarkRunId ?? null,
        benchmark_result_id: options?.benchmarkResultId ?? null
      }
    );
  },
  promptRegressionReport: (params?: URLSearchParams) => {
    const query = params?.toString();
    const path = query ? `/prompt-regressions/report?${query}` : "/prompt-regressions/report";
    return fetchJson<PromptRegressionReport>(path, emptyPromptRegressionReport);
  },
  experimentLineageReport: (params?: URLSearchParams) => {
    const query = params?.toString();
    const path = query ? `/experiment-lineage/report?${query}` : "/experiment-lineage/report";
    return fetchJson<ExperimentLineageReport>(path, emptyExperimentLineageReport);
  },
  releaseReadinessSnapshot: (params?: URLSearchParams) => {
    const query = params?.toString();
    const path = query ? `/release-readiness/snapshot?${query}` : "/release-readiness/snapshot";
    return fetchJson<ReleaseReadinessSnapshot | null>(path, null);
  },
  releaseDecisions: (params?: URLSearchParams) => {
    const query = params?.toString();
    const path = query ? `/release-decisions?${query}` : "/release-decisions";
    return fetchJson<ReleaseDecision[]>(path, []);
  },
  releaseDecision: (id: string) => fetchJson<ReleaseDecision | null>(`/release-decisions/${id}`, null),
  releaseDecisionActions: (id: string) =>
    fetchJson<ReleaseDecisionAction[]>(
      `/release-decisions/${id}/actions`,
      []
    ),
  releaseDecisionSnapshotDiff: (id: string) =>
    fetchJson<ReleaseSnapshotDiff | null>(`/release-decisions/${id}/snapshot-diff`, null),
  operatorIdentity: () =>
    fetchJson<OperatorIdentity>("/operator-identity/me", emptyOperatorIdentity),
  operationalMetrics: () =>
    fetchJson<OperationalMetrics>("/operations/metrics", emptyOperationalMetrics),
  isolationPolicies: () =>
    fetchJson<IsolationPolicyRegistry>(
      "/isolation/policies",
      emptyIsolationPolicyRegistry
    ),
  recommendationScenarios: () =>
    fetchJson<RecommendationScenarioRead[]>("/recommendations/scenarios", []),
  recommendationReport: (params?: URLSearchParams) => {
    const query = params?.toString();
    const path = query ? `/recommendations/report?${query}` : "/recommendations/report";
    return fetchJson<RecommendationReport>(path, emptyRecommendationReport);
  }
};
