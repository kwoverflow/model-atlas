from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkResult, EvaluationCase
from app.schemas import JudgeLabelReviewResponse, JudgeLabelReviewRow
from app.services.evidence_trust import summarize_evidence_trust
from app.services.supply_chain import verified_production_run_ids


def review_judge_labels(
    db: Session,
    *,
    limit: int,
    offset: int,
    benchmark_run_id: UUID | None = None,
    benchmark_result_id: UUID | None = None,
) -> JudgeLabelReviewResponse:
    query = select(BenchmarkResult, EvaluationCase).outerjoin(
        EvaluationCase,
        BenchmarkResult.evaluation_case_id == EvaluationCase.id,
    )
    if benchmark_run_id is not None:
        query = query.where(BenchmarkResult.benchmark_run_id == benchmark_run_id)
    if benchmark_result_id is not None:
        query = query.where(BenchmarkResult.id == benchmark_result_id)
    records = list(
        db.execute(
            query.order_by(BenchmarkResult.created_at.desc(), BenchmarkResult.sample_id.asc())
        )
    )
    results = [result for result, _case in records]
    trust = summarize_evidence_trust(
        results,
        {result.id: case for result, case in records if case is not None},
        verified_production_run_ids=verified_production_run_ids(
            db,
            {result.benchmark_run_id for result in results},
        ),
    )
    all_rows = [_review_row(result, case) for result, case in records]
    visible_rows = all_rows[offset : offset + limit]
    quality_values = [row.quality_score for row in all_rows if row.quality_score is not None]
    candidate_deltas = [
        row.quality_delta_vs_candidate
        for row in all_rows
        if row.quality_delta_vs_candidate is not None
    ]

    return JudgeLabelReviewResponse(
        benchmark_run_id=benchmark_run_id,
        benchmark_result_id=benchmark_result_id,
        result_count=len(all_rows),
        reviewed_count=sum(
            1
            for row in all_rows
            if row.score_source in {"applied_judge_label", "human_reviewed"}
        ),
        candidate_label_count=sum(1 for row in all_rows if row.candidate_judge_labels),
        heuristic_scored_count=sum(1 for row in all_rows if row.scorer_metadata),
        heuristic_only_count=trust.heuristic_only_count,
        applied_label_count=trust.applied_judge_label_count,
        human_reviewed_count=trust.human_reviewed_count,
        unlabeled_count=sum(1 for row in all_rows if row.score_source == "unlabeled"),
        needs_review_count=sum(1 for row in all_rows if row.needs_review),
        applied_label_coverage_rate=trust.applied_judge_label_rate,
        critical_result_count=trust.critical_result_count,
        critical_reviewed_count=trust.critical_reviewed_count,
        critical_review_coverage_rate=trust.critical_review_coverage_rate,
        average_quality_score=_mean(quality_values),
        average_abs_quality_delta_vs_candidate=_mean(candidate_deltas),
        rows=visible_rows,
    )


def _review_row(
    result: BenchmarkResult,
    evaluation_case: EvaluationCase | None,
) -> JudgeLabelReviewRow:
    candidate_labels = _candidate_judge_labels(evaluation_case)
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    judge_label_metadata = _dict_or_none(metadata.get("judge_label"))
    scorer_metadata = _dict_or_none(metadata.get("scorer"))
    quality_delta = _quality_delta(result.quality_score, candidate_labels)
    score_source = _score_source(
        result=result,
        candidate_labels=candidate_labels,
        judge_label_metadata=judge_label_metadata,
        scorer_metadata=scorer_metadata,
    )

    return JudgeLabelReviewRow(
        benchmark_result_id=result.id,
        benchmark_run_id=result.benchmark_run_id,
        evaluation_case_id=result.evaluation_case_id,
        sample_id=result.sample_id,
        external_case_id=evaluation_case.external_case_id if evaluation_case else None,
        title=evaluation_case.title if evaluation_case else None,
        category=evaluation_case.category if evaluation_case else None,
        criticality=evaluation_case.criticality if evaluation_case else None,
        quality_score=result.quality_score,
        groundedness_score=result.groundedness_score,
        faithfulness_score=result.faithfulness_score,
        human_label=result.human_label,
        data_source=result.data_source,
        score_source=score_source,
        candidate_judge_labels=candidate_labels,
        judge_label_metadata=judge_label_metadata,
        scorer_metadata=scorer_metadata,
        quality_delta_vs_candidate=quality_delta,
        needs_review=_needs_review(
            result=result,
            score_source=score_source,
            candidate_labels=candidate_labels,
            quality_delta=quality_delta,
        ),
    )


def _candidate_judge_labels(evaluation_case: EvaluationCase | None) -> dict[str, Any] | None:
    if evaluation_case is None or not isinstance(evaluation_case.reference_context_json, dict):
        return None
    return _dict_or_none(evaluation_case.reference_context_json.get("judge_labels"))


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) and value else None


def _quality_delta(
    quality_score: float | None,
    candidate_labels: dict[str, Any] | None,
) -> float | None:
    if quality_score is None or candidate_labels is None:
        return None
    candidate_quality = candidate_labels.get("quality_score")
    if candidate_quality is None:
        return None
    return abs(float(candidate_quality) - quality_score)


def _score_source(
    *,
    result: BenchmarkResult,
    candidate_labels: dict[str, Any] | None,
    judge_label_metadata: dict[str, Any] | None,
    scorer_metadata: dict[str, Any] | None,
) -> str:
    if (
        judge_label_metadata
        and judge_label_metadata.get("applied") is True
        and (
            judge_label_metadata.get("human_reviewed") is True
            or judge_label_metadata.get("reviewer_type") == "human"
        )
    ):
        return "human_reviewed"
    if judge_label_metadata and judge_label_metadata.get("applied") is True:
        return "applied_judge_label"
    if candidate_labels:
        return "candidate_judge_label"
    if scorer_metadata:
        return "heuristic"
    if result.human_label:
        return "raw_label"
    return "unlabeled"


def _needs_review(
    *,
    result: BenchmarkResult,
    score_source: str,
    candidate_labels: dict[str, Any] | None,
    quality_delta: float | None,
) -> bool:
    if score_source in {"applied_judge_label", "human_reviewed"}:
        return False
    if candidate_labels is not None:
        return True
    if score_source in {"heuristic", "raw_label", "unlabeled"}:
        return True
    if quality_delta is not None and quality_delta >= 0.1:
        return True
    return result.quality_score is None or result.human_label in {
        None,
        "captured-needs-scoring",
    }


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)
