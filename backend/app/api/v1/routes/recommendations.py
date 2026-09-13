from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    RecommendationReport,
    RecommendationRequest,
    RecommendationScenarioCreate,
    RecommendationScenarioRead,
    RecommendationScenarioUpdate,
    RecommendationWeights,
)
from app.services import recommendation_scenarios
from app.services.recommendation_exports import (
    render_recommendation_report_markdown,
    render_recommendation_report_pdf,
)
from app.services.recommendations import build_recommendation_report
from app.validators import DomainValidationError

router = APIRouter()


def _weights_from_query(
    *,
    quality: float,
    latency: float,
    throughput: float,
    vram_efficiency: float,
) -> RecommendationWeights:
    if quality + latency + throughput + vram_efficiency <= 0:
        raise DomainValidationError(
            "at least one recommendation weight must be greater than zero"
        )
    return RecommendationWeights(
        quality=quality,
        latency=latency,
        throughput=throughput,
        vram_efficiency=vram_efficiency,
    )


def recommendation_request_from_query(
    hardware_profile_id: UUID | None = None,
    benchmark_task_id: UUID | None = None,
    require_tool_calling: bool = False,
    require_structured_output: bool = False,
    commercial_use_required: bool = False,
    min_context_length: int | None = Query(default=None, gt=0),
    top_k: int = Query(default=5, ge=1, le=20),
    quality_weight: float = Query(default=0.45, ge=0, le=1),
    latency_weight: float = Query(default=0.20, ge=0, le=1),
    throughput_weight: float = Query(default=0.20, ge=0, le=1),
    vram_efficiency_weight: float = Query(default=0.15, ge=0, le=1),
) -> RecommendationRequest:
    return RecommendationRequest(
        hardware_profile_id=hardware_profile_id,
        benchmark_task_id=benchmark_task_id,
        require_tool_calling=require_tool_calling,
        require_structured_output=require_structured_output,
        commercial_use_required=commercial_use_required,
        min_context_length=min_context_length,
        top_k=top_k,
        weights=_weights_from_query(
            quality=quality_weight,
            latency=latency_weight,
            throughput=throughput_weight,
            vram_efficiency=vram_efficiency_weight,
        ),
    )


def _markdown_response(markdown: str, filename: str) -> Response:
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _pdf_response(pdf: bytes, filename: str) -> Response:
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report", response_model=RecommendationReport)
def get_recommendation_report(
    request: RecommendationRequest = Depends(recommendation_request_from_query),
    db: Session = Depends(get_db),
) -> RecommendationReport:
    return build_recommendation_report(db, request)


@router.get("/report/export.md", response_class=Response)
def export_recommendation_report_markdown(
    request: RecommendationRequest = Depends(recommendation_request_from_query),
    db: Session = Depends(get_db),
) -> Response:
    report = build_recommendation_report(db, request)
    markdown = render_recommendation_report_markdown(report)
    return _markdown_response(markdown, "model-atlas-recommendation-report.md")


@router.get("/report/export.pdf", response_class=Response)
def export_recommendation_report_pdf(
    request: RecommendationRequest = Depends(recommendation_request_from_query),
    db: Session = Depends(get_db),
) -> Response:
    report = build_recommendation_report(db, request)
    pdf = render_recommendation_report_pdf(report)
    return _pdf_response(pdf, "model-atlas-recommendation-report.pdf")


@router.post("/report", response_model=RecommendationReport)
def create_recommendation_report(
    payload: RecommendationRequest,
    db: Session = Depends(get_db),
) -> RecommendationReport:
    return build_recommendation_report(db, payload)


@router.get("/scenarios", response_model=list[RecommendationScenarioRead])
def list_recommendation_scenarios(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[RecommendationScenarioRead]:
    return recommendation_scenarios.list_scenarios(db, limit=limit, offset=offset)


@router.post("/scenarios", response_model=RecommendationScenarioRead, status_code=201)
def create_recommendation_scenario(
    payload: RecommendationScenarioCreate,
    db: Session = Depends(get_db),
) -> RecommendationScenarioRead:
    return recommendation_scenarios.create_scenario(db, payload)


@router.get("/scenarios/{scenario_id}", response_model=RecommendationScenarioRead)
def get_recommendation_scenario(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> RecommendationScenarioRead:
    return recommendation_scenarios.get_scenario(db, scenario_id)


@router.patch("/scenarios/{scenario_id}", response_model=RecommendationScenarioRead)
def update_recommendation_scenario(
    scenario_id: UUID,
    payload: RecommendationScenarioUpdate,
    db: Session = Depends(get_db),
) -> RecommendationScenarioRead:
    return recommendation_scenarios.update_scenario(db, scenario_id, payload)


@router.delete("/scenarios/{scenario_id}", status_code=204, response_class=Response)
def delete_recommendation_scenario(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    recommendation_scenarios.delete_scenario(db, scenario_id)
    return Response(status_code=204)


@router.get("/scenarios/{scenario_id}/report", response_model=RecommendationReport)
def get_recommendation_scenario_report(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> RecommendationReport:
    scenario = recommendation_scenarios.get_scenario(db, scenario_id)
    return build_recommendation_report(db, scenario.request)


@router.get("/scenarios/{scenario_id}/report/export.md", response_class=Response)
def export_recommendation_scenario_report_markdown(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    scenario = recommendation_scenarios.get_scenario(db, scenario_id)
    report = build_recommendation_report(db, scenario.request)
    markdown = render_recommendation_report_markdown(
        report,
        title=f"Model Atlas Recommendation Report: {scenario.name}",
    )
    return _markdown_response(markdown, "model-atlas-recommendation-scenario.md")


@router.get("/scenarios/{scenario_id}/report/export.pdf", response_class=Response)
def export_recommendation_scenario_report_pdf(
    scenario_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    scenario = recommendation_scenarios.get_scenario(db, scenario_id)
    report = build_recommendation_report(db, scenario.request)
    pdf = render_recommendation_report_pdf(
        report,
        title=f"Model Atlas Recommendation Report: {scenario.name}",
    )
    return _pdf_response(pdf, "model-atlas-recommendation-scenario.pdf")
