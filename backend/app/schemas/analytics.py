from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DataQualityWarning(BaseModel):
    code: str
    message: str
    count: int


class OverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_count: int
    model_artifact_count: int
    benchmark_task_count: int
    benchmark_run_count: int
    benchmark_result_count: int
    latest_benchmark_run_timestamp: datetime | None
    synthetic_record_count: int
    latest_data_quality_warnings: list[DataQualityWarning]


class ControlPlaneLatestGate(BaseModel):
    id: UUID
    verdict: str
    evidence_trust_status: str
    production_readiness: str
    decision_summary: str
    created_at: datetime


class ControlPlaneNextAction(BaseModel):
    priority: Literal["high", "medium", "low"]
    kind: str
    title: str
    description: str
    href: str


class ControlPlaneWorkflowStep(BaseModel):
    key: str
    label: str
    status: Literal["complete", "attention", "not_started"]
    href: str


class ControlPlaneRecentRun(BaseModel):
    id: UUID
    status: str
    runtime_name: str
    data_source: str
    started_at: datetime


class ControlPlaneOverviewResponse(BaseModel):
    mode: Literal["empty", "demo", "production_evidence"]
    latest_gate: ControlPlaneLatestGate | None
    release_ready_configuration_count: int
    needs_review_count: int
    production_evidence_result_count: int
    local_authored_result_count: int
    synthetic_evidence_result_count: int
    unknown_evidence_result_count: int
    failed_critical_case_count: int
    active_baseline_count: int
    next_actions: list[ControlPlaneNextAction]
    workflow_steps: list[ControlPlaneWorkflowStep]
    inventory: OverviewResponse
    recent_runs: list[ControlPlaneRecentRun]


class ModelComparisonRow(BaseModel):
    model_artifact_id: str
    model_name: str
    artifact_name: str
    benchmark_task_id: str
    benchmark_task_name: str
    average_quality_score: float | None
    average_ttft_ms: float | None
    average_end_to_end_latency_ms: float | None
    average_tokens_per_second: float | None
    average_vram_usage_mb: float | None
    json_validity_rate: float | None
    tool_call_validity_rate: float | None
    benchmark_coverage_count: int
