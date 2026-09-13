from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import OIDCBrowserSession, OIDCCacheEntry
from app.services.oidc_contracts import (
    BrowserSessionContext,
    BrowserSessionIssue,
    OIDCCachedDocument,
)
from app.services.oidc_session_administration import append_browser_session_event
from app.services.operator_identity import SignerIdentity

SessionFactory = Callable[[], Session]


class DatabaseBrowserSessionStore:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        secret: str,
        ttl_seconds: int,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("browser session secret must contain at least 32 characters")
        self._session_factory = session_factory
        self._ttl_seconds = max(300, int(ttl_seconds))
        self._encryption_key = hashlib.sha256(
            f"model-atlas-oidc-id-token:{secret}".encode()
        ).digest()

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
    ) -> BrowserSessionIssue:
        issued_at = _utc(now)
        session_token = secrets.token_urlsafe(48)
        csrf_token = secrets.token_urlsafe(32)
        token_hash = _secret_hash(session_token)
        session_hash = hashlib.sha256(
            f"{token_hash}:{subject_id}:{issued_at.isoformat()}".encode()
        ).hexdigest()
        row = OIDCBrowserSession(
            token_hash=token_hash,
            csrf_token_hash=_secret_hash(csrf_token),
            session_hash=session_hash,
            subject_id=subject_id,
            display_name=display_name,
            role=role,
            identity_provider=identity_provider,
            provider_session_id=provider_session_id,
            provider_session_hash=(
                _secret_hash(provider_session_id) if provider_session_id else None
            ),
            client_fingerprint=(
                self._fingerprint(client_descriptor) if client_descriptor else None
            ),
            provider_id_token_ciphertext=(
                self._encrypt(provider_id_token) if provider_id_token else None
            ),
            authenticated_at=issued_at,
            expires_at=issued_at + dt.timedelta(seconds=self._ttl_seconds),
            last_seen_at=issued_at,
        )
        with self._session_factory() as db:
            db.add(row)
            db.flush()
            append_browser_session_event(
                db,
                row=row,
                event_type="issued",
                reason="oidc_login_completed",
                actor_identity=SignerIdentity(
                    subject_id=subject_id,
                    display_name=display_name,
                    role=role,
                    identity_provider=identity_provider,
                    auth_source="oidc_browser_session",
                    identity_verified=True,
                    ticket_reference=None,
                ),
                metadata_json={
                    "provider_session_present": bool(provider_session_id),
                    "provider_id_token_retained": bool(provider_id_token),
                    "client_fingerprint_present": bool(client_descriptor),
                },
                occurred_at=issued_at,
            )
            db.commit()
            db.refresh(row)
        return BrowserSessionIssue(
            session_token=session_token,
            csrf_token=csrf_token,
            context=self._context(row),
        )

    def resolve(
        self,
        session_token: str,
        *,
        now: dt.datetime | None = None,
    ) -> BrowserSessionContext | None:
        current = _utc(now)
        with self._session_factory() as db:
            row = db.scalar(
                select(OIDCBrowserSession).where(
                    OIDCBrowserSession.token_hash == _secret_hash(session_token)
                )
            )
            if row is None or row.revoked_at is not None or row.expires_at <= current:
                return None
            if row.last_seen_at <= current - dt.timedelta(minutes=5):
                row.last_seen_at = current
                db.commit()
                db.refresh(row)
            return self._context(row)

    def csrf_matches(
        self,
        context: BrowserSessionContext,
        csrf_token: str,
    ) -> bool:
        return bool(csrf_token) and hmac.compare_digest(
            context.csrf_token_hash,
            _secret_hash(csrf_token),
        )

    def revoke(
        self,
        session_token: str,
        *,
        reason: str,
        actor_identity: SignerIdentity | None = None,
        now: dt.datetime | None = None,
    ) -> BrowserSessionContext | None:
        current = _utc(now)
        with self._session_factory() as db:
            row = db.scalar(
                select(OIDCBrowserSession).where(
                    OIDCBrowserSession.token_hash == _secret_hash(session_token)
                )
            )
            if row is None:
                return None
            had_provider_ciphertext = bool(row.provider_id_token_ciphertext)
            try:
                provider_id_token = (
                    self._decrypt(row.provider_id_token_ciphertext)
                    if row.provider_id_token_ciphertext
                    else None
                )
            except (InvalidTag, ValueError, UnicodeDecodeError):
                provider_id_token = None
            if row.revoked_at is None:
                row.revoked_at = current
                row.revocation_reason = reason[:80]
                row.logout_initiated_at = current
                row.provider_id_token_ciphertext = None
                row.provider_session_id = None
                if had_provider_ciphertext:
                    row.provider_token_purged_at = current
                append_browser_session_event(
                    db,
                    row=row,
                    event_type="revoked",
                    reason=reason[:160],
                    actor_identity=actor_identity
                    or SignerIdentity(
                        subject_id=row.subject_id,
                        display_name=row.display_name,
                        role=row.role,
                        identity_provider=row.identity_provider,
                        auth_source="oidc_browser_session",
                        identity_verified=True,
                        ticket_reference=None,
                    ),
                    metadata_json={
                        "scope": "current_session",
                        "provider_logout_available": bool(provider_id_token),
                        "provider_token_purged": had_provider_ciphertext,
                    },
                    occurred_at=current,
                )
                db.commit()
                db.refresh(row)
            return self._context(row, provider_id_token=provider_id_token)

    def counts(self, *, now: dt.datetime | None = None) -> dict[str, int]:
        current = _utc(now)
        with self._session_factory() as db:
            active = db.scalar(
                select(func.count()).select_from(OIDCBrowserSession).where(
                    OIDCBrowserSession.revoked_at.is_(None),
                    OIDCBrowserSession.expires_at > current,
                )
            )
            revoked = db.scalar(
                select(func.count()).select_from(OIDCBrowserSession).where(
                    OIDCBrowserSession.revoked_at.is_not(None)
                )
            )
        return {"active": int(active or 0), "revoked": int(revoked or 0)}

    def _context(
        self,
        row: OIDCBrowserSession,
        *,
        provider_id_token: str | None = None,
    ) -> BrowserSessionContext:
        return BrowserSessionContext(
            session_id=row.id,
            session_hash=row.session_hash,
            subject_id=row.subject_id,
            display_name=row.display_name,
            role=row.role,
            identity_provider=row.identity_provider,
            provider_session_id=row.provider_session_id,
            provider_session_hash=row.provider_session_hash,
            client_fingerprint=row.client_fingerprint,
            csrf_token_hash=row.csrf_token_hash,
            authenticated_at=row.authenticated_at,
            expires_at=row.expires_at,
            last_seen_at=row.last_seen_at,
            provider_id_token=provider_id_token,
        )

    def _encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._encryption_key).encrypt(
            nonce,
            plaintext.encode(),
            b"model-atlas-oidc-id-token-v1",
        )
        return base64.urlsafe_b64encode(nonce + ciphertext).decode()

    def _decrypt(self, encoded: str) -> str:
        raw = base64.urlsafe_b64decode(encoded.encode())
        plaintext = AESGCM(self._encryption_key).decrypt(
            raw[:12],
            raw[12:],
            b"model-atlas-oidc-id-token-v1",
        )
        return plaintext.decode()

    def _fingerprint(self, descriptor: str) -> str:
        return hmac.new(
            self._encryption_key,
            descriptor.encode(),
            hashlib.sha256,
        ).hexdigest()


class DatabaseOIDCDocumentCache:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        instance_name: str,
    ) -> None:
        self._session_factory = session_factory
        self._instance_name = instance_name[:160]

    def get(
        self,
        document_type: str,
        source_url: str,
        *,
        now: dt.datetime | None = None,
    ) -> OIDCCachedDocument | None:
        current = _utc(now)
        with self._session_factory() as db:
            row = db.scalar(
                select(OIDCCacheEntry).where(
                    OIDCCacheEntry.cache_key == _cache_key(document_type, source_url),
                    OIDCCacheEntry.expires_at > current,
                )
            )
            if row is None or not isinstance(row.payload_json, dict):
                return None
            return OIDCCachedDocument(
                payload=dict(row.payload_json),
                expires_at=row.expires_at,
            )

    def put(
        self,
        document_type: str,
        source_url: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
        now: dt.datetime | None = None,
    ) -> None:
        current = _utc(now)
        key = _cache_key(document_type, source_url)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        values = {
            "document_type": document_type,
            "source_url": source_url,
            "payload_json": payload,
            "content_hash": hashlib.sha256(canonical.encode()).hexdigest(),
            "fetched_at": current,
            "expires_at": current + dt.timedelta(seconds=max(15, int(ttl_seconds))),
            "refreshed_by": self._instance_name,
        }
        with self._session_factory() as db:
            row = db.scalar(select(OIDCCacheEntry).where(OIDCCacheEntry.cache_key == key))
            if row is None:
                row = OIDCCacheEntry(cache_key=key, refresh_count=1, **values)
                db.add(row)
            else:
                for name, value in values.items():
                    setattr(row, name, value)
                row.refresh_count += 1
            try:
                db.commit()
                return
            except IntegrityError:
                db.rollback()
            row = db.scalar(select(OIDCCacheEntry).where(OIDCCacheEntry.cache_key == key))
            if row is None:
                raise RuntimeError("OIDC shared cache update conflicted")
            for name, value in values.items():
                setattr(row, name, value)
            row.refresh_count += 1
            db.commit()

    def counts(self, *, now: dt.datetime | None = None) -> dict[str, int]:
        current = _utc(now)
        with self._session_factory() as db:
            fresh = db.scalar(
                select(func.count()).select_from(OIDCCacheEntry).where(
                    OIDCCacheEntry.expires_at > current
                )
            )
            stale = db.scalar(
                select(func.count()).select_from(OIDCCacheEntry).where(
                    OIDCCacheEntry.expires_at <= current
                )
            )
        return {"fresh": int(fresh or 0), "stale": int(stale or 0)}


def _secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _cache_key(document_type: str, source_url: str) -> str:
    if document_type not in {"discovery", "jwks"}:
        raise ValueError("OIDC cache document type is invalid")
    return hashlib.sha256(f"{document_type}\0{source_url}".encode()).hexdigest()


def _utc(value: dt.datetime | None) -> dt.datetime:
    current = value or dt.datetime.now(dt.UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=dt.UTC)
    return current.astimezone(dt.UTC)
