from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import BenchmarkResult, EvaluationCase, GateEvaluation

EVIDENCE_TRUST_VERSION = "evidence-trust-v1"


class EvidenceSourceTrustTier(StrEnum):
    SYNTHETIC_DEMO = "synthetic_demo"
    LOCAL_AUTHORED = "local_authored"
    PRODUCTION_CAPTURED = "production_captured"
    PRODUCTION_CAPTURED_UNVERIFIED = "production_captured_unverified"
    EXTERNAL_BENCHMARK = "external_benchmark"
    UNKNOWN = "unknown"


class EvidenceScoreTrustTier(StrEnum):
    HEURISTIC = "heuristic"
    CANDIDATE_JUDGE_LABEL = "candidate_judge_label"
    APPLIED_JUDGE_LABEL = "applied_judge_label"
    HUMAN_REVIEWED = "human_reviewed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EvidenceTrustThresholds:
    minimum_applied_judge_label_rate_for_local_demo: float
    minimum_critical_reviewed_count_for_local_demo: int
    minimum_production_captured_result_count: int
    minimum_applied_judge_label_rate_for_production: float
    minimum_critical_review_coverage_rate_for_production: float

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> EvidenceTrustThresholds:
        resolved = settings or get_settings()
        return cls(
            minimum_applied_judge_label_rate_for_local_demo=(
                resolved.minimum_applied_judge_label_rate_for_local_demo
            ),
            minimum_critical_reviewed_count_for_local_demo=(
                resolved.minimum_critical_reviewed_count_for_local_demo
            ),
            minimum_production_captured_result_count=(
                resolved.minimum_production_captured_result_count
            ),
            minimum_applied_judge_label_rate_for_production=(
                resolved.minimum_applied_judge_label_rate_for_production
            ),
            minimum_critical_review_coverage_rate_for_production=(
                resolved.minimum_critical_review_coverage_rate_for_production
            ),
        )


@dataclass(frozen=True)
class EvidenceTrustSummary:
    source_distribution: dict[str, int]
    score_distribution: dict[str, int]
    total_result_count: int
    synthetic_demo_count: int
    local_authored_count: int
    production_captured_count: int
    unverified_production_captured_count: int
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
    trust_status: str
    production_readiness: str
    reasons: list[str]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_source_tier(value: str | None) -> EvidenceSourceTrustTier:
    normalized = (value or "").strip().lower()
    if normalized in {"captured_local", "local_actual_runtime"}:
        normalized = EvidenceSourceTrustTier.LOCAL_AUTHORED.value
    try:
        return EvidenceSourceTrustTier(normalized)
    except ValueError:
        return EvidenceSourceTrustTier.UNKNOWN


def classify_score_tier(
    result: BenchmarkResult,
    evaluation_case: EvaluationCase | None = None,
) -> EvidenceScoreTrustTier:
    metadata = _mapping(result.metadata_json)
    judge_label = _mapping(metadata.get("judge_label"))
    if _has_explicit_human_review(metadata, judge_label):
        return EvidenceScoreTrustTier.HUMAN_REVIEWED
    if judge_label.get("applied") is True:
        return EvidenceScoreTrustTier.APPLIED_JUDGE_LABEL
    if _candidate_judge_labels(evaluation_case):
        return EvidenceScoreTrustTier.CANDIDATE_JUDGE_LABEL
    scorer = _mapping(metadata.get("scorer"))
    if any(
        value
        for value in (
            scorer.get("scorer_id"),
            scorer.get("scorer_version"),
            scorer.get("version"),
            metadata.get("scorer_id"),
            metadata.get("scorer_version"),
        )
    ):
        return EvidenceScoreTrustTier.HEURISTIC
    return EvidenceScoreTrustTier.UNKNOWN


def summarize_evidence_trust(
    results: Sequence[BenchmarkResult],
    result_case_map: Mapping[UUID, EvaluationCase],
    *,
    thresholds: EvidenceTrustThresholds | None = None,
    verified_production_run_ids: set[UUID] | None = None,
) -> EvidenceTrustSummary:
    resolved_thresholds = thresholds or EvidenceTrustThresholds.from_settings()
    source_counter: Counter[str] = Counter()
    score_counter: Counter[str] = Counter()
    critical_result_count = 0
    critical_reviewed_count = 0

    for result in results:
        source_tier = normalize_source_tier(result.data_source)
        if (
            source_tier == EvidenceSourceTrustTier.PRODUCTION_CAPTURED
            and verified_production_run_ids is not None
            and result.benchmark_run_id not in verified_production_run_ids
        ):
            source_tier = EvidenceSourceTrustTier.PRODUCTION_CAPTURED_UNVERIFIED
        evaluation_case = result_case_map.get(result.id)
        score_tier = classify_score_tier(result, evaluation_case)
        source_counter[source_tier.value] += 1
        score_counter[score_tier.value] += 1
        if evaluation_case is not None and evaluation_case.criticality == "critical":
            critical_result_count += 1
            if score_tier in {
                EvidenceScoreTrustTier.APPLIED_JUDGE_LABEL,
                EvidenceScoreTrustTier.HUMAN_REVIEWED,
            }:
                critical_reviewed_count += 1

    total_result_count = len(results)
    applied_count = score_counter[EvidenceScoreTrustTier.APPLIED_JUDGE_LABEL.value]
    human_reviewed_count = score_counter[EvidenceScoreTrustTier.HUMAN_REVIEWED.value]
    applied_rate = _rate(applied_count + human_reviewed_count, total_result_count)
    critical_rate = _rate(critical_reviewed_count, critical_result_count)
    trust_status = _trust_status(
        source_counter=source_counter,
        total_result_count=total_result_count,
        applied_rate=applied_rate,
        critical_result_count=critical_result_count,
        critical_reviewed_count=critical_reviewed_count,
        critical_rate=critical_rate,
        thresholds=resolved_thresholds,
    )
    production_readiness = (
        "production_ready"
        if trust_status == "production_evidence_ready"
        else "unknown"
        if trust_status == "unknown"
        else "not_production_ready"
    )
    reasons, limitations = _explain_summary(
        source_counter=source_counter,
        score_counter=score_counter,
        total_result_count=total_result_count,
        applied_rate=applied_rate,
        critical_result_count=critical_result_count,
        critical_reviewed_count=critical_reviewed_count,
        critical_rate=critical_rate,
        trust_status=trust_status,
        thresholds=resolved_thresholds,
    )

    return EvidenceTrustSummary(
        source_distribution=dict(sorted(source_counter.items())),
        score_distribution=dict(sorted(score_counter.items())),
        total_result_count=total_result_count,
        synthetic_demo_count=source_counter[EvidenceSourceTrustTier.SYNTHETIC_DEMO.value],
        local_authored_count=source_counter[EvidenceSourceTrustTier.LOCAL_AUTHORED.value],
        production_captured_count=source_counter[EvidenceSourceTrustTier.PRODUCTION_CAPTURED.value],
        unverified_production_captured_count=source_counter[
            EvidenceSourceTrustTier.PRODUCTION_CAPTURED_UNVERIFIED.value
        ],
        external_benchmark_count=source_counter[EvidenceSourceTrustTier.EXTERNAL_BENCHMARK.value],
        unknown_source_count=source_counter[EvidenceSourceTrustTier.UNKNOWN.value],
        heuristic_only_count=score_counter[EvidenceScoreTrustTier.HEURISTIC.value],
        candidate_judge_label_count=score_counter[
            EvidenceScoreTrustTier.CANDIDATE_JUDGE_LABEL.value
        ],
        applied_judge_label_count=applied_count,
        human_reviewed_count=human_reviewed_count,
        unknown_score_count=score_counter[EvidenceScoreTrustTier.UNKNOWN.value],
        critical_result_count=critical_result_count,
        critical_reviewed_count=critical_reviewed_count,
        applied_judge_label_rate=round(applied_rate, 4),
        critical_review_coverage_rate=round(critical_rate, 4),
        trust_status=trust_status,
        production_readiness=production_readiness,
        reasons=reasons,
        limitations=limitations,
    )


def summarize_gate_evidence_trust(
    db: Session,
    gate: GateEvaluation,
    *,
    thresholds: EvidenceTrustThresholds | None = None,
) -> EvidenceTrustSummary:
    snapshot = gate.evidence_snapshot_json if isinstance(gate.evidence_snapshot_json, dict) else {}
    run_ids = _uuid_values(snapshot.get("benchmark_run_ids"))
    if not run_ids:
        return summarize_evidence_trust([], {}, thresholds=thresholds)
    results = list(
        db.scalars(select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id.in_(run_ids)))
    )
    case_ids = {result.evaluation_case_id for result in results if result.evaluation_case_id}
    cases = (
        list(db.scalars(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))))
        if case_ids
        else []
    )
    cases_by_id = {evaluation_case.id: evaluation_case for evaluation_case in cases}
    result_case_map = {
        result.id: cases_by_id[result.evaluation_case_id]
        for result in results
        if result.evaluation_case_id in cases_by_id
    }
    from app.services.supply_chain import verified_production_run_ids

    return summarize_evidence_trust(
        results,
        result_case_map,
        thresholds=thresholds,
        verified_production_run_ids=verified_production_run_ids(db, set(run_ids)),
    )


def _trust_status(
    *,
    source_counter: Counter[str],
    total_result_count: int,
    applied_rate: float,
    critical_result_count: int,
    critical_reviewed_count: int,
    critical_rate: float,
    thresholds: EvidenceTrustThresholds,
) -> str:
    if (
        total_result_count == 0
        or source_counter[EvidenceSourceTrustTier.UNKNOWN.value] == total_result_count
    ):
        return "unknown"
    if source_counter[EvidenceSourceTrustTier.SYNTHETIC_DEMO.value] == total_result_count:
        return "synthetic_only"

    production_review_ready = (
        applied_rate >= thresholds.minimum_applied_judge_label_rate_for_production
        and (
            critical_result_count == 0
            or critical_rate >= thresholds.minimum_critical_review_coverage_rate_for_production
        )
    )
    if (
        source_counter[EvidenceSourceTrustTier.PRODUCTION_CAPTURED.value]
        >= thresholds.minimum_production_captured_result_count
        and production_review_ready
    ):
        return "production_evidence_ready"

    local_review_ready = (
        applied_rate >= thresholds.minimum_applied_judge_label_rate_for_local_demo
        and (
            critical_result_count == 0
            or critical_reviewed_count >= thresholds.minimum_critical_reviewed_count_for_local_demo
        )
    )
    if not local_review_ready:
        return "needs_judge_review"
    if (
        source_counter[EvidenceSourceTrustTier.LOCAL_AUTHORED.value]
        or source_counter[EvidenceSourceTrustTier.PRODUCTION_CAPTURED.value]
    ):
        return "local_demo_ready"
    return "unknown"


def _explain_summary(
    *,
    source_counter: Counter[str],
    score_counter: Counter[str],
    total_result_count: int,
    applied_rate: float,
    critical_result_count: int,
    critical_reviewed_count: int,
    critical_rate: float,
    trust_status: str,
    thresholds: EvidenceTrustThresholds,
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    limitations: list[str] = []
    if trust_status == "unknown":
        reasons.append("Evidence trust could not be established from the available provenance.")
    elif trust_status == "synthetic_only":
        reasons.append("All selected benchmark results use synthetic demonstration evidence.")
    elif trust_status == "needs_judge_review":
        reasons.append("The selected evidence does not meet the minimum judge-review coverage.")
    elif trust_status == "local_demo_ready":
        reasons.append(
            "Locally authored evidence meets the minimum review coverage for a reproducible demo."
        )
    else:
        reasons.append(
            "Production-captured evidence and review coverage meet the configured thresholds."
        )

    if total_result_count == 0:
        limitations.append("No benchmark results are available for trust classification.")
    if source_counter[EvidenceSourceTrustTier.UNKNOWN.value]:
        limitations.append("Some results have an unknown or legacy evidence source.")
    if source_counter[EvidenceSourceTrustTier.PRODUCTION_CAPTURED_UNVERIFIED.value]:
        limitations.append(
            "Some production-labeled results do not have an active signed capture receipt."
        )
    if source_counter[EvidenceSourceTrustTier.SYNTHETIC_DEMO.value]:
        limitations.append("Synthetic evidence cannot establish production readiness.")
    if not source_counter[EvidenceSourceTrustTier.PRODUCTION_CAPTURED.value]:
        limitations.append("Production-captured evidence is missing.")
    elif (
        source_counter[EvidenceSourceTrustTier.PRODUCTION_CAPTURED.value]
        < thresholds.minimum_production_captured_result_count
    ):
        limitations.append(
            "Production-captured result count is below the configured production threshold."
        )
    if applied_rate < thresholds.minimum_applied_judge_label_rate_for_local_demo:
        limitations.append(
            "Applied or human-reviewed label coverage is below the local-demo threshold."
        )
    if critical_result_count and critical_reviewed_count == 0:
        limitations.append(
            "Critical cases exist, but none have an applied or human-reviewed label."
        )
    elif (
        critical_result_count
        and critical_rate < thresholds.minimum_critical_review_coverage_rate_for_production
    ):
        limitations.append("Critical-case review coverage is below the production threshold.")
    if (
        source_counter[EvidenceSourceTrustTier.EXTERNAL_BENCHMARK.value]
        and not source_counter[EvidenceSourceTrustTier.LOCAL_AUTHORED.value]
        and not source_counter[EvidenceSourceTrustTier.PRODUCTION_CAPTURED.value]
    ):
        limitations.append(
            "External benchmark evidence alone does not establish workload-specific readiness."
        )
    if (
        score_counter[EvidenceScoreTrustTier.HEURISTIC.value] == total_result_count
        and total_result_count
    ):
        limitations.append(
            "All result scores are heuristic and require judge review before release."
        )
    return list(dict.fromkeys(reasons)), list(dict.fromkeys(limitations))


def _has_explicit_human_review(
    metadata: Mapping[str, Any],
    judge_label: Mapping[str, Any],
) -> bool:
    if metadata.get("human_reviewed") is True:
        return True
    human_review = _mapping(metadata.get("human_review"))
    if human_review.get("reviewed") is True or human_review.get("applied") is True:
        return True
    review = _mapping(metadata.get("review"))
    if review.get("human_reviewed") is True or review.get("reviewer_type") == "human":
        return True
    source = str(judge_label.get("source") or "").strip().lower()
    return judge_label.get("applied") is True and (
        judge_label.get("human_reviewed") is True
        or judge_label.get("reviewer_type") == "human"
        or source in {"human", "human_review", "human_reviewer", "manual_review"}
    )


def _candidate_judge_labels(evaluation_case: EvaluationCase | None) -> Mapping[str, Any]:
    if evaluation_case is None:
        return {}
    reference = _mapping(evaluation_case.reference_context_json)
    return _mapping(reference.get("judge_labels"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _uuid_values(values: Any) -> list[UUID]:
    if not isinstance(values, list):
        return []
    output: list[UUID] = []
    for value in values:
        try:
            output.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue
    return output
