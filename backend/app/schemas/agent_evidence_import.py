from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.agent_execution import AgentExecutionTraceRead


class AgentEvidenceProvenanceInput(BaseModel):
    source_system: str = Field(min_length=1, max_length=160)
    source_event_id: str = Field(min_length=1, max_length=200)
    collector_version: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=80)
    captured_at: datetime
    source_trace_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    @field_validator("captured_at")
    @classmethod
    def captured_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a UTC offset")
        return value


class AgentCapturedInferenceMetricInput(BaseModel):
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


class AgentEvidenceImportCreate(BaseModel):
    benchmark_run_id: UUID
    evaluation_case_id: UUID
    sample_id: str = Field(min_length=1, max_length=120)
    raw_output: str = Field(min_length=1)
    normalized_output: str = Field(min_length=1)
    trace: AgentExecutionTraceRead
    metric: AgentCapturedInferenceMetricInput
    provenance: AgentEvidenceProvenanceInput
    human_label: str | None = Field(default=None, max_length=120)


class AgentEvidenceImportRead(BaseModel):
    import_contract_version: str
    import_policy_version: str
    benchmark_run_id: UUID
    benchmark_result_id: UUID
    inference_metric_id: UUID
    evaluation_case_id: UUID
    sample_id: str
    source_event_id: str
    source_trace_hash: str
    evidence_hash: str
    trace_status: str
    quality_score: float | None
    data_source: str


class AgentTrafficEvidenceBatchCreate(BaseModel):
    source_system: str = Field(min_length=1, max_length=160)
    batch_id: str = Field(min_length=1, max_length=200)
    collector_version: str = Field(min_length=1, max_length=120)
    captured_at: datetime
    events: list[AgentEvidenceImportCreate] = Field(min_length=1, max_length=100)

    @field_validator("captured_at")
    @classmethod
    def batch_captured_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("captured_at must include a UTC offset")
        return value
