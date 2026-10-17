import ipaddress
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.api.v1.routes.structured_requests import actor_for
from app.core.config import get_settings
from app.schemas.personal_assistant import (
    ReviewApproval,
    ReviewBinding,
    ReviewConfirmation,
    ReviewEdit,
    ReviewInput,
)
from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.release_generation import (
    generate_review_draft as generate_draft,
)
from app.services.personal_assistant_workspace import open_review_service
from app.services.structured_requests import owner_key
from app.version import __version__

router = APIRouter()


def review_service(request: Request):
    actor = actor_for(request)
    host = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "testclient"
    if not local:
        raise HTTPException(403, "local_assistant_only")
    settings = get_settings()
    if not settings.personal_assistant_workspace:
        raise HTTPException(503, "assistant_workspace_not_configured")
    base = Path(settings.personal_assistant_workspace).absolute()
    if not base.is_dir() or base.resolve() != base:
        raise HTTPException(503, "assistant_workspace_not_initialized")
    try:
        return open_review_service(base, owner_key(actor))
    except GuardError as exc:
        raise HTTPException(503, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "assistant_workspace_unavailable") from exc


def perform(function):
    try:
        return function()
    except GuardError as exc:
        code = str(exc)
        raise HTTPException(404 if code == "review_not_found" else 409, code) from exc


@router.get("/workspace")
def workspace(request: Request):
    service = review_service(request)
    return perform(
        lambda: {
            "mode": "isolated_local_workspace",
            "model": "qwen3.5:9b",
            "application_version": __version__,
            "draft_strategy": get_settings().personal_assistant_draft_strategy,
            "state": service.state(),
        }
    )


@router.get("/reviews")
def list_reviews(request: Request):
    return review_service(request).list_reviews()


@router.post("/reviews", status_code=201)
def create_review(payload: ReviewInput, request: Request):
    service = review_service(request)
    return perform(
        lambda: service.create(
            payload.request,
            lambda text, state: generate_draft(
                text,
                state,
                get_settings().personal_assistant_runtime_url,
                get_settings().personal_assistant_draft_strategy,
            ),
        )
    )


@router.get("/reviews/{review_id}")
def get_review(review_id: str, request: Request):
    service = review_service(request)
    return perform(lambda: service.get(review_id))


@router.put("/reviews/{review_id}")
def save_review(review_id: str, payload: ReviewEdit, request: Request):
    service = review_service(request)
    return perform(
        lambda: service.save(review_id, payload.revision, payload.content_hash, payload.fields)
    )


@router.post("/reviews/{review_id}/confirm")
def confirm_review(review_id: str, payload: ReviewConfirmation, request: Request):
    service = review_service(request)
    return perform(lambda: service.confirm(review_id, payload.revision, payload.content_hash))


@router.post("/reviews/{review_id}/approve")
def approve_review(review_id: str, payload: ReviewApproval, request: Request):
    service = review_service(request)
    return perform(
        lambda: service.approve_review(
            review_id, payload.revision, payload.content_hash, payload.plan_hash
        )
    )


@router.post("/reviews/{review_id}/cancel")
def cancel_review(review_id: str, payload: ReviewBinding, request: Request):
    service = review_service(request)
    return perform(lambda: service.cancel_review(review_id, payload.revision, payload.content_hash))


@router.post("/reviews/{review_id}/restore")
def restore_review(review_id: str, payload: ReviewBinding, request: Request):
    service = review_service(request)
    return perform(
        lambda: service.restore_preview(review_id, payload.revision, payload.content_hash)
    )


@router.post("/reviews/{review_id}/recover")
def recover_review(review_id: str, payload: ReviewBinding, request: Request):
    service = review_service(request)
    return perform(lambda: service.recover(review_id, payload.revision, payload.content_hash))
