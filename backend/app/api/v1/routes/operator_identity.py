from __future__ import annotations

from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import (
    AgentExecutionJobRead,
    BrowserSessionBulkActionRead,
    BrowserSessionCleanupRequest,
    BrowserSessionOverviewRead,
    BrowserSessionRevokeCreate,
    OIDCBrowserSessionEventRead,
    OIDCBrowserSessionRead,
)
from app.schemas.operator_identity import (
    BrowserLogoutRead,
    BrowserOIDCStatusRead,
    OperatorIdentityRead,
)
from app.services.agent_jobs import enqueue_oidc_session_cleanup_job
from app.services.browser_oidc import (
    BROWSER_OIDC_VERSION,
    BrowserOIDCClient,
    BrowserOIDCConfig,
    BrowserSessionConfig,
)
from app.services.oidc_runtime import browser_session_store, oidc_document_cache
from app.services.oidc_session_administration import (
    build_browser_session_overview,
    list_browser_session_events,
    list_browser_sessions,
    revoke_browser_session,
    revoke_provider_sessions,
    revoke_subject_sessions,
    session_administration_permissions,
)
from app.services.operator_identity import (
    JWTVerificationConfig,
    local_operator_identity,
)
from app.services.release_approval_policy import release_decision_permissions

router = APIRouter()
settings = get_settings()


@lru_cache
def _browser_client() -> BrowserOIDCClient:
    return BrowserOIDCClient(
        oidc_config=BrowserOIDCConfig(
            enabled=settings.oidc_browser_login_enabled,
            client_id=settings.oidc_client_id,
            client_secret=settings.oidc_client_secret,
            redirect_uri=settings.oidc_redirect_uri,
            frontend_url=settings.oidc_frontend_url,
            scopes=tuple(settings.oidc_scopes),
            authorization_endpoint=settings.oidc_authorization_endpoint,
            token_endpoint=settings.oidc_token_endpoint,
            end_session_endpoint=settings.oidc_end_session_endpoint,
        ),
        session_config=BrowserSessionConfig(
            enabled=settings.oidc_browser_login_enabled,
            secret=settings.oidc_session_secret,
            cookie_name=settings.oidc_session_cookie_name,
            secure=settings.oidc_session_secure,
            ttl_seconds=settings.oidc_session_ttl_seconds,
        ),
        jwt_config=JWTVerificationConfig(
            enabled=True,
            issuer=settings.oidc_jwt_issuer,
            audience=settings.oidc_client_id,
            keys=settings.oidc_jwt_hs256_keys,
            algorithms=tuple(settings.oidc_jwt_algorithms),
            role_claim=settings.oidc_jwt_role_claim,
            name_claim=settings.oidc_jwt_name_claim,
            leeway_seconds=settings.oidc_jwt_leeway_seconds,
            discovery_url=settings.oidc_discovery_url,
            jwks_uri=settings.oidc_jwks_uri,
            discovery_cache_ttl_seconds=(
                settings.oidc_discovery_cache_ttl_seconds
            ),
            jwks_cache_ttl_seconds=settings.oidc_jwks_cache_ttl_seconds,
            http_timeout_seconds=settings.oidc_http_timeout_seconds,
            allow_insecure_http=settings.oidc_allow_insecure_http,
        ),
        document_cache=oidc_document_cache(),
    )


@router.get("/me", response_model=OperatorIdentityRead)
def get_current_operator_identity(request: Request) -> OperatorIdentityRead:
    identity = getattr(request.state, "operator_identity", None) or local_operator_identity()
    return OperatorIdentityRead(
        **identity.to_json(),
        release_permissions=release_decision_permissions(identity),
        session_permissions=session_administration_permissions(identity).model_dump(),
    )


@router.get("/browser-config", response_model=BrowserOIDCStatusRead)
def get_browser_oidc_status(request: Request) -> BrowserOIDCStatusRead:
    identity = getattr(request.state, "operator_identity", None)
    enabled = settings.oidc_browser_login_enabled
    return BrowserOIDCStatusRead(
        schema_version=BROWSER_OIDC_VERSION,
        enabled=enabled,
        authenticated=bool(
            identity is not None
            and identity.identity_verified
            and identity.auth_source == "oidc_browser_session"
        ),
        login_url=(
            "/api/v1/operator-identity/login" if enabled else None
        ),
        logout_url=(
            "/api/v1/operator-identity/logout" if enabled else None
        ),
        session_cookie_name=settings.oidc_session_cookie_name,
        identity_provider=settings.oidc_jwt_issuer,
        logout_method="POST",
        csrf_cookie_name=settings.oidc_csrf_cookie_name,
        csrf_header_name=settings.oidc_csrf_header_name,
        session_store="database",
        session_id=(
            str(request.state.browser_session_context.session_id)
            if getattr(request.state, "browser_session_context", None)
            else None
        ),
        session_fingerprint=(
            request.state.browser_session_context.session_hash[:16]
            if getattr(request.state, "browser_session_context", None)
            else None
        ),
        session_expires_at=(
            request.state.browser_session_context.expires_at.isoformat()
            if getattr(request.state, "browser_session_context", None)
            else None
        ),
    )


@router.get(
    "/sessions/overview",
    response_model=BrowserSessionOverviewRead,
)
def get_browser_session_overview(
    request: Request,
    db: Session = Depends(get_db),
) -> BrowserSessionOverviewRead:
    identity = _session_operator(request)
    _require_session_auditor(identity)
    return build_browser_session_overview(
        db,
        signer_identity=identity,
        retention_days=settings.oidc_session_retention_days,
        cleanup_enabled=settings.oidc_session_cleanup_enabled,
        cleanup_interval_seconds=settings.oidc_session_cleanup_interval_seconds,
        cleanup_batch_size=settings.oidc_session_cleanup_batch_size,
    )


@router.get(
    "/sessions",
    response_model=list[OIDCBrowserSessionRead],
)
def get_browser_sessions(
    request: Request,
    status: str | None = Query(default=None),
    subject_id: str | None = Query(default=None, max_length=240),
    provider_session_hash: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[OIDCBrowserSessionRead]:
    identity = _session_operator(request)
    _require_session_auditor(identity)
    return list_browser_sessions(
        db,
        signer_identity=identity,
        status=status,
        subject_id=subject_id,
        provider_session_hash=provider_session_hash,
        current_session_id=_current_session_id(request),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/session-events",
    response_model=list[OIDCBrowserSessionEventRead],
)
def get_browser_session_events(
    request: Request,
    session_id: UUID | None = Query(default=None),
    subject_id: str | None = Query(default=None, max_length=240),
    event_type: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[OIDCBrowserSessionEventRead]:
    identity = _session_operator(request)
    _require_session_auditor(identity)
    return list_browser_session_events(
        db,
        signer_identity=identity,
        session_id=session_id,
        subject_id=subject_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/sessions/{session_id}/revoke",
    response_model=BrowserSessionBulkActionRead,
)
def revoke_managed_browser_session(
    session_id: UUID,
    payload: BrowserSessionRevokeCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> BrowserSessionBulkActionRead:
    identity = _session_operator(request)
    _require_session_administrator(identity)
    return revoke_browser_session(
        db,
        session_id=session_id,
        reason=payload.reason,
        signer_identity=identity,
        current_session_id=_current_session_id(request),
    )


@router.post(
    "/subjects/{subject_id}/sessions/revoke",
    response_model=BrowserSessionBulkActionRead,
)
def revoke_managed_subject_sessions(
    subject_id: str,
    payload: BrowserSessionRevokeCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> BrowserSessionBulkActionRead:
    identity = _session_operator(request)
    _require_session_administrator(identity)
    return revoke_subject_sessions(
        db,
        subject_id=subject_id,
        reason=payload.reason,
        signer_identity=identity,
        current_session_id=_current_session_id(request),
    )


@router.post(
    "/provider-sessions/{provider_session_hash}/revoke",
    response_model=BrowserSessionBulkActionRead,
)
def revoke_managed_provider_sessions(
    provider_session_hash: str,
    payload: BrowserSessionRevokeCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> BrowserSessionBulkActionRead:
    identity = _session_operator(request)
    _require_session_administrator(identity)
    return revoke_provider_sessions(
        db,
        provider_session_hash=provider_session_hash,
        reason=payload.reason,
        signer_identity=identity,
        current_session_id=_current_session_id(request),
    )


@router.post(
    "/sessions/cleanup",
    response_model=AgentExecutionJobRead,
    status_code=202,
)
def queue_browser_session_cleanup(
    payload: BrowserSessionCleanupRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    identity = _session_operator(request)
    _require_session_administrator(identity)
    return enqueue_oidc_session_cleanup_job(
        db,
        schedule_key=f"manual-{uuid4()}",
        signer_identity=identity,
        retention_days=settings.oidc_session_retention_days,
        batch_size=settings.oidc_session_cleanup_batch_size,
        reason=payload.reason,
    )


@router.get("/login")
def begin_browser_login(
    return_to: str = Query(default="/", max_length=500),
) -> RedirectResponse:
    if not settings.oidc_browser_login_enabled:
        raise HTTPException(status_code=404, detail="browser OIDC login is disabled")
    login = _browser_client().begin_login(return_to=return_to)
    response = RedirectResponse(login.authorization_url, status_code=302)
    response.set_cookie(
        _browser_client().oidc_config.transaction_cookie_name,
        login.transaction_token,
        max_age=600,
        httponly=True,
        secure=settings.oidc_session_secure,
        samesite="lax",
        path="/api/v1/operator-identity/callback",
    )
    return response


@router.get("/callback")
def complete_browser_login(
    request: Request,
    code: str = Query(min_length=1, max_length=4000),
    state: str = Query(min_length=1, max_length=500),
) -> RedirectResponse:
    if not settings.oidc_browser_login_enabled:
        raise HTTPException(status_code=404, detail="browser OIDC login is disabled")
    transaction_cookie_name = _browser_client().oidc_config.transaction_cookie_name
    transaction_token = request.cookies.get(transaction_cookie_name)
    if not transaction_token:
        raise HTTPException(status_code=401, detail="OIDC login transaction cookie is missing")
    completion = _browser_client().complete_login(
        code=code,
        state=state,
        transaction_token=transaction_token,
    )
    store = browser_session_store()
    if store is None:
        raise HTTPException(status_code=503, detail="browser session store is unavailable")
    session = store.issue(
        subject_id=completion.identity.subject_id,
        display_name=completion.identity.display_name,
        role=completion.identity.role,
        identity_provider=completion.identity.identity_provider,
        provider_session_id=completion.provider_session_id,
        provider_id_token=completion.provider_id_token,
        client_descriptor=(
            f"{request.client.host if request.client else 'unknown'}\0"
            f"{(request.headers.get('user-agent') or 'unknown')[:500]}"
        ),
    )
    response = RedirectResponse(completion.return_url, status_code=302)
    response.set_cookie(
        settings.oidc_session_cookie_name,
        session.session_token,
        max_age=settings.oidc_session_ttl_seconds,
        httponly=True,
        secure=settings.oidc_session_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.oidc_csrf_cookie_name,
        session.csrf_token,
        max_age=settings.oidc_session_ttl_seconds,
        httponly=False,
        secure=settings.oidc_session_secure,
        samesite="lax",
        path="/",
    )
    response.delete_cookie(
        transaction_cookie_name,
        path="/api/v1/operator-identity/callback",
        secure=settings.oidc_session_secure,
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/logout", response_model=BrowserLogoutRead)
def logout_browser_session(
    request: Request,
    return_to: str = Query(default="/", max_length=500),
) -> JSONResponse:
    if not return_to.startswith("/") or return_to.startswith("//"):
        raise HTTPException(status_code=422, detail="return_to must be a local path")
    session_token = getattr(request.state, "browser_session_token", None)
    store = browser_session_store()
    if not session_token or store is None:
        raise HTTPException(status_code=401, detail="active browser session is required")
    context = store.revoke(
        session_token,
        reason="operator_logout",
        actor_identity=getattr(request.state, "operator_identity", None),
    )
    if context is None:
        raise HTTPException(status_code=401, detail="browser session is invalid")
    target = _browser_client().build_logout_target(
        provider_id_token=context.provider_id_token,
        return_to=return_to,
    )
    response = JSONResponse(
        content=BrowserLogoutRead(
            redirect_url=target.url,
            provider_logout=target.provider_logout,
            session_revoked=True,
        ).model_dump(),
    )
    response.delete_cookie(
        settings.oidc_session_cookie_name,
        path="/",
        secure=settings.oidc_session_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        settings.oidc_csrf_cookie_name,
        path="/",
        secure=settings.oidc_session_secure,
        httponly=False,
        samesite="lax",
    )
    return response


def _session_operator(request: Request):
    return getattr(request.state, "operator_identity", None) or local_operator_identity()


def _current_session_id(request: Request) -> UUID | None:
    context = getattr(request.state, "browser_session_context", None)
    return context.session_id if context is not None else None


def _require_session_auditor(identity) -> None:
    if not session_administration_permissions(identity).can_audit:
        raise HTTPException(
            status_code=403,
            detail="verified browser session auditor role is required",
        )


def _require_session_administrator(identity) -> None:
    if not session_administration_permissions(identity).can_administer:
        raise HTTPException(
            status_code=403,
            detail="verified Admin or SRE Lead role is required",
        )
