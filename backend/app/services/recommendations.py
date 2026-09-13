from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkTask, HardwareProfile, Model, ModelArtifact
from app.schemas.recommendations import (
    EligibilityIssue,
    RecommendationReport,
    RecommendationRequest,
)
from app.services.analytics import get_model_comparison
from app.services.recommendation_evidence import aggregate_evidence, comparison_by_artifact
from app.services.recommendation_policy import eligibility_issue
from app.services.recommendation_scoring import EligibleArtifactEvidence, rank_candidates
from app.validators import DomainValidationError


def _resolve_hardware(db: Session, hardware_profile_id: UUID | None) -> HardwareProfile:
    if hardware_profile_id is not None:
        hardware = db.get(HardwareProfile, hardware_profile_id)
    else:
        hardware = db.scalars(select(HardwareProfile).order_by(HardwareProfile.name)).first()
    if hardware is None:
        raise DomainValidationError("no hardware profile is available for recommendation")
    return hardware


def _resolve_task(db: Session, benchmark_task_id: UUID | None) -> BenchmarkTask | None:
    if benchmark_task_id is None:
        return None
    task = db.get(BenchmarkTask, benchmark_task_id)
    if task is None:
        raise DomainValidationError("benchmark_task_id does not reference an existing task")
    return task


def _artifact_rows(db: Session) -> list[tuple[ModelArtifact, Model]]:
    return list(
        db.execute(
            select(ModelArtifact, Model)
            .join(Model, ModelArtifact.model_id == Model.id)
            .order_by(Model.display_name, ModelArtifact.artifact_name)
        ).all()
    )


def _eligible_artifacts(
    artifact_rows: list[tuple[ModelArtifact, Model]],
    hardware: HardwareProfile,
    request: RecommendationRequest,
    rows_by_artifact: dict[str, list],
) -> tuple[list[EligibleArtifactEvidence], list[EligibilityIssue]]:
    eligible: list[EligibleArtifactEvidence] = []
    excluded: list[EligibilityIssue] = []

    for artifact, model in artifact_rows:
        rows = rows_by_artifact.get(str(artifact.id), [])
        issue = eligibility_issue(artifact, model, hardware, request, rows)
        if issue is not None:
            excluded.append(issue)
            continue
        eligible.append(
            EligibleArtifactEvidence(
                artifact=artifact,
                model=model,
                rows=rows,
                metrics=aggregate_evidence(rows),
            )
        )

    return eligible, excluded


def _decision_summary(report: RecommendationReport) -> str:
    recommended = report.recommended_candidate
    if recommended is None:
        return "No eligible model artifact matched the selected hard filters."
    return (
        f"{recommended.artifact_name} is the top deterministic recommendation for "
        f"{report.hardware_profile_name} with confidence-adjusted score "
        f"{recommended.recommendation_score:.2f}."
    )


def build_recommendation_report(
    db: Session,
    request: RecommendationRequest,
) -> RecommendationReport:
    hardware = _resolve_hardware(db, request.hardware_profile_id)
    task = _resolve_task(db, request.benchmark_task_id)
    comparison_rows = get_model_comparison(db)
    rows_by_artifact = comparison_by_artifact(comparison_rows, request.benchmark_task_id)
    artifacts = _artifact_rows(db)
    eligible, excluded = _eligible_artifacts(artifacts, hardware, request, rows_by_artifact)
    ranked_candidates = rank_candidates(eligible, hardware, request)
    top_candidates = ranked_candidates[: request.top_k]
    pareto_frontier = [candidate for candidate in ranked_candidates if candidate.pareto_optimal]

    report = RecommendationReport(
        hardware_profile_id=str(hardware.id),
        hardware_profile_name=hardware.name,
        benchmark_task_id=str(task.id) if task else None,
        benchmark_task_name=task.name if task else None,
        request=request,
        candidate_count=len(artifacts),
        eligible_count=len(ranked_candidates),
        recommended_candidate=top_candidates[0] if top_candidates else None,
        candidates=top_candidates,
        pareto_frontier=pareto_frontier,
        excluded=excluded,
        decision_summary="",
    )
    return report.model_copy(update={"decision_summary": _decision_summary(report)})
