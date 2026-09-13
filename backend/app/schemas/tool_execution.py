from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.agent_execution import (
    AgentExecutionSummaryRead,
    AgentExecutionTraceRecordRead,
)
from app.schemas.entities import (
    BenchmarkRunRead,
    RagEvaluationSummaryRead,
    ToolExecutionSummaryRead,
)
from app.schemas.rag_evaluation import RagEvaluationTraceRecordRead
from app.schemas.runtime_reliability import (
    RuntimeReliabilitySummaryRead,
    RuntimeReliabilityTraceRecordRead,
)
from app.schemas.tool_fault_scenarios import ToolFaultScenarioRead


class ToolDescriptorRead(BaseModel):
    tool_id: str
    tool_version: str
    display_name: str
    description: str
    argument_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capabilities: list[str] = Field(default_factory=list)
    side_effect_mode: Literal["none", "simulated"]
    default_max_attempts: int


class ToolRegistryRead(BaseModel):
    registry_id: str
    registry_version: str
    tool_count: int
    tools: list[ToolDescriptorRead] = Field(default_factory=list)


class ToolExecutionAttemptRead(BaseModel):
    attempt_number: int
    status: Literal["success", "failed"]
    retryable: bool
    duration_ms: float
    error_type: str | None = None
    message: str | None = None
    fault_injected: bool | None = None
    handler_invoked: bool | None = None


class ToolExecutionStepRead(BaseModel):
    step_index: int
    call_id: str
    expected_tool_name: str | None = None
    tool_name: str
    arguments: dict[str, Any]
    selection_valid: bool
    arguments_valid: bool
    validation_errors: list[str] = Field(default_factory=list)
    execution_status: Literal["success", "failed", "skipped"]
    attempt_count: int
    retry_count: int
    recovered: bool
    output_valid: bool
    output_validation_errors: list[str] = Field(default_factory=list)
    output: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: float
    attempts: list[ToolExecutionAttemptRead] = Field(default_factory=list)


class ToolExecutionTraceRead(BaseModel):
    schema_version: str
    registry_id: str
    registry_version: str
    external_case_id: str
    parse_valid: bool
    parse_error: str | None = None
    call_valid: bool
    status: Literal["success", "partial_failure", "failed", "invalid_call"]
    successful: bool
    sequence_match: bool
    expected_tool_sequence: list[str] = Field(default_factory=list)
    actual_tool_sequence: list[str] = Field(default_factory=list)
    selection_accuracy: float | None = None
    argument_validity_rate: float | None = None
    execution_success_rate: float | None = None
    retry_recovery_rate: float | None = None
    total_duration_ms: float
    steps: list[ToolExecutionStepRead] = Field(default_factory=list)
    fault_scenario: ToolFaultScenarioRead | None = None


class ToolExecutionTraceRecordRead(BaseModel):
    benchmark_result_id: UUID
    evaluation_case_id: UUID | None = None
    sample_id: str
    case_title: str | None = None
    criticality: str | None = None
    trace: ToolExecutionTraceRead


class BenchmarkExecutionDetailRead(BaseModel):
    benchmark_run: BenchmarkRunRead
    result_count: int
    metric_count: int
    log_count: int
    tool_execution_summary: ToolExecutionSummaryRead
    tool_traces: list[ToolExecutionTraceRecordRead] = Field(default_factory=list)
    rag_evaluation_summary: RagEvaluationSummaryRead
    rag_traces: list[RagEvaluationTraceRecordRead] = Field(default_factory=list)
    runtime_reliability_summary: RuntimeReliabilitySummaryRead
    reliability_traces: list[RuntimeReliabilityTraceRecordRead] = Field(default_factory=list)
    agent_execution_summary: AgentExecutionSummaryRead
    agent_traces: list[AgentExecutionTraceRecordRead] = Field(default_factory=list)
