from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    BaselinePromotionCreate,
    DeploymentBaselineRead,
    GateEvaluationCreate,
    GateEvaluationRead,
    GatePreflightRequest,
    GatePreflightResponse,
)
from app.services.deployment_gate.baselines import (
    get_deployment_baseline,
    list_deployment_baselines,
    promote_gate_evaluation_as_baseline,
)
from app.services.deployment_gate.evaluator import (
    create_gate_evaluation,
    get_gate_evaluation,
    list_gate_evaluations,
)
from app.services.deployment_gate.preflight import build_gate_preflight
from app.services.deployment_gate.reporting import (
    render_gate_report_markdown,
    render_gate_report_pdf,
)

router = APIRouter()


@router.post("/preflight", response_model=GatePreflightResponse)
def preflight(
    payload: GatePreflightRequest,
    db: Session = Depends(get_db),
) -> GatePreflightResponse:
    return build_gate_preflight(db, payload)


@router.post("/evaluations", response_model=GateEvaluationRead, status_code=201)
def create_evaluation(
    payload: GateEvaluationCreate,
    db: Session = Depends(get_db),
) -> GateEvaluationRead:
    return create_gate_evaluation(db, payload)


@router.get("/evaluations", response_model=list[GateEvaluationRead])
def list_evaluations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[GateEvaluationRead]:
    return list_gate_evaluations(db, limit=limit, offset=offset)


@router.get("/evaluations/{gate_evaluation_id}", response_model=GateEvaluationRead)
def get_evaluation(
    gate_evaluation_id: UUID,
    db: Session = Depends(get_db),
) -> GateEvaluationRead:
    return get_gate_evaluation(db, gate_evaluation_id)


@router.post(
    "/evaluations/{gate_evaluation_id}/promote-baseline",
    response_model=DeploymentBaselineRead,
    status_code=201,
)
def promote_evaluation_baseline(
    gate_evaluation_id: UUID,
    payload: BaselinePromotionCreate | None = None,
    db: Session = Depends(get_db),
) -> DeploymentBaselineRead:
    return promote_gate_evaluation_as_baseline(
        db,
        gate_evaluation_id=gate_evaluation_id,
        payload=payload or BaselinePromotionCreate(),
    )


@router.get("/baselines", response_model=list[DeploymentBaselineRead])
def list_baselines(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    active_only: bool = Query(default=False),
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[DeploymentBaselineRead]:
    return list_deployment_baselines(
        db,
        limit=limit,
        offset=offset,
        active_only=active_only,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
    )


@router.get("/baselines/{baseline_id}", response_model=DeploymentBaselineRead)
def get_baseline(
    baseline_id: UUID,
    db: Session = Depends(get_db),
) -> DeploymentBaselineRead:
    return get_deployment_baseline(db, baseline_id)


@router.get("/evaluations/{gate_evaluation_id}/report.md", response_class=Response)
def export_gate_report_markdown(
    gate_evaluation_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    gate = get_gate_evaluation(db, gate_evaluation_id)
    markdown = render_gate_report_markdown(gate)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="model-atlas-gate-report.md"'},
    )


@router.get("/evaluations/{gate_evaluation_id}/report.pdf", response_class=Response)
def export_gate_report_pdf(
    gate_evaluation_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    gate = get_gate_evaluation(db, gate_evaluation_id)
    pdf = render_gate_report_pdf(gate)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="model-atlas-gate-report.pdf"'},
    )
