from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas import GateEvaluationCreate
from app.services.deployment_gate.evaluator import create_gate_evaluation
from tests.test_deployment_gate import _build_gate_graph


def test_control_plane_overview_returns_valid_empty_state(client: TestClient) -> None:
    response = client.get("/api/v1/analytics/control-plane-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "empty"
    assert payload["latest_gate"] is None
    assert payload["release_ready_configuration_count"] == 0
    assert payload["needs_review_count"] == 0
    assert payload["failed_critical_case_count"] == 0
    assert len(payload["workflow_steps"]) == 6
    assert all(step["status"] == "not_started" for step in payload["workflow_steps"])
    assert payload["next_actions"]


def test_control_plane_overview_reports_latest_gate_and_evidence(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="control-overview")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    response = client.get("/api/v1/analytics/control-plane-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "demo"
    assert payload["latest_gate"]["id"] == str(gate.id)
    assert payload["latest_gate"]["verdict"] == "APPROVED"
    assert payload["latest_gate"]["evidence_trust_status"] == "local_demo_ready"
    assert payload["latest_gate"]["production_readiness"] == "not_production_ready"
    assert payload["release_ready_configuration_count"] == 1
    assert payload["local_authored_result_count"] == 3
    assert payload["production_evidence_result_count"] == 0
    assert payload["inventory"]["benchmark_result_count"] == 3
    assert payload["recent_runs"][0]["id"] == gate.evidence_snapshot_json[
        "benchmark_run_ids"
    ][0]


def test_control_plane_overview_prioritizes_failed_critical_case_action(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="control-critical",
        critical_fail=True,
    )
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    payload = client.get("/api/v1/analytics/control-plane-overview").json()

    assert payload["latest_gate"]["id"] == str(gate.id)
    assert payload["failed_critical_case_count"] == 1
    assert payload["next_actions"][0]["priority"] == "high"
    assert payload["next_actions"][0]["kind"] == "judge_review"
    priority_rank = {"high": 0, "medium": 1, "low": 2}
    priorities = [priority_rank[item["priority"]] for item in payload["next_actions"]]
    assert priorities == sorted(priorities)
