from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BenchmarkRun, GateEvaluation
from app.schemas import BaselinePromotionCreate, GateEvaluationCreate
from app.services.deployment_gate.baselines import promote_gate_evaluation_as_baseline
from app.services.deployment_gate.evaluator import create_gate_evaluation
from tests.test_deployment_gate import _build_gate_graph


def test_preflight_reports_selected_evidence_without_persisting_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="preflight")
    gate_count_before = _gate_count(db_session)

    response = client.post(
        "/api/v1/deployment-gates/preflight",
        json=_payload(ids),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_evaluate"] is True
    assert payload["suite"]["active_case_count"] == 3
    assert payload["suite"]["critical_case_count"] == 1
    assert payload["policy"]["rule_count"] == 8
    assert payload["policy"]["blocking_rule_count"] == 7
    assert payload["policy"]["warning_rule_count"] == 1
    assert payload["evidence"]["completed_run_count"] == 1
    assert payload["evidence"]["result_count"] == 3
    assert payload["evidence"]["metric_count"] == 3
    assert payload["evidence"]["source_distribution"] == {"local_authored": 3}
    assert payload["evidence"]["score_distribution"] == {"human_reviewed": 3}
    assert payload["evidence"]["trust_status"] == "local_demo_ready"
    assert payload["baseline"] is None
    assert _gate_count(db_session) == gate_count_before


def test_preflight_auto_detects_active_baseline(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="preflight-active-baseline")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    promote_gate_evaluation_as_baseline(
        db_session,
        gate_evaluation_id=gate.id,
        payload=BaselinePromotionCreate(promoted_by="test"),
    )

    response = client.post("/api/v1/deployment-gates/preflight", json=_payload(ids))

    assert response.status_code == 200
    baseline = response.json()["baseline"]
    assert baseline["source"] == "active_scope_baseline"
    assert baseline["gate_evaluation_id"] == str(gate.id)


def test_explicit_preflight_baseline_takes_precedence(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="preflight-explicit-baseline")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    promote_gate_evaluation_as_baseline(
        db_session,
        gate_evaluation_id=gate.id,
        payload=BaselinePromotionCreate(promoted_by="test"),
    )
    payload = _payload(ids)
    payload["baseline_gate_evaluation_id"] = str(gate.id)

    response = client.post("/api/v1/deployment-gates/preflight", json=payload)

    assert response.status_code == 200
    assert response.json()["baseline"]["source"] == "explicit"


def test_preflight_blocks_when_no_completed_run_exists(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="preflight-no-run")
    run = db_session.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id == ids["deployment_configuration_id"]
        )
    )
    assert run is not None
    db_session.delete(run)
    db_session.commit()

    response = client.post("/api/v1/deployment-gates/preflight", json=_payload(ids))

    assert response.status_code == 200
    payload = response.json()
    assert payload["can_evaluate"] is False
    assert payload["evidence"]["completed_run_count"] == 0
    assert any("No completed benchmark run" in item for item in payload["blocking_preconditions"])


def test_preflight_reports_scope_mismatch_as_blocking_precondition(
    client: TestClient,
    db_session: Session,
) -> None:
    first = _build_gate_graph(db_session, config_name="preflight-scope-a")
    second = _build_gate_graph(db_session, config_name="preflight-scope-b")
    payload = _payload(first)
    payload["evaluation_suite_id"] = str(second["evaluation_suite_id"])

    response = client.post("/api/v1/deployment-gates/preflight", json=payload)

    assert response.status_code == 200
    assert response.json()["can_evaluate"] is False
    assert any("workloads differ" in item for item in response.json()["blocking_preconditions"])


def test_preflight_invalid_entity_returns_validation_error(client: TestClient) -> None:
    response = client.post(
        "/api/v1/deployment-gates/preflight",
        json={
            "deployment_configuration_id": str(uuid4()),
            "evaluation_suite_id": str(uuid4()),
            "acceptance_policy_id": str(uuid4()),
            "baseline_gate_evaluation_id": None,
        },
    )

    assert response.status_code == 422
    assert "deployment_configuration was not found" in response.text


def _payload(ids: dict[str, object]) -> dict[str, str | None]:
    return {
        "deployment_configuration_id": str(ids["deployment_configuration_id"]),
        "evaluation_suite_id": str(ids["evaluation_suite_id"]),
        "acceptance_policy_id": str(ids["acceptance_policy_id"]),
        "baseline_gate_evaluation_id": None,
    }


def _gate_count(db_session: Session) -> int:
    return int(db_session.scalar(select(func.count()).select_from(GateEvaluation)) or 0)
