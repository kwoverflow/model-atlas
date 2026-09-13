from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationCase
from app.seed.demo import seed_demo_data
from app.seed.runtime_reliability import seed_runtime_reliability_pack


def _task_and_prompt(client: TestClient) -> tuple[dict, dict]:
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    task = next(item for item in tasks if item["name"] == "Korean document QA")
    prompt = next(item for item in prompts if item["benchmark_task_id"] == task["id"])
    return task, prompt


def _execute_pack(client: TestClient, seeded: dict, configuration_index: int = 0) -> dict:
    task, prompt = _task_and_prompt(client)
    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_ids"][
                configuration_index
            ],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 10,
            "seed": 11,
            "reliability_mode": True,
            "trials_per_case": 5,
            "concurrency": 4,
            "case_timeout_ms": 2_000,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_runtime_reliability_pack_runs_and_passes_policy(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_runtime_reliability_pack(db_session)

    execution = _execute_pack(client, seeded)
    summary = execution["runtime_reliability_summary"]
    assert summary["reliability_case_count"] == 6
    assert summary["trial_count"] == 30
    assert summary["expected_trial_count"] == 30
    assert summary["success_rate"] == 1.0
    assert summary["timeout_rate"] == 0.0
    assert summary["oom_rate"] == 0.0
    assert summary["trial_coverage_rate"] == 1.0
    assert summary["context_stress_trial_count"] == 10
    assert summary["context_stress_success_rate"] == 1.0
    assert summary["p99_end_to_end_latency_ms"] < 2_000
    assert summary["latency_variation_coefficient"] < 0.1

    run_id = execution["benchmark_run"]["id"]
    detail = client.get(f"/api/v1/benchmark-executions/{run_id}").json()
    assert detail["runtime_reliability_summary"] == summary
    assert len(detail["reliability_traces"]) == 30
    assert all(
        trace["trace"]["benchmark_run_id"] == run_id
        for trace in detail["reliability_traces"]
    )

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_ids"][0],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "APPROVED"
    assert len(gate["rule_results"]) == 7
    assert all(rule["status"] == "pass" for rule in gate["rule_results"])
    metrics = gate["scorecard_json"]["metrics"]
    assert metrics["reliability_success_rate"]["value"] == 1.0
    assert metrics["reliability_timeout_rate"]["value"] == 0.0
    assert metrics["reliability_oom_rate"]["value"] == 0.0
    assert metrics["trial_coverage_rate"]["value"] == 1.0
    assert gate["evidence_snapshot_json"]["runtime_reliability_versions"] == [
        "runtime-reliability-trace-v1"
    ]


def test_timeout_and_oom_trials_block_runtime_reliability_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_runtime_reliability_pack(db_session)
    critical_case = db_session.scalar(
        select(EvaluationCase).where(EvaluationCase.external_case_id == "runtime-rel-001")
    )
    assert critical_case is not None
    profile = dict(critical_case.input_payload_json["reliability"])
    critical_case.input_payload_json = {
        **critical_case.input_payload_json,
        "reliability": {
            **profile,
            "timeout_trials": [2],
            "oom_trials": [3],
        },
    }
    db_session.commit()

    execution = _execute_pack(client, seeded)
    summary = execution["runtime_reliability_summary"]
    assert summary["success_count"] == 28
    assert summary["timeout_count"] == 1
    assert summary["oom_count"] == 1

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_ids"][0],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "BLOCKED"
    failed_rules = {
        rule["metric_key"]
        for rule in gate["scorecard_json"]["rule_results"]
        if rule["status"] == "fail"
    }
    assert "reliability_success_rate" in failed_rules
    assert "reliability_timeout_rate" in failed_rules
    assert "reliability_oom_rate" in failed_rules
    failed_trials = [
        outcome
        for outcome in gate["scorecard_json"]["critical_case_outcomes"]
        if outcome["external_case_id"] == "runtime-rel-001"
        and outcome["status"] == "fail"
    ]
    assert {outcome["runtime_reliability_status"] for outcome in failed_trials} == {
        "timeout",
        "oom",
    }


def test_runtime_reliability_seed_is_idempotent(db_session: Session) -> None:
    seed_demo_data(db_session)
    first = seed_runtime_reliability_pack(db_session)
    second = seed_runtime_reliability_pack(db_session)

    assert first["created"] is True
    assert second["created"] is False
    assert second["evaluation_suite_id"] == first["evaluation_suite_id"]
    assert second["acceptance_policy_id"] == first["acceptance_policy_id"]
    assert set(second["deployment_configuration_ids"]) == set(
        first["deployment_configuration_ids"]
    )
    assert second["case_count"] == 6


def test_runtime_reliability_comparison_prefers_faster_equal_success_run(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_runtime_reliability_pack(db_session)
    left = _execute_pack(client, seeded, configuration_index=0)
    right = _execute_pack(client, seeded, configuration_index=1)

    response = client.get(
        "/api/v1/runtime-reliability/compare",
        params={
            "left_run_id": left["benchmark_run"]["id"],
            "right_run_id": right["benchmark_run"]["id"],
        },
    )

    assert response.status_code == 200
    comparison = response.json()
    assert comparison["schema_version"] == "runtime-reliability-comparison-v1"
    assert comparison["winner"] == "left"
    assert comparison["recommended_benchmark_run_id"] == left["benchmark_run"]["id"]
    assert comparison["reason"] == "lower P99 latency"
    assert comparison["left"]["summary"]["success_rate"] == 1.0
    assert comparison["right"]["summary"]["success_rate"] == 1.0
    assert comparison["right_minus_left"]["p99_end_to_end_latency_ms"] > 0
