from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.agent_execution import (
    AgentApprovalDecisionInput,
    AgentExecutionSummaryRead,
)
from app.schemas.runtime_reliability import RuntimeReliabilitySummaryRead
from app.schemas.tool_fault_scenarios import ToolFaultScenarioSummaryRead
from app.validators import (
    ensure_json_output_when_marked_valid,
    ensure_tool_call_output_when_marked_valid,
    ensure_utc_datetime,
)

_FORBIDDEN_ADAPTER_SECRET_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "authorization",
        "bearer_token",
        "client_secret",
        "headers",
        "password",
        "secret",
        "token",
    }
)
_ALLOWED_ADAPTER_SECRET_ENVS = {
    "api_key_env": "OPENAI_COMPATIBLE_API_KEY",
    "agent_replan_api_key_env": "AGENT_REPLAN_API_KEY",
}


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class HardwareProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    cpu_name: str = Field(min_length=1, max_length=160)
    cpu_cores: int = Field(gt=0)
    ram_gb: int = Field(gt=0)
    gpu_name: str = Field(min_length=1, max_length=160)
    gpu_vram_gb: int = Field(ge=0)
    gpu_count: int = Field(gt=0, default=1)
    os_name: str | None = None
    cuda_version: str | None = None
    driver_version: str | None = None
    notes: str | None = None


class HardwareProfileCreate(HardwareProfileBase):
    pass


class HardwareProfileRead(HardwareProfileBase, ReadModel):
    pass


class ModelBase(BaseModel):
    provider: str = Field(min_length=1, max_length=120)
    family: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    display_name: str = Field(min_length=1, max_length=180)
    parameter_count_b: float | None = Field(default=None, gt=0)
    architecture_type: str = Field(min_length=1, max_length=120)
    supports_text: bool = True
    supports_vision: bool = False
    supports_tool_calling: bool = False
    supports_structured_output: bool = False
    context_length: int = Field(gt=0)
    license_name: str | None = None
    commercial_use_allowed: bool | None = None
    primary_languages: list[str] = Field(default_factory=list)
    source_url: str | None = None
    notes: str | None = None


class ModelCreate(ModelBase):
    pass


class ModelRead(ModelBase, ReadModel):
    pass


class ModelArtifactBase(BaseModel):
    model_id: UUID
    artifact_name: str = Field(min_length=1, max_length=180)
    format: str = Field(min_length=1, max_length=80)
    quantization: str | None = None
    precision: str | None = None
    file_size_gb: float | None = Field(default=None, ge=0)
    minimum_vram_gb: float | None = Field(default=None, ge=0)
    recommended_vram_gb: float | None = Field(default=None, ge=0)
    context_limit: int = Field(gt=0)
    runtime_compatibility: list[str] = Field(default_factory=list)
    checksum: str | None = None
    is_active: bool = True
    notes: str | None = None


class ModelArtifactCreate(ModelArtifactBase):
    pass


class ModelArtifactRead(ModelArtifactBase, ReadModel):
    pass


class BenchmarkTaskBase(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    category: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1)
    task_type: str = Field(min_length=1, max_length=80)
    language: str = Field(min_length=1, max_length=80)
    input_format: str = Field(min_length=1, max_length=80)
    expected_output_format: str = Field(min_length=1, max_length=80)
    scoring_method: str = Field(min_length=1, max_length=120)
    dataset_version: str = Field(min_length=1, max_length=80)
    is_active: bool = True


class BenchmarkTaskCreate(BenchmarkTaskBase):
    pass


class BenchmarkTaskRead(BenchmarkTaskBase, ReadModel):
    pass


class PromptVersionBase(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    benchmark_task_id: UUID
    system_prompt: str = Field(min_length=1)
    user_template: str = Field(min_length=1)
    output_schema: dict[str, Any] | None = None
    prompt_hash: str = Field(min_length=1, max_length=128)
    version_label: str = Field(min_length=1, max_length=80)
    is_active: bool = True
    notes: str | None = None


class PromptVersionCreate(PromptVersionBase):
    pass


class PromptVersionRead(PromptVersionBase, ReadModel):
    pass


class BenchmarkRunBase(BaseModel):
    hardware_profile_id: UUID
    model_artifact_id: UUID
    benchmark_task_id: UUID
    prompt_version_id: UUID
    deployment_configuration_id: UUID | None = None
    evaluation_suite_id: UUID | None = None
    parent_benchmark_run_id: UUID | None = None
    root_benchmark_run_id: UUID | None = None
    revision_number: int = Field(default=1, ge=1)
    revision_reason: str | None = None
    evidence_revision_hash: str | None = None
    runtime_name: str = Field(min_length=1, max_length=120)
    runtime_version: str | None = None
    runtime_config_json: dict[str, Any] = Field(min_length=1)
    dataset_version: str = Field(min_length=1, max_length=80)
    seed: int | None = None
    started_at: datetime
    completed_at: datetime | None = None
    status: str = Field(default="completed", min_length=1, max_length=40)
    failure_reason: str | None = None
    data_source: str = Field(default="synthetic_demo", min_length=1, max_length=80)

    @field_validator("started_at", "completed_at")
    @classmethod
    def datetimes_must_be_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return ensure_utc_datetime(value, info.field_name)


class BenchmarkRunCreate(BenchmarkRunBase):
    pass


class BenchmarkRunRead(BenchmarkRunBase, ReadModel):
    pass


class BenchmarkResultBase(BaseModel):
    benchmark_run_id: UUID
    evaluation_case_id: UUID | None = None
    parent_benchmark_result_id: UUID | None = None
    root_benchmark_result_id: UUID | None = None
    revision_number: int = Field(default=1, ge=1)
    evidence_revision_hash: str | None = None
    sample_id: str = Field(min_length=1, max_length=120)
    quality_score: float | None = Field(default=None, ge=0, le=1)
    exact_match: bool | None = None
    json_valid: bool = False
    tool_call_valid: bool = False
    groundedness_score: float | None = Field(default=None, ge=0, le=1)
    faithfulness_score: float | None = Field(default=None, ge=0, le=1)
    human_label: str | None = None
    error_type: str | None = None
    raw_output: str | None = None
    normalized_output: str | None = None
    metadata_json: dict[str, Any] | None = None
    data_source: str = Field(default="synthetic_demo", min_length=1, max_length=80)

    @model_validator(mode="after")
    def validate_output_flags(self) -> BenchmarkResultBase:
        ensure_json_output_when_marked_valid(self.json_valid, self.normalized_output)
        ensure_tool_call_output_when_marked_valid(self.tool_call_valid, self.normalized_output)
        return self


class BenchmarkResultCreate(BenchmarkResultBase):
    pass


class BenchmarkResultRead(BenchmarkResultBase, ReadModel):
    pass


class InferenceMetricBase(BaseModel):
    benchmark_run_id: UUID
    sample_id: str = Field(min_length=1, max_length=120)
    ttft_ms: float = Field(ge=0)
    end_to_end_latency_ms: float = Field(ge=0)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    tokens_per_second: float = Field(ge=0)
    gpu_vram_used_mb: float | None = Field(default=None, ge=0)
    gpu_utilization_pct: float | None = Field(default=None, ge=0, le=100)
    cpu_utilization_pct: float | None = Field(default=None, ge=0, le=100)
    peak_memory_mb: float | None = Field(default=None, ge=0)
    oom_occurred: bool = False
    retry_count: int = Field(default=0, ge=0)
    data_source: str = Field(default="synthetic_demo", min_length=1, max_length=80)


class InferenceMetricCreate(InferenceMetricBase):
    pass


class InferenceMetricRead(InferenceMetricBase, ReadModel):
    pass


class BenchmarkExecutionLogRead(ReadModel):
    benchmark_run_id: UUID
    event_type: str
    level: Literal["debug", "info", "warning", "error"]
    message: str
    payload_json: dict[str, Any] | None = None
    occurred_at: datetime
    data_source: str


class BenchmarkExecutionCreate(BaseModel):
    deployment_configuration_id: UUID
    evaluation_suite_id: UUID
    benchmark_task_id: UUID
    prompt_version_id: UUID
    adapter_name: Literal["mock", "openai_compatible"] = "mock"
    adapter_config_json: dict[str, Any] = Field(default_factory=dict)
    data_source: str = Field(default="local_authored", min_length=1, max_length=80)
    max_cases: int | None = Field(default=None, gt=0, le=500)
    evaluation_case_external_ids: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    seed: int | None = None
    reliability_mode: bool = False
    trials_per_case: int = Field(default=1, ge=1, le=20)
    concurrency: int = Field(default=1, ge=1, le=16)
    case_timeout_ms: int = Field(default=120_000, ge=100, le=300_000)
    isolation_policy_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
    )
    agent_live_replan_mode: Literal["disabled", "mock_fixture", "openai_compatible"] = "disabled"
    agent_approval_decisions: dict[str, AgentApprovalDecisionInput] = Field(default_factory=dict)

    @field_validator("adapter_config_json")
    @classmethod
    def reject_persisted_adapter_secrets(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        _validate_adapter_config_secrets(value)
        return value

    @field_validator("evaluation_case_external_ids")
    @classmethod
    def validate_case_external_ids(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [case_id.strip() for case_id in value]
        if any(not case_id or len(case_id) > 120 for case_id in normalized):
            raise ValueError("evaluation case external IDs must contain 1 to 120 characters")
        if len(normalized) != len(set(normalized)):
            raise ValueError("evaluation case external IDs must be unique")
        return normalized

    @field_validator("agent_approval_decisions")
    @classmethod
    def validate_agent_approval_decision_keys(
        cls,
        value: dict[str, AgentApprovalDecisionInput],
    ) -> dict[str, AgentApprovalDecisionInput]:
        if len(value) > 20:
            raise ValueError("agent approval decisions are limited to 20 checkpoints")
        if any(not key.strip() or len(key) > 120 for key in value):
            raise ValueError("agent approval checkpoint IDs must be 1-120 characters")
        return value

    @model_validator(mode="after")
    def validate_reliability_options(self) -> BenchmarkExecutionCreate:
        if not self.reliability_mode and (self.trials_per_case != 1 or self.concurrency != 1):
            raise ValueError("trials_per_case and concurrency require reliability_mode=true")
        if self.agent_live_replan_mode == "mock_fixture" and self.adapter_name != "mock":
            raise ValueError("mock_fixture live replan mode requires adapter_name=mock")
        return self


def _validate_adapter_config_secrets(
    value: Any,
    *,
    path: str = "adapter_config_json",
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            allowed_env = _ALLOWED_ADAPTER_SECRET_ENVS.get(normalized)
            if allowed_env is not None:
                if item != allowed_env:
                    raise ValueError(f"{path}.{key} must be {allowed_env}")
            elif (
                normalized in _FORBIDDEN_ADAPTER_SECRET_KEYS
                or normalized.endswith("_secret")
                or normalized.endswith("_password")
                or normalized.endswith("_token")
            ):
                raise ValueError(
                    f"{path}.{key} cannot persist credentials; "
                    "use an approved environment reference"
                )
            _validate_adapter_config_secrets(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_adapter_config_secrets(item, path=f"{path}[{index}]")


class ToolExecutionSummaryRead(BaseModel):
    schema_version: str = "tool-execution-summary-v1"
    tool_case_count: int = 0
    call_count: int = 0
    successful_call_count: int = 0
    failed_call_count: int = 0
    retried_call_count: int = 0
    recovered_call_count: int = 0
    multi_step_case_count: int = 0
    invalid_call_case_count: int = 0
    selection_accuracy: float | None = None
    argument_validity_rate: float | None = None
    execution_success_rate: float | None = None
    sequence_success_rate: float | None = None
    retry_recovery_rate: float | None = None
    fault_scenario_summary: ToolFaultScenarioSummaryRead | None = None


class RagEvaluationSummaryRead(BaseModel):
    schema_version: str = "rag-evaluation-summary-v5"
    rag_case_count: int = 0
    successful_case_count: int = 0
    failed_case_count: int = 0
    retrieval_empty_case_count: int = 0
    average_retrieval_recall: float | None = None
    average_citation_precision: float | None = None
    average_citation_recall: float | None = None
    average_groundedness_score: float | None = None
    average_unsupported_claim_rate: float | None = None
    average_evidence_selection_recall: float | None = None
    retrieval_contract_satisfied_count: int = 0
    citation_contract_satisfied_count: int = 0
    evidence_selection_contract_satisfied_count: int = 0
    alternative_evidence_match_count: int = 0
    low_confidence_selection_count: int = 0
    semantic_contract_case_count: int = 0
    semantic_contract_successful_case_count: int = 0
    required_fact_contract_satisfied_count: int = 0
    alternative_required_fact_match_count: int = 0
    bounded_answer_contract_case_count: int = 0
    bounded_answer_contract_satisfied_count: int = 0
    refusal_case_count: int = 0
    successful_refusal_case_count: int = 0
    average_required_fact_coverage: float | None = None
    forbidden_claim_violation_count: int = 0
    corpus_versions: list[str] = Field(default_factory=list)
    retriever_versions: list[str] = Field(default_factory=list)


class BenchmarkExecutionRead(BaseModel):
    benchmark_run: BenchmarkRunRead
    result_count: int
    metric_count: int
    log_count: int
    tool_execution_summary: ToolExecutionSummaryRead = Field(
        default_factory=ToolExecutionSummaryRead
    )
    rag_evaluation_summary: RagEvaluationSummaryRead = Field(
        default_factory=RagEvaluationSummaryRead
    )
    runtime_reliability_summary: RuntimeReliabilitySummaryRead = Field(
        default_factory=RuntimeReliabilitySummaryRead
    )
    agent_execution_summary: AgentExecutionSummaryRead = Field(
        default_factory=AgentExecutionSummaryRead
    )


class RuntimeHealthRead(BaseModel):
    adapter_name: str
    healthy: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


SuiteStatus = Literal["draft", "active", "archived"]
Criticality = Literal["critical", "standard", "exploratory"]
MetricDomain = Literal[
    "quality", "reliability", "performance", "resource", "governance", "evidence"
]
MetricAggregation = Literal["mean", "rate", "p50", "p95", "p99", "max", "min", "count"]
MetricDirection = Literal["higher_is_better", "lower_is_better", "exact"]
PolicyOperator = Literal["gte", "lte", "eq", "gt", "lt"]
RuleSeverity = Literal["blocker", "warning"]
DeploymentStatus = Literal["draft", "ready", "archived"]
GateStatus = Literal["draft", "completed", "failed", "stale"]
GateVerdict = Literal["APPROVED", "CONDITIONAL", "BLOCKED", "INSUFFICIENT_EVIDENCE"]
RuleResultStatus = Literal["pass", "fail", "insufficient"]
DeploymentBaselineStatus = Literal["active", "superseded", "archived"]


class WorkloadProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    slug: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1)
    domain: str = Field(min_length=1, max_length=120)
    primary_language: str = Field(min_length=1, max_length=40)
    local_only_required: bool = True
    data_classification: str = Field(min_length=1, max_length=80)
    expected_output_modes_json: list[str] = Field(default_factory=list)
    risk_notes: str | None = None
    is_active: bool = True


class WorkloadProfileCreate(WorkloadProfileBase):
    pass


class WorkloadProfileRead(WorkloadProfileBase, ReadModel):
    pass


class EvaluationSuiteBase(BaseModel):
    workload_profile_id: UUID
    name: str = Field(min_length=1, max_length=180)
    version_label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1)
    suite_hash: str | None = Field(default=None, max_length=128)
    status: SuiteStatus = "draft"
    dataset_source: str = Field(min_length=1, max_length=120)
    is_synthetic: bool = True


class EvaluationSuiteCreate(EvaluationSuiteBase):
    pass


class EvaluationSuiteRead(EvaluationSuiteBase, ReadModel):
    suite_hash: str


class EvaluationCaseBase(BaseModel):
    evaluation_suite_id: UUID
    external_case_id: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    input_payload_json: dict[str, Any]
    expected_output_json: dict[str, Any] | None = None
    reference_context_json: dict[str, Any] | None = None
    expected_tool_schema_json: dict[str, Any] | None = None
    tags_json: list[str] = Field(default_factory=list)
    criticality: Criticality = "standard"
    weight: float = Field(default=1.0, gt=0)
    is_active: bool = True
    data_source: str = Field(min_length=1, max_length=80)


class EvaluationCaseCreate(EvaluationCaseBase):
    pass


class EvaluationCaseRead(EvaluationCaseBase, ReadModel):
    pass


class MetricDefinitionBase(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=180)
    domain: MetricDomain
    aggregation: MetricAggregation
    direction: MetricDirection
    unit: str | None = Field(default=None, max_length=40)
    description: str = Field(min_length=1)
    calculation_version: str = Field(min_length=1, max_length=80)
    is_active: bool = True


class MetricDefinitionCreate(MetricDefinitionBase):
    pass


class MetricDefinitionRead(MetricDefinitionBase, ReadModel):
    pass


class AcceptancePolicyBase(BaseModel):
    workload_profile_id: UUID
    name: str = Field(min_length=1, max_length=180)
    version_label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1)
    policy_hash: str | None = Field(default=None, max_length=128)
    allow_conditional: bool = True
    is_active: bool = True


class AcceptancePolicyCreate(AcceptancePolicyBase):
    pass


class AcceptancePolicyRead(AcceptancePolicyBase, ReadModel):
    policy_hash: str


class AcceptancePolicyRuleBase(BaseModel):
    acceptance_policy_id: UUID
    metric_definition_id: UUID
    rule_name: str = Field(min_length=1, max_length=180)
    operator: PolicyOperator
    threshold_value: float
    severity: RuleSeverity
    minimum_sample_size: int | None = Field(default=None, ge=0)
    required: bool = True
    enabled: bool = True
    message_on_fail: str = Field(min_length=1)


class AcceptancePolicyRuleCreate(AcceptancePolicyRuleBase):
    pass


class AcceptancePolicyRuleRead(AcceptancePolicyRuleBase, ReadModel):
    pass


class DeploymentConfigurationBase(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    workload_profile_id: UUID
    hardware_profile_id: UUID
    model_artifact_id: UUID
    runtime_name: str = Field(min_length=1, max_length=120)
    runtime_version: str | None = None
    runtime_config_json: dict[str, Any] = Field(default_factory=dict)
    context_length: int = Field(gt=0)
    generation_config_json: dict[str, Any] = Field(default_factory=dict)
    prompt_bundle_json: dict[str, Any] = Field(default_factory=dict)
    output_schema_version: str | None = None
    tool_schema_version: str | None = None
    retrieval_config_json: dict[str, Any] | None = None
    concurrency_target: int = Field(default=1, gt=0)
    status: DeploymentStatus = "draft"
    notes: str | None = None


class DeploymentConfigurationCreate(DeploymentConfigurationBase):
    pass


class DeploymentConfigurationRead(DeploymentConfigurationBase, ReadModel):
    configuration_hash: str


class GateEvaluationCreate(BaseModel):
    deployment_configuration_id: UUID
    evaluation_suite_id: UUID
    acceptance_policy_id: UUID
    baseline_gate_evaluation_id: UUID | None = None


class GateRuleResultRead(ReadModel):
    gate_evaluation_id: UUID
    acceptance_policy_rule_id: UUID
    metric_value: float | None
    sample_size: int
    status: RuleResultStatus
    severity: RuleSeverity
    details_json: dict[str, Any] | None = None


class GateEvaluationRead(ReadModel):
    deployment_configuration_id: UUID
    evaluation_suite_id: UUID
    acceptance_policy_id: UUID
    baseline_gate_evaluation_id: UUID | None = None
    status: GateStatus
    verdict: GateVerdict
    evidence_snapshot_json: dict[str, Any]
    scorecard_json: dict[str, Any]
    decision_summary: str
    decision_hash: str
    evidence_revision_hash: str | None = None
    stale_at: datetime | None = None
    stale_reason: str | None = None
    superseded_by_gate_evaluation_id: UUID | None = None
    evaluated_at: datetime
    rule_results: list[GateRuleResultRead] = Field(default_factory=list)


class BaselinePromotionCreate(BaseModel):
    promoted_by: str | None = Field(default=None, max_length=120)
    promotion_reason: str | None = None
    notes: str | None = None


class DeploymentBaselineRead(ReadModel):
    deployment_configuration_id: UUID
    evaluation_suite_id: UUID
    acceptance_policy_id: UUID
    gate_evaluation_id: UUID
    promoted_at: datetime
    promoted_by: str | None = None
    promotion_reason: str | None = None
    baseline_hash: str
    status: DeploymentBaselineStatus
    superseded_at: datetime | None = None
    superseded_by_baseline_id: UUID | None = None
    notes: str | None = None
