from __future__ import annotations

import datetime as dt
import gzip
import io
import json
from urllib.error import HTTPError

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes.agent_execution import settings as agent_route_settings
from app.collectors.agent_traffic_collector import (
    AgentTrafficCollector,
    CollectorConfig,
)
from app.models import (
    AgentTrafficReceipt,
    BenchmarkResult,
    BenchmarkRun,
    InferenceMetric,
)
from app.seed.adaptive_agent_operations import seed_adaptive_agent_operations_pack
from app.seed.demo import seed_demo_data
from app.services.agent_evidence_import import agent_trace_hash
from app.services.agent_jobs import run_agent_worker_once
from app.services.agent_traffic_ingestion import (
    AGENT_TRAFFIC_SIGNATURE_V2,
    traffic_batch_signature,
)


def _headers() -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": "production-evidence-importer",
        "x-model-atlas-operator-name": "Production Evidence Importer",
        "x-model-atlas-operator-role": "SRE Lead",
        "x-model-atlas-identity-provider": "pytest-identity",
    }


def _source_execution(client: TestClient, db_session: Session) -> tuple[dict, BenchmarkRun]:
    seed_demo_data(db_session)
    seeded = seed_adaptive_agent_operations_pack(db_session)
    task = next(
        item
        for item in client.get("/api/v1/benchmark-tasks").json()
        if item["name"] == "Korean document QA"
    )
    prompt = next(
        item
        for item in client.get("/api/v1/prompt-versions").json()
        if item["benchmark_task_id"] == task["id"]
    )
    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "agent_approval_decisions": {
                "*": {
                    "decision": "approved",
                    "decided_by": "legacy-test-approver",
                    "reason": "Create a complete source trace for import contract tests.",
                }
            },
        },
    )
    assert response.status_code == 201, response.text
    source_run = db_session.get(BenchmarkRun, response.json()["benchmark_run"]["id"])
    assert source_run is not None
    return response.json(), source_run


def test_production_agent_evidence_import_validates_identity_hash_and_duplicates(
    client: TestClient,
    db_session: Session,
) -> None:
    execution, source_run = _source_execution(client, db_session)
    detail = client.get(
        f"/api/v1/benchmark-executions/{execution['benchmark_run']['id']}"
    ).json()
    source_record = next(
        record
        for record in detail["agent_traces"]
        if record["sample_id"] == "agent-adaptive-003"
    )
    source_result = db_session.get(BenchmarkResult, source_record["benchmark_result_id"])
    assert source_result is not None
    source_metric = db_session.scalar(
        select(InferenceMetric)
        .where(InferenceMetric.benchmark_run_id == source_run.id)
        .where(InferenceMetric.sample_id == source_result.sample_id)
    )
    assert source_metric is not None
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    production_run = BenchmarkRun(
        hardware_profile_id=source_run.hardware_profile_id,
        model_artifact_id=source_run.model_artifact_id,
        benchmark_task_id=source_run.benchmark_task_id,
        prompt_version_id=source_run.prompt_version_id,
        deployment_configuration_id=source_run.deployment_configuration_id,
        evaluation_suite_id=source_run.evaluation_suite_id,
        runtime_name="captured-agent-runtime",
        runtime_version="captured-runtime-v1",
        runtime_config_json={
            "collector": "pytest-production-agent-collector",
            "agent_execution_schema_version": source_record["trace"]["schema_version"],
        },
        dataset_version=source_run.dataset_version,
        seed=None,
        started_at=now,
        completed_at=now,
        status="completed",
        data_source="production_captured",
    )
    db_session.add(production_run)
    db_session.commit()
    trace = source_record["trace"]
    payload = {
        "benchmark_run_id": str(production_run.id),
        "evaluation_case_id": str(source_result.evaluation_case_id),
        "sample_id": "prod-agent-event-003",
        "raw_output": source_result.raw_output,
        "normalized_output": source_result.normalized_output,
        "trace": trace,
        "metric": {
            "ttft_ms": source_metric.ttft_ms,
            "end_to_end_latency_ms": source_metric.end_to_end_latency_ms,
            "prompt_tokens": source_metric.prompt_tokens,
            "completion_tokens": source_metric.completion_tokens,
            "tokens_per_second": source_metric.tokens_per_second,
            "gpu_vram_used_mb": source_metric.gpu_vram_used_mb,
            "gpu_utilization_pct": source_metric.gpu_utilization_pct,
            "cpu_utilization_pct": source_metric.cpu_utilization_pct,
            "peak_memory_mb": source_metric.peak_memory_mb,
            "oom_occurred": source_metric.oom_occurred,
            "retry_count": source_metric.retry_count,
        },
        "provenance": {
            "source_system": "prod-agent-runner",
            "source_event_id": "prod-agent-event-003",
            "collector_version": "agent-collector-v1",
            "environment": "production",
            "captured_at": now.isoformat(),
            "source_trace_hash": agent_trace_hash(trace),
        },
        "human_label": "captured-needs-scoring",
    }

    unverified = client.post("/api/v1/agents/evidence/import", json=payload)
    assert unverified.status_code == 422
    assert "verified operator identity" in unverified.text

    tampered = {
        **payload,
        "provenance": {
            **payload["provenance"],
            "source_trace_hash": "0" * 64,
        },
    }
    tampered_response = client.post(
        "/api/v1/agents/evidence/import",
        headers=_headers(),
        json=tampered,
    )
    assert tampered_response.status_code == 422
    assert "does not match" in tampered_response.text

    imported_response = client.post(
        "/api/v1/agents/evidence/import",
        headers=_headers(),
        json=payload,
    )
    assert imported_response.status_code == 201, imported_response.text
    imported = imported_response.json()
    assert imported["import_contract_version"] == "production-agent-evidence-import-v1"
    assert imported["import_policy_version"] == "agent-evidence-import-rbac-v1"
    assert imported["data_source"] == "production_captured"
    assert imported["source_trace_hash"] == payload["provenance"]["source_trace_hash"]
    assert len(imported["evidence_hash"]) == 64
    stored = db_session.get(BenchmarkResult, imported["benchmark_result_id"])
    assert stored is not None
    assert stored.data_source == "production_captured"
    assert stored.metadata_json["agent_evidence_import"]["identity_verified"] is True

    duplicate = client.post(
        "/api/v1/agents/evidence/import",
        headers=_headers(),
        json=payload,
    )
    assert duplicate.status_code == 422
    assert "already exists" in duplicate.text or "already imported" in duplicate.text


def test_signed_traffic_batch_is_queued_and_imported_by_worker(
    client: TestClient,
    db_session: Session,
    monkeypatch: MonkeyPatch,
) -> None:
    execution, source_run = _source_execution(client, db_session)
    detail = client.get(
        f"/api/v1/benchmark-executions/{execution['benchmark_run']['id']}"
    ).json()
    source_record = next(
        record
        for record in detail["agent_traces"]
        if record["sample_id"] == "agent-adaptive-003"
    )
    source_result = db_session.get(BenchmarkResult, source_record["benchmark_result_id"])
    assert source_result is not None
    source_metric = db_session.scalar(
        select(InferenceMetric)
        .where(InferenceMetric.benchmark_run_id == source_run.id)
        .where(InferenceMetric.sample_id == source_result.sample_id)
    )
    assert source_metric is not None
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    production_run = BenchmarkRun(
        hardware_profile_id=source_run.hardware_profile_id,
        model_artifact_id=source_run.model_artifact_id,
        benchmark_task_id=source_run.benchmark_task_id,
        prompt_version_id=source_run.prompt_version_id,
        deployment_configuration_id=source_run.deployment_configuration_id,
        evaluation_suite_id=source_run.evaluation_suite_id,
        runtime_name="traffic-agent-runtime",
        runtime_version="traffic-runtime-v1",
        runtime_config_json={"collector": "signed-traffic-pytest"},
        dataset_version=source_run.dataset_version,
        started_at=now,
        completed_at=now,
        status="completed",
        data_source="production_captured",
    )
    db_session.add(production_run)
    db_session.commit()
    trace = source_record["trace"]
    event = {
        "benchmark_run_id": str(production_run.id),
        "evaluation_case_id": str(source_result.evaluation_case_id),
        "sample_id": "traffic-agent-event-001",
        "raw_output": source_result.raw_output,
        "normalized_output": source_result.normalized_output,
        "trace": trace,
        "metric": {
            "ttft_ms": source_metric.ttft_ms,
            "end_to_end_latency_ms": source_metric.end_to_end_latency_ms,
            "prompt_tokens": source_metric.prompt_tokens,
            "completion_tokens": source_metric.completion_tokens,
            "tokens_per_second": source_metric.tokens_per_second,
            "gpu_vram_used_mb": source_metric.gpu_vram_used_mb,
            "gpu_utilization_pct": source_metric.gpu_utilization_pct,
            "cpu_utilization_pct": source_metric.cpu_utilization_pct,
            "peak_memory_mb": source_metric.peak_memory_mb,
            "oom_occurred": source_metric.oom_occurred,
            "retry_count": source_metric.retry_count,
        },
        "provenance": {
            "source_system": "signed-agent-collector",
            "source_event_id": "traffic-agent-event-001",
            "collector_version": "traffic-collector-v1",
            "environment": "production",
            "captured_at": now.isoformat(),
            "source_trace_hash": agent_trace_hash(trace),
        },
        "human_label": "captured-needs-scoring",
    }
    batch = {
        "source_system": "signed-agent-collector",
        "batch_id": "traffic-batch-001",
        "collector_version": "traffic-collector-v1",
        "captured_at": now.isoformat(),
        "events": [event],
    }
    secret = "pytest-traffic-secret"
    monkeypatch.setattr(
        agent_route_settings,
        "agent_traffic_hmac_keys",
        {"signed-agent-collector": secret},
    )
    signature = traffic_batch_signature(batch, secret=secret)

    tampered = client.post(
        "/api/v1/agents/evidence/traffic-batches",
        headers={"X-Model-Atlas-Traffic-Signature": "0" * 64},
        json=batch,
    )
    assert tampered.status_code == 422
    queued_response = client.post(
        "/api/v1/agents/evidence/traffic-batches",
        headers={"X-Model-Atlas-Traffic-Signature": f"sha256={signature}"},
        json=batch,
    )
    assert queued_response.status_code == 202, queued_response.text
    assert queued_response.json()["status"] == "queued"

    completed = run_agent_worker_once(
        db_session,
        worker_id="traffic-import-worker",
    )
    assert completed is not None
    assert completed.status == "completed"
    assert completed.result_json is not None
    assert completed.result_json["imported_count"] == 1
    imported_result = db_session.get(
        BenchmarkResult,
        completed.result_json["benchmark_result_ids"][0],
    )
    assert imported_result is not None
    assert imported_result.data_source == "production_captured"

    atomic_event = {
        **event,
        "sample_id": "traffic-agent-event-atomic",
        "provenance": {
            **event["provenance"],
            "source_event_id": "traffic-agent-event-atomic",
        },
    }
    failing_batch = {
        **batch,
        "batch_id": "traffic-batch-atomic-rollback",
        "events": [atomic_event, atomic_event],
    }
    failing_signature = traffic_batch_signature(failing_batch, secret=secret)
    failing_response = client.post(
        "/api/v1/agents/evidence/traffic-batches",
        headers={"X-Model-Atlas-Traffic-Signature": failing_signature},
        json=failing_batch,
    )
    assert failing_response.status_code == 202, failing_response.text

    failed = run_agent_worker_once(
        db_session,
        worker_id="traffic-import-worker",
    )
    assert failed is not None
    assert failed.status == "failed"
    assert (
        db_session.scalars(
            select(BenchmarkResult).where(
                BenchmarkResult.sample_id == "traffic-agent-event-atomic"
            )
        ).all()
        == []
    )

    active_secret = "pytest-active-traffic-secret-with-32-bytes"
    retiring_secret = "pytest-retiring-traffic-secret-with-32-bytes"
    monkeypatch.setattr(
        agent_route_settings,
        "agent_traffic_hmac_keys",
        {
            "signed-agent-collector": secret,
            "signed-agent-collector:active-key": active_secret,
            "signed-agent-collector:retiring-key": retiring_secret,
        },
    )
    v2_event = {
        **event,
        "sample_id": "traffic-agent-event-v2",
        "provenance": {
            **event["provenance"],
            "source_event_id": "traffic-agent-event-v2",
        },
    }
    v2_batch = {
        **batch,
        "batch_id": "traffic-batch-v2",
        "events": [v2_event],
    }
    nonce = "pytest-traffic-nonce-00000001"
    sent_at = now.isoformat()
    v2_signature = traffic_batch_signature(
        v2_batch,
        secret=active_secret,
        signature_version=AGENT_TRAFFIC_SIGNATURE_V2,
        key_id="active-key",
        nonce=nonce,
        sent_at=sent_at,
    )
    encoded_batch = gzip.compress(
        json.dumps(v2_batch, separators=(",", ":")).encode("utf-8")
    )
    v2_headers = {
        "content-type": "application/json",
        "content-encoding": "gzip",
        "X-Model-Atlas-Traffic-Signature": v2_signature,
        "X-Model-Atlas-Traffic-Signature-Version": AGENT_TRAFFIC_SIGNATURE_V2,
        "X-Model-Atlas-Traffic-Key-Id": "active-key",
        "X-Model-Atlas-Traffic-Nonce": nonce,
        "X-Model-Atlas-Traffic-Sent-At": sent_at,
    }
    v2_response = client.post(
        "/api/v1/agents/evidence/traffic-batches",
        headers=v2_headers,
        content=encoded_batch,
    )
    assert v2_response.status_code == 202, v2_response.text
    replay = client.post(
        "/api/v1/agents/evidence/traffic-batches",
        headers=v2_headers,
        content=encoded_batch,
    )
    assert replay.status_code == 202
    assert replay.json()["id"] == v2_response.json()["id"]
    receipt = db_session.scalar(
        select(AgentTrafficReceipt).where(
            AgentTrafficReceipt.batch_id == "traffic-batch-v2"
        )
    )
    assert receipt is not None
    assert receipt.replay_count == 1
    assert receipt.key_id == "active-key"

    traffic_sources = client.get(
        "/api/v1/agents/evidence/traffic-sources"
    )
    assert traffic_sources.status_code == 200
    source_status = next(
        row
        for row in traffic_sources.json()
        if row["source_system"] == "signed-agent-collector"
    )
    assert source_status["health"] == "active"
    assert source_status["replay_count"] == 1
    assert source_status["configured_key_ids"] == [
        "active-key",
        "legacy",
        "retiring-key",
    ]

    conflicting_batch = {
        **v2_batch,
        "batch_id": "traffic-batch-v2-conflict",
    }
    conflicting_signature = traffic_batch_signature(
        conflicting_batch,
        secret=retiring_secret,
        signature_version=AGENT_TRAFFIC_SIGNATURE_V2,
        key_id="retiring-key",
        nonce=nonce,
        sent_at=sent_at,
    )
    conflict = client.post(
        "/api/v1/agents/evidence/traffic-batches",
        headers={
            **v2_headers,
            "X-Model-Atlas-Traffic-Signature": conflicting_signature,
            "X-Model-Atlas-Traffic-Key-Id": "retiring-key",
        },
        content=gzip.compress(
            json.dumps(conflicting_batch).encode("utf-8")
        ),
    )
    assert conflict.status_code == 422
    assert "conflicts" in conflict.text

    collector_attempts: list[object] = []

    class FakeCollectorResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self) -> bytes:
            return json.dumps({"id": "collector-job"}).encode("utf-8")

    def fake_collector_urlopen(request, timeout):
        collector_attempts.append(request)
        assert timeout == 3.0
        assert request.headers["Content-encoding"] == "gzip"
        assert gzip.decompress(request.data)
        if len(collector_attempts) == 1:
            raise HTTPError(
                request.full_url,
                503,
                "temporary",
                hdrs=None,
                fp=io.BytesIO(b'{"detail":"temporary"}'),
            )
        return FakeCollectorResponse()

    monkeypatch.setattr(
        "app.collectors.agent_traffic_collector.urlopen",
        fake_collector_urlopen,
    )
    monkeypatch.setattr(
        "app.collectors.agent_traffic_collector.time.sleep",
        lambda _: None,
    )
    collector = AgentTrafficCollector(
        CollectorConfig(
            endpoint="http://collector.pytest/traffic-batches",
            key_id="active-key",
            secret=active_secret,
            timeout_seconds=3,
            max_attempts=3,
        )
    )
    collector_result, attempt_count = collector.deliver_with_retry(
        v2_batch,
        nonce="pytest-collector-retry-nonce",
        sent_at=sent_at,
    )
    assert collector_result["id"] == "collector-job"
    assert attempt_count == 2
