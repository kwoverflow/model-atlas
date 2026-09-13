from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationCase
from app.seed.demo import seed_demo_data
from app.services import benchmark_execution
from app.services.inference_adapters.mock import MockInferenceAdapter


def _seeded_execution_ids(client: TestClient) -> dict[str, str]:
    configurations = client.get("/api/v1/deployment-configurations").json()
    suites = client.get("/api/v1/evaluation-suites").json()
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    task = next(item for item in tasks if item["name"] == "Korean document QA")
    prompt = next(item for item in prompts if item["benchmark_task_id"] == task["id"])
    return {
        "deployment_configuration_id": configurations[0]["id"],
        "evaluation_suite_id": suites[0]["id"],
        "benchmark_task_id": task["id"],
        "prompt_version_id": prompt["id"],
    }


def test_mock_runtime_health(client: TestClient, db_session: Session) -> None:
    seed_demo_data(db_session)
    ids = _seeded_execution_ids(client)

    response = client.get(
        "/api/v1/benchmark-executions/runtime-health"
        f"?deployment_configuration_id={ids['deployment_configuration_id']}"
        "&adapter_name=mock"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_name"] == "mock"
    assert payload["healthy"] is True
    assert "configuration_hash" in payload["details"]


def test_openai_compatible_runtime_health_reports_unavailable(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    ids = _seeded_execution_ids(client)

    response = client.get(
        "/api/v1/benchmark-executions/runtime-health"
        f"?deployment_configuration_id={ids['deployment_configuration_id']}"
        "&adapter_name=openai_compatible"
        "&base_url=http://127.0.0.1:1"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_name"] == "openai_compatible"
    assert payload["healthy"] is False
    assert payload["details"]["attempted_base_urls"] == ["http://127.0.0.1:1"]


def test_mock_benchmark_execution_creates_gate_ready_evidence(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    ids = _seeded_execution_ids(client)

    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            **ids,
            "adapter_name": "mock",
            "adapter_config_json": {"ignored_by_mock": True},
            "data_source": "captured_demo",
            "max_cases": 3,
            "seed": 42,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    run = payload["benchmark_run"]
    assert run["status"] == "completed"
    assert run["deployment_configuration_id"] == ids["deployment_configuration_id"]
    assert run["evaluation_suite_id"] == ids["evaluation_suite_id"]
    assert run["data_source"] == "captured_demo"
    assert payload["result_count"] == 3
    assert payload["metric_count"] == 3
    assert payload["log_count"] == 5

    results = client.get("/api/v1/benchmark-results?limit=200").json()
    captured_results = [item for item in results if item["benchmark_run_id"] == run["id"]]
    assert len(captured_results) == 3
    assert all(item["evaluation_case_id"] for item in captured_results)
    assert all(item["raw_output"] for item in captured_results)

    metrics = client.get(f"/api/v1/inference-metrics?benchmark_run_id={run['id']}").json()
    assert len(metrics) == 3
    assert all(item["end_to_end_latency_ms"] >= 0 for item in metrics)

    logs = client.get(f"/api/v1/benchmark-executions/{run['id']}/logs").json()
    assert len(logs) == 5
    assert logs[0]["event_type"] == "run_started"
    assert logs[-1]["event_type"] == "run_completed"

    lineage = client.get(
        "/api/v1/experiment-lineage/events"
        "?sync_missing=false&event_type=benchmark_run_completed"
    ).json()
    assert any(event["benchmark_run_id"] == run["id"] for event in lineage)


def test_reliability_execution_repeats_trials_and_captures_failures(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    ids = _seeded_execution_ids(client)
    evaluation_case = db_session.scalar(
        select(EvaluationCase)
        .where(EvaluationCase.evaluation_suite_id == ids["evaluation_suite_id"])
        .order_by(EvaluationCase.external_case_id)
    )
    assert evaluation_case is not None
    evaluation_case.input_payload_json = {
        **evaluation_case.input_payload_json,
        "reliability": {
            "base_latency_ms": 700,
            "latency_jitter_ms": [0, 50, 100],
            "context_tokens": 3_800,
            "context_stress": True,
            "timeout_trials": [2],
            "oom_trials": [3],
        },
    }
    db_session.commit()

    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            **ids,
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 1,
            "seed": 42,
            "reliability_mode": True,
            "trials_per_case": 3,
            "concurrency": 3,
            "case_timeout_ms": 1_000,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    summary = payload["runtime_reliability_summary"]
    assert payload["result_count"] == 3
    assert payload["metric_count"] == 3
    assert summary["trial_count"] == 3
    assert summary["success_count"] == 1
    assert summary["timeout_count"] == 1
    assert summary["oom_count"] == 1
    assert summary["trial_coverage_rate"] == 1.0
    assert summary["context_stress_success_rate"] == 0.3333

    run_id = payload["benchmark_run"]["id"]
    detail = client.get(f"/api/v1/benchmark-executions/{run_id}").json()
    assert detail["runtime_reliability_summary"] == summary
    assert [trace["trace"]["status"] for trace in detail["reliability_traces"]] == [
        "success",
        "timeout",
        "oom",
    ]
    assert [trace["sample_id"] for trace in detail["reliability_traces"]] == [
        f"{evaluation_case.external_case_id}::trial-01",
        f"{evaluation_case.external_case_id}::trial-02",
        f"{evaluation_case.external_case_id}::trial-03",
    ]


def test_reliability_mode_persists_adapter_exceptions_per_trial(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_demo_data(db_session)
    ids = _seeded_execution_ids(client)
    adapter = MockInferenceAdapter()
    original_run_case = adapter.run_case

    def run_case(
        *,
        configuration: Any,
        evaluation_case: Any,
        seed: int | None = None,
    ) -> Any:
        trial_index = evaluation_case.input_payload_json["_execution_trial"]
        if trial_index == 2:
            raise TimeoutError("adapter timed out")
        if trial_index == 3:
            raise MemoryError("out of memory")
        return original_run_case(
            configuration=configuration,
            evaluation_case=evaluation_case,
            seed=seed,
        )

    monkeypatch.setattr(adapter, "run_case", run_case)
    monkeypatch.setattr(
        benchmark_execution,
        "get_inference_adapter",
        lambda _adapter_name: adapter,
    )

    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            **ids,
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 1,
            "reliability_mode": True,
            "trials_per_case": 3,
            "concurrency": 2,
            "case_timeout_ms": 1_000,
        },
    )

    assert response.status_code == 201
    summary = response.json()["runtime_reliability_summary"]
    assert summary["success_count"] == 1
    assert summary["timeout_count"] == 1
    assert summary["oom_count"] == 1


def test_mock_execution_exposes_executable_tool_traces(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    ids = _seeded_execution_ids(client)

    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            **ids,
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 50,
            "seed": 7,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    summary = payload["tool_execution_summary"]
    assert summary["tool_case_count"] > 0
    assert summary["call_count"] == summary["successful_call_count"]
    assert summary["selection_accuracy"] == 1.0
    assert summary["argument_validity_rate"] == 1.0
    assert summary["execution_success_rate"] == 1.0

    run_id = payload["benchmark_run"]["id"]
    detail_response = client.get(f"/api/v1/benchmark-executions/{run_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["tool_execution_summary"] == summary
    assert len(detail["tool_traces"]) == summary["tool_case_count"]
    first_trace = detail["tool_traces"][0]["trace"]
    assert first_trace["schema_version"] == "tool-execution-trace-v1"
    assert first_trace["registry_version"] == "local-tool-registry-v1"
    assert first_trace["steps"][0]["output"]["status"] == "ok"

    registry_response = client.get("/api/v1/benchmark-executions/tool-registry")
    assert registry_response.status_code == 200
    registry = registry_response.json()
    assert registry["registry_version"] == "local-tool-registry-v1"
    assert registry["tool_count"] >= 6
    assert any(
        tool["tool_id"] == "create_ticket" and tool["side_effect_mode"] == "simulated"
        for tool in registry["tools"]
    )

    policies = client.get("/api/v1/acceptance-policies").json()
    demo_policy = next(policy for policy in policies if policy["name"] == "Demo Policy")
    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": ids["deployment_configuration_id"],
            "evaluation_suite_id": ids["evaluation_suite_id"],
            "acceptance_policy_id": demo_policy["id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    metrics = gate["scorecard_json"]["metrics"]
    assert metrics["tool_selection_accuracy"]["value"] == 1.0
    assert metrics["tool_argument_validity_rate"]["value"] == 1.0
    assert metrics["tool_execution_success_rate"]["value"] == 1.0
    assert metrics["tool_sequence_success_rate"]["value"] == 1.0
    snapshot = gate["evidence_snapshot_json"]
    assert snapshot["schema_version"] == "gate-evidence-snapshot-v8"
    assert snapshot["tool_registry_versions"] == ["local-tool-registry-v1"]
    assert snapshot["tool_execution_versions"] == ["tool-execution-trace-v1"]
