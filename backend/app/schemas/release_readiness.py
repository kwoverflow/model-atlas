from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.evidence_trust import (
    EvidenceTrustSummaryRead,
    ProductionReadiness,
)

ReleaseReadinessStatus = Literal[
    "READY",
    "READY_TO_PROMOTE",
    "NEEDS_REVIEW",
    "BLOCKED",
    "INSUFFICIENT_EVIDENCE",
]


class ReleaseReadinessGateSummary(BaseModel):
    gate_evaluation_id: UUID
    status: Literal["draft", "completed", "failed", "stale"]
    verdict: Literal["APPROVED", "CONDITIONAL", "BLOCKED", "INSUFFICIENT_EVIDENCE"]
    decision_hash: str
    decision_summary: str
    evaluated_at: datetime
    passed_rule_count: int
    failed_rule_count: int
    insufficient_rule_count: int
    critical_failure_count: int
    benchmark_run_ids: list[UUID]
    metric_count: int
    result_count: int
    source_distribution: dict[str, int]
    evidence_revision_hash: str | None = None
    stale_at: datetime | None = None
    stale_reason: str | None = None
    superseded_by_gate_evaluation_id: UUID | None = None


class ReleaseReadinessBaselineSummary(BaseModel):
    active_baseline_id: UUID | None
    active_baseline_gate_evaluation_id: UUID | None
    gate_is_active_baseline: bool
    baseline_status: Literal["active_source", "different_active_baseline", "not_promoted"]
    baseline_hash: str | None
    promoted_at: datetime | None


class ReleaseReadinessJudgeSummary(BaseModel):
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
    critical_review_coverage_rate: float
    average_quality_score: float | None
    average_abs_quality_delta_vs_candidate: float | None


class ReleaseReadinessPromptSummary(BaseModel):
    prompt_version_count: int
    baseline_prompt_version_id: UUID | None
    risk_row_count: int
    risk_flags: list[str]


class ReleaseReadinessLineageSummary(BaseModel):
    event_count: int
    lineage_count: int
    latest_events: list[dict[str, Any]]


class ReleaseReadinessSnapshot(BaseModel):
    schema_version: str = "release-readiness-snapshot-v2"
    evidence_trust_version: str = "evidence-trust-v1"
    generated_at: datetime
    status: ReleaseReadinessStatus
    production_readiness: ProductionReadiness
    release_summary: str
    deployment_configuration_id: UUID
    evaluation_suite_id: UUID
    acceptance_policy_id: UUID
    readiness_reasons: list[str]
    review_reasons: list[str]
    next_actions: list[str]
    evidence_trust: EvidenceTrustSummaryRead
    gate: ReleaseReadinessGateSummary
    baseline: ReleaseReadinessBaselineSummary
    judge_calibration: ReleaseReadinessJudgeSummary
    prompt_regression: ReleaseReadinessPromptSummary
    lineage: ReleaseReadinessLineageSummary
