from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.agent_jobs import enqueue_checkpoint_reconciliation_job
from app.services.operator_identity import SignerIdentity


def test_operational_metrics_export_queue_alerts_and_prometheus(
    client: TestClient,
    db_session: Session,
) -> None:
    enqueue_checkpoint_reconciliation_job(
        db_session,
        schedule_key="metrics-test-queue",
        signer_identity=SignerIdentity(
            subject_id="metrics-test",
            display_name="Metrics Test",
            role="System Worker",
            identity_provider="pytest",
            auth_source="pytest",
            identity_verified=True,
            ticket_reference=None,
        ),
    )

    response = client.get("/api/v1/operations/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "model-atlas-operational-metrics-v1"
    assert body["health"] == "critical"
    samples = {sample["name"]: sample["value"] for sample in body["samples"]}
    assert samples["model_atlas_job_queue_depth"] == 1
    assert samples["model_atlas_worker_online"] == 0
    assert samples["model_atlas_supply_chain_attestation_verified"] == 0
    assert samples["model_atlas_production_run_unverified"] == 0
    assert samples["model_atlas_trust_root_active"] == 0
    assert samples["model_atlas_trust_source_registered"] == 0
    assert samples["model_atlas_trust_source_stale"] == 0
    assert samples["model_atlas_transparency_proof_pending"] == 0
    assert samples["model_atlas_browser_session_active"] == 0
    assert samples["model_atlas_browser_session_revoked"] == 0
    assert samples["model_atlas_oidc_shared_cache_fresh"] == 0
    assert samples["model_atlas_oidc_shared_cache_stale"] == 0
    assert any(alert["key"] == "worker_queue_blocked" for alert in body["alerts"])
    assert any(
        alert["route"] == "model-atlas-critical" for alert in body["alerts"]
    )

    alerts = client.get("/api/v1/operations/alerts")
    assert alerts.status_code == 200
    assert alerts.json() == body["alerts"]

    prometheus = client.get("/metrics")
    assert prometheus.status_code == 200
    assert "text/plain" in prometheus.headers["content-type"]
    assert "# TYPE model_atlas_job_queue_depth gauge" in prometheus.text
    assert "model_atlas_job_queue_depth 1" in prometheus.text
    assert 'alert_key="worker_queue_blocked"' in prometheus.text
