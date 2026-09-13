from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.structured_requests import StructuredRequest
from app.schemas.structured_requests import (
    ContractBinding,
    ContractConfirmation,
    ContractEdit,
    ProposalCheck,
    StructuredTicketInput,
)
from app.services import structured_requests as service
from app.services.operator_identity import local_operator_identity

router = APIRouter()


def actor_for(request: Request):
    settings = get_settings()
    actor = getattr(request.state, "operator_identity", None) or local_operator_identity()
    if not actor.identity_verified and (
        settings.oidc_jwt_enabled or settings.oidc_browser_login_enabled
    ):
        raise HTTPException(401, "operator_authentication_required")
    if actor.identity_verified and actor.role not in {
        "Admin",
        "ML Engineer",
        "ML Ops Lead",
        "QA Lead",
        "Release Manager",
    }:
        raise HTTPException(403, "operator_role_not_allowed")
    if request.method != "GET":
        if request.headers.get("x-model-atlas-lab-action") != "1":
            raise HTTPException(403, "explicit_lab_action_required")
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in settings.cors_origins:
            raise HTTPException(403, "origin_not_allowed")
    return actor


@router.get("")
def list_requests(
    request: Request, limit: int = Query(ge=1, le=50, default=20), db: Session = Depends(get_db)
):
    actor = actor_for(request)
    rows = db.scalars(
        select(StructuredRequest)
        .where(StructuredRequest.owner_key == service.owner_key(actor))
        .order_by(StructuredRequest.created_at.desc())
        .limit(limit)
    ).all()
    return [service.read_request(db, row) for row in rows]


@router.post("", status_code=201)
def create_request(payload: StructuredTicketInput, request: Request, db: Session = Depends(get_db)):
    return service.save_draft(db, payload, actor_for(request))


@router.get("/{request_id}")
def get_request(request_id: UUID, request: Request, db: Session = Depends(get_db)):
    return service.read_request(db, service.get_owned(db, request_id, actor_for(request)))


@router.put("/{request_id}")
def edit_request(
    request_id: UUID, payload: ContractEdit, request: Request, db: Session = Depends(get_db)
):
    return service.save_draft(
        db, payload.draft, actor_for(request), request_id=request_id, binding=payload
    )


@router.post("/{request_id}/confirm")
def confirm_request(
    request_id: UUID, payload: ContractConfirmation, request: Request, db: Session = Depends(get_db)
):
    return service.confirm(db, request_id, payload, actor_for(request))


@router.post("/{request_id}/revoke")
def revoke_request(
    request_id: UUID, payload: ContractBinding, request: Request, db: Session = Depends(get_db)
):
    return service.revoke(db, request_id, payload, actor_for(request))


@router.post("/{request_id}/checks", status_code=201)
def check_proposal(
    request_id: UUID, payload: ProposalCheck, request: Request, db: Session = Depends(get_db)
):
    return service.add_check(db, request_id, payload, actor_for(request), payload.proposal)


@router.post("/{request_id}/generate", status_code=201)
def generate_proposal(
    request_id: UUID, payload: ContractBinding, request: Request, db: Session = Depends(get_db)
):
    return service.generate(db, request_id, payload, actor_for(request))


@router.post("/{request_id}/checks/{check_id}/execute")
def execute_proposal(
    request_id: UUID, check_id: UUID, request: Request, db: Session = Depends(get_db)
):
    return service.execute(db, request_id, check_id, actor_for(request))
