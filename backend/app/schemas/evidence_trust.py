from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EvidenceTrustStatus = Literal[
    "synthetic_only",
    "needs_judge_review",
    "local_demo_ready",
    "production_evidence_ready",
    "unknown",
]
ProductionReadiness = Literal[
    "production_ready",
    "not_production_ready",
    "unknown",
]


class EvidenceTrustSummaryRead(BaseModel):
    source_distribution: dict[str, int]
    score_distribution: dict[str, int]
    total_result_count: int
    synthetic_demo_count: int
    local_authored_count: int
    production_captured_count: int
    unverified_production_captured_count: int = 0
    external_benchmark_count: int
    unknown_source_count: int
    heuristic_only_count: int
    candidate_judge_label_count: int
    applied_judge_label_count: int
    human_reviewed_count: int
    unknown_score_count: int
    critical_result_count: int
    critical_reviewed_count: int
    applied_judge_label_rate: float
    critical_review_coverage_rate: float
    trust_status: EvidenceTrustStatus
    production_readiness: ProductionReadiness
    reasons: list[str]
    limitations: list[str]
