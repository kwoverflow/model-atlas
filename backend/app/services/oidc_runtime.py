from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.oidc_state import (
    DatabaseBrowserSessionStore,
    DatabaseOIDCDocumentCache,
)


@lru_cache
def oidc_document_cache() -> DatabaseOIDCDocumentCache | None:
    settings = get_settings()
    if not settings.oidc_shared_cache_enabled:
        return None
    return DatabaseOIDCDocumentCache(
        SessionLocal,
        instance_name=settings.instance_name,
    )


@lru_cache
def browser_session_store() -> DatabaseBrowserSessionStore | None:
    settings = get_settings()
    if not settings.oidc_browser_login_enabled:
        return None
    if not settings.oidc_session_secret:
        raise ValueError(
            "OIDC_SESSION_SECRET is required when browser login is enabled"
        )
    return DatabaseBrowserSessionStore(
        SessionLocal,
        secret=settings.oidc_session_secret,
        ttl_seconds=settings.oidc_session_ttl_seconds,
    )
