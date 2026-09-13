from __future__ import annotations

import hmac
import ipaddress
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.services.browser_oidc import (
    BrowserSessionConfig,
    extract_browser_session_identity,
)
from app.services.oidc_contracts import (
    BrowserSessionContext,
    BrowserSessionStore,
    OIDCDocumentCache,
)
from app.services.operator_identity import (
    TRUSTED_IDENTITY_PROVIDER_HEADER,
    TRUSTED_OPERATOR_ID_HEADER,
    TRUSTED_OPERATOR_NAME_HEADER,
    TRUSTED_OPERATOR_ROLE_HEADER,
    JWTAuthenticationError,
    JWTVerificationConfig,
    OIDCJWTVerifier,
    SignerIdentity,
    extract_bearer_operator_identity,
    extract_trusted_operator_identity,
)

FORWARDED_HEADERS = (
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
)
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class BrowserCSRFConfig:
    def __init__(
        self,
        *,
        enabled: bool,
        cookie_name: str,
        header_name: str,
        allowed_origins: list[str],
    ) -> None:
        self.enabled = enabled
        self.cookie_name = cookie_name
        self.header_name = header_name.lower()
        self.allowed_origins = {
            origin.rstrip("/") for origin in allowed_origins if origin.strip()
        }


class OperatorIdentityMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        trusted_headers_enabled: bool,
        trusted_proxy_networks: list[str],
        jwt_config: JWTVerificationConfig,
        browser_session_config: BrowserSessionConfig | None = None,
        browser_session_store: BrowserSessionStore | None = None,
        document_cache: OIDCDocumentCache | None = None,
        browser_csrf_config: BrowserCSRFConfig | None = None,
        reject_untrusted_forwarded_headers: bool = True,
    ) -> None:
        super().__init__(app)
        self.trusted_headers_enabled = trusted_headers_enabled
        self.trusted_proxy_networks = trusted_proxy_networks
        self.jwt_config = jwt_config
        self.jwt_verifier = OIDCJWTVerifier(
            jwt_config,
            document_cache=document_cache,
        )
        self.browser_session_config = browser_session_config or BrowserSessionConfig(
            enabled=False,
            secret=None,
        )
        self.browser_session_store = browser_session_store
        self.browser_csrf_config = browser_csrf_config or BrowserCSRFConfig(
            enabled=False,
            cookie_name="model_atlas_csrf",
            header_name="x-model-atlas-csrf",
            allowed_origins=[],
        )
        self.reject_untrusted_forwarded_headers = reject_untrusted_forwarded_headers

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_host = request.client.host if request.client is not None else ""
        proxy_trusted = is_trusted_proxy(client_host, self.trusted_proxy_networks)
        forwarded_header_present = any(
            request.headers.get(header) for header in FORWARDED_HEADERS
        )
        if (
            self.reject_untrusted_forwarded_headers
            and forwarded_header_present
            and not proxy_trusted
        ):
            return _bad_request(
                "Forwarded headers were received from an untrusted proxy source"
            )

        try:
            bearer_identity = extract_bearer_operator_identity(
                request.headers,
                config=self.jwt_config,
                verifier=self.jwt_verifier,
            )
        except JWTAuthenticationError as exc:
            return _unauthorized(str(exc))
        if bearer_identity is not None:
            request.state.operator_identity = bearer_identity
            return await call_next(request)

        session_token = request.cookies.get(self.browser_session_config.cookie_name)
        browser_context = None
        browser_identity = None
        if session_token and self.browser_session_store is not None:
            browser_context = self.browser_session_store.resolve(str(session_token))
            if browser_context is None:
                return _unauthorized("browser session is invalid or expired")
            browser_identity = _identity_from_browser_context(browser_context)
        else:
            try:
                browser_identity = extract_browser_session_identity(
                    request.cookies,
                    config=self.browser_session_config,
                )
            except JWTAuthenticationError as exc:
                request.state.browser_session_error = str(exc)
                browser_identity = None
        if browser_identity is not None:
            request.state.operator_identity = browser_identity
            if browser_context is not None:
                request.state.browser_session_context = browser_context
                request.state.browser_session_token = str(session_token)
                csrf_error = self._browser_csrf_error(request, browser_context)
                if csrf_error:
                    return _forbidden(csrf_error)
            return await call_next(request)

        trusted_header_present = any(
            request.headers.get(header)
            for header in (
                TRUSTED_OPERATOR_ID_HEADER,
                TRUSTED_OPERATOR_NAME_HEADER,
                TRUSTED_OPERATOR_ROLE_HEADER,
                TRUSTED_IDENTITY_PROVIDER_HEADER,
            )
        )
        if trusted_header_present and not proxy_trusted:
            return _unauthorized(
                "Operator identity headers were received from an untrusted proxy source"
            )
        request.state.operator_identity = extract_trusted_operator_identity(
            request.headers,
            trusted_headers_enabled=(
                self.trusted_headers_enabled and proxy_trusted
            ),
        )
        return await call_next(request)

    def _browser_csrf_error(
        self,
        request: Request,
        context: BrowserSessionContext,
    ) -> str | None:
        config = self.browser_csrf_config
        if not config.enabled or request.method.upper() not in UNSAFE_METHODS:
            return None
        origin = (request.headers.get("origin") or "").rstrip("/")
        if not origin or origin not in config.allowed_origins:
            return "browser request origin is not allowed"
        csrf_token = request.headers.get(config.header_name) or ""
        csrf_cookie = request.cookies.get(config.cookie_name) or ""
        if not csrf_token or not csrf_cookie or not hmac.compare_digest(
            csrf_token,
            csrf_cookie,
        ):
            return "browser CSRF token is missing or invalid"
        if not self.browser_session_store or not self.browser_session_store.csrf_matches(
            context,
            csrf_token,
        ):
            return "browser CSRF token is missing or invalid"
        return None


def is_trusted_proxy(client_host: str, trusted_sources: list[str]) -> bool:
    normalized_host = client_host.strip().lower()
    if not normalized_host:
        return False
    try:
        address = ipaddress.ip_address(normalized_host)
    except ValueError:
        return normalized_host in {source.strip().lower() for source in trusted_sources}
    for source in trusted_sources:
        normalized_source = source.strip()
        if not normalized_source:
            continue
        try:
            if address in ipaddress.ip_network(normalized_source, strict=False):
                return True
        except ValueError:
            continue
    return False


def _unauthorized(message: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _forbidden(message: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"detail": message})


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": message})


def _identity_from_browser_context(context: BrowserSessionContext) -> SignerIdentity:
    return SignerIdentity(
        subject_id=context.subject_id,
        display_name=context.display_name,
        role=context.role,
        identity_provider=context.identity_provider,
        auth_source="oidc_browser_session",
        identity_verified=True,
        ticket_reference=None,
    )
