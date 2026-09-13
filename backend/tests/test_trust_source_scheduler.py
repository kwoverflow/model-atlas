from __future__ import annotations

import datetime as dt
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes import trust_registry as trust_registry_routes
from app.core.config import get_settings
from app.models import (
    EvidenceTrustSourceSchedule,
    EvidenceTrustSourceSync,
)
from app.services import trust_source_scheduler
from app.services.agent_jobs import (
    claim_agent_job,
    process_claimed_agent_job,
    system_worker_identity,
)
from app.services.trust_source_scheduler import enqueue_due_trust_source_sync_jobs
from app.services.trust_source_sync import FetchedJwksPayload, TrustSourceFetchError


def _operator_headers() -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": "schedule-governor",
        "x-model-atlas-operator-name": "Schedule Governor",
        "x-model-atlas-operator-role": "Model Governance",
    }


def _public_jwk(key_id: str) -> dict[str, Any]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": key_id, "alg": "RS256", "use": "sig"})
    return jwk


def _configure_source_and_schedule(
    client: TestClient,
    monkeypatch: Any,
    *,
    max_attempts: int = 3,
) -> tuple[dict[str, Any], dict[str, Any]]:
    monkeypatch.setattr(
        trust_registry_routes.settings,
        "trust_source_allowed_hosts",
        ["scheduled.example.test"],
    )
    monkeypatch.setattr(
        trust_registry_routes.settings,
        "trust_source_allow_insecure_http",
        False,
    )
    settings = get_settings()
    monkeypatch.setattr(
        settings,
        "trust_source_allowed_hosts",
        ["scheduled.example.test"],
    )
    monkeypatch.setattr(settings, "trust_source_allow_insecure_http", False)
    source_response = client.post(
        "/api/v1/trust-registry/sources",
        headers=_operator_headers(),
        json={
            "name": "Scheduled publisher registry",
            "purpose": "model_publisher",
            "issuer": "scheduled-publisher",
            "trust_tier": "external",
            "endpoint_url": "https://scheduled.example.test/jwks.json",
            "allowed_algorithms": ["RS256"],
            "freshness_seconds": 600,
        },
    )
    assert source_response.status_code == 201, source_response.text
    source = source_response.json()["trust_source"]
    schedule_response = client.put(
        f"/api/v1/trust-registry/sources/{source['id']}/schedule",
        headers=_operator_headers(),
        json={
            "enabled": True,
            "interval_seconds": 300,
            "jitter_seconds": 30,
            "max_attempts": max_attempts,
            "retry_base_seconds": 5,
            "retry_max_seconds": 20,
            "retry_jitter_seconds": 0,
            "run_immediately": True,
        },
    )
    assert schedule_response.status_code == 200, schedule_response.text
    return source, schedule_response.json()


def test_due_schedule_is_enqueued_once_and_records_success_lineage(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    source, configured = _configure_source_and_schedule(client, monkeypatch)
    assert configured["status"] == "due"
    observed_at = dt.datetime.now(dt.UTC).replace(microsecond=0) + dt.timedelta(seconds=1)
    first = enqueue_due_trust_source_sync_jobs(
        db_session,
        scheduler_id="scheduler-one",
        signer_identity=system_worker_identity("scheduler-one"),
        lease_seconds=300,
        now=observed_at,
    )
    second = enqueue_due_trust_source_sync_jobs(
        db_session,
        scheduler_id="scheduler-two",
        signer_identity=system_worker_identity("scheduler-two"),
        lease_seconds=300,
        now=observed_at,
    )
    assert len(first) == 1
    assert second == []

    monkeypatch.setattr(
        trust_source_scheduler,
        "fetch_remote_jwks",
        lambda *args, **kwargs: FetchedJwksPayload(
            payload={"keys": [_public_jwk("scheduled-2026")]},
            http_status=200,
            fetched_at=observed_at,
        ),
    )
    claimed = claim_agent_job(
        db_session,
        worker_id="executor-one",
        lease_seconds=300,
        now=observed_at,
    )
    assert claimed is not None
    assert claimed.id == first[0].id
    assert claimed.lease_token is not None
    completed = process_claimed_agent_job(
        db_session,
        job_id=claimed.id,
        lease_token=claimed.lease_token,
    )
    assert completed.status == "completed"
    assert completed.result_json is not None
    assert completed.result_json["outcome"] == "succeeded"

    schedule = db_session.get(EvidenceTrustSourceSchedule, configured["id"])
    assert schedule is not None
    assert schedule.last_job_id == completed.id
    assert schedule.last_sync_id is not None
    assert schedule.consecutive_failures == 0
    assert schedule.lease_token_hash is None
    assert schedule.next_run_at > observed_at
    sync = db_session.get(EvidenceTrustSourceSync, schedule.last_sync_id)
    assert sync is not None
    assert str(sync.trust_source_id) == source["id"]
    assert sync.trigger == "scheduled"
    assert sync.schedule_id == schedule.id
    assert sync.job_id == completed.id
    assert sync.attempt_number == 1

    schedules = client.get("/api/v1/trust-registry/source-schedules").json()
    assert schedules[0]["status"] == "scheduled"
    assert schedules[0]["last_job_status"] == "completed"
    overview = client.get("/api/v1/trust-registry/overview").json()
    assert overview["automatic_schedule_count"] == 1
    assert overview["automatic_schedule_enabled_count"] == 1


def test_transient_schedule_failure_retries_then_dead_letters_with_receipts(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    source, configured = _configure_source_and_schedule(
        client,
        monkeypatch,
        max_attempts=3,
    )

    def unavailable(*args: Any, **kwargs: Any) -> FetchedJwksPayload:
        raise TrustSourceFetchError("transport_error", "scheduled publisher unavailable")

    monkeypatch.setattr(trust_source_scheduler, "fetch_remote_jwks", unavailable)
    observed_at = dt.datetime.now(dt.UTC).replace(microsecond=0) + dt.timedelta(seconds=1)
    jobs = enqueue_due_trust_source_sync_jobs(
        db_session,
        scheduler_id="retry-scheduler",
        signer_identity=system_worker_identity("retry-scheduler"),
        lease_seconds=300,
        now=observed_at,
    )
    assert len(jobs) == 1
    job = jobs[0]

    for attempt in range(1, 4):
        job.available_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
        db_session.commit()
        claimed = claim_agent_job(
            db_session,
            worker_id=f"retry-executor-{attempt}",
            lease_seconds=300,
        )
        assert claimed is not None
        assert claimed.id == job.id
        assert claimed.lease_token is not None
        job = process_claimed_agent_job(
            db_session,
            job_id=claimed.id,
            lease_token=claimed.lease_token,
        )
        if attempt < 3:
            assert job.status == "queued"
            assert job.available_at > dt.datetime.now(dt.UTC)
        else:
            assert job.status == "failed"
            assert job.dead_lettered_at is not None

    schedule = db_session.get(EvidenceTrustSourceSchedule, configured["id"])
    assert schedule is not None
    assert schedule.consecutive_failures == 3
    assert schedule.lease_token_hash is None
    assert schedule.next_run_at > dt.datetime.now(dt.UTC)
    receipts = list(
        db_session.scalars(
            select(EvidenceTrustSourceSync)
            .where(EvidenceTrustSourceSync.trust_source_id == source["id"])
            .order_by(EvidenceTrustSourceSync.attempt_number)
        ).all()
    )
    assert [receipt.attempt_number for receipt in receipts] == [1, 2, 3]
    assert all(receipt.status == "failed" for receipt in receipts)
    assert all(receipt.trigger == "scheduled" for receipt in receipts)
    assert all(receipt.job_id == job.id for receipt in receipts)

    schedule_read = client.get("/api/v1/trust-registry/source-schedules").json()[0]
    assert schedule_read["status"] == "failed"
    metrics = client.get("/api/v1/operations/metrics").json()
    samples = {sample["name"]: sample["value"] for sample in metrics["samples"]}
    assert samples["model_atlas_trust_source_schedule_failed"] == 1
    assert any(
        alert["key"] == "trust_source_schedule_failed"
        for alert in metrics["alerts"]
    )
