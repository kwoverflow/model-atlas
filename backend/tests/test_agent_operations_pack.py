from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationCase
from app.seed.agent_operations import seed_agent_operations_pack
from app.seed.demo import seed_demo_data


def _task_and_prompt(client: TestClient) -> tuple[dict, dict]:
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    task = next(item for item in tasks if item["name"] == "Korean document QA")
    prompt = next(item for item in prompts if item["benchmark_task_id"] == task["id"])
    return task, prompt


def _execute_pack(client: TestClient, seeded: dict) -> dict:
    task, prompt = _task_and_prompt(client)
    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 10,
            "seed": 13,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_agent_pack_executes_and_passes_policy(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_agent_operations_pack(db_session)

    execution = _execute_pack(client, seeded)
    summary = execution["agent_execution_summary"]
    assert summary["agent_case_count"] == 8
    assert summary["successful_case_count"] == 8
    assert summary["failed_case_count"] == 0
    assert summary["total_step_count"] == 24
    assert summary["task_success_rate"] == 1.0
    assert summary["plan_validity_rate"] == 1.0
    assert summary["step_success_rate"] == 1.0
    assert summary["action_sequence_accuracy"] == 1.0
    assert summary["policy_violation_rate"] == 0.0
    assert summary["final_response_rate"] == 1.0
    assert summary["memory_provenance_rate"] == 1.0
    assert summary["tool_retry_recovery_rate"] == 1.0

    run_id = execution["benchmark_run"]["id"]
    detail_response = client.get(f"/api/v1/benchmark-executions/{run_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["agent_execution_summary"] == summary
    assert len(detail["agent_traces"]) == 8
    recovery_trace = next(
        trace
        for trace in detail["agent_traces"]
        if trace["sample_id"] == "agent-ops-005"
    )
    assert recovery_trace["trace"]["recovered_tool_count"] == 1
    assert recovery_trace["trace"]["steps"][0]["recovered"] is True
    memory_write_trace = next(
        trace
        for trace in detail["agent_traces"]
        if trace["sample_id"] == "agent-ops-006"
    )
    memory_output = memory_write_trace["trace"]["steps"][0]["output"]
    assert memory_output["scope"] == "task_local_simulated"
    assert memory_output["persisted"] is False

    replay_response = client.post(
        f"/api/v1/agents/replay/{detail['agent_traces'][0]['benchmark_result_id']}"
    )
    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["version_compatible"] is True
    assert replay["deterministic_match"] is True
    assert replay["original_signature"] == replay["replay_signature"]
    assert replay["changed_paths"] == []

    runtime_response = client.get("/api/v1/agents/runtime")
    assert runtime_response.status_code == 200
    assert runtime_response.json()["runtime_version"] == "bounded-agent-runtime-v2"
    memory_response = client.get("/api/v1/agents/memory-registry")
    assert memory_response.status_code == 200
    memory_registry = memory_response.json()
    assert memory_registry["registry_version"] == "operational-memory-registry-v1"
    assert memory_registry["record_count"] == 4
    assert all(record["content_hash"] for record in memory_registry["records"])

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "APPROVED"
    assert len(gate["rule_results"]) == 8
    assert all(rule["status"] == "pass" for rule in gate["rule_results"])
    metrics = gate["scorecard_json"]["metrics"]
    assert metrics["agent_task_success_rate"]["value"] == 1.0
    assert metrics["agent_policy_violation_rate"]["value"] == 0.0
    assert metrics["agent_memory_provenance_rate"]["value"] == 1.0
    snapshot = gate["evidence_snapshot_json"]
    assert snapshot["schema_version"] == "gate-evidence-snapshot-v8"
    assert snapshot["agent_runtime_versions"] == ["bounded-agent-runtime-v2"]
    assert snapshot["agent_execution_versions"] == ["agent-execution-trace-v2"]
    assert snapshot["operational_memory_registry_versions"] == [
        "operational-memory-registry-v1"
    ]


def test_agent_policy_violation_blocks_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_agent_operations_pack(db_session)
    critical_case = db_session.scalar(
        select(EvaluationCase).where(EvaluationCase.external_case_id == "agent-ops-001")
    )
    assert critical_case is not None
    plan = dict(critical_case.input_payload_json["mock_agent_plan"])
    steps = [dict(step) for step in plan["steps"]]
    steps[0] = {
        "action": "memory_write",
        "key": "forbidden",
        "value": "persistent mutation",
    }
    critical_case.input_payload_json = {
        **critical_case.input_payload_json,
        "mock_agent_plan": {"steps": steps},
    }
    db_session.commit()

    execution = _execute_pack(client, seeded)
    summary = execution["agent_execution_summary"]
    assert summary["successful_case_count"] == 7
    assert summary["failed_case_count"] == 1
    assert summary["plan_validity_rate"] < 1.0
    assert summary["policy_violation_rate"] > 0.0

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "BLOCKED"
    failed_metrics = {
        rule["metric_key"]
        for rule in gate["scorecard_json"]["rule_results"]
        if rule["status"] == "fail"
    }
    assert "agent_task_success_rate" in failed_metrics
    assert "agent_plan_validity_rate" in failed_metrics
    assert "agent_policy_violation_rate" in failed_metrics
    critical_outcome = next(
        outcome
        for outcome in gate["scorecard_json"]["critical_case_outcomes"]
        if outcome["external_case_id"] == "agent-ops-001"
    )
    assert critical_outcome["status"] == "fail"
    assert critical_outcome["agent_execution_status"] == "failed"


def test_agent_seed_is_idempotent(db_session: Session) -> None:
    seed_demo_data(db_session)
    first = seed_agent_operations_pack(db_session)
    second = seed_agent_operations_pack(db_session)

    assert first["created"] is True
    assert second["created"] is False
    assert second["deployment_configuration_id"] == first["deployment_configuration_id"]
    assert second["evaluation_suite_id"] == first["evaluation_suite_id"]
    assert second["acceptance_policy_id"] == first["acceptance_policy_id"]
    assert second["case_count"] == 8
