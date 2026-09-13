from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.seed.adaptive_agent_operations import (
    seed_adaptive_agent_operations_pack,
)
from app.seed.demo import seed_demo_data


def _task_and_prompt(client: TestClient) -> tuple[dict, dict]:
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    task = next(item for item in tasks if item["name"] == "Korean document QA")
    prompt = next(item for item in prompts if item["benchmark_task_id"] == task["id"])
    return task, prompt


def _execute_pack(
    client: TestClient,
    seeded: dict,
    *,
    decisions: dict | None,
) -> dict:
    task, prompt = _task_and_prompt(client)
    payload = {
        "deployment_configuration_id": seeded["deployment_configuration_id"],
        "evaluation_suite_id": seeded["evaluation_suite_id"],
        "benchmark_task_id": task["id"],
        "prompt_version_id": prompt["id"],
        "adapter_name": "mock",
        "data_source": "local_authored",
        "max_cases": 10,
        "seed": 17,
        "agent_approval_decisions": decisions or {},
    }
    response = client.post("/api/v1/benchmark-executions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _approved_decisions() -> dict:
    return {
        "*": {
            "decision": "approved",
            "decided_by": "release-manager@example.local",
            "reason": "Sprint 5B deterministic CAB approval fixture.",
        }
    }


def test_adaptive_agent_pack_approves_recovery_and_checkpoint_evidence(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_adaptive_agent_operations_pack(db_session)

    execution = _execute_pack(
        client,
        seeded,
        decisions=_approved_decisions(),
    )
    summary = execution["agent_execution_summary"]
    assert summary["schema_version"] == "agent-execution-summary-v2"
    assert summary["agent_case_count"] == 5
    assert summary["successful_case_count"] == 5
    assert summary["total_step_count"] == 14
    assert summary["successful_step_count"] == 12
    assert summary["step_success_rate"] == 0.8571
    assert summary["replan_count"] == 2
    assert summary["replan_success_rate"] == 1.0
    assert summary["recovery_step_success_rate"] == 1.0
    assert summary["approval_checkpoint_count"] == 2
    assert summary["approval_compliance_rate"] == 1.0
    assert summary["approval_provenance_rate"] == 1.0
    assert summary["pending_approval_rate"] == 0.0
    assert summary["observation_coverage_rate"] == 1.0
    assert summary["unrecovered_failure_rate"] == 0.0

    run_id = execution["benchmark_run"]["id"]
    detail_response = client.get(f"/api/v1/benchmark-executions/{run_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    approval_trace = next(
        record
        for record in detail["agent_traces"]
        if record["sample_id"] == "agent-adaptive-001"
    )
    checkpoint = approval_trace["trace"]["steps"][0]
    assert checkpoint["status"] == "approved"
    assert checkpoint["approval_provenance_valid"] is True
    assert len(checkpoint["output"]["decision_hash"]) == 64
    assert "agent_approval_decisions" not in checkpoint["input"]

    recovery_trace = next(
        record
        for record in detail["agent_traces"]
        if record["sample_id"] == "agent-adaptive-003"
    )
    assert recovery_trace["trace"]["successful"] is True
    assert recovery_trace["trace"]["steps"][0]["successful"] is False
    assert recovery_trace["trace"]["steps"][0]["recovered_by_replan"] is True
    assert recovery_trace["trace"]["replans"][0]["status"] == "success"

    for record in (approval_trace, recovery_trace):
        replay_response = client.post(
            f"/api/v1/agents/replay/{record['benchmark_result_id']}"
        )
        assert replay_response.status_code == 200
        replay = replay_response.json()
        assert replay["version_compatible"] is True
        assert replay["deterministic_match"] is True
        assert replay["changed_paths"] == []

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
    assert all(rule["status"] == "pass" for rule in gate["rule_results"])
    metrics = gate["scorecard_json"]["metrics"]
    assert metrics["agent_replan_success_rate"]["value"] == 1.0
    assert metrics["agent_approval_compliance_rate"]["value"] == 1.0
    assert metrics["agent_pending_approval_rate"]["value"] == 0.0
    assert metrics["agent_observation_coverage_rate"]["value"] == 1.0
    assert metrics["agent_unrecovered_failure_rate"]["value"] == 0.0
    snapshot = gate["evidence_snapshot_json"]
    assert snapshot["schema_version"] == "gate-evidence-snapshot-v8"
    assert snapshot["agent_observation_versions"] == ["agent-observation-v1"]
    assert snapshot["agent_recovery_policy_versions"] == [
        "bounded-recovery-policy-v1"
    ]
    assert snapshot["agent_approval_policy_versions"] == [
        "human-checkpoint-policy-v1"
    ]


def test_pending_agent_approval_halts_execution_and_blocks_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_adaptive_agent_operations_pack(db_session)

    execution = _execute_pack(client, seeded, decisions=None)
    summary = execution["agent_execution_summary"]
    assert summary["successful_case_count"] == 3
    assert summary["failed_case_count"] == 2
    assert summary["pending_checkpoint_count"] == 2
    assert summary["pending_approval_rate"] == 1.0
    assert summary["approval_compliance_rate"] == 0.0

    detail = client.get(
        f"/api/v1/benchmark-executions/{execution['benchmark_run']['id']}"
    ).json()
    pending_traces = [
        record["trace"]
        for record in detail["agent_traces"]
        if record["trace"]["status"] == "pending_approval"
    ]
    assert len(pending_traces) == 2
    assert all(trace["step_count"] == 1 for trace in pending_traces)
    assert all(trace["halt_reason"] == "approval_pending" for trace in pending_traces)

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
    assert "agent_approval_compliance_rate" in failed_metrics
    assert "agent_approval_provenance_rate" in failed_metrics
    assert "agent_pending_approval_rate" in failed_metrics
    pending_outcome = next(
        outcome
        for outcome in gate["scorecard_json"]["critical_case_outcomes"]
        if outcome["external_case_id"] == "agent-adaptive-001"
    )
    assert pending_outcome["status"] == "fail"
    assert pending_outcome["agent_execution_status"] == "pending_approval"
    assert pending_outcome["agent_halt_reason"] == "approval_pending"
    assert pending_outcome["agent_pending_approval_count"] == 1


def test_agent_approval_request_requires_actor_and_reason(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_adaptive_agent_operations_pack(db_session)
    task, prompt = _task_and_prompt(client)

    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "agent_approval_decisions": {
                "*": {"decision": "approved", "decided_by": "", "reason": ""}
            },
        },
    )

    assert response.status_code == 422


def test_adaptive_agent_seed_is_idempotent(db_session: Session) -> None:
    seed_demo_data(db_session)
    first = seed_adaptive_agent_operations_pack(db_session)
    second = seed_adaptive_agent_operations_pack(db_session)

    assert first["created"] is True
    assert second["created"] is False
    assert second["deployment_configuration_id"] == first[
        "deployment_configuration_id"
    ]
    assert second["evaluation_suite_id"] == first["evaluation_suite_id"]
    assert second["acceptance_policy_id"] == first["acceptance_policy_id"]
    assert second["case_count"] == 5
