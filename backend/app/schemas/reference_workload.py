from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.evidence_trust import EvidenceTrustSummaryRead


class ReferenceWorkloadDefinitionRead(BaseModel):
    id: UUID | None = None
    name: str
    slug: str
    version: str
    description: str
    domain: str
    primary_language: str
    local_only_required: bool
    evaluation_suite_id: UUID | None = None
    evaluation_suite_name: str
    evaluation_suite_status: str
    evaluation_suite_hash: str | None = None


class ReferenceManifestRead(BaseModel):
    schema_version: str
    manifest_hash: str
    file_count: int
    total_bytes: int
    source_paths: list[str]


class ReferenceCorpusRead(BaseModel):
    corpus_id: str
    corpus_version: str
    corpus_hash: str
    chunking_version: str
    chunk_count: int


class ReferenceCaseCoverageRead(BaseModel):
    case_count: int
    active_case_count: int
    approved_case_count: int
    approved_critical_case_count: int
    critical_case_count: int
    draft_case_count: int
    rejected_case_count: int
    category_counts: dict[str, int]
    critical_category_counts: dict[str, int]
    source_review_coverage_rate: float


class ReferenceOutputReviewCoverageRead(BaseModel):
    result_count: int
    human_reviewed_count: int
    applied_judge_label_count: int
    critical_result_count: int
    critical_reviewed_count: int
    human_review_coverage_rate: float
    critical_review_coverage_rate: float
    target_review_count: int = 30
    remaining_to_target: int


class ReferenceMetricSetRead(BaseModel):
    mean_quality_score: float | None = None
    json_validity_rate: float | None = None
    tool_selection_accuracy: float | None = None
    tool_argument_validity_rate: float | None = None
    tool_execution_success_rate: float | None = None
    tool_sequence_success_rate: float | None = None
    rag_retrieval_recall: float | None = None
    rag_groundedness_score: float | None = None
    rag_unsupported_claim_rate: float | None = None
    agent_task_success_rate: float | None = None
    task_completion_rate: float | None = None
    critical_case_failure_rate: float | None = None
    p95_end_to_end_latency_ms: float | None = None
    oom_rate: float | None = None


class ReferenceConfigurationRead(BaseModel):
    entry_name: str
    enabled: bool
    status: Literal["completed", "not_run", "disabled"]
    deployment_configuration_id: UUID | None = None
    configuration_hash: str | None = None
    model_artifact_id: UUID | None = None
    model_name: str | None = None
    model_digest: str | None = None
    digest_status: Literal["observed", "missing", "not_run"]
    runtime_name: str | None = None
    runtime_version: str | None = None
    context_length: int
    prompt_bundle: str
    generation_config: dict[str, Any]
    concurrency: int
    latest_run_id: UUID | None = None
    latest_run_started_at: dt.datetime | None = None
    latest_run_completed_at: dt.datetime | None = None
    data_source: str | None = None
    completed_case_count: int = 0
    result_count: int = 0
    metric_count: int = 0
    minimum_trials_per_case: int = 0
    maximum_trials_per_case: int = 0
    error_count: int = 0
    timeout_count: int = 0
    oom_count: int = 0
    critical_failure_count: int = 0
    human_reviewed_count: int = 0
    metrics: ReferenceMetricSetRead
    gate_evaluation_id: UUID | None = None
    gate_verdict: str = "NOT_EVALUATED"


class ReferenceLatestRunRead(BaseModel):
    id: UUID
    entry_name: str
    deployment_configuration_id: UUID
    status: str
    data_source: str
    result_count: int
    started_at: dt.datetime
    completed_at: dt.datetime | None = None
    benchmark_execution_href: str


class ReferenceMetricComparisonRowRead(BaseModel):
    entry_name: str
    deployment_configuration_id: UUID | None = None
    benchmark_run_id: UUID | None = None
    model_name: str | None = None
    prompt_bundle: str
    metrics: ReferenceMetricSetRead
    delta_from_baseline: dict[str, float | None]


class ReferenceMetricComparisonRead(BaseModel):
    schema_version: str = "model-atlas-reference-workload-comparison-v1"
    baseline_entry_name: str | None = None
    generated_from_run_ids: list[UUID]
    comparison_hash: str
    rows: list[ReferenceMetricComparisonRowRead]


class ReferenceCriticalFailureRead(BaseModel):
    benchmark_result_id: UUID
    benchmark_run_id: UUID
    deployment_configuration_id: UUID
    entry_name: str
    evaluation_case_id: UUID
    external_case_id: str
    title: str
    category: str
    criticality: str
    sample_id: str
    failure_reason: str
    expected_contract_summary: str
    observed_output_summary: str
    quality_score: float | None = None
    groundedness_score: float | None = None
    faithfulness_score: float | None = None
    evidence_source: str
    review_status: str
    benchmark_execution_href: str
    judge_review_href: str
    gate_detail_href: str | None = None


class ReferenceReviewCandidateAssessmentRead(BaseModel):
    schema_version: str = "model-atlas-reference-review-candidate-v1"
    source: Literal["deterministic_failure_triage"] = "deterministic_failure_triage"
    candidate_label: str
    quality_score: float | None = None
    groundedness_score: float | None = None
    faithfulness_score: float | None = None
    confidence: Literal["high", "medium"]
    basis: list[str]
    assessment_hash: str
    applied: Literal[False] = False
    human_reviewed: Literal[False] = False


class ReferenceFailureClusterRead(BaseModel):
    cluster_key: str
    external_case_id: str
    title: str
    category: str
    failure_reason: str
    priority: Literal["P0", "P1", "P2"]
    priority_reasons: list[str]
    occurrence_count: int
    configuration_count: int
    configuration_names: list[str]
    unreviewed_count: int
    mean_quality_score: float | None = None
    minimum_quality_score: float | None = None
    representative_result_id: UUID
    representative_review_href: str


class ReferenceOutputReviewItemRead(BaseModel):
    rank: int
    cluster_key: str
    priority: Literal["P0", "P1", "P2"]
    priority_reasons: list[str]
    failure: ReferenceCriticalFailureRead
    candidate_assessment: ReferenceReviewCandidateAssessmentRead


class ReferenceOutputReviewPlanRead(BaseModel):
    schema_version: str = "model-atlas-reference-output-review-plan-v1"
    generated_at: dt.datetime
    plan_hash: str
    comparison_hash: str
    status: Literal["empty", "ready_for_human_review"]
    total_failure_count: int
    cluster_count: int
    target_review_count: int
    selected_result_count: int
    selected_unique_case_count: int
    selected_category_count: int
    selected_configuration_count: int
    currently_human_reviewed_count: int
    remaining_human_review_target: int
    priority_counts: dict[str, int]
    clusters: list[ReferenceFailureClusterRead]
    selected_items: list[ReferenceOutputReviewItemRead]
    limitations: list[str]


class ReferenceGateOutcomeRead(BaseModel):
    entry_name: str
    deployment_configuration_id: UUID | None = None
    gate_evaluation_id: UUID | None = None
    verdict: str
    evidence_trust_status: str
    release_readiness: str
    production_readiness: str
    decision_summary: str
    gate_detail_href: str | None = None


class ReferencePortfolioCheckRead(BaseModel):
    key: str
    label: str
    passed: bool
    observed: int | str
    required: int | str
    href: str | None = None


class ReferenceNextActionRead(BaseModel):
    priority: Literal["high", "medium", "low"]
    title: str
    description: str
    href: str


class ReferencePortfolioCompletionRead(BaseModel):
    status: Literal["incomplete", "ready"]
    checks: list[ReferencePortfolioCheckRead]
    next_actions: list[ReferenceNextActionRead]


class ReferenceCaseRead(BaseModel):
    evaluation_case_id: UUID | None = None
    external_case_id: str
    title: str
    category: str
    criticality: str
    weight: float
    is_active: bool
    source_review_status: str
    source_reviewed_at: dt.datetime | None = None
    result_count: int
    failed_result_count: int
    human_reviewed_result_count: int


class ReferenceCaseListRead(BaseModel):
    schema_version: str = "model-atlas-reference-workload-cases-v1"
    workload_profile_id: UUID | None = None
    evaluation_suite_id: UUID | None = None
    coverage: ReferenceCaseCoverageRead
    cases: list[ReferenceCaseRead]


class ReferenceConfigurationListRead(BaseModel):
    schema_version: str = "model-atlas-reference-workload-configurations-v1"
    configurations: list[ReferenceConfigurationRead]


class ReferenceWorkloadOverviewRead(BaseModel):
    schema_version: str = "model-atlas-reference-workload-overview-v1"
    generated_at: dt.datetime
    workload: ReferenceWorkloadDefinitionRead
    manifest: ReferenceManifestRead
    corpus: ReferenceCorpusRead
    case_coverage: ReferenceCaseCoverageRead
    review_coverage: ReferenceOutputReviewCoverageRead
    evaluation_status: Literal["COMPLETE", "INCOMPLETE"]
    configuration_matrix: list[ReferenceConfigurationRead]
    latest_runs: list[ReferenceLatestRunRead]
    metric_comparison: list[ReferenceMetricComparisonRowRead]
    comparison_hash: str
    critical_failure_count: int
    critical_failures: list[ReferenceCriticalFailureRead]
    gate_outcomes: list[ReferenceGateOutcomeRead]
    gate_verdict: str
    evidence_trust: EvidenceTrustSummaryRead
    actual_runtime_result_count: int
    production_captured_result_count: int
    production_readiness: Literal["not_production_ready", "production_ready"]
    portfolio_completion: ReferencePortfolioCompletionRead
    reproduction_commands: list[str]
    limitations: list[str]


class ReferenceFailureListRead(BaseModel):
    schema_version: str = "model-atlas-reference-workload-failures-v1"
    total: int
    items: list[ReferenceCriticalFailureRead]
    limit: int = Field(ge=1, le=500)
    offset: int = Field(ge=0)


class ReferenceCategoryMetricRead(BaseModel):
    entry_name: str
    category: str
    result_count: int
    critical_result_count: int
    failed_result_count: int
    reviewed_result_count: int
    mean_quality_score: float | None = None
    exact_match_rate: float | None = None
    json_validity_rate: float | None = None
    tool_call_validity_rate: float | None = None
    mean_groundedness_score: float | None = None
    error_count: int


class ReferenceGateRuleResultRead(BaseModel):
    rule_name: str
    metric_key: str
    metric_value: float | None = None
    sample_size: int
    status: str
    severity: str
    details: dict[str, Any]


class ReferenceGateReportOutcomeRead(BaseModel):
    entry_name: str
    deployment_configuration_id: UUID
    gate_evaluation_id: UUID
    acceptance_policy_id: UUID
    status: str
    verdict: str
    decision_summary: str
    decision_hash: str
    evidence_revision_hash: str | None = None
    evaluated_at: dt.datetime
    stale: bool
    rule_results: list[ReferenceGateRuleResultRead]
    release_readiness: str
    release_summary: str
    production_readiness: str
    gate_detail_href: str
    release_readiness_href: str


class ReferenceLinkedEvidenceRead(BaseModel):
    workload_profile_id: UUID | None = None
    evaluation_suite_id: UUID | None = None
    deployment_configuration_ids: list[UUID]
    model_artifact_ids: list[UUID]
    benchmark_run_ids: list[UUID]
    benchmark_result_ids: list[UUID]
    critical_result_ids: list[UUID]
    gate_evaluation_ids: list[UUID]


class ReferenceWorkloadReportRead(BaseModel):
    schema_version: str = "reference-workload-report-v1"
    generated_at: dt.datetime
    workload: ReferenceWorkloadDefinitionRead
    manifest: ReferenceManifestRead
    corpus: ReferenceCorpusRead
    case_coverage: ReferenceCaseCoverageRead
    review_coverage: ReferenceOutputReviewCoverageRead
    evaluation_status: str
    configuration_matrix: list[ReferenceConfigurationRead]
    metric_comparison: list[ReferenceMetricComparisonRowRead]
    comparison_hash: str
    category_metrics: list[ReferenceCategoryMetricRead]
    critical_failures: list[ReferenceCriticalFailureRead]
    gate_outcomes: list[ReferenceGateReportOutcomeRead]
    gate_verdict: str
    evidence_trust: EvidenceTrustSummaryRead
    release_readiness: str
    production_readiness: str
    portfolio_completion: ReferencePortfolioCompletionRead
    incomplete_matrix_entries: list[str]
    reproduction_commands: list[str]
    limitations: list[str]
    linked_evidence_ids: ReferenceLinkedEvidenceRead


class ReferenceReproductionArtifactRead(BaseModel):
    path: str
    sha256: str
    size_bytes: int


class ReferenceReproductionManifestRead(BaseModel):
    schema_version: str = "model-atlas-reference-reproduction-manifest-v1"
    generated_at: dt.datetime
    report_schema_version: str
    report_sha256: str
    workload_slug: str
    workload_version: str
    manifest_hash: str
    corpus_hash: str
    evaluation_suite_hash: str | None = None
    comparison_hash: str
    production_readiness: str
    linked_evidence_ids: ReferenceLinkedEvidenceRead
    commands: list[str]
    artifacts: list[ReferenceReproductionArtifactRead]


class ReferenceGateRunEntryRead(BaseModel):
    entry_name: str
    status: Literal["created", "reused", "blocked", "not_run"]
    deployment_configuration_id: UUID | None = None
    gate_evaluation_id: UUID | None = None
    verdict: str | None = None
    preflight_can_evaluate: bool
    blocking_preconditions: list[str]
    warnings: list[str]


class ReferenceGateRunSummaryRead(BaseModel):
    schema_version: str = "model-atlas-reference-gate-run-summary-v1"
    generated_at: dt.datetime
    workload_profile_id: UUID
    evaluation_suite_id: UUID
    acceptance_policy_id: UUID
    created_count: int
    reused_count: int
    blocked_count: int
    entries: list[ReferenceGateRunEntryRead]
    production_readiness: Literal["not_production_ready"] = "not_production_ready"


class ReferenceArtifactWriteSummaryRead(BaseModel):
    schema_version: str = "model-atlas-reference-artifact-write-summary-v1"
    output_directory: str
    report_sha256: str
    artifacts: list[ReferenceReproductionArtifactRead]
    production_readiness: str
