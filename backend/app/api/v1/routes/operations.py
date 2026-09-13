from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import (
    AgentExecutionJobRead,
    OperationalAlertIncidentActionRead,
    OperationalAlertRead,
    OperationalCycleCreate,
    OperationalIncidentActionCreate,
    OperationalMetricsRead,
    OperationalReliabilityOverviewRead,
    OperationalTestPageCreate,
)
from app.services.agent_jobs import (
    enqueue_operational_alert_delivery_job,
    enqueue_operational_observability_cycle_job,
)
from app.services.operational_metrics import (
    collect_operational_metrics,
    render_prometheus_metrics,
)
from app.services.operational_reliability import (
    build_operational_reliability_overview,
    create_operational_test_delivery,
    operational_reliability_permissions,
    record_operational_incident_action,
)
from app.services.operator_identity import SignerIdentity, local_operator_identity

router = APIRouter()
prometheus_router = APIRouter()
settings = get_settings()


@router.get("/metrics", response_model=OperationalMetricsRead)
def get_operational_metrics(
    db: Session = Depends(get_db),
) -> OperationalMetricsRead:
    return collect_operational_metrics(db, settings=settings)


@router.get("/alerts", response_model=list[OperationalAlertRead])
def get_operational_alerts(
    db: Session = Depends(get_db),
) -> list[OperationalAlertRead]:
    return collect_operational_metrics(db, settings=settings).alerts


@router.get(
    "/reliability",
    response_model=OperationalReliabilityOverviewRead,
)
def get_operational_reliability(
    request: Request,
    snapshot_limit: int = Query(default=60, ge=1, le=500),
    incident_limit: int = Query(default=100, ge=1, le=500),
    action_limit: int = Query(default=200, ge=1, le=1000),
    delivery_limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> OperationalReliabilityOverviewRead:
    return build_operational_reliability_overview(
        db,
        settings=settings,
        signer_identity=_operator(request),
        snapshot_limit=snapshot_limit,
        incident_limit=incident_limit,
        action_limit=action_limit,
        delivery_limit=delivery_limit,
    )


@router.post(
    "/reliability/cycles",
    response_model=AgentExecutionJobRead,
    status_code=202,
)
def queue_operational_reliability_cycle(
    payload: OperationalCycleCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    identity = _operator(request)
    _require_operational_administrator(identity)
    return enqueue_operational_observability_cycle_job(
        db,
        schedule_key=f"manual-{uuid4()}",
        signer_identity=identity,
        reason=payload.reason,
    )


@router.post(
    "/reliability/test-pages",
    response_model=AgentExecutionJobRead,
    status_code=202,
)
def queue_operational_test_page(
    payload: OperationalTestPageCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    identity = _operator(request)
    _require_operational_administrator(identity)
    delivery = create_operational_test_delivery(
        db,
        settings=settings,
        signer_identity=identity,
        severity=payload.severity,
        reason=payload.reason,
    )
    return enqueue_operational_alert_delivery_job(
        db,
        delivery_id=delivery.id,
        signer_identity=identity,
    )


@router.post(
    "/reliability/incidents/{incident_id}/actions",
    response_model=OperationalAlertIncidentActionRead,
    status_code=201,
)
def create_operational_incident_action(
    incident_id: UUID,
    payload: OperationalIncidentActionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> OperationalAlertIncidentActionRead:
    identity = _operator(request)
    _require_operational_administrator(identity)
    return record_operational_incident_action(
        db,
        incident_id=incident_id,
        signer_identity=identity,
        action_type=payload.action_type,
        reason=payload.reason,
        assignee=payload.assignee,
    )


@prometheus_router.get("/metrics", response_class=PlainTextResponse)
def get_prometheus_metrics(db: Session = Depends(get_db)) -> PlainTextResponse:
    body = render_prometheus_metrics(
        collect_operational_metrics(db, settings=settings)
    )
    return PlainTextResponse(
        body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _operator(request: Request) -> SignerIdentity:
    return getattr(request.state, "operator_identity", None) or local_operator_identity()


def _require_operational_administrator(identity: SignerIdentity) -> None:
    if not operational_reliability_permissions(identity).can_administer:
        raise HTTPException(
            status_code=403,
            detail="Verified Admin or SRE Lead identity is required.",
        )
