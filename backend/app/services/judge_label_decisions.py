from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkResult, EvaluationCase, JudgeLabelReviewDecision
from app.schemas import JudgeLabelReviewDecisionCreate
from app.services.deployment_gate.evidence import stable_hash
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

JUDGE_REVIEW_DECISION_VERSION = "judge-label-review-decision-v1"
JUDGE_REVIEW_ROLES = frozenset(
    {
        "admin",
        "ml engineer",
        "ml ops lead",
        "model governance",
        "qa lead",
    }
)


def create_judge_label_review_decision(
    db: Session,
    *,
    payload: JudgeLabelReviewDecisionCreate,
    reviewer_identity: SignerIdentity,
) -> JudgeLabelReviewDecision:
    assert_judge_reviewer(reviewer_identity)
    result = db.scalar(
        select(BenchmarkResult)
        .where(BenchmarkResult.id == payload.benchmark_result_id)
        .with_for_update()
    )
    if result is None:
        raise DomainValidationError("benchmark_result was not found")
    evaluation_case = (
        db.get(EvaluationCase, result.evaluation_case_id)
        if result.evaluation_case_id
        else None
    )
    candidate = _candidate_labels(evaluation_case)
    _assert_separation_of_duties(candidate, reviewer_identity)
    applied_scores = _review_scores(payload, candidate=candidate)
    prior_scores = _result_scores(result)
    candidate_hash = stable_hash(candidate) if candidate else None
    review_payload = {
        "version": JUDGE_REVIEW_DECISION_VERSION,
        "benchmark_result_id": str(result.id),
        "decision_type": payload.decision_type,
        "candidate_label_hash": candidate_hash,
        "applied_scores": applied_scores,
        "reviewer_identity": reviewer_identity.to_json(),
        "rationale": payload.rationale.strip(),
    }
    review_hash = stable_hash(review_payload)
    existing = db.scalar(
        select(JudgeLabelReviewDecision).where(
            JudgeLabelReviewDecision.review_hash == review_hash
        )
    )
    if existing is not None:
        return existing
    if applied_scores is not None:
        prior_applied = db.scalar(
            select(JudgeLabelReviewDecision)
            .where(JudgeLabelReviewDecision.benchmark_result_id == result.id)
            .where(JudgeLabelReviewDecision.applied.is_(True))
        )
        if prior_applied is not None:
            raise DomainValidationError(
                "benchmark result already has an applied reviewed-label decision"
            )
    reviewed_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    decision = JudgeLabelReviewDecision(
        benchmark_result_id=result.id,
        evaluation_case_id=result.evaluation_case_id,
        decision_type=payload.decision_type,
        candidate_label_hash=candidate_hash,
        prior_scores_json=prior_scores,
        applied_scores_json=applied_scores,
        applied=applied_scores is not None,
        reviewer_identity_json=reviewer_identity.to_json(),
        identity_verified=True,
        rationale=payload.rationale.strip(),
        criticality=evaluation_case.criticality if evaluation_case else None,
        reviewed_at=reviewed_at,
        review_hash=review_hash,
    )
    if applied_scores is not None:
        _apply_reviewed_scores(
            result,
            applied_scores=applied_scores,
            candidate=candidate,
            reviewer_identity=reviewer_identity,
            review_hash=review_hash,
            reviewed_at=reviewed_at,
            decision_type=payload.decision_type,
        )
        db.add(result)
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision


def list_judge_label_review_decisions(
    db: Session,
    *,
    benchmark_result_id: UUID | None = None,
    benchmark_run_id: UUID | None = None,
    limit: int = 200,
) -> list[JudgeLabelReviewDecision]:
    query = select(JudgeLabelReviewDecision)
    if benchmark_result_id is not None:
        query = query.where(
            JudgeLabelReviewDecision.benchmark_result_id == benchmark_result_id
        )
    if benchmark_run_id is not None:
        query = query.join(
            BenchmarkResult,
            JudgeLabelReviewDecision.benchmark_result_id == BenchmarkResult.id,
        ).where(BenchmarkResult.benchmark_run_id == benchmark_run_id)
    return list(
        db.scalars(
            query.order_by(JudgeLabelReviewDecision.reviewed_at.desc()).limit(limit)
        ).all()
    )


def assert_judge_reviewer(identity: SignerIdentity) -> None:
    role = (identity.role or "").strip().lower()
    if not identity.identity_verified:
        raise DomainValidationError("judge label application requires verified identity")
    if role not in JUDGE_REVIEW_ROLES:
        raise DomainValidationError("operator role cannot review judge labels")


def _candidate_labels(evaluation_case: EvaluationCase | None) -> dict[str, Any]:
    if evaluation_case is None or not isinstance(
        evaluation_case.reference_context_json,
        dict,
    ):
        return {}
    labels = evaluation_case.reference_context_json.get("judge_labels")
    return dict(labels) if isinstance(labels, dict) else {}


def _review_scores(
    payload: JudgeLabelReviewDecisionCreate,
    *,
    candidate: Mapping[str, Any],
) -> dict[str, Any] | None:
    if payload.decision_type == "rejected":
        return None
    if payload.decision_type == "overridden":
        return {
            "quality_score": payload.quality_score,
            "groundedness_score": payload.groundedness_score,
            "faithfulness_score": payload.faithfulness_score,
            "human_label": payload.human_label,
        }
    if not candidate:
        raise DomainValidationError("candidate judge labels were not found")
    scores = {
        "quality_score": _candidate_score(candidate, "quality_score"),
        "groundedness_score": _candidate_score(candidate, "groundedness_score"),
        "faithfulness_score": _candidate_score(candidate, "faithfulness_score"),
        "human_label": _candidate_text(candidate, "human_label"),
    }
    if not any(value is not None for value in scores.values()):
        raise DomainValidationError("candidate judge labels do not contain label values")
    return scores


def _result_scores(result: BenchmarkResult) -> dict[str, Any]:
    return {
        "quality_score": result.quality_score,
        "groundedness_score": result.groundedness_score,
        "faithfulness_score": result.faithfulness_score,
        "human_label": result.human_label,
    }


def _apply_reviewed_scores(
    result: BenchmarkResult,
    *,
    applied_scores: Mapping[str, Any],
    candidate: Mapping[str, Any],
    reviewer_identity: SignerIdentity,
    review_hash: str,
    reviewed_at: dt.datetime,
    decision_type: str,
) -> None:
    for field in ("quality_score", "groundedness_score", "faithfulness_score"):
        value = applied_scores.get(field)
        if value is not None:
            setattr(result, field, float(value))
    human_label = applied_scores.get("human_label")
    if human_label is not None:
        result.human_label = str(human_label)
    metadata = dict(result.metadata_json or {})
    metadata["judge_label"] = {
        "version": JUDGE_REVIEW_DECISION_VERSION,
        "source": (
            "reviewed_candidate"
            if decision_type == "approved_candidate"
            else "manual_review"
        ),
        "candidate_source": candidate.get("judge_source"),
        "applied": True,
        "human_reviewed": True,
        "reviewer_type": "human",
        "review_hash": review_hash,
        "reviewed_at": reviewed_at.isoformat(),
        "reviewer_identity": reviewer_identity.to_json(),
    }
    metadata["human_reviewed"] = True
    metadata["human_review"] = {
        "reviewed": True,
        "review_hash": review_hash,
        "reviewer_identity": reviewer_identity.to_json(),
    }
    result.metadata_json = metadata


def _candidate_score(candidate: Mapping[str, Any], key: str) -> float | None:
    value = candidate.get(key)
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(f"candidate {key} is invalid") from exc
    if not 0 <= score <= 1:
        raise DomainValidationError(f"candidate {key} must be between 0 and 1")
    return score


def _candidate_text(candidate: Mapping[str, Any], key: str) -> str | None:
    value = candidate.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:120]


def _assert_separation_of_duties(
    candidate: Mapping[str, Any],
    reviewer_identity: SignerIdentity,
) -> None:
    candidate_subject = str(
        candidate.get("judge_subject_id")
        or candidate.get("reviewer_subject_id")
        or ""
    ).strip()
    if candidate_subject and candidate_subject == reviewer_identity.subject_id:
        raise DomainValidationError(
            "candidate judge and approving reviewer must be different identities"
        )
