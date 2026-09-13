from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.structured_requests import actor_for
from app.db.session import get_db
from app.models.request_workflows import RequestWorkflowAttempt
from app.schemas.request_workflows import (
    FinishWorkflow,
    StartWorkflow,
    WorkflowBinding,
    WorkflowDraft,
)
from app.services import request_workflows as service
from app.services.request_workflow_catalog import catalog as public_catalog
from app.services.structured_requests import owner_key

router = APIRouter()


@router.get("/catalog")
def catalog(request: Request):
    actor_for(request)
    return public_catalog()


@router.get("/summary")
def summary(request: Request, db: Session = Depends(get_db)):
    return service.summary(db, actor_for(request))


@router.get("/attempts")
def list_attempts(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    actor = actor_for(request)
    rows = db.scalars(
        select(RequestWorkflowAttempt)
        .where(RequestWorkflowAttempt.owner_key == owner_key(actor))
        .order_by(RequestWorkflowAttempt.started_at.desc(), RequestWorkflowAttempt.id)
        .offset(offset)
        .limit(limit)
    )
    return [service.read(db, row, actor) for row in rows]


@router.post("/attempts", status_code=201)
def start(payload: StartWorkflow, request: Request, db: Session = Depends(get_db)):
    return service.start(db, payload, actor_for(request))


@router.get("/attempts/{attempt_id}")
def read(attempt_id: UUID, request: Request, db: Session = Depends(get_db)):
    actor = actor_for(request)
    return service.read(db, service.owned(db, attempt_id, actor), actor)


@router.post("/attempts/{attempt_id}/request", status_code=201)
def create_request(
    attempt_id: UUID, payload: WorkflowDraft, request: Request, db: Session = Depends(get_db)
):
    return service.create_draft(db, attempt_id, payload, actor_for(request))


@router.post("/attempts/{attempt_id}/help")
def help_requested(
    attempt_id: UUID, payload: WorkflowBinding, request: Request, db: Session = Depends(get_db)
):
    return service.record_help(db, attempt_id, payload, actor_for(request))


@router.post("/attempts/{attempt_id}/finish")
def finish(
    attempt_id: UUID, payload: FinishWorkflow, request: Request, db: Session = Depends(get_db)
):
    return service.finish(db, attempt_id, payload, actor_for(request))
