from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationCase
from app.seed.demo import seed_demo_data
from app.seed.tool_calling import seed_tool_calling_pack


def test_executable_tool_calling_pack_runs_and_passes_its_policy(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_tool_calling_pack(db_session)

    configurations = client.get("/api/v1/deployment-configurations").json()
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    tool_task = next(task for task in tasks if task["name"] == "Tool calling")
    prompt = next(
        prompt for prompt in prompts if prompt["benchmark_task_id"] == tool_task["id"]
    )
    execution_response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": configurations[0]["id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": tool_task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 20,
            "seed": 4,
            "isolation_policy_id": "tool-offline-strict",
        },
    )

    assert execution_response.status_code == 201
    execution = execution_response.json()
    isolation = execution["benchmark_run"]["runtime_config_json"][
        "isolation_preflights"
    ]
    assert len(isolation) == 1
    assert isolation[0]["allowed"] is True
    assert isolation[0]["policy"]["policy_id"] == "tool-offline-strict"
    summary = execution["tool_execution_summary"]
    assert summary["tool_case_count"] == 10
    assert summary["call_count"] == 12
    assert summary["successful_call_count"] == 12
    assert summary["retried_call_count"] == 1
    assert summary["recovered_call_count"] == 1
    assert summary["multi_step_case_count"] == 1
    assert summary["selection_accuracy"] == 1.0
    assert summary["argument_validity_rate"] == 1.0
    assert summary["execution_success_rate"] == 1.0
    assert summary["sequence_success_rate"] == 1.0
    assert summary["retry_recovery_rate"] == 1.0

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": configurations[0]["id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )

    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "APPROVED"
    rule_results = gate["rule_results"]
    assert len(rule_results) == 5
    assert all(rule["status"] == "pass" for rule in rule_results)
    metrics = gate["scorecard_json"]["metrics"]
    assert metrics["tool_retry_recovery_rate"]["value"] == 1.0
    assert metrics["tool_retry_recovery_rate"]["sample_size"] == 1


def test_tool_calling_pack_seed_is_idempotent(db_session: Session) -> None:
    seed_demo_data(db_session)
    first = seed_tool_calling_pack(db_session)
    second = seed_tool_calling_pack(db_session)

    assert first["created"] is True
    assert second["created"] is False
    assert second["evaluation_suite_id"] == first["evaluation_suite_id"]
    assert second["acceptance_policy_id"] == first["acceptance_policy_id"]
    assert second["case_count"] == 10


def test_invalid_critical_tool_selection_is_skipped_and_blocks_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_tool_calling_pack(db_session)
    critical_case = db_session.scalar(
        select(EvaluationCase).where(EvaluationCase.external_case_id == "tool-exec-001")
    )
    assert critical_case is not None
    critical_case.input_payload_json = {
        **critical_case.input_payload_json,
        "mock_tool_calls": [
            {"tool_name": "create_ticket", "arguments": {"query": "wrong tool"}}
        ],
    }
    db_session.commit()

    configurations = client.get("/api/v1/deployment-configurations").json()
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    tool_task = next(task for task in tasks if task["name"] == "Tool calling")
    prompt = next(
        prompt for prompt in prompts if prompt["benchmark_task_id"] == tool_task["id"]
    )
    execution_response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": configurations[0]["id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": tool_task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 20,
        },
    )
    assert execution_response.status_code == 201
    summary = execution_response.json()["tool_execution_summary"]
    assert summary["failed_call_count"] == 1
    assert summary["invalid_call_case_count"] == 1

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": configurations[0]["id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "BLOCKED"
    assert gate["scorecard_json"]["metrics"]["tool_selection_accuracy"]["value"] < 1
    critical_outcome = next(
        outcome
        for outcome in gate["scorecard_json"]["critical_case_outcomes"]
        if outcome["external_case_id"] == "tool-exec-001"
    )
    assert critical_outcome["status"] == "fail"
    assert critical_outcome["tool_execution_status"] == "failed"
