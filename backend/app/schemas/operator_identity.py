from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class OperatorIdentityRead(BaseModel):
    subject_id: str
    display_name: str
    role: str | None
    identity_provider: str
    auth_source: str
    identity_verified: bool
    ticket_reference: str | None
    release_permissions: dict[str, Any]
    session_permissions: dict[str, Any]


class BrowserOIDCStatusRead(BaseModel):
    schema_version: str
    enabled: bool
    authenticated: bool
    login_url: str | None
    logout_url: str | None
    session_cookie_name: str
    identity_provider: str | None
    logout_method: str
    csrf_cookie_name: str
    csrf_header_name: str
    session_store: str
    session_id: str | None
    session_fingerprint: str | None
    session_expires_at: str | None


class BrowserLogoutRead(BaseModel):
    redirect_url: str
    provider_logout: bool
    session_revoked: bool
