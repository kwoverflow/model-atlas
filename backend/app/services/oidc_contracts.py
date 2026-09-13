from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BrowserSessionContext:
    session_id: uuid.UUID
    session_hash: str
    subject_id: str
    display_name: str
    role: str | None
    identity_provider: str
    provider_session_id: str | None
    provider_session_hash: str | None
    client_fingerprint: str | None
    csrf_token_hash: str
    authenticated_at: dt.datetime
    expires_at: dt.datetime
    last_seen_at: dt.datetime
    provider_id_token: str | None = None


@dataclass(frozen=True)
class BrowserSessionIssue:
    session_token: str
    csrf_token: str
    context: BrowserSessionContext


@dataclass(frozen=True)
class OIDCCachedDocument:
    payload: dict[str, Any]
    expires_at: dt.datetime


class BrowserSessionStore(Protocol):
    def issue(
        self,
        *,
        subject_id: str,
        display_name: str,
        role: str | None,
        identity_provider: str,
        provider_session_id: str | None,
        provider_id_token: str | None,
        client_descriptor: str | None = None,
        now: dt.datetime | None = None,
    ) -> BrowserSessionIssue: ...

    def resolve(
        self,
        session_token: str,
        *,
        now: dt.datetime | None = None,
    ) -> BrowserSessionContext | None: ...

    def csrf_matches(self, context: BrowserSessionContext, csrf_token: str) -> bool: ...

    def revoke(
        self,
        session_token: str,
        *,
        reason: str,
        actor_identity: Any | None = None,
        now: dt.datetime | None = None,
    ) -> BrowserSessionContext | None: ...


class OIDCDocumentCache(Protocol):
    def get(
        self,
        document_type: str,
        source_url: str,
        *,
        now: dt.datetime | None = None,
    ) -> OIDCCachedDocument | None: ...

    def put(
        self,
        document_type: str,
        source_url: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
        now: dt.datetime | None = None,
    ) -> None: ...
