from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from app.models import BenchmarkResult, EvaluationCase
from app.services.evidence_trust import (
    EvidenceScoreTrustTier,
    EvidenceSourceTrustTier,
    EvidenceTrustThresholds,
    classify_score_tier,
    normalize_source_tier,
    summarize_evidence_trust,
)

THRESHOLDS = EvidenceTrustThresholds(
    minimum_applied_judge_label_rate_for_local_demo=0.20,
    minimum_critical_reviewed_count_for_local_demo=1,
    minimum_production_captured_result_count=2,
    minimum_applied_judge_label_rate_for_production=0.30,
    minimum_critical_review_coverage_rate_for_production=0.80,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("synthetic_demo", EvidenceSourceTrustTier.SYNTHETIC_DEMO),
        ("captured_local", EvidenceSourceTrustTier.LOCAL_AUTHORED),
        ("local_authored", EvidenceSourceTrustTier.LOCAL_AUTHORED),
        ("production_captured", EvidenceSourceTrustTier.PRODUCTION_CAPTURED),
        ("external_benchmark", EvidenceSourceTrustTier.EXTERNAL_BENCHMARK),
        ("captured_demo", EvidenceSourceTrustTier.UNKNOWN),
        (None, EvidenceSourceTrustTier.UNKNOWN),
    ],
)
def test_source_tier_normalization(
    source: str | None,
    expected: EvidenceSourceTrustTier,
) -> None:
    assert normalize_source_tier(source) == expected


def test_score_tier_priority_uses_strongest_provenance() -> None:
    heuristic, heuristic_case = _evidence(
        metadata={"scorer": {"scorer_id": "text_presence", "scorer_version": "v1"}}
    )
    assert classify_score_tier(heuristic, heuristic_case) == EvidenceScoreTrustTier.HEURISTIC

    candidate, candidate_case = _evidence(
        metadata={"scorer": {"scorer_id": "text_presence"}},
        candidate_labels=True,
    )
    assert (
        classify_score_tier(candidate, candidate_case)
        == EvidenceScoreTrustTier.CANDIDATE_JUDGE_LABEL
    )

    applied, applied_case = _evidence(
        metadata={
            "scorer": {"scorer_id": "text_presence"},
            "judge_label": {"applied": True, "source": "model_judge"},
        },
        candidate_labels=True,
    )
    assert (
        classify_score_tier(applied, applied_case)
        == EvidenceScoreTrustTier.APPLIED_JUDGE_LABEL
    )

    human, human_case = _evidence(
        metadata={
            "scorer": {"scorer_id": "text_presence"},
            "judge_label": {"applied": True, "source": "human_review"},
        },
        candidate_labels=True,
    )
    assert (
        classify_score_tier(human, human_case)
        == EvidenceScoreTrustTier.HUMAN_REVIEWED
    )


def test_synthetic_only_bundle_is_not_release_evidence() -> None:
    results, case_map = _bundle(
        [("synthetic_demo", _applied_metadata(), "critical")]
    )
    summary = summarize_evidence_trust(results, case_map, thresholds=THRESHOLDS)

    assert summary.trust_status == "synthetic_only"
    assert summary.production_readiness == "not_production_ready"


def test_local_authored_without_review_needs_judge_review() -> None:
    results, case_map = _bundle(
        [("local_authored", _heuristic_metadata(), "critical")]
    )
    summary = summarize_evidence_trust(results, case_map, thresholds=THRESHOLDS)

    assert summary.trust_status == "needs_judge_review"
    assert summary.heuristic_only_count == 1
    assert summary.critical_reviewed_count == 0


def test_local_authored_with_minimum_review_is_local_demo_ready() -> None:
    rows = [
        ("captured_local", _applied_metadata(), "critical"),
        *[("local_authored", _heuristic_metadata(), "standard") for _ in range(4)],
    ]
    results, case_map = _bundle(rows)
    summary = summarize_evidence_trust(results, case_map, thresholds=THRESHOLDS)

    assert summary.trust_status == "local_demo_ready"
    assert summary.local_authored_count == 5
    assert summary.applied_judge_label_rate == 0.2
    assert summary.production_readiness == "not_production_ready"


def test_production_thresholds_create_production_evidence_ready() -> None:
    results, case_map = _bundle(
        [
            ("production_captured", _human_metadata(), "critical"),
            ("production_captured", _applied_metadata(), "standard"),
        ]
    )
    summary = summarize_evidence_trust(results, case_map, thresholds=THRESHOLDS)

    assert summary.trust_status == "production_evidence_ready"
    assert summary.production_readiness == "production_ready"
    assert summary.production_captured_count == 2
    assert summary.critical_review_coverage_rate == 1.0


def test_external_benchmark_only_never_becomes_production_ready() -> None:
    results, case_map = _bundle(
        [
            ("external_benchmark", _human_metadata(), "critical"),
            ("external_benchmark", _applied_metadata(), "standard"),
        ]
    )
    summary = summarize_evidence_trust(results, case_map, thresholds=THRESHOLDS)

    assert summary.trust_status != "production_evidence_ready"
    assert summary.production_readiness != "production_ready"


def test_empty_evidence_is_unknown() -> None:
    summary = summarize_evidence_trust([], {}, thresholds=THRESHOLDS)

    assert summary.trust_status == "unknown"
    assert summary.production_readiness == "unknown"


def _bundle(
    rows: list[tuple[str, dict[str, Any], str]],
) -> tuple[list[BenchmarkResult], dict[UUID, EvaluationCase]]:
    results: list[BenchmarkResult] = []
    case_map: dict[UUID, EvaluationCase] = {}
    for source, metadata, criticality in rows:
        result, evaluation_case = _evidence(
            source=source,
            metadata=metadata,
            criticality=criticality,
        )
        results.append(result)
        case_map[result.id] = evaluation_case
    return results, case_map


def _evidence(
    *,
    source: str = "local_authored",
    metadata: dict[str, Any] | None = None,
    criticality: str = "standard",
    candidate_labels: bool = False,
) -> tuple[BenchmarkResult, EvaluationCase]:
    result_id = uuid4()
    case_id = uuid4()
    reference_context = (
        {"judge_labels": {"quality_score": 0.9}} if candidate_labels else None
    )
    evaluation_case = EvaluationCase(
        id=case_id,
        evaluation_suite_id=uuid4(),
        external_case_id=str(case_id),
        category="test",
        title="Trust test case",
        input_payload_json={"input": "test"},
        reference_context_json=reference_context,
        tags_json=[],
        criticality=criticality,
        weight=1.0,
        is_active=True,
        data_source=source,
    )
    result = BenchmarkResult(
        id=result_id,
        benchmark_run_id=uuid4(),
        evaluation_case_id=case_id,
        sample_id=str(result_id),
        quality_score=0.9,
        json_valid=False,
        tool_call_valid=False,
        metadata_json=metadata,
        data_source=source,
    )
    return result, evaluation_case


def _heuristic_metadata() -> dict[str, Any]:
    return {"scorer": {"scorer_id": "text_presence", "scorer_version": "v1"}}


def _applied_metadata() -> dict[str, Any]:
    return {"judge_label": {"applied": True, "source": "model_judge"}}


def _human_metadata() -> dict[str, Any]:
    return {"judge_label": {"applied": True, "source": "human_review"}}
