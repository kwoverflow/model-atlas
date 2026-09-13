from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    EvaluationCase,
    EvaluationSuite,
    WorkloadProfile,
)
from app.reference_workload.bootstrap import bootstrap_reference_workload
from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root
from app.reference_workload.reporting import (
    build_reference_workload_report,
    run_reference_workload_gates,
    write_reference_workload_artifacts,
)
from app.reference_workload.runtime_matrix import (
    ACTUAL_RUNTIME_DATA_SOURCE,
    ResolvedRuntimeEntry,
    RuntimeObservation,
    _ensure_configuration,
    _ensure_hardware,
    _ensure_model_and_artifact,
    _ensure_prompt,
    _ensure_task,
    load_runtime_matrix,
)
from app.services.evidence_trust import EvidenceSourceTrustTier, normalize_source_tier
from app.services.reference_workload_read_model import _select_reference_run


def test_reference_overview_keeps_source_and_runtime_coverage_separate(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/reference-workload/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["case_coverage"]["case_count"] == 64
    assert payload["case_coverage"]["approved_case_count"] == 64
    assert payload["case_coverage"]["approved_critical_case_count"] == 20
    assert payload["case_coverage"]["active_case_count"] == 0
    assert payload["review_coverage"]["result_count"] == 0
    assert payload["configuration_matrix"][0]["status"] == "not_run"
    assert payload["evaluation_status"] == "INCOMPLETE"
    assert payload["gate_verdict"] == "NOT_EVALUATED"
    assert payload["production_readiness"] == "not_production_ready"
    assert payload["portfolio_completion"]["status"] == "incomplete"


def test_reference_report_routes_keep_decision_states_separate(client: TestClient) -> None:
    response = client.get("/api/v1/reference-workload/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "reference-workload-report-v1"
    assert payload["evaluation_status"] == "INCOMPLETE"
    assert payload["gate_verdict"] == "NOT_EVALUATED"
    assert payload["release_readiness"] == "NOT_EVALUATED"
    assert payload["production_readiness"] == "not_production_ready"
    assert payload["linked_evidence_ids"]["benchmark_result_ids"] == []

    markdown = client.get("/api/v1/reference-workload/report.md")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Gate: `NOT_EVALUATED`" in markdown.text
    assert "Production Readiness: `not_production_ready`" in markdown.text
    assert "Heuristic-only Results: 0" in markdown.text
    assert "Candidate judge labels: 0" in markdown.text
    assert "Production-captured Results: 0" in markdown.text


def test_reference_report_artifacts_are_hash_bound(
    db_session: Session,
    tmp_path: Path,
) -> None:
    report = build_reference_workload_report(db_session)

    summary = write_reference_workload_artifacts(report, tmp_path)

    assert len(summary.artifacts) == 5
    report_path = tmp_path / "reference-workload-report.json"
    expected_hash = hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert summary.report_sha256 == expected_hash
    manifest = json.loads((tmp_path / "reproduction-manifest.json").read_text("utf-8"))
    assert manifest["report_sha256"] == expected_hash
    assert len(manifest["artifacts"]) == 4
    for artifact in manifest["artifacts"]:
        content = (tmp_path / artifact["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]


def test_reference_overview_selects_latest_actual_runtime_run(
    client: TestClient,
    db_session: Session,
) -> None:
    bundle = build_reference_corpus()
    case_pack = load_reference_case_pack(corpus_bundle=bundle)
    summary = bootstrap_reference_workload(
        db_session,
        corpus_bundle=bundle,
        case_pack=case_pack,
    )
    workload = db_session.get(WorkloadProfile, summary["workload_profile_id"])
    suite = db_session.get(EvaluationSuite, summary["evaluation_suite_id"])
    assert workload is not None
    assert suite is not None

    matrix = load_runtime_matrix(
        default_repository_root() / "reference_workload" / "runtime_matrix.json"
    )
    entry = matrix.entries[0]
    resolved = ResolvedRuntimeEntry(
        entry=entry,
        base_url="http://localhost:11434",
        model_name="qwen2.5:0.5b",
        api_key_configured=False,
    )
    observation = RuntimeObservation(
        runtime_provider="ollama",
        runtime_version="test",
        model_name=resolved.model_name,
        digest="a" * 64,
        format="gguf",
        family="qwen2",
        parameter_size="0.5B",
        quantization="Q4_K_M",
        context_length=entry.context_length,
    )
    hardware = _ensure_hardware(db_session, {})
    _, artifact = _ensure_model_and_artifact(
        db_session,
        observation,
        requested_context_length=entry.context_length,
    )
    task = _ensure_task(db_session)
    prompt = _ensure_prompt(db_session, task, entry.prompt_bundle)
    configuration = _ensure_configuration(
        db_session,
        workload=workload,
        hardware=hardware,
        artifact=artifact,
        resolved=resolved,
        observation=observation,
        corpus_bundle=bundle,
    )
    critical_case = db_session.scalar(
        select(EvaluationCase)
        .where(EvaluationCase.evaluation_suite_id == suite.id)
        .where(EvaluationCase.criticality == "critical")
        .order_by(EvaluationCase.external_case_id)
    )
    assert critical_case is not None

    old_run = _add_run(
        db_session,
        hardware_id=hardware.id,
        artifact_id=artifact.id,
        task_id=task.id,
        prompt_id=prompt.id,
        configuration_id=configuration.id,
        suite_id=suite.id,
        case=critical_case,
        started_at=dt.datetime(2026, 8, 1, tzinfo=dt.UTC),
        failed=False,
    )
    latest_run = _add_run(
        db_session,
        hardware_id=hardware.id,
        artifact_id=artifact.id,
        task_id=task.id,
        prompt_id=prompt.id,
        configuration_id=configuration.id,
        suite_id=suite.id,
        case=critical_case,
        started_at=dt.datetime(2026, 8, 2, tzinfo=dt.UTC),
        failed=True,
    )
    db_session.commit()

    response = client.get("/api/v1/reference-workload/overview")

    assert response.status_code == 200
    payload = response.json()
    selected = payload["configuration_matrix"][0]
    assert selected["entry_name"] == entry.name
    assert selected["latest_run_id"] == str(latest_run.id)
    assert selected["latest_run_id"] != str(old_run.id)
    assert selected["result_count"] == 1
    assert selected["critical_failure_count"] == 1
    assert payload["metric_comparison"][0]["benchmark_run_id"] == str(latest_run.id)
    assert payload["actual_runtime_result_count"] == 1
    assert payload["evidence_trust"]["local_authored_count"] == 1
    assert payload["evidence_trust"]["unknown_source_count"] == 0
    assert payload["critical_failure_count"] == 1
    failure = payload["critical_failures"][0]
    assert failure["benchmark_run_id"] == str(latest_run.id)
    assert failure["failure_reason"] == "runtime_timeout"
    assert failure["benchmark_execution_href"].endswith(str(latest_run.id))
    assert failure["judge_review_href"].endswith(
        f"benchmark_result_id={latest_run.results[0].id}"
    )

    review_plan = client.get(
        "/api/v1/reference-workload/output-review-plan?target_count=1"
    )
    assert review_plan.status_code == 200
    review_payload = review_plan.json()
    assert review_payload["schema_version"] == (
        "model-atlas-reference-output-review-plan-v1"
    )
    assert review_payload["total_failure_count"] == 1
    assert review_payload["cluster_count"] == 1
    assert review_payload["selected_result_count"] == 1
    assert review_payload["selected_items"][0]["candidate_assessment"]["applied"] is False
    assert (
        review_payload["selected_items"][0]["candidate_assessment"]["human_reviewed"]
        is False
    )

    failures = client.get("/api/v1/reference-workload/failures?limit=1&offset=0")
    assert failures.status_code == 200
    assert failures.json()["total"] == 1
    assert len(failures.json()["items"]) == 1

    gate_summary = run_reference_workload_gates(db_session)
    assert gate_summary.created_count == 1
    assert gate_summary.reused_count == 0
    assert gate_summary.blocked_count == 0
    created = next(item for item in gate_summary.entries if item.status == "created")
    assert created.deployment_configuration_id == configuration.id
    assert created.gate_evaluation_id is not None

    repeated_gate_summary = run_reference_workload_gates(db_session)
    assert repeated_gate_summary.created_count == 0
    assert repeated_gate_summary.reused_count == 1

    report = client.get("/api/v1/reference-workload/report")
    assert report.status_code == 200
    report_payload = report.json()
    assert len(report_payload["gate_outcomes"]) == 1
    assert report_payload["linked_evidence_ids"]["benchmark_run_ids"] == [str(latest_run.id)]
    assert report_payload["linked_evidence_ids"]["benchmark_result_ids"] == [
        str(latest_run.results[0].id)
    ]
    assert report_payload["category_metrics"][0]["failed_result_count"] == 1


def test_actual_runtime_source_uses_local_authored_trust_tier() -> None:
    assert (
        normalize_source_tier(ACTUAL_RUNTIME_DATA_SOURCE) is EvidenceSourceTrustTier.LOCAL_AUTHORED
    )


def test_reference_run_selection_prefers_complete_portfolio_coverage() -> None:
    first_case_id = uuid4()
    second_case_id = uuid4()
    portfolio_run = SimpleNamespace(id=uuid4())
    latest_smoke_run = SimpleNamespace(id=uuid4())

    selected = _select_reference_run(
        [latest_smoke_run, portfolio_run],
        entry=SimpleNamespace(trials=2),
        expected_case_ids={first_case_id, second_case_id},
        trials_by_run={
            latest_smoke_run.id: Counter({first_case_id: 1, second_case_id: 1}),
            portfolio_run.id: Counter({first_case_id: 2, second_case_id: 2}),
        },
    )

    assert selected is portfolio_run


def _add_run(
    db: Session,
    *,
    hardware_id: object,
    artifact_id: object,
    task_id: object,
    prompt_id: object,
    configuration_id: object,
    suite_id: object,
    case: EvaluationCase,
    started_at: dt.datetime,
    failed: bool,
) -> BenchmarkRun:
    run = BenchmarkRun(
        hardware_profile_id=hardware_id,
        model_artifact_id=artifact_id,
        benchmark_task_id=task_id,
        prompt_version_id=prompt_id,
        deployment_configuration_id=configuration_id,
        evaluation_suite_id=suite_id,
        runtime_name="ollama",
        runtime_version="test",
        runtime_config_json={"local": True},
        dataset_version="reference-workload-1.0.0",
        started_at=started_at,
        completed_at=started_at + dt.timedelta(minutes=1),
        status="completed",
        data_source=ACTUAL_RUNTIME_DATA_SOURCE,
    )
    db.add(run)
    db.flush()
    db.add(
        BenchmarkResult(
            benchmark_run_id=run.id,
            evaluation_case_id=case.id,
            sample_id=f"{case.external_case_id}-trial-1",
            quality_score=0.2 if failed else 0.95,
            exact_match=not failed,
            json_valid=not failed,
            tool_call_valid=not failed,
            groundedness_score=0.2 if failed else 0.95,
            faithfulness_score=0.2 if failed else 0.95,
            error_type="runtime_timeout" if failed else None,
            raw_output="timed out" if failed else "grounded response",
            metadata_json={
                "scorer": {
                    "scorer_id": "reference_test_scorer",
                    "scorer_version": "v1",
                },
                "runtime_reliability": {
                    "status": "timeout" if failed else "success",
                    "within_timeout": not failed,
                },
            },
            data_source=ACTUAL_RUNTIME_DATA_SOURCE,
        )
    )
    db.flush()
    return run
