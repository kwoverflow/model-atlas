from __future__ import annotations

import datetime as dt
import hashlib
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OIDCBrowserSession, OIDCBrowserSessionEvent
from app.services.agent_jobs import (
    claim_agent_job,
    enqueue_oidc_session_cleanup_job,
    process_claimed_agent_job,
    system_worker_identity,
)
from app.services.oidc_session_administration import (
    revoke_provider_sessions,
    revoke_subject_sessions,
)
from app.services.operator_identity import SignerIdentity


def _headers(role: str, subject: str = "session-operator") -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": subject,
        "x-model-atlas-operator-name": "Session Operator",
        "x-model-atlas-operator-role": role,
    }


def _identity(role: str, subject: str = "session-admin") -> SignerIdentity:
    return SignerIdentity(
        subject_id=subject,
        display_name="Session Admin",
        role=role,
        identity_provider="trusted-header",
        auth_source="trusted_header",
        identity_verified=True,
        ticket_reference=None,
    )


def _session(
    *,
    subject_id: str,
    provider_session_id: str,
    authenticated_at: dt.datetime,
    expires_at: dt.datetime,
    revoked_at: dt.datetime | None = None,
) -> OIDCBrowserSession:
    suffix = uuid.uuid4().hex
    return OIDCBrowserSession(
        token_hash=hashlib.sha256(f"token-{suffix}".encode()).hexdigest(),
        csrf_token_hash=hashlib.sha256(f"csrf-{suffix}".encode()).hexdigest(),
        session_hash=hashlib.sha256(f"session-{suffix}".encode()).hexdigest(),
        subject_id=subject_id,
        display_name=subject_id,
        role="ML Ops Lead",
        identity_provider="https://idp.example/realms/model-atlas",
        provider_session_id=provider_session_id,
        provider_session_hash=hashlib.sha256(provider_session_id.encode()).hexdigest(),
        client_fingerprint=hashlib.sha256(f"client-{suffix}".encode()).hexdigest(),
        provider_id_token_ciphertext=f"ciphertext-{suffix}",
        authenticated_at=authenticated_at,
        expires_at=expires_at,
        last_seen_at=authenticated_at,
        revoked_at=revoked_at,
        revocation_reason="preexisting_revocation" if revoked_at else None,
    )


def test_session_auditor_and_administrator_routes_are_separated(
    client: TestClient,
    db_session: Session,
) -> None:
    now = dt.datetime.now(dt.UTC)
    row = _session(
        subject_id="operator-a",
        provider_session_id="provider-a",
        authenticated_at=now - dt.timedelta(minutes=10),
        expires_at=now + dt.timedelta(hours=1),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    overview = client.get(
        "/api/v1/operator-identity/sessions/overview",
        headers=_headers("ML Ops Lead", "auditor"),
    )
    assert overview.status_code == 200
    assert overview.json()["active_count"] == 1
    assert overview.json()["permissions"]["can_audit"] is True
    assert overview.json()["permissions"]["can_administer"] is False

    denied = client.post(
        f"/api/v1/operator-identity/sessions/{row.id}/revoke",
        headers=_headers("ML Ops Lead", "auditor"),
        json={"reason": "Auditor must not revoke sessions"},
    )
    assert denied.status_code == 403

    revoked = client.post(
        f"/api/v1/operator-identity/sessions/{row.id}/revoke",
        headers=_headers("Admin", "administrator"),
        json={"reason": "Confirmed compromised browser session"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_count"] == 1

    db_session.expire_all()
    updated = db_session.get(OIDCBrowserSession, row.id)
    assert updated is not None
    assert updated.revoked_at is not None
    assert updated.provider_id_token_ciphertext is None
    assert updated.provider_session_id is None
    assert updated.provider_session_hash
    event = db_session.scalar(select(OIDCBrowserSessionEvent))
    assert event is not None
    assert event.event_type == "revoked"
    assert event.actor_identity_json["subject_id"] == "administrator"


def test_subject_and_provider_revocation_preserve_current_session(
    db_session: Session,
) -> None:
    now = dt.datetime.now(dt.UTC)
    current = _session(
        subject_id="shared-subject",
        provider_session_id="provider-shared",
        authenticated_at=now - dt.timedelta(minutes=5),
        expires_at=now + dt.timedelta(hours=1),
    )
    sibling = _session(
        subject_id="shared-subject",
        provider_session_id="provider-shared",
        authenticated_at=now - dt.timedelta(minutes=4),
        expires_at=now + dt.timedelta(hours=1),
    )
    db_session.add_all([current, sibling])
    db_session.commit()

    subject_result = revoke_subject_sessions(
        db_session,
        subject_id="shared-subject",
        reason="Subject-wide incident containment",
        signer_identity=_identity("Admin"),
        current_session_id=current.id,
        now=now,
    )
    assert subject_result.matched_count == 2
    assert subject_result.revoked_count == 1
    assert subject_result.current_session_preserved is True

    provider_result = revoke_provider_sessions(
        db_session,
        provider_session_hash=current.provider_session_hash or "",
        reason="Provider session containment review",
        signer_identity=_identity("SRE Lead", "session-sre"),
        current_session_id=current.id,
        now=now + dt.timedelta(seconds=1),
    )
    assert provider_result.current_session_preserved is True
    assert provider_result.revoked_count == 0
    db_session.expire_all()
    assert db_session.get(OIDCBrowserSession, current.id).revoked_at is None  # type: ignore[union-attr]
    assert db_session.get(OIDCBrowserSession, sibling.id).revoked_at is not None  # type: ignore[union-attr]


def test_durable_cleanup_is_deduplicated_and_preserves_audit(
    db_session: Session,
) -> None:
    now = dt.datetime.now(dt.UTC)
    old_revoked = _session(
        subject_id="old-revoked",
        provider_session_id="provider-old-revoked",
        authenticated_at=now - dt.timedelta(days=60),
        expires_at=now - dt.timedelta(days=40),
        revoked_at=now - dt.timedelta(days=35),
    )
    old_expired = _session(
        subject_id="old-expired",
        provider_session_id="provider-old-expired",
        authenticated_at=now - dt.timedelta(days=60),
        expires_at=now - dt.timedelta(days=35),
    )
    recent_expired = _session(
        subject_id="recent-expired",
        provider_session_id="provider-recent-expired",
        authenticated_at=now - dt.timedelta(days=1),
        expires_at=now - dt.timedelta(hours=1),
    )
    db_session.add_all([old_revoked, old_expired, recent_expired])
    db_session.commit()
    recent_id = recent_expired.id

    first = enqueue_oidc_session_cleanup_job(
        db_session,
        schedule_key="interval-5he",
        signer_identity=system_worker_identity("scheduler-a"),
        retention_days=30,
        batch_size=100,
        reason="Scheduled browser session retention cleanup",
    )
    second = enqueue_oidc_session_cleanup_job(
        db_session,
        schedule_key="interval-5he",
        signer_identity=system_worker_identity("scheduler-b"),
        retention_days=30,
        batch_size=100,
        reason="Scheduled browser session retention cleanup",
    )
    assert first.id == second.id

    claimed = claim_agent_job(
        db_session,
        worker_id="cleanup-worker",
        lease_seconds=30,
    )
    assert claimed is not None
    assert claimed.lease_token is not None
    completed = process_claimed_agent_job(
        db_session,
        job_id=claimed.id,
        lease_token=claimed.lease_token,
    )
    assert completed.status == "completed"
    assert completed.result_json["deleted_count"] == 2
    assert completed.result_json["provider_token_purged_count"] == 3
    assert completed.result_json["retention_due_remaining"] == 0
    assert completed.result_json["inactive_provider_token_remaining"] == 0

    remaining = db_session.get(OIDCBrowserSession, recent_id)
    assert remaining is not None
    assert remaining.provider_id_token_ciphertext is None
    assert remaining.provider_session_id is None
    events = list(db_session.scalars(select(OIDCBrowserSessionEvent)).all())
    assert len(events) == 3
    assert sorted(event.event_type for event in events) == [
        "provider_token_purged",
        "retention_deleted",
        "retention_deleted",
    ]
    assert all(event.event_hash for event in events)
