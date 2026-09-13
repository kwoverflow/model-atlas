from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.agent_jobs import (
    claim_agent_job,
    enqueue_checkpoint_reconciliation_job,
    enqueue_traffic_evidence_job,
    get_agent_job_overview,
    heartbeat_agent_job,
    heartbeat_agent_worker,
    process_claimed_agent_job,
    register_agent_worker,
    system_worker_identity,
)


def test_expired_job_lease_is_reclaimed_and_reconciliation_completes(
    db_session: Session,
) -> None:
    queued = enqueue_checkpoint_reconciliation_job(
        db_session,
        schedule_key="pytest-reconciliation-window",
        signer_identity=system_worker_identity("scheduler-worker"),
    )
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    first_claim = claim_agent_job(
        db_session,
        worker_id="worker-one",
        lease_seconds=5,
        now=now,
    )
    assert first_claim is not None
    assert first_claim.id == queued.id
    assert first_claim.status == "leased"
    assert first_claim.attempt_count == 1

    first_claim.lease_expires_at = now - dt.timedelta(seconds=1)
    db_session.commit()
    second_claim = claim_agent_job(
        db_session,
        worker_id="worker-two",
        lease_seconds=30,
        now=now + dt.timedelta(seconds=1),
    )
    assert second_claim is not None
    assert second_claim.id == queued.id
    assert second_claim.lease_owner == "worker-two"
    assert second_claim.attempt_count == 2
    assert second_claim.lease_token is not None

    completed = process_claimed_agent_job(
        db_session,
        job_id=second_claim.id,
        lease_token=second_claim.lease_token,
    )
    assert completed.status == "completed"
    assert completed.result_json is not None
    assert completed.result_json["checkpoint_reconciliation"]["expired_count"] == 0
    assert completed.result_json["gate_staleness"]["stale_count"] == 0


def test_worker_heartbeat_dead_letter_requeue_and_overview(
    db_session: Session,
    client: TestClient,
) -> None:
    worker_id = "pytest-operations-worker"
    register_agent_worker(
        db_session,
        worker_id=worker_id,
        metadata_json={"hostname": "pytest"},
    )
    queued = enqueue_traffic_evidence_job(
        db_session,
        source_system="pytest-collector",
        batch_id="dead-letter-batch",
        payload_json={"schema_version": "unsupported"},
        signer_identity=system_worker_identity(worker_id),
    )
    claimed = claim_agent_job(
        db_session,
        worker_id=worker_id,
        lease_seconds=30,
    )
    assert claimed is not None
    assert claimed.id == queued.id
    assert claimed.heartbeat_count == 1
    assert claimed.lease_token is not None
    heartbeat_agent_worker(
        db_session,
        worker_id=worker_id,
        current_job_id=claimed.id,
    )
    heartbeat = heartbeat_agent_job(
        db_session,
        job_id=claimed.id,
        lease_token=claimed.lease_token,
        lease_seconds=60,
    )
    assert heartbeat.heartbeat_count == 2
    assert heartbeat.last_heartbeat_at is not None

    failed = process_claimed_agent_job(
        db_session,
        job_id=claimed.id,
        lease_token=claimed.lease_token,
    )
    assert failed.status == "failed"
    assert failed.dead_lettered_at is not None
    assert "not supported" in (failed.dead_letter_reason or "")

    overview = get_agent_job_overview(
        db_session,
        worker_offline_seconds=90,
    )
    assert overview["health"] == "degraded"
    assert overview["dead_letter_count"] == 1
    assert overview["workers"][0]["status"] == "online"

    api_overview = client.get("/api/v1/agents/jobs/overview")
    assert api_overview.status_code == 200
    assert api_overview.json()["dead_letter_count"] == 1
    requeue_response = client.post(
        f"/api/v1/agents/jobs/{failed.id}/requeue",
        headers={
            "x-model-atlas-operator-id": "maintenance-worker",
            "x-model-atlas-operator-name": "Maintenance Worker",
            "x-model-atlas-operator-role": "SRE Lead",
            "x-model-atlas-identity-provider": "pytest",
        },
        json={
            "reason": "Operator approved one controlled retry.",
            "max_attempts": 4,
        },
    )
    assert requeue_response.status_code == 200, requeue_response.text
    requeued = requeue_response.json()
    assert requeued["status"] == "queued"
    assert requeued["requeue_count"] == 1
    assert requeued["attempt_count"] == 0
    assert requeued["max_attempts"] == 4
    assert requeued["last_requeued_by_identity_json"]["reason"].startswith(
        "Operator approved"
    )

    queued_overview = get_agent_job_overview(
        db_session,
        worker_offline_seconds=90,
    )
    assert queued_overview["queue_depth"] == 1
    assert queued_overview["retrying_count"] == 1
