from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.structured_requests import actor_for
from app.db.session import get_db
from app.models.request_scenarios import RequestScenarioRun, RequestStudyAttempt
from app.schemas.request_scenarios import SaveStudy, StartStudy, SubmitStudy
from app.services import request_scenario_studies as studies
from app.services.structured_requests import owner_key

router = APIRouter()


@router.get("/catalog")
def catalog(request: Request):
    actor_for(request)
    return studies.public_catalog()


@router.get("/runs")
def list_runs(request: Request, limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)):
    actor = actor_for(request)
    rows = db.scalars(
        select(RequestScenarioRun)
        .where(RequestScenarioRun.owner_key == owner_key(actor))
        .order_by(RequestScenarioRun.created_at.desc())
        .limit(limit)
    )
    return [studies.read_run(row) for row in rows]


@router.post("/runs", status_code=201)
def run(request: Request, db: Session = Depends(get_db)):
    return studies.create_run(db, actor_for(request))


@router.get("/studies")
def list_studies(
    request: Request, limit: int = Query(20, ge=1, le=50), db: Session = Depends(get_db)
):
    actor = actor_for(request)
    rows = db.scalars(
        select(RequestStudyAttempt)
        .where(RequestStudyAttempt.owner_key == owner_key(actor))
        .order_by(RequestStudyAttempt.started_at.desc())
        .limit(limit)
    )
    return [studies.read_attempt(row) for row in rows]


@router.post("/studies", status_code=201)
def start_study(payload: StartStudy, request: Request, db: Session = Depends(get_db)):
    return studies.start_attempt(db, payload, actor_for(request))


@router.get("/studies/{attempt_id}")
def get_study(attempt_id: UUID, request: Request, db: Session = Depends(get_db)):
    return studies.read_attempt(studies.owned_attempt(db, attempt_id, actor_for(request)))


@router.put("/studies/{attempt_id}")
def save_study(
    attempt_id: UUID, payload: SaveStudy, request: Request, db: Session = Depends(get_db)
):
    return studies.save_answer(db, attempt_id, payload, actor_for(request))


@router.post("/studies/{attempt_id}/submit")
def submit_study(
    attempt_id: UUID, payload: SubmitStudy, request: Request, db: Session = Depends(get_db)
):
    return studies.submit_answer(db, attempt_id, payload, actor_for(request))
