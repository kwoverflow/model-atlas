from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    EvaluationCase,
    JudgeLabelReviewDecision,
)
from app.services.evidence_trust import EvidenceScoreTrustTier, classify_score_tier
from tests.test_deployment_gate import _build_gate_graph


def _reviewer_headers(subject_id: str = "judge-reviewer") -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": subject_id,
        "x-model-atlas-operator-name": "Judge Reviewer",
        "x-model-atlas-operator-role": "QA Lead",
    }


def test_reviewed_candidate_label_is_audited_and_applied_once(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="judge-reviewed-label")
    run = db_session.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id
            == ids["deployment_configuration_id"]
        )
    )
    assert run is not None
    result = db_session.scalar(
        select(BenchmarkResult).where(
            BenchmarkResult.benchmark_run_id == run.id
        )
    )
    assert result is not None
    evaluation_case = db_session.get(EvaluationCase, result.evaluation_case_id)
    assert evaluation_case is not None
    context = dict(evaluation_case.reference_context_json or {})
    context["judge_labels"] = {
        "quality_score": 0.93,
        "groundedness_score": 0.91,
        "faithfulness_score": 0.92,
        "human_label": "reviewed-pass",
        "judge_source": "candidate-judge-v2",
        "judge_subject_id": "candidate-judge-service",
    }
    evaluation_case.reference_context_json = context
    db_session.commit()
    payload = {
        "benchmark_result_id": str(result.id),
        "decision_type": "approved_candidate",
        "rationale": "Critical and representative response checked against the rubric.",
    }

    unverified = client.post(
        "/api/v1/judge-labels/review-decisions",
        json=payload,
    )
    assert unverified.status_code == 422
    assert "verified identity" in unverified.text

    response = client.post(
        "/api/v1/judge-labels/review-decisions",
        headers=_reviewer_headers(),
        json=payload,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["decision_type"] == "approved_candidate"
    assert body["applied"] is True
    assert body["identity_verified"] is True
    assert body["applied_scores_json"]["quality_score"] == 0.93

    db_session.refresh(result)
    assert result.quality_score == 0.93
    assert result.groundedness_score == 0.91
    assert result.faithfulness_score == 0.92
    assert result.human_label == "reviewed-pass"
    assert result.metadata_json["judge_label"]["human_reviewed"] is True
    assert classify_score_tier(result, evaluation_case) == (
        EvidenceScoreTrustTier.HUMAN_REVIEWED
    )

    repeated = client.post(
        "/api/v1/judge-labels/review-decisions",
        headers=_reviewer_headers(),
        json=payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["id"] == body["id"]
    assert db_session.scalar(select(JudgeLabelReviewDecision)) is not None

    conflicting = client.post(
        "/api/v1/judge-labels/review-decisions",
        headers=_reviewer_headers(),
        json={
            "benchmark_result_id": str(result.id),
            "decision_type": "overridden",
            "quality_score": 0.5,
            "rationale": "A second applied decision must not rewrite reviewed evidence.",
        },
    )
    assert conflicting.status_code == 422
    assert "already has an applied" in conflicting.text

    listed = client.get(
        "/api/v1/judge-labels/review-decisions",
        params={"benchmark_run_id": str(run.id)},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]


def test_judge_review_enforces_separation_and_records_rejection_without_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="judge-review-separation")
    run = db_session.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id
            == ids["deployment_configuration_id"]
        )
    )
    assert run is not None
    results = list(
        db_session.scalars(
            select(BenchmarkResult)
            .where(BenchmarkResult.benchmark_run_id == run.id)
            .order_by(BenchmarkResult.sample_id)
        )
    )
    assert len(results) >= 2
    first_case = db_session.get(EvaluationCase, results[0].evaluation_case_id)
    assert first_case is not None
    first_context = dict(first_case.reference_context_json or {})
    first_context["judge_labels"] = {
        "quality_score": 0.8,
        "judge_subject_id": "same-reviewer",
    }
    first_case.reference_context_json = first_context
    second_case = db_session.get(EvaluationCase, results[1].evaluation_case_id)
    assert second_case is not None
    second_context = dict(second_case.reference_context_json or {})
    second_context["judge_labels"] = {"quality_score": 0.2}
    second_case.reference_context_json = second_context
    original_quality = results[1].quality_score
    db_session.commit()

    same_actor = client.post(
        "/api/v1/judge-labels/review-decisions",
        headers=_reviewer_headers("same-reviewer"),
        json={
            "benchmark_result_id": str(results[0].id),
            "decision_type": "approved_candidate",
            "rationale": "This must fail separation of duties.",
        },
    )
    assert same_actor.status_code == 422
    assert "different identities" in same_actor.text

    rejected = client.post(
        "/api/v1/judge-labels/review-decisions",
        headers=_reviewer_headers(),
        json={
            "benchmark_result_id": str(results[1].id),
            "decision_type": "rejected",
            "rationale": "Candidate score conflicts with the documented rubric.",
        },
    )
    assert rejected.status_code == 201
    assert rejected.json()["applied"] is False
    db_session.refresh(results[1])
    assert results[1].quality_score == original_quality
