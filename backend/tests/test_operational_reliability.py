from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.secret_projection import read_projected_secret, read_projected_string_map
from app.models import (
    OperationalAlertDelivery,
    OperationalAlertIncident,
    OperationalAlertIncidentAction,
    OperationalMetricPoint,
    OperationalMetricSnapshot,
    OperationalSLOEvaluation,
)
from app.operations.paging_secrets import (
    initialize_paging_secrets,
    rotate_paging_secrets,
)
from app.services.agent_jobs import (
    claim_agent_job,
    enqueue_operational_observability_cycle_job,
    process_claimed_agent_job,
    register_agent_worker,
    system_worker_identity,
)
from app.services.operational_reliability import (
    PagingDeliveryError,
    build_operational_reliability_overview,
    capture_operational_reliability_cycle,
    create_operational_test_delivery,
    execute_operational_alert_delivery,
)
from app.services.operator_identity import SignerIdentity
from app.validators.rules import DomainValidationError


def _identity(role: str, subject: str = "operations-admin") -> SignerIdentity:
    return SignerIdentity(
        subject_id=subject,
        display_name="Operations Admin",
        role=role,
        identity_provider="pytest",
        auth_source="pytest",
        identity_verified=True,
        ticket_reference=None,
    )


def _headers(role: str, subject: str = "operations-admin") -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": subject,
        "x-model-atlas-operator-name": "Operations Admin",
        "x-model-atlas-operator-role": role,
    }


def _configure_reliability(monkeypatch, *, paging: bool = False) -> None:  # type: ignore[no-untyped-def]
    settings = get_settings()
    monkeypatch.setattr(settings, "operational_snapshot_enabled", True)
    monkeypatch.setattr(settings, "operational_snapshot_interval_seconds", 60)
    monkeypatch.setattr(settings, "operational_snapshot_retention_days", 1)
    monkeypatch.setattr(settings, "operational_slo_window_seconds", 300)
    monkeypatch.setattr(settings, "operational_slo_short_window_seconds", 120)
    monkeypatch.setattr(settings, "operational_slo_min_samples", 2)
    monkeypatch.setattr(settings, "operational_identity_slo_target", 0.9)
    monkeypatch.setattr(settings, "operational_worker_slo_target", 0.9)
    monkeypatch.setattr(settings, "operational_slo_warning_burn_rate", 1.5)
    monkeypatch.setattr(settings, "operational_slo_critical_burn_rate", 3.0)
    monkeypatch.setattr(settings, "operational_incident_escalation_seconds", 60)
    monkeypatch.setattr(settings, "operational_paging_enabled", paging)
    monkeypatch.setattr(
        settings,
        "operational_paging_webhook_url",
        "https://paging.example.test/page",
    )
    monkeypatch.setattr(
        settings,
        "operational_paging_allowed_hosts",
        ["paging.example.test"],
    )
    monkeypatch.setattr(settings, "operational_paging_allow_insecure_http", False)
    monkeypatch.setattr(
        settings,
        "operational_paging_hmac_secret",
        "pytest-operational-paging-secret-32-characters",
    )
    monkeypatch.setattr(
        settings,
        "operational_paging_hmac_keys",
        {
            "pytest-primary": "pytest-primary-paging-secret-32-characters",
            "pytest-retiring": "pytest-retiring-paging-secret-32-characters",
        },
    )
    monkeypatch.setattr(
        settings,
        "operational_paging_active_key_id",
        "pytest-primary",
    )
    monkeypatch.setattr(settings, "operational_paging_hmac_keys_file", None)
    monkeypatch.setattr(settings, "operational_paging_active_key_id_file", None)
    monkeypatch.setattr(settings, "operational_paging_ca_bundle_path", None)
    monkeypatch.setattr(settings, "operational_paging_provider", "generic-webhook")
    monkeypatch.setattr(settings, "operational_paging_require_receipt", False)
    monkeypatch.setattr(
        settings,
        "operational_paging_receipt_max_age_seconds",
        300,
    )
    monkeypatch.setattr(settings, "operational_paging_timeout_seconds", 2.0)
    monkeypatch.setattr(settings, "operational_paging_max_response_bytes", 4096)


def test_durable_snapshots_slo_gap_and_retention(
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch)
    settings = get_settings()
    observed_at = dt.datetime.now(dt.UTC).replace(second=1, microsecond=0)
    collector = system_worker_identity("snapshot-worker")
    register_agent_worker(db_session, worker_id="snapshot-worker")

    first = capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="First deterministic operational capture",
        now=observed_at,
    )
    replay = capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="Same bucket must be idempotent",
        now=observed_at + dt.timedelta(seconds=10),
    )
    assert first["created"] is True
    assert replay["created"] is False
    assert replay["snapshot_id"] == first["snapshot_id"]

    worker = register_agent_worker(db_session, worker_id="snapshot-worker")
    worker.last_seen_at = observed_at + dt.timedelta(minutes=3)
    db_session.commit()
    later = capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="Capture after two missing intervals",
        now=observed_at + dt.timedelta(minutes=3),
    )
    assert later["created"] is True

    evaluations = list(
        db_session.scalars(
            select(OperationalSLOEvaluation).order_by(OperationalSLOEvaluation.evaluated_at)
        ).all()
    )
    latest = {row.slo_key: row for row in evaluations[-2:]}
    assert latest["identity_session_hygiene"].sample_count == 4
    assert latest["identity_session_hygiene"].details_json["missing_sample_count"] == 2
    assert latest["identity_session_hygiene"].status == "breached"
    assert latest["worker_control_plane_availability"].status == "breached"
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(OperationalAlertIncident)
            .where(OperationalAlertIncident.status == "open")
        )
        == 2
    )

    expired = OperationalMetricSnapshot(
        bucket_started_at=observed_at - dt.timedelta(days=3),
        generated_at=observed_at - dt.timedelta(days=3),
        expires_at=observed_at - dt.timedelta(days=2),
        health="healthy",
        schema_version="test",
        sample_count=0,
        alert_count=0,
        content_hash=hashlib.sha256(b"expired-snapshot").hexdigest(),
        collected_by="pytest",
        created_at=observed_at - dt.timedelta(days=3),
    )
    db_session.add(expired)
    db_session.commit()
    capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="Retention cleanup capture",
        now=observed_at + dt.timedelta(minutes=4),
    )
    assert db_session.get(OperationalMetricSnapshot, expired.id) is None
    assert (db_session.scalar(select(func.count()).select_from(OperationalMetricPoint)) or 0) > 0


def test_multi_window_burn_rate_and_unacknowledged_escalation(
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    settings = get_settings()
    observed_at = dt.datetime.now(dt.UTC).replace(second=1, microsecond=0)
    collector = system_worker_identity("burn-rate-worker")
    worker = register_agent_worker(db_session, worker_id="burn-rate-worker")

    capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="Capture the first healthy burn-rate sample",
        now=observed_at,
    )
    worker.last_seen_at = observed_at + dt.timedelta(minutes=1)
    db_session.commit()
    capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="Capture the second healthy burn-rate sample",
        now=observed_at + dt.timedelta(minutes=1),
    )
    worker.status = "stopped"
    db_session.commit()
    capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="Capture a failed worker availability sample",
        now=observed_at + dt.timedelta(minutes=2),
    )

    evaluation = db_session.scalar(
        select(OperationalSLOEvaluation)
        .where(
            OperationalSLOEvaluation.slo_key == "worker_control_plane_availability",
        )
        .order_by(OperationalSLOEvaluation.evaluated_at.desc())
        .limit(1)
    )
    assert evaluation is not None
    assert evaluation.status == "breached"
    assert evaluation.burn_alert_level == "critical"
    assert evaluation.burn_rate is not None and evaluation.burn_rate >= 3
    assert evaluation.short_burn_rate is not None and evaluation.short_burn_rate >= 3
    assert evaluation.details_json["short_window"]["sample_count"] == 3

    capture_operational_reliability_cycle(
        db_session,
        settings=settings,
        collector_identity=collector,
        reason="Escalate the unacknowledged critical incident",
        now=observed_at + dt.timedelta(minutes=3),
    )
    incident = db_session.scalar(
        select(OperationalAlertIncident).where(
            OperationalAlertIncident.alert_key == "slo:worker_control_plane_availability",
            OperationalAlertIncident.status == "open",
        )
    )
    assert incident is not None
    assert incident.escalation_level == 1
    action = db_session.scalar(
        select(OperationalAlertIncidentAction).where(
            OperationalAlertIncidentAction.incident_id == incident.id,
            OperationalAlertIncidentAction.action_type == "escalated",
        )
    )
    assert action is not None
    assert action.identity_verified is True
    transitions = list(
        db_session.scalars(
            select(OperationalAlertDelivery.transition_type).where(
                OperationalAlertDelivery.incident_id == incident.id
            )
        ).all()
    )
    assert set(transitions) == {"opened", "escalated"}


def test_owned_paging_delivery_is_signed_and_idempotent(
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    settings = get_settings()
    delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("Admin"),
        severity="critical",
        reason="Verify the owned paging delivery path",
    )
    monkeypatch.setattr(
        settings,
        "operational_paging_active_key_id",
        "pytest-retiring",
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        timestamp = request.headers["x-model-atlas-timestamp"]
        assert request.headers["x-model-atlas-key-id"] == "pytest-primary"
        expected = hmac.new(
            settings.operational_paging_hmac_keys["pytest-primary"].encode(),
            timestamp.encode() + b"." + request.content,
            hashlib.sha256,
        ).hexdigest()
        assert request.headers["x-model-atlas-signature"] == f"sha256={expected}"
        assert request.headers["idempotency-key"] == str(delivery.id)
        payload = json.loads(request.content)
        assert payload["delivery_id"] == str(delivery.id)
        return httpx.Response(202, json={"accepted": True})

    first = execute_operational_alert_delivery(
        db_session,
        delivery_id=delivery.id,
        settings=settings,
        attempt_number=1,
        max_attempts=4,
        transport=httpx.MockTransport(handler),
    )
    replay = execute_operational_alert_delivery(
        db_session,
        delivery_id=delivery.id,
        settings=settings,
        attempt_number=2,
        max_attempts=4,
        transport=httpx.MockTransport(handler),
    )
    assert first["status"] == "delivered"
    assert first["replay"] is False
    assert replay["replay"] is True
    assert len(requests) == 1
    stored = db_session.get(OperationalAlertDelivery, delivery.id)
    assert stored is not None
    assert stored.status == "delivered"
    assert stored.response_status == 202
    assert stored.response_hash
    assert stored.signing_key_id == "pytest-primary"


def test_paging_delivery_records_permanent_and_retryable_failures(
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    settings = get_settings()
    invalid_delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("SRE Lead"),
        severity="warning",
        reason="Verify invalid destination policy failure",
    )
    monkeypatch.setattr(
        settings,
        "operational_paging_webhook_url",
        "https://untrusted.example.test/page",
    )
    with pytest.raises(DomainValidationError):
        execute_operational_alert_delivery(
            db_session,
            delivery_id=invalid_delivery.id,
            settings=settings,
            attempt_number=1,
            max_attempts=4,
        )
    db_session.refresh(invalid_delivery)
    assert invalid_delivery.status == "failed"
    assert invalid_delivery.attempt_count == 1
    assert "OPERATIONAL_PAGING_ALLOWED_HOSTS" in (invalid_delivery.error_message or "")

    monkeypatch.setattr(
        settings,
        "operational_paging_webhook_url",
        "https://paging.example.test/page",
    )
    retryable_delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("Admin"),
        severity="critical",
        reason="Verify retryable paging destination failure",
    )
    with pytest.raises(PagingDeliveryError):
        execute_operational_alert_delivery(
            db_session,
            delivery_id=retryable_delivery.id,
            settings=settings,
            attempt_number=1,
            max_attempts=4,
            transport=httpx.MockTransport(lambda _request: httpx.Response(503, text="unavailable")),
        )
    db_session.refresh(retryable_delivery)
    assert retryable_delivery.status == "queued"
    assert retryable_delivery.response_status == 503
    assert retryable_delivery.attempt_count == 1

    recovered = execute_operational_alert_delivery(
        db_session,
        delivery_id=retryable_delivery.id,
        settings=settings,
        attempt_number=1,
        max_attempts=4,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(202, json={"accepted": True})
        ),
    )
    db_session.refresh(retryable_delivery)
    assert recovered["status"] == "delivered"
    assert retryable_delivery.attempt_count == 2


def test_projected_key_rotation_and_provider_receipt_correlation(
    db_session: Session,
    monkeypatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    settings = get_settings()
    initialize_paging_secrets(
        tmp_path,
        active_key_id="pytest-file-primary",
        retiring_key_id="pytest-file-retiring",
    )
    monkeypatch.setattr(settings, "operational_paging_hmac_secret", None)
    monkeypatch.setattr(settings, "operational_paging_hmac_keys", {})
    monkeypatch.setattr(
        settings,
        "operational_paging_hmac_keys_file",
        str(tmp_path / "hmac-keys.json"),
    )
    monkeypatch.setattr(settings, "operational_paging_active_key_id", None)
    monkeypatch.setattr(
        settings,
        "operational_paging_active_key_id_file",
        str(tmp_path / "active-key-id"),
    )
    monkeypatch.setattr(settings, "operational_paging_provider", "pytest-pager")
    monkeypatch.setattr(settings, "operational_paging_require_receipt", True)
    observed_at = dt.datetime.now(dt.UTC).replace(microsecond=0)

    retiring_delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("Admin"),
        severity="warning",
        reason="Queue a delivery before rotating projected paging keys",
        now=observed_at,
    )
    assert retiring_delivery.signing_key_id == "pytest-file-primary"
    rotation = rotate_paging_secrets(
        tmp_path,
        new_key_id="pytest-file-next",
        retain=2,
    )
    assert rotation["previous_active_key_id"] == "pytest-file-primary"
    active_delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("Admin"),
        severity="critical",
        reason="Queue a delivery after rotating projected paging keys",
        now=observed_at + dt.timedelta(seconds=1),
    )
    assert active_delivery.signing_key_id == "pytest-file-next"

    observed_key_ids: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        keyring = read_projected_string_map(
            str(tmp_path / "hmac-keys.json"),
            label="pytest paging keyring",
        )
        key_id = request.headers["x-model-atlas-key-id"]
        timestamp = request.headers["x-model-atlas-timestamp"]
        signature = hmac.new(
            keyring[key_id].encode(),
            timestamp.encode() + b"." + request.content,
            hashlib.sha256,
        ).hexdigest()
        assert request.headers["x-model-atlas-signature"] == f"sha256={signature}"
        event_id = request.headers["x-model-atlas-event-id"]
        observed_key_ids.append(key_id)
        return httpx.Response(
            202,
            json={
                "schema_version": "model-atlas-paging-provider-receipt-v1",
                "accepted": True,
                "provider": "pytest-pager",
                "provider_event_id": event_id,
                "receipt_id": f"pytest-receipt-{event_id}",
                "accepted_at": int(timestamp),
            },
        )

    transport = httpx.MockTransport(handler)
    first = execute_operational_alert_delivery(
        db_session,
        delivery_id=retiring_delivery.id,
        settings=settings,
        attempt_number=1,
        max_attempts=4,
        now=observed_at + dt.timedelta(seconds=2),
        transport=transport,
    )
    second = execute_operational_alert_delivery(
        db_session,
        delivery_id=active_delivery.id,
        settings=settings,
        attempt_number=1,
        max_attempts=4,
        now=observed_at + dt.timedelta(seconds=3),
        transport=transport,
    )
    assert observed_key_ids == ["pytest-file-primary", "pytest-file-next"]
    assert first["provider_receipt_id"] == (f"pytest-receipt-{retiring_delivery.id}")
    assert second["provider_event_id"] == str(active_delivery.id)

    overview = build_operational_reliability_overview(
        db_session,
        settings=settings,
        signer_identity=_identity("SRE Lead"),
        now=observed_at + dt.timedelta(seconds=4),
    )
    assert overview.schema_version == "model-atlas-operational-reliability-v3"
    assert overview.policy.paging_secret_source == "projected_file"
    assert overview.policy.paging_key_count == 2
    assert overview.staging_readiness.ready is True
    assert overview.staging_readiness.failed_count == 0


def test_required_provider_receipt_rejects_uncorrelated_success(
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    settings = get_settings()
    monkeypatch.setattr(settings, "operational_paging_provider", "pytest-pager")
    monkeypatch.setattr(settings, "operational_paging_require_receipt", True)
    delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("Admin"),
        severity="warning",
        reason="Reject a success response without provider correlation",
    )
    with pytest.raises(PagingDeliveryError):
        execute_operational_alert_delivery(
            db_session,
            delivery_id=delivery.id,
            settings=settings,
            attempt_number=1,
            max_attempts=4,
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    202,
                    json={
                        "schema_version": "model-atlas-paging-provider-receipt-v1",
                        "accepted": True,
                        "provider": "pytest-pager",
                        "provider_event_id": "another-delivery",
                        "receipt_id": "uncorrelated-provider-event",
                        "accepted_at": int(dt.datetime.now(dt.UTC).timestamp()),
                    },
                )
            ),
        )
    db_session.refresh(delivery)
    assert delivery.status == "queued"
    assert delivery.provider_receipt_id is None
    assert delivery.error_message == "operational paging provider receipt is invalid"


def test_required_provider_receipt_rejects_unsupported_schema(
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    settings = get_settings()
    monkeypatch.setattr(settings, "operational_paging_provider", "pytest-pager")
    monkeypatch.setattr(settings, "operational_paging_require_receipt", True)
    delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("Admin"),
        severity="warning",
        reason="Reject a provider receipt with an unsupported schema",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            202,
            json={
                "schema_version": "model-atlas-paging-provider-receipt-v0",
                "accepted": True,
                "provider": "pytest-pager",
                "provider_event_id": request.headers["x-model-atlas-event-id"],
                "receipt_id": "unsupported-receipt-schema",
                "accepted_at": int(dt.datetime.now(dt.UTC).timestamp()),
            },
        )

    with pytest.raises(PagingDeliveryError):
        execute_operational_alert_delivery(
            db_session,
            delivery_id=delivery.id,
            settings=settings,
            attempt_number=1,
            max_attempts=4,
            transport=httpx.MockTransport(handler),
        )

    db_session.refresh(delivery)
    assert delivery.status == "queued"
    assert delivery.provider_receipt_id is None
    assert delivery.error_message == "operational paging provider receipt is invalid"


def test_projected_paging_secret_outage_remains_retryable(
    db_session: Session,
    monkeypatch,
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    settings = get_settings()
    initialize_paging_secrets(
        tmp_path,
        active_key_id="pytest-file-primary",
        retiring_key_id="pytest-file-retiring",
    )
    keyring_path = tmp_path / "hmac-keys.json"
    monkeypatch.setattr(settings, "operational_paging_hmac_secret", None)
    monkeypatch.setattr(settings, "operational_paging_hmac_keys", {})
    monkeypatch.setattr(
        settings,
        "operational_paging_hmac_keys_file",
        str(keyring_path),
    )
    monkeypatch.setattr(settings, "operational_paging_active_key_id", None)
    monkeypatch.setattr(
        settings,
        "operational_paging_active_key_id_file",
        str(tmp_path / "active-key-id"),
    )
    delivery = create_operational_test_delivery(
        db_session,
        settings=settings,
        signer_identity=_identity("Admin"),
        severity="warning",
        reason="Retry after a temporary projected secret outage",
    )

    keyring_path.unlink()
    with pytest.raises(
        PagingDeliveryError,
        match="credential or CA projection is unavailable",
    ):
        execute_operational_alert_delivery(
            db_session,
            delivery_id=delivery.id,
            settings=settings,
            attempt_number=1,
            max_attempts=4,
        )

    db_session.refresh(delivery)
    assert delivery.status == "queued"
    assert delivery.attempt_count == 1
    assert delivery.error_message == (
        "operational paging credential or CA projection is unavailable"
    )


def test_projected_secret_reader_is_bounded_and_fail_closed(tmp_path) -> None:  # type: ignore[no-untyped-def]
    projection = tmp_path / "projection"
    projection.write_bytes(b"12345")
    with pytest.raises(ValueError, match="outside the allowed size"):
        read_projected_secret(
            str(projection),
            label="pytest projection",
            max_bytes=4,
        )

    invalid_keyrings = (
        {"valid": "a" * 32, "": "b" * 32},
        {"key": "a" * 32, " key ": "b" * 32},
    )
    for keyring in invalid_keyrings:
        projection.write_text(json.dumps(keyring), encoding="utf-8")
        with pytest.raises(ValueError):
            read_projected_string_map(
                str(projection),
                label="pytest keyring",
            )


def test_incident_actions_are_rbac_guarded_and_hash_chained(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch)
    observed_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    incident = OperationalAlertIncident(
        active_key="pytest:incident-response",
        alert_key="pytest:incident-response",
        source_type="derived_alert",
        severity="critical",
        route="model-atlas-critical",
        summary="Exercise operator acknowledgement and assignment",
        status="open",
        opened_at=observed_at,
        last_seen_at=observed_at,
        occurrence_count=1,
        transition_version=1,
        latest_context_json={"pytest": True},
    )
    db_session.add(incident)
    db_session.commit()

    denied = client.post(
        f"/api/v1/operations/reliability/incidents/{incident.id}/actions",
        headers=_headers("ML Ops Lead", "operations-auditor"),
        json={
            "action_type": "acknowledged",
            "reason": "Auditor cannot acknowledge this incident",
        },
    )
    assert denied.status_code == 403
    acknowledged = client.post(
        f"/api/v1/operations/reliability/incidents/{incident.id}/actions",
        headers=_headers("SRE Lead", "operations-sre"),
        json={
            "action_type": "acknowledged",
            "reason": "SRE accepted ownership of the incident",
        },
    )
    assert acknowledged.status_code == 201
    first_action = acknowledged.json()
    assert first_action["previous_action_hash"] is None

    assigned = client.post(
        f"/api/v1/operations/reliability/incidents/{incident.id}/actions",
        headers=_headers("Admin"),
        json={
            "action_type": "assigned",
            "reason": "Assign incident investigation to the platform team",
            "assignee": "platform-on-call",
        },
    )
    assert assigned.status_code == 201
    assert assigned.json()["previous_action_hash"] == first_action["action_hash"]
    db_session.refresh(incident)
    assert incident.acknowledged_at is not None
    assert incident.assigned_to == "platform-on-call"

    overview = client.get("/api/v1/operations/reliability")
    assert overview.status_code == 200
    payload = overview.json()
    assert len(payload["incident_actions"]) == 2
    assert payload["incidents"][0]["assigned_to"] == "platform-on-call"


def test_operational_cycle_job_dedupe_and_api_rbac(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    _configure_reliability(monkeypatch, paging=True)
    identity = system_worker_identity("operations-job-worker")
    register_agent_worker(db_session, worker_id="operations-job-worker")
    first = enqueue_operational_observability_cycle_job(
        db_session,
        schedule_key="interval-test",
        signer_identity=identity,
        reason="Scheduled observability capture test",
    )
    second = enqueue_operational_observability_cycle_job(
        db_session,
        schedule_key="interval-test",
        signer_identity=identity,
        reason="Scheduled observability capture test",
    )
    assert second.id == first.id
    claimed = claim_agent_job(db_session, worker_id="operations-job-worker")
    assert claimed is not None and claimed.lease_token
    completed = process_claimed_agent_job(
        db_session,
        job_id=claimed.id,
        lease_token=claimed.lease_token,
    )
    assert completed.status == "completed"
    assert completed.result_json["created"] is True

    overview = client.get("/api/v1/operations/reliability")
    assert overview.status_code == 200
    assert overview.json()["snapshot_count"] == 1
    assert overview.json()["permissions"]["can_administer"] is False

    denied = client.post(
        "/api/v1/operations/reliability/cycles",
        headers=_headers("ML Ops Lead", "operations-auditor"),
        json={"reason": "Auditor must not queue this cycle"},
    )
    assert denied.status_code == 403
    queued = client.post(
        "/api/v1/operations/reliability/cycles",
        headers=_headers("Admin"),
        json={"reason": "Administrator requested an immediate capture"},
    )
    assert queued.status_code == 202
    assert queued.json()["job_type"] == "operational_observability_cycle"

    test_page = client.post(
        "/api/v1/operations/reliability/test-pages",
        headers=_headers("SRE Lead", "operations-sre"),
        json={
            "severity": "warning",
            "reason": "End to end paging delivery contract test",
        },
    )
    assert test_page.status_code == 202
    assert test_page.json()["job_type"] == "operational_alert_delivery"
