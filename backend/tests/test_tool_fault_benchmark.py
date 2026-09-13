from uuid import UUID

import pytest

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
)
from app.seed.demo import seed_demo_data
from app.services.deployment_gate.evidence import collect_evidence, deployment_configuration_hash
from app.services.tool_fault_scenarios import TOOL_FAULT_DATA_SOURCE, ToolFaultScenario


def setup_execution(client, db_session, mode="transient_once", legacy=False):
    seed_demo_data(db_session)
    original = client.get("/api/v1/deployment-configurations").json()[0]
    configuration = {
        key: value
        for key, value in original.items()
        if key not in {"id", "created_at", "updated_at", "configuration_hash"}
    }
    configuration["name"] = f"Isolated fault test {mode}"
    configuration["runtime_config_json"] = {
        **configuration.get("runtime_config_json", {}),
        "tool_fault_scenario": ToolFaultScenario(mode).to_dict(),
    }
    response = client.post("/api/v1/deployment-configurations", json=configuration)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["configuration_hash"] != original["configuration_hash"]
    assert created["configuration_hash"] == deployment_configuration_hash(configuration)
    suite = client.get("/api/v1/evaluation-suites").json()[0]
    task = next(
        t for t in client.get("/api/v1/benchmark-tasks").json() if t["name"] == "Korean document QA"
    )
    prompt = next(
        p
        for p in client.get("/api/v1/prompt-versions").json()
        if p["benchmark_task_id"] == task["id"]
    )
    schema = {"tool_name": "lookup_policy", "required_arguments": ["query"]}
    if legacy:
        schema["required_arguments"].append("simulate_failure")
    db_session.add(
        EvaluationCase(
            evaluation_suite_id=UUID(suite["id"]),
            external_case_id="FAULT-CONTRACT-001",
            category="tool_single_step",
            title="Fault contract fixture",
            input_payload_json={"query": "policy"},
            expected_output_json=None,
            reference_context_json=None,
            expected_tool_schema_json=schema,
            tags_json=["fault-fixture"],
            criticality="critical",
            weight=1.0,
            is_active=True,
            data_source="local_authored",
        )
    )
    db_session.commit()
    return {
        "deployment_configuration_id": created["id"],
        "evaluation_suite_id": suite["id"],
        "benchmark_task_id": task["id"],
        "prompt_version_id": prompt["id"],
        "adapter_name": "mock",
        "data_source": TOOL_FAULT_DATA_SOURCE,
        "evaluation_case_external_ids": ["FAULT-CONTRACT-001"],
        "seed": 42,
    }, original


@pytest.mark.parametrize(
    "mode,success", [("normal", True), ("transient_once", True), ("permanent", False)]
)
def test_benchmark_persists_separate_fault_and_execution_outcomes(
    client, db_session, mode, success
):
    payload, original = setup_execution(client, db_session, mode)
    response = client.post("/api/v1/benchmark-executions", json=payload)
    assert response.status_code == 201, response.text
    outcome = response.json()
    run = outcome["benchmark_run"]
    assert (
        run["runtime_config_json"]["tool_fault_scenario_hash"]
        == ToolFaultScenario(mode).scenario_hash
    )
    summary = outcome["tool_execution_summary"]
    assert summary["successful_call_count"] == int(success)
    assert summary["fault_scenario_summary"]["passed_count"] == 1
    detail = client.get(f"/api/v1/benchmark-executions/{run['id']}").json()
    trace = detail["tool_traces"][0]["trace"]
    assert trace["successful"] is success
    assert trace["fault_scenario"]["passed"] is True
    assert "simulate_failure" not in trace["steps"][0]["arguments"]
    attempts = trace["steps"][0]["attempts"]
    assert all(type(a["fault_injected"]) is bool for a in attempts)
    assert sum(a["handler_invoked"] for a in attempts) == int(success)
    current = next(
        c
        for c in client.get("/api/v1/deployment-configurations").json()
        if c["id"] == original["id"]
    )
    assert current["runtime_config_json"] == original["runtime_config_json"]
    assert current["configuration_hash"] == original["configuration_hash"]


@pytest.mark.parametrize("invalid", ["legacy_case", "wrong_source", "override"])
def test_invalid_fixture_requests_fail_before_any_run_is_created(client, db_session, invalid):
    payload, _ = setup_execution(client, db_session, legacy=invalid == "legacy_case")
    if invalid == "wrong_source":
        payload["data_source"] = "production_captured"
    if invalid == "override":
        payload["adapter_config_json"] = {
            "tool_fault_scenario": ToolFaultScenario("normal").to_dict()
        }
    count = db_session.query(BenchmarkRun).count()
    response = client.post("/api/v1/benchmark-executions", json=payload)
    assert response.status_code == 422, response.text
    assert db_session.query(BenchmarkRun).count() == count


def test_fault_configuration_cannot_be_promoted_through_gate_api(client, db_session):
    payload, _ = setup_execution(client, db_session, "normal")
    assert client.post("/api/v1/benchmark-executions", json=payload).status_code == 201
    policies = client.get("/api/v1/acceptance-policies").json()
    policy = next(p for p in policies if p["name"] == "Demo Policy")
    response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": payload["deployment_configuration_id"],
            "evaluation_suite_id": payload["evaluation_suite_id"],
            "acceptance_policy_id": policy["id"],
        },
    )
    assert response.status_code == 422, response.text
    assert "cannot supply release Gate evidence" in response.text


def test_diagnostic_runs_are_excluded_from_gate_evidence_collection(client, db_session):
    payload, _ = setup_execution(client, db_session, "normal")
    response = client.post("/api/v1/benchmark-executions", json=payload)
    assert response.status_code == 201, response.text
    run_id = UUID(response.json()["benchmark_run"]["id"])
    assert db_session.get(BenchmarkRun, run_id).status == "completed"
    assert db_session.query(BenchmarkResult).filter_by(benchmark_run_id=run_id).count() == 1
    configuration = db_session.get(
        DeploymentConfiguration, UUID(payload["deployment_configuration_id"])
    )
    suite = db_session.get(EvaluationSuite, UUID(payload["evaluation_suite_id"]))
    # Exclusion is bound to the run source even if configuration settings later change.
    configuration.runtime_config_json = {}
    db_session.flush()
    bundle = collect_evidence(
        db_session, deployment_configuration=configuration, evaluation_suite=suite
    )
    assert bundle.runs == []
    assert bundle.results == []
    assert bundle.metrics == []
