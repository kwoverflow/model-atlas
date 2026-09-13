from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

JudgeLabelScoreSource = Literal[
    "applied_judge_label",
    "human_reviewed",
    "candidate_judge_label",
    "heuristic",
    "raw_label",
    "unlabeled",
]
JudgeLabelReviewDecisionType = Literal[
    "approved_candidate",
    "overridden",
    "rejected",
]


class JudgeLabelReviewRow(BaseModel):
    benchmark_result_id: UUID
    benchmark_run_id: UUID
    evaluation_case_id: UUID | None
    sample_id: str
    external_case_id: str | None
    title: str | None
    category: str | None
    criticality: str | None
    quality_score: float | None
    groundedness_score: float | None
    faithfulness_score: float | None
    human_label: str | None
    data_source: str
    score_source: JudgeLabelScoreSource
    candidate_judge_labels: dict[str, Any] | None
    judge_label_metadata: dict[str, Any] | None
    scorer_metadata: dict[str, Any] | None
    quality_delta_vs_candidate: float | None
    needs_review: bool


class JudgeLabelReviewResponse(BaseModel):
    benchmark_run_id: UUID | None
    benchmark_result_id: UUID | None = None
    result_count: int
    reviewed_count: int
    candidate_label_count: int
    heuristic_scored_count: int
    heuristic_only_count: int
    applied_label_count: int
    human_reviewed_count: int
    unlabeled_count: int
    needs_review_count: int
    applied_label_coverage_rate: float
    critical_result_count: int
    critical_reviewed_count: int
    critical_review_coverage_rate: float
    average_quality_score: float | None
    average_abs_quality_delta_vs_candidate: float | None
    rows: list[JudgeLabelReviewRow]


class JudgeLabelImportRequest(BaseModel):
    benchmark_run_id: UUID
    filename: str
    content: str
    apply_labels: bool = False


class JudgeLabelImportSummaryRead(BaseModel):
    benchmark_run_id: str
    label_count: int
    matched_label_count: int
    missing_result_count: int
    applied: bool
    quality_label_count: int
    average_abs_quality_delta: float | None
    import_format_version: str


class JudgeLabelReviewDecisionCreate(BaseModel):
    benchmark_result_id: UUID
    decision_type: JudgeLabelReviewDecisionType
    quality_score: float | None = Field(default=None, ge=0, le=1)
    groundedness_score: float | None = Field(default=None, ge=0, le=1)
    faithfulness_score: float | None = Field(default=None, ge=0, le=1)
    human_label: str | None = Field(default=None, min_length=1, max_length=120)
    rationale: str = Field(min_length=3, max_length=4000)

    @model_validator(mode="after")
    def validate_decision_values(self) -> JudgeLabelReviewDecisionCreate:
        supplied = any(
            value is not None
            for value in (
                self.quality_score,
                self.groundedness_score,
                self.faithfulness_score,
                self.human_label,
            )
        )
        if self.decision_type == "overridden" and not supplied:
            raise ValueError("overridden review requires at least one label value")
        if self.decision_type != "overridden" and supplied:
            raise ValueError(
                "label values are only accepted for an overridden review"
            )
        return self


class JudgeLabelReviewDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    benchmark_result_id: UUID
    evaluation_case_id: UUID | None
    decision_type: JudgeLabelReviewDecisionType
    candidate_label_hash: str | None
    prior_scores_json: dict[str, Any]
    applied_scores_json: dict[str, Any] | None
    applied: bool
    reviewer_identity_json: dict[str, Any]
    identity_verified: bool
    rationale: str
    criticality: str | None
    reviewed_at: datetime
    review_hash: str
    created_at: datetime
    updated_at: datetime
