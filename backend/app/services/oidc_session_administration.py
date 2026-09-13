from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AgentExecutionJob,
    OIDCBrowserSession,
    OIDCBrowserSessionEvent,
)
from app.schemas import (
    BrowserSessionBulkActionRead,
    BrowserSessionOverviewRead,
    BrowserSessionPermissionRead,
    BrowserSessionRetentionPolicyRead,
    OIDCBrowserSessionEventRead,
    OIDCBrowserSessionRead,
)
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

OIDC_SESSION_ADMINISTRATION_VERSION = "oidc-session-administration-v1"
OIDC_SESSION_ADMIN_POLICY_VERSION = "oidc-session-administration-rbac-v1"
SESSION_AUDITOR_ROLES = ("Admin", "SRE Lead", "ML Ops Lead")
SESSION_ADMINISTRATOR_ROLES = ("Admin", "SRE Lead")
MAX_BULK_SESSION_ACTION = 1000


def session_administration_permissions(
    signer_identity: SignerIdentity,
) -> BrowserSessionPermissionRead:
    role_key = _role_key(signer_identity.role)
    verified = signer_identity.identity_verified
    return BrowserSessionPermissionRead(
        policy_version=OIDC_SESSION_ADMIN_POLICY_VERSION,
        can_audit=bool(
            verified and role_key in {_role_key(role) for role in SESSION_AUDITOR_ROLES}
        ),
        can_administer=bool(
            verified
            and role_key in {_role_key(role) for role in SESSION_ADMINISTRATOR_ROLES}
        ),
        auditor_roles=list(SESSION_AUDITOR_ROLES),
        administrator_roles=list(SESSION_ADMINISTRATOR_ROLES),
        identity_verified=verified,
        signer_role=signer_identity.role,
    )


def list_browser_sessions(
    db: Session,
    *,
    signer_identity: SignerIdentity,
    status: str | None = None,
    subject_id: str | None = None,
    provider_session_hash: str | None = None,
    current_session_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
    now: dt.datetime | None = None,
) -> list[OIDCBrowserSessionRead]:
    _assert_can_audit(signer_identity)
    observed_at = _utc(now)
    query = select(OIDCBrowserSession)
    if status == "active":
        query = query.where(
            OIDCBrowserSession.revoked_at.is_(None),
            OIDCBrowserSession.expires_at > observed_at,
        )
    elif status == "expired":
        query = query.where(
            OIDCBrowserSession.revoked_at.is_(None),
            OIDCBrowserSession.expires_at <= observed_at,
        )
    elif status == "revoked":
        query = query.where(OIDCBrowserSession.revoked_at.is_not(None))
    elif status:
        raise DomainValidationError("browser session status filter is invalid")
    if subject_id:
        query = query.where(OIDCBrowserSession.subject_id == subject_id.strip())
    if provider_session_hash:
        query = query.where(
            OIDCBrowserSession.provider_session_hash == provider_session_hash.strip()
        )
    rows = list(
        db.scalars(
            query.order_by(
                OIDCBrowserSession.last_seen_at.desc(),
                OIDCBrowserSession.created_at.desc(),
            )
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        ).all()
    )
    return [
        browser_session_read(
            row,
            current_session_id=current_session_id,
            now=observed_at,
        )
        for row in rows
    ]


def list_browser_session_events(
    db: Session,
    *,
    signer_identity: SignerIdentity,
    session_id: UUID | None = None,
    subject_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[OIDCBrowserSessionEventRead]:
    _assert_can_audit(signer_identity)
    query = select(OIDCBrowserSessionEvent)
    if session_id:
        query = query.where(OIDCBrowserSessionEvent.session_id == session_id)
    if subject_id:
        query = query.where(OIDCBrowserSessionEvent.subject_id == subject_id.strip())
    if event_type:
        query = query.where(OIDCBrowserSessionEvent.event_type == event_type.strip())
    rows = list(
        db.scalars(
            query.order_by(
                OIDCBrowserSessionEvent.occurred_at.desc(),
                OIDCBrowserSessionEvent.created_at.desc(),
            )
            .limit(max(1, min(limit, 500)))
            .offset(max(0, offset))
        ).all()
    )
    return [browser_session_event_read(row) for row in rows]


def build_browser_session_overview(
    db: Session,
    *,
    signer_identity: SignerIdentity,
    retention_days: int,
    cleanup_enabled: bool,
    cleanup_interval_seconds: int,
    cleanup_batch_size: int,
    now: dt.datetime | None = None,
) -> BrowserSessionOverviewRead:
    _assert_can_audit(signer_identity)
    observed_at = _utc(now)
    retention_cutoff = observed_at - dt.timedelta(days=max(1, retention_days))
    active_count = _count(
        db,
        OIDCBrowserSession.revoked_at.is_(None),
        OIDCBrowserSession.expires_at > observed_at,
    )
    expired_count = _count(
        db,
        OIDCBrowserSession.revoked_at.is_(None),
        OIDCBrowserSession.expires_at <= observed_at,
    )
    revoked_count = _count(db, OIDCBrowserSession.revoked_at.is_not(None))
    retention_due_count = _count(db, _retention_due_expression(retention_cutoff))
    inactive_provider_token_count = _count(
        db,
        OIDCBrowserSession.provider_id_token_ciphertext.is_not(None),
        or_(
            OIDCBrowserSession.revoked_at.is_not(None),
            OIDCBrowserSession.expires_at <= observed_at,
        ),
    )
    audit_event_count = int(
        db.scalar(select(func.count()).select_from(OIDCBrowserSessionEvent)) or 0
    )
    last_cleanup_job = db.scalar(
        select(AgentExecutionJob)
        .where(AgentExecutionJob.job_type == "oidc_session_cleanup")
        .order_by(AgentExecutionJob.created_at.desc())
        .limit(1)
    )
    return BrowserSessionOverviewRead(
        schema_version=OIDC_SESSION_ADMINISTRATION_VERSION,
        generated_at=observed_at,
        health=(
            "attention"
            if retention_due_count or inactive_provider_token_count
            else "healthy"
        ),
        active_count=active_count,
        expired_count=expired_count,
        revoked_count=revoked_count,
        retention_due_count=retention_due_count,
        inactive_provider_token_count=inactive_provider_token_count,
        audit_event_count=audit_event_count,
        last_cleanup_job_id=(last_cleanup_job.id if last_cleanup_job else None),
        last_cleanup_job_status=(
            last_cleanup_job.status if last_cleanup_job else None
        ),
        last_cleanup_completed_at=(
            last_cleanup_job.completed_at if last_cleanup_job else None
        ),
        policy=BrowserSessionRetentionPolicyRead(
            retention_days=max(1, retention_days),
            cleanup_enabled=cleanup_enabled,
            cleanup_interval_seconds=max(60, cleanup_interval_seconds),
            cleanup_batch_size=max(1, cleanup_batch_size),
            provider_token_policy=(
                "Retained only while a session is active; purged on revocation "
                "or by the next cleanup after expiry."
            ),
        ),
        permissions=session_administration_permissions(signer_identity),
    )


def revoke_browser_session(
    db: Session,
    *,
    session_id: UUID,
    reason: str,
    signer_identity: SignerIdentity,
    current_session_id: UUID | None = None,
    now: dt.datetime | None = None,
) -> BrowserSessionBulkActionRead:
    _assert_can_administer(signer_identity)
    row = db.scalar(
        select(OIDCBrowserSession)
        .where(OIDCBrowserSession.id == session_id)
        .with_for_update()
    )
    if row is None:
        raise DomainValidationError("browser session was not found")
    if current_session_id == row.id:
        raise DomainValidationError(
            "Use browser logout for the current browser session"
        )
    return _revoke_rows(
        db,
        rows=[row],
        action="session",
        reason=reason,
        signer_identity=signer_identity,
        current_session_id=current_session_id,
        now=now,
    )


def revoke_subject_sessions(
    db: Session,
    *,
    subject_id: str,
    reason: str,
    signer_identity: SignerIdentity,
    current_session_id: UUID | None = None,
    now: dt.datetime | None = None,
) -> BrowserSessionBulkActionRead:
    _assert_can_administer(signer_identity)
    normalized_subject = subject_id.strip()
    if not normalized_subject:
        raise DomainValidationError("browser session subject_id is required")
    rows = list(
        db.scalars(
            select(OIDCBrowserSession)
            .where(OIDCBrowserSession.subject_id == normalized_subject)
            .order_by(OIDCBrowserSession.last_seen_at.desc())
            .limit(MAX_BULK_SESSION_ACTION)
            .with_for_update(skip_locked=True)
        ).all()
    )
    return _revoke_rows(
        db,
        rows=rows,
        action="subject",
        reason=reason,
        signer_identity=signer_identity,
        current_session_id=current_session_id,
        now=now,
    )


def revoke_provider_sessions(
    db: Session,
    *,
    provider_session_hash: str,
    reason: str,
    signer_identity: SignerIdentity,
    current_session_id: UUID | None = None,
    now: dt.datetime | None = None,
) -> BrowserSessionBulkActionRead:
    _assert_can_administer(signer_identity)
    normalized_hash = provider_session_hash.strip().lower()
    if len(normalized_hash) != 64 or any(
        character not in "0123456789abcdef" for character in normalized_hash
    ):
        raise DomainValidationError("provider session hash must be 64 hexadecimal characters")
    rows = list(
        db.scalars(
            select(OIDCBrowserSession)
            .where(OIDCBrowserSession.provider_session_hash == normalized_hash)
            .order_by(OIDCBrowserSession.last_seen_at.desc())
            .limit(MAX_BULK_SESSION_ACTION)
            .with_for_update(skip_locked=True)
        ).all()
    )
    return _revoke_rows(
        db,
        rows=rows,
        action="provider_session",
        reason=reason,
        signer_identity=signer_identity,
        current_session_id=current_session_id,
        now=now,
    )


def cleanup_browser_sessions(
    db: Session,
    *,
    signer_identity: SignerIdentity,
    retention_days: int,
    batch_size: int,
    reason: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    permissions = session_administration_permissions(signer_identity)
    system_worker = bool(
        signer_identity.identity_verified and signer_identity.role == "System Worker"
    )
    if not system_worker and not permissions.can_administer:
        raise DomainValidationError(
            "browser session cleanup requires a verified System Worker or session administrator"
        )
    observed_at = _utc(now)
    bounded_retention = max(1, min(retention_days, 3650))
    bounded_batch = max(1, min(batch_size, 1000))
    retention_cutoff = observed_at - dt.timedelta(days=bounded_retention)
    deleted_rows = list(
        db.scalars(
            select(OIDCBrowserSession)
            .where(_retention_due_expression(retention_cutoff))
            .order_by(
                OIDCBrowserSession.revoked_at.asc(),
                OIDCBrowserSession.expires_at.asc(),
            )
            .limit(bounded_batch)
            .with_for_update(skip_locked=True)
        ).all()
    )
    event_ids: list[UUID] = []
    provider_token_purged_count = 0
    for row in deleted_rows:
        had_provider_token = bool(row.provider_id_token_ciphertext)
        if had_provider_token:
            provider_token_purged_count += 1
        event = append_browser_session_event(
            db,
            row=row,
            event_type="retention_deleted",
            reason=reason,
            actor_identity=signer_identity,
            metadata_json={
                "retention_days": bounded_retention,
                "provider_token_purged": had_provider_token,
                "status_before_delete": _session_status(row, observed_at),
            },
            occurred_at=observed_at,
        )
        event_ids.append(event.id)
        db.delete(row)

    purge_query = select(OIDCBrowserSession).where(
        OIDCBrowserSession.provider_id_token_ciphertext.is_not(None),
        or_(
            OIDCBrowserSession.revoked_at.is_not(None),
            OIDCBrowserSession.expires_at <= observed_at,
        ),
    )
    deleted_ids = [row.id for row in deleted_rows]
    if deleted_ids:
        purge_query = purge_query.where(
            OIDCBrowserSession.id.not_in(deleted_ids)
        )
    purged_rows = list(
        db.scalars(
            purge_query.order_by(OIDCBrowserSession.expires_at.asc())
            .limit(bounded_batch)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for row in purged_rows:
        row.provider_id_token_ciphertext = None
        row.provider_session_id = None
        row.provider_token_purged_at = observed_at
        provider_token_purged_count += 1
        event = append_browser_session_event(
            db,
            row=row,
            event_type="provider_token_purged",
            reason="inactive_session_cleanup",
            actor_identity=signer_identity,
            metadata_json={"cleanup_reason": reason},
            occurred_at=observed_at,
        )
        event_ids.append(event.id)
    db.commit()
    return {
        "schema_version": OIDC_SESSION_ADMINISTRATION_VERSION,
        "observed_at": observed_at.isoformat(),
        "retention_days": bounded_retention,
        "batch_size": bounded_batch,
        "deleted_count": len(deleted_rows),
        "provider_token_purged_count": provider_token_purged_count,
        "event_ids": [str(event_id) for event_id in event_ids],
        "retention_due_remaining": _count(
            db,
            _retention_due_expression(retention_cutoff),
        ),
        "inactive_provider_token_remaining": _count(
            db,
            OIDCBrowserSession.provider_id_token_ciphertext.is_not(None),
            or_(
                OIDCBrowserSession.revoked_at.is_not(None),
                OIDCBrowserSession.expires_at <= observed_at,
            ),
        ),
    }


def append_browser_session_event(
    db: Session,
    *,
    row: OIDCBrowserSession,
    event_type: str,
    reason: str | None,
    actor_identity: SignerIdentity,
    metadata_json: dict[str, Any] | None = None,
    occurred_at: dt.datetime | None = None,
) -> OIDCBrowserSessionEvent:
    observed_at = _utc(occurred_at)
    previous_event_hash = db.scalar(
        select(OIDCBrowserSessionEvent.event_hash)
        .where(OIDCBrowserSessionEvent.session_id == row.id)
        .order_by(
            OIDCBrowserSessionEvent.occurred_at.desc(),
            OIDCBrowserSessionEvent.created_at.desc(),
        )
        .limit(1)
    )
    event_id = uuid.uuid4()
    actor_json = actor_identity.to_json()
    metadata = metadata_json or {}
    canonical = {
        "id": str(event_id),
        "session_id": str(row.id),
        "session_hash": row.session_hash,
        "subject_id": row.subject_id,
        "identity_provider": row.identity_provider,
        "provider_session_hash": row.provider_session_hash,
        "event_type": event_type,
        "reason": reason,
        "actor_identity_json": actor_json,
        "identity_verified": actor_identity.identity_verified,
        "metadata_json": metadata,
        "previous_event_hash": previous_event_hash,
        "occurred_at": observed_at.isoformat(),
    }
    event = OIDCBrowserSessionEvent(
        id=event_id,
        session_id=row.id,
        session_hash=row.session_hash,
        subject_id=row.subject_id,
        identity_provider=row.identity_provider,
        provider_session_hash=row.provider_session_hash,
        event_type=event_type,
        reason=reason,
        actor_identity_json=actor_json,
        identity_verified=actor_identity.identity_verified,
        metadata_json=metadata,
        previous_event_hash=previous_event_hash,
        event_hash=hashlib.sha256(
            json.dumps(
                canonical,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest(),
        occurred_at=observed_at,
        created_at=observed_at,
    )
    db.add(event)
    return event


def browser_session_read(
    row: OIDCBrowserSession,
    *,
    current_session_id: UUID | None,
    now: dt.datetime | None = None,
) -> OIDCBrowserSessionRead:
    observed_at = _utc(now)
    return OIDCBrowserSessionRead(
        id=row.id,
        session_fingerprint=row.session_hash[:16],
        subject_id=row.subject_id,
        display_name=row.display_name,
        role=row.role,
        identity_provider=row.identity_provider,
        provider_session_hash=row.provider_session_hash,
        client_fingerprint=row.client_fingerprint,
        authenticated_at=row.authenticated_at,
        expires_at=row.expires_at,
        last_seen_at=row.last_seen_at,
        revoked_at=row.revoked_at,
        revocation_reason=row.revocation_reason,
        provider_token_state=(
            "retained"
            if row.provider_id_token_ciphertext
            else "purged"
            if row.provider_token_purged_at
            else "not_available"
        ),
        provider_token_purged_at=row.provider_token_purged_at,
        status=_session_status(row, observed_at),
        current_session=row.id == current_session_id,
    )


def browser_session_event_read(
    row: OIDCBrowserSessionEvent,
) -> OIDCBrowserSessionEventRead:
    return OIDCBrowserSessionEventRead(
        id=row.id,
        session_id=row.session_id,
        session_fingerprint=row.session_hash[:16],
        subject_id=row.subject_id,
        identity_provider=row.identity_provider,
        provider_session_hash=row.provider_session_hash,
        event_type=row.event_type,
        reason=row.reason,
        actor_identity_json=row.actor_identity_json,
        identity_verified=row.identity_verified,
        metadata_json=row.metadata_json,
        previous_event_hash=row.previous_event_hash,
        event_hash=row.event_hash,
        occurred_at=row.occurred_at,
        created_at=row.created_at,
    )


def _revoke_rows(
    db: Session,
    *,
    rows: list[OIDCBrowserSession],
    action: Literal["session", "subject", "provider_session"],
    reason: str,
    signer_identity: SignerIdentity,
    current_session_id: UUID | None,
    now: dt.datetime | None,
) -> BrowserSessionBulkActionRead:
    observed_at = _utc(now)
    revoked_count = 0
    already_inactive_count = 0
    current_session_preserved = False
    event_ids: list[UUID] = []
    for row in rows:
        if row.id == current_session_id:
            current_session_preserved = True
            continue
        if row.revoked_at is not None or row.expires_at <= observed_at:
            already_inactive_count += 1
            if row.provider_id_token_ciphertext:
                row.provider_id_token_ciphertext = None
                row.provider_session_id = None
                row.provider_token_purged_at = observed_at
                event = append_browser_session_event(
                    db,
                    row=row,
                    event_type="provider_token_purged",
                    reason="administrative_inactive_session_action",
                    actor_identity=signer_identity,
                    metadata_json={"scope": action, "operator_reason": reason},
                    occurred_at=observed_at,
                )
                event_ids.append(event.id)
            continue
        had_provider_token = bool(row.provider_id_token_ciphertext)
        row.revoked_at = observed_at
        row.revocation_reason = f"administrator_{action}_revocation"[:80]
        row.provider_id_token_ciphertext = None
        row.provider_session_id = None
        row.provider_token_purged_at = observed_at if had_provider_token else None
        event = append_browser_session_event(
            db,
            row=row,
            event_type="revoked",
            reason=reason,
            actor_identity=signer_identity,
            metadata_json={
                "scope": action,
                "provider_token_purged": had_provider_token,
            },
            occurred_at=observed_at,
        )
        event_ids.append(event.id)
        revoked_count += 1
    db.commit()
    return BrowserSessionBulkActionRead(
        action=action,
        matched_count=len(rows),
        revoked_count=revoked_count,
        already_inactive_count=already_inactive_count,
        current_session_preserved=current_session_preserved,
        event_ids=event_ids,
    )


def _assert_can_audit(identity: SignerIdentity) -> None:
    if not session_administration_permissions(identity).can_audit:
        raise DomainValidationError(
            "browser session audit requires a verified session auditor role"
        )


def _assert_can_administer(identity: SignerIdentity) -> None:
    if not session_administration_permissions(identity).can_administer:
        raise DomainValidationError(
            "browser session administration requires a verified Admin or SRE Lead"
        )


def _session_status(
    row: OIDCBrowserSession,
    observed_at: dt.datetime,
) -> Literal["active", "expired", "revoked"]:
    if row.revoked_at is not None:
        return "revoked"
    if row.expires_at <= observed_at:
        return "expired"
    return "active"


def _retention_due_expression(retention_cutoff: dt.datetime) -> Any:
    return or_(
        OIDCBrowserSession.revoked_at <= retention_cutoff,
        and_(
            OIDCBrowserSession.revoked_at.is_(None),
            OIDCBrowserSession.expires_at <= retention_cutoff,
        ),
    )


def _count(db: Session, *criteria: Any) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(OIDCBrowserSession).where(*criteria)
        )
        or 0
    )


def _role_key(role: str | None) -> str:
    return " ".join((role or "").strip().split()).lower()


def _utc(value: dt.datetime | None) -> dt.datetime:
    current = value or dt.datetime.now(dt.UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=dt.UTC)
    return current.astimezone(dt.UTC)
