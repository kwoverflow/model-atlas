from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.api import api_router
from app.api.v1.routes.operations import prometheus_router
from app.core.config import get_settings
from app.middleware.operator_identity import BrowserCSRFConfig, OperatorIdentityMiddleware
from app.services.browser_oidc import BrowserSessionConfig
from app.services.oidc_runtime import browser_session_store, oidc_document_cache
from app.services.operator_identity import JWTVerificationConfig
from app.validators import DomainValidationError

settings = get_settings()

app = FastAPI(
    title=settings.project_name,
    version="0.1.0",
    description="Evidence-driven local AI deployment gate and candidate discovery platform.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    OperatorIdentityMiddleware,
    trusted_headers_enabled=settings.trusted_operator_headers_enabled,
    trusted_proxy_networks=settings.trusted_proxy_networks,
    reject_untrusted_forwarded_headers=settings.reject_untrusted_forwarded_headers,
    jwt_config=JWTVerificationConfig(
        enabled=settings.oidc_jwt_enabled,
        issuer=settings.oidc_jwt_issuer,
        audience=settings.oidc_jwt_audience,
        keys=settings.oidc_jwt_hs256_keys,
        algorithms=tuple(settings.oidc_jwt_algorithms),
        role_claim=settings.oidc_jwt_role_claim,
        name_claim=settings.oidc_jwt_name_claim,
        leeway_seconds=settings.oidc_jwt_leeway_seconds,
        discovery_url=settings.oidc_discovery_url,
        jwks_uri=settings.oidc_jwks_uri,
        discovery_cache_ttl_seconds=settings.oidc_discovery_cache_ttl_seconds,
        jwks_cache_ttl_seconds=settings.oidc_jwks_cache_ttl_seconds,
        http_timeout_seconds=settings.oidc_http_timeout_seconds,
        allow_insecure_http=settings.oidc_allow_insecure_http,
    ),
    browser_session_config=BrowserSessionConfig(
        enabled=settings.oidc_browser_login_enabled,
        secret=settings.oidc_session_secret,
        cookie_name=settings.oidc_session_cookie_name,
        secure=settings.oidc_session_secure,
        ttl_seconds=settings.oidc_session_ttl_seconds,
    ),
    browser_session_store=browser_session_store(),
    document_cache=oidc_document_cache(),
    browser_csrf_config=BrowserCSRFConfig(
        enabled=settings.oidc_browser_login_enabled,
        cookie_name=settings.oidc_csrf_cookie_name,
        header_name=settings.oidc_csrf_header_name,
        allowed_origins=list(
            dict.fromkeys([*settings.cors_origins, settings.oidc_frontend_url])
        ),
    ),
)


@app.exception_handler(DomainValidationError)
async def domain_validation_exception_handler(
    request: Request, exc: DomainValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {
                    "type": "domain_validation",
                    "loc": ["body"],
                    "msg": exc.message,
                    "input": None,
                }
            ]
        },
    )


app.include_router(prometheus_router)
app.include_router(api_router, prefix=settings.api_v1_prefix)
