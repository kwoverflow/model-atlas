from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RuntimeReliabilitySummaryRead(BaseModel):
    schema_version: str = "runtime-reliability-summary-v1"
    reliability_case_count: int = 0
    trial_count: int = 0
    expected_trial_count: int = 0
    success_count: int = 0
    timeout_count: int = 0
    oom_count: int = 0
    error_count: int = 0
    success_rate: float | None = None
    timeout_rate: float | None = None
    oom_rate: float | None = None
    error_rate: float | None = None
    p50_end_to_end_latency_ms: float | None = None
    p95_end_to_end_latency_ms: float | None = None
    p99_end_to_end_latency_ms: float | None = None
    p50_ttft_ms: float | None = None
    p95_ttft_ms: float | None = None
    mean_tokens_per_second: float | None = None
    latency_variation_coefficient: float | None = None
    trial_coverage_rate: float | None = None
    minimum_trials_per_case: int = 0
    maximum_trials_per_case: int = 0
    context_stress_trial_count: int = 0
    context_stress_success_rate: float | None = None
    trace_versions: list[str] = Field(default_factory=list)


class RuntimeReliabilityTraceRead(BaseModel):
    schema_version: str
    benchmark_run_id: UUID | None = None
    external_case_id: str
    trial_index: int
    total_trials: int
    concurrency: int
    case_timeout_ms: int
    status: Literal["success", "timeout", "oom", "error"]
    successful: bool
    within_timeout: bool
    ttft_ms: float
    end_to_end_latency_ms: float
    tokens_per_second: float
    prompt_tokens: int
    completion_tokens: int
    gpu_vram_used_mb: float | None = None
    peak_memory_mb: float | None = None
    oom_occurred: bool
    error_type: str | None = None
    error_message: str | None = None
    seed: int | None = None
    context_tokens: float
    context_window_tokens: int
    context_utilization_ratio: float
    context_stress: bool


class RuntimeReliabilityTraceRecordRead(BaseModel):
    benchmark_result_id: UUID
    evaluation_case_id: UUID | None = None
    sample_id: str
    case_title: str | None = None
    criticality: str | None = None
    trace: RuntimeReliabilityTraceRead


class RuntimeReliabilityRunRead(BaseModel):
    benchmark_run_id: UUID
    deployment_configuration_id: UUID | None = None
    runtime_name: str
    runtime_version: str | None = None
    dataset_version: str
    summary: RuntimeReliabilitySummaryRead


class RuntimeReliabilityComparisonRead(BaseModel):
    schema_version: str = "runtime-reliability-comparison-v1"
    left: RuntimeReliabilityRunRead
    right: RuntimeReliabilityRunRead
    right_minus_left: dict[str, float | None] = Field(default_factory=dict)
    winner: Literal["left", "right", "tie", "insufficient_evidence"]
    recommended_benchmark_run_id: UUID | None = None
    reason: str
