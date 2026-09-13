from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkResult, BenchmarkRun, EvaluationCase
from app.schemas import BaselinePromotionCreate, GateEvaluationCreate
from app.seed.demo import seed_demo_data
from app.services.deployment_gate.baselines import promote_gate_evaluation_as_baseline
from app.services.deployment_gate.evaluator import create_gate_evaluation
from app.services.release_readiness import build_release_readiness_snapshot
from tests.test_deployment_gate import _build_gate_graph


def test_release_readiness_snapshot_bundles_gate_context(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    gate = client.get("/api/v1/deployment-gates/evaluations").json()[0]

    response = client.get(
        f"/api/v1/release-readiness/snapshot?gate_evaluation_id={gate['id']}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["gate"]["gate_evaluation_id"] == gate["id"]
    assert payload["gate"]["verdict"] == gate["verdict"]
    assert payload["status"] in {
        "READY",
        "READY_TO_PROMOTE",
        "NEEDS_REVIEW",
        "BLOCKED",
        "INSUFFICIENT_EVIDENCE",
    }
    assert "baseline_status" in payload["baseline"]
    assert "needs_review_count" in payload["judge_calibration"]
    assert "risk_row_count" in payload["prompt_regression"]
    assert payload["lineage"]["event_count"] >= 1


def test_release_readiness_markdown_export(client: TestClient, db_session: Session) -> None:
    seed_demo_data(db_session)
    gate = client.get("/api/v1/deployment-gates/evaluations").json()[0]

    response = client.get(f"/api/v1/release-readiness/snapshot.md?gate_evaluation_id={gate['id']}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Model Atlas Release Readiness Snapshot" in response.text
    assert gate["id"] in response.text


def test_local_demo_readiness_is_not_production_readiness(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, config_name="local-demo-readiness")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    snapshot = build_release_readiness_snapshot(db_session, gate_evaluation_id=gate.id)

    assert snapshot.status == "READY_TO_PROMOTE"
    assert snapshot.evidence_trust.trust_status == "local_demo_ready"
    assert snapshot.production_readiness == "not_production_ready"


def test_heuristic_only_evidence_requires_review(db_session: Session) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="heuristic-readiness",
        reviewed_evidence=False,
    )
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    snapshot = build_release_readiness_snapshot(db_session, gate_evaluation_id=gate.id)

    assert gate.verdict == "APPROVED"
    assert snapshot.status == "NEEDS_REVIEW"
    assert snapshot.evidence_trust.trust_status == "needs_judge_review"
    assert snapshot.evidence_trust.heuristic_only_count == 3
    assert snapshot.production_readiness == "not_production_ready"


def test_unsigned_production_label_cannot_become_production_ready(
    db_session: Session,
) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="production-readiness",
        data_source="production_captured",
    )
    run = db_session.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id == ids["deployment_configuration_id"]
        )
    )
    standard_case = db_session.scalar(
        select(EvaluationCase)
        .where(EvaluationCase.evaluation_suite_id == ids["evaluation_suite_id"])
        .where(EvaluationCase.criticality == "standard")
    )
    assert run is not None
    assert standard_case is not None
    for index in range(17):
        db_session.add(
            BenchmarkResult(
                benchmark_run_id=run.id,
                evaluation_case_id=standard_case.id,
                sample_id=f"production-extra-{index:02d}",
                quality_score=0.92,
                exact_match=True,
                json_valid=True,
                tool_call_valid=False,
                groundedness_score=0.92,
                faithfulness_score=0.92,
                human_label="reviewed-pass",
                normalized_output="{\"ok\": true}",
                metadata_json={
                    "judge_label": {"applied": True, "source": "human_review"}
                },
                data_source="production_captured",
            )
        )
    db_session.commit()
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    promote_gate_evaluation_as_baseline(
        db_session,
        gate_evaluation_id=gate.id,
        payload=BaselinePromotionCreate(promoted_by="test"),
    )

    snapshot = build_release_readiness_snapshot(db_session, gate_evaluation_id=gate.id)

    assert snapshot.status == "NEEDS_REVIEW"
    assert snapshot.evidence_trust.trust_status == "unknown"
    assert snapshot.evidence_trust.production_captured_count == 0
    assert snapshot.evidence_trust.unverified_production_captured_count == 20
    assert snapshot.production_readiness == "unknown"
