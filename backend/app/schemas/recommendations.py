from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecommendationWeights(BaseModel):
    quality: float = Field(default=0.45, ge=0, le=1)
    latency: float = Field(default=0.20, ge=0, le=1)
    throughput: float = Field(default=0.20, ge=0, le=1)
    vram_efficiency: float = Field(default=0.15, ge=0, le=1)

    @model_validator(mode="after")
    def total_weight_must_be_positive(self) -> RecommendationWeights:
        if self.quality + self.latency + self.throughput + self.vram_efficiency <= 0:
            raise ValueError("at least one recommendation weight must be greater than zero")
        return self


class RecommendationRequest(BaseModel):
    hardware_profile_id: UUID | None = None
    benchmark_task_id: UUID | None = None
    require_text: bool = True
    require_vision: bool = False
    require_tool_calling: bool = False
    require_structured_output: bool = False
    commercial_use_required: bool = False
    min_context_length: int | None = Field(default=None, gt=0)
    top_k: int = Field(default=5, ge=1, le=20)
    weights: RecommendationWeights = Field(default_factory=RecommendationWeights)


class EligibilityIssue(BaseModel):
    artifact_name: str
    reason_code: str
    message: str


class RecommendationCandidate(BaseModel):
    rank: int
    model_id: str
    model_name: str
    provider: str
    family: str
    artifact_id: str
    artifact_name: str
    format: str
    quantization: str | None
    precision: str | None
    recommended_vram_gb: float | None
    context_limit: int
    runtime_compatibility: list[str]
    average_quality_score: float | None
    average_ttft_ms: float | None
    average_end_to_end_latency_ms: float | None
    average_tokens_per_second: float | None
    average_vram_usage_mb: float | None
    json_validity_rate: float | None
    tool_call_validity_rate: float | None
    benchmark_coverage_count: int
    quality_component: float
    latency_component: float
    throughput_component: float
    vram_efficiency_component: float
    raw_recommendation_score: float
    evidence_confidence: float
    confidence_penalty: float
    recommendation_score: float
    pareto_optimal: bool
    rationale: list[str]


class RecommendationReport(BaseModel):
    hardware_profile_id: str
    hardware_profile_name: str
    benchmark_task_id: str | None
    benchmark_task_name: str | None
    request: RecommendationRequest
    candidate_count: int
    eligible_count: int
    recommended_candidate: RecommendationCandidate | None
    candidates: list[RecommendationCandidate]
    pareto_frontier: list[RecommendationCandidate]
    excluded: list[EligibilityIssue]
    decision_summary: str


class RecommendationScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    description: str | None = None
    request: RecommendationRequest = Field(default_factory=RecommendationRequest)


class RecommendationScenarioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    description: str | None = None
    request: RecommendationRequest | None = None


class RecommendationScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    request: RecommendationRequest
    created_at: str
    updated_at: str
