from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OperationalMemoryRecordRead(BaseModel):
    memory_id: str
    memory_version: str
    title: str
    tags: list[str] = Field(default_factory=list)
    data_classification: str
    content_hash: str


class OperationalMemoryRegistryRead(BaseModel):
    registry_id: str
    registry_version: str
    record_count: int
    records: list[OperationalMemoryRecordRead] = Field(default_factory=list)


class AgentApprovalDecisionInput(BaseModel):
    decision: Literal["approved", "denied"]
    decided_by: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


AgentApprovalCheckpointStatus = Literal[
    "pending",
    "approved",
    "denied",
    "revoked",
    "expired",
    "resumed",
]


class AgentCheckpointPolicyRead(BaseModel):
    policy_version: str
    checkpoint_id: str
    allowed_roles: list[str] = Field(default_factory=list)
    resume_roles: list[str] = Field(default_factory=list)
    requires_verified_identity: bool
    separation_of_duties: bool
    expires_in_seconds: int


class AgentApprovalCheckpointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    benchmark_run_id: UUID
    benchmark_result_id: UUID
    checkpoint_id: str
    status: AgentApprovalCheckpointStatus
    requested_by_subject_id: str
    requested_by_identity_json: dict[str, Any]
    request_snapshot_json: dict[str, Any]
    approval_policy_json: AgentCheckpointPolicyRead
    request_hash: str
    expires_at: datetime
    decision: Literal["approved", "denied"] | None = None
    decision_reason: str | None = None
    decided_at: datetime | None = None
    approver_identity_json: dict[str, Any] | None = None
    identity_verified: bool
    decision_hash: str | None = None
    revoked_at: datetime | None = None
    revocation_reason: str | None = None
    revoked_by_identity_json: dict[str, Any] | None = None
    revocation_hash: str | None = None
    resumed_at: datetime | None = None
    resumed_by_identity_json: dict[str, Any] | None = None
    resume_hash: str | None = None
    transition_benchmark_run_id: UUID | None = None
    transition_benchmark_result_id: UUID | None = None
    version: int
    created_at: datetime
    updated_at: datetime


class AgentCheckpointDecisionCreate(BaseModel):
    decision: Literal["approved", "denied"]
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)


class AgentCheckpointRevocationCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int = Field(ge=1)


class AgentCheckpointResumeCreate(BaseModel):
    expected_version: int = Field(ge=1)


class AgentRuntimeDescriptorRead(BaseModel):
    runtime_id: str
    runtime_version: str
    trace_schema_version: str
    context_schema_version: str
    observation_schema_version: str
    recovery_policy_version: str
    approval_policy_version: str
    live_replan_callback_version: str
    allowed_actions: list[str] = Field(default_factory=list)
    limits: dict[str, int] = Field(default_factory=dict)
    tool_registry_version: str
    memory_registry_version: str
    corpus_version: str
    retriever_version: str
    memory_write_mode: Literal["task_local_simulated"]
    approval_decision_mode: Literal["external_request_only"]


class AgentObservationRead(BaseModel):
    schema_version: str
    status: str
    successful: bool
    error_type: str | None = None
    policy_violation_count: int = 0
    output_digest: str | None = None


class AgentExecutionStepRead(BaseModel):
    step_index: int
    action: str
    expected_action: str | None = None
    status: str
    successful: bool
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    policy_violations: list[str] = Field(default_factory=list)
    recovered: bool = False
    retry_count: int = 0
    memory_provenance_valid: bool = False
    approval_provenance_valid: bool = False
    recovered_by_replan: bool = False
    phase: Literal["plan", "recovery"] = "plan"
    parent_step_index: int | None = None
    observation: AgentObservationRead | None = None
    duration_ms: float


class AgentReplanRead(BaseModel):
    replan_index: int
    trigger_step_index: int
    trigger_error_type: str | None = None
    observation: AgentObservationRead | None = None
    strategy: str
    expected_action_sequence: list[str] = Field(default_factory=list)
    actual_action_sequence: list[str] = Field(default_factory=list)
    sequence_match: bool
    recovery_step_indices: list[int] = Field(default_factory=list)
    status: str
    successful: bool
    policy_version: str
    source: Literal["predeclared_plan", "live_callback"] = "predeclared_plan"
    model_call: dict[str, Any] | None = None


class AgentExecutionTraceRead(BaseModel):
    schema_version: str
    context_version: str
    runtime_version: str | None = None
    observation_schema_version: str | None = None
    recovery_policy_version: str | None = None
    approval_policy_version: str | None = None
    memory_registry_version: str
    tool_registry_version: str
    corpus_version: str
    retriever_version: str
    external_case_id: str
    parse_valid: bool
    parse_error: str | None = None
    plan_valid: bool
    status: Literal[
        "success",
        "partial_failure",
        "failed",
        "invalid_plan",
        "limit_exceeded",
        "pending_approval",
        "approval_denied",
    ]
    successful: bool
    step_limit: int
    execution_step_limit: int | None = None
    replan_limit: int = 0
    step_count: int
    expected_action_sequence: list[str] = Field(default_factory=list)
    actual_action_sequence: list[str] = Field(default_factory=list)
    sequence_match: bool
    successful_step_count: int
    failed_step_count: int
    step_success_rate: float | None = None
    tool_call_count: int
    retrieval_count: int
    memory_read_count: int
    memory_write_count: int
    retried_tool_count: int
    recovered_tool_count: int
    policy_violation_count: int
    final_response_present: bool
    memory_provenance_count: int
    memory_action_count: int
    observation_count: int = 0
    replan_count: int = 0
    successful_replan_count: int = 0
    recovery_step_count: int = 0
    successful_recovery_step_count: int = 0
    recovery_sequence_match: bool | None = None
    unrecovered_failure_count: int = 0
    approval_checkpoint_count: int = 0
    approved_checkpoint_count: int = 0
    denied_checkpoint_count: int = 0
    pending_checkpoint_count: int = 0
    approval_provenance_count: int = 0
    halt_reason: str | None = None
    total_duration_ms: float
    live_replan_count: int = 0
    live_replan_model_call_count: int = 0
    live_replan_prompt_tokens: int = 0
    live_replan_completion_tokens: int = 0
    live_replan_latency_ms: float = 0.0
    live_replan_estimated_cost_usd: float = 0.0
    replans: list[AgentReplanRead] = Field(default_factory=list)
    steps: list[AgentExecutionStepRead] = Field(default_factory=list)


class AgentExecutionSummaryRead(BaseModel):
    schema_version: str = "agent-execution-summary-v2"
    agent_case_count: int = 0
    successful_case_count: int = 0
    failed_case_count: int = 0
    total_step_count: int = 0
    successful_step_count: int = 0
    failed_step_count: int = 0
    task_success_rate: float | None = None
    plan_validity_rate: float | None = None
    step_success_rate: float | None = None
    action_sequence_accuracy: float | None = None
    policy_violation_rate: float | None = None
    final_response_rate: float | None = None
    memory_provenance_rate: float | None = None
    retried_tool_count: int = 0
    recovered_tool_count: int = 0
    tool_retry_recovery_rate: float | None = None
    replan_case_count: int = 0
    replan_count: int = 0
    successful_replan_count: int = 0
    replan_success_rate: float | None = None
    live_replan_count: int = 0
    live_replan_model_call_count: int = 0
    live_replan_prompt_tokens: int = 0
    live_replan_completion_tokens: int = 0
    live_replan_latency_ms: float = 0.0
    live_replan_estimated_cost_usd: float = 0.0
    recovery_step_count: int = 0
    successful_recovery_step_count: int = 0
    recovery_step_success_rate: float | None = None
    approval_checkpoint_count: int = 0
    approved_checkpoint_count: int = 0
    denied_checkpoint_count: int = 0
    pending_checkpoint_count: int = 0
    approval_compliance_rate: float | None = None
    approval_provenance_rate: float | None = None
    pending_approval_rate: float | None = None
    observation_coverage_rate: float | None = None
    unrecovered_failure_rate: float | None = None
    halted_case_count: int = 0
    average_steps_per_case: float | None = None
    memory_registry_versions: list[str] = Field(default_factory=list)
    tool_registry_versions: list[str] = Field(default_factory=list)
    corpus_versions: list[str] = Field(default_factory=list)
    retriever_versions: list[str] = Field(default_factory=list)
    observation_versions: list[str] = Field(default_factory=list)
    recovery_policy_versions: list[str] = Field(default_factory=list)
    approval_policy_versions: list[str] = Field(default_factory=list)
    trace_versions: list[str] = Field(default_factory=list)


class AgentExecutionTraceRecordRead(BaseModel):
    benchmark_result_id: UUID
    evaluation_case_id: UUID | None = None
    sample_id: str
    case_title: str | None = None
    criticality: str | None = None
    trace: AgentExecutionTraceRead


class AgentReplayRead(BaseModel):
    benchmark_result_id: UUID
    benchmark_run_id: UUID
    evaluation_case_id: UUID
    version_compatible: bool
    deterministic_match: bool
    original_signature: str
    replay_signature: str
    changed_paths: list[str] = Field(default_factory=list)
    original_trace: AgentExecutionTraceRead
    replay_trace: AgentExecutionTraceRead


class AgentCheckpointResumeRead(BaseModel):
    checkpoint: AgentApprovalCheckpointRead
    benchmark_run_id: UUID
    benchmark_result_id: UUID
    parent_benchmark_run_id: UUID
    parent_benchmark_result_id: UUID
    result_revision: int
    trace: AgentExecutionTraceRead
    summary: AgentExecutionSummaryRead
