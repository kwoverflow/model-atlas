import datetime as dt
from io import BytesIO
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    HardwareProfile,
    InferenceMetric,
    MetricDefinition,
    Model,
    ModelArtifact,
    PromptVersion,
    WorkloadProfile,
)
from app.schemas import BaselinePromotionCreate, GateEvaluationCreate
from app.seed.captured_local import CAPTURED_SUITE_NAME, seed_captured_local_suite
from app.seed.demo import seed_demo_data
from app.services.deployment_gate.baselines import promote_gate_evaluation_as_baseline
from app.services.deployment_gate.evaluator import create_gate_evaluation
from app.services.deployment_gate.evidence import deployment_configuration_hash, stable_hash
from app.validators import DomainValidationError


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _build_gate_graph(
    db: Session,
    *,
    data_source: str = "local_authored",
    json_valid: bool = True,
    critical_fail: bool = False,
    warning_latency: bool = False,
    include_metrics: bool = True,
    allow_conditional: bool = True,
    config_name: str = "candidate",
    quality_base: float = 0.92,
    latency_base: float = 900,
    latency_threshold: float = 2000,
    reviewed_evidence: bool = True,
) -> dict[str, Any]:
    hardware = HardwareProfile(
        name=f"Hardware {config_name}",
        cpu_name="CPU",
        cpu_cores=16,
        ram_gb=64,
        gpu_name="RTX 4080 Super",
        gpu_vram_gb=16,
        gpu_count=1,
    )
    model = Model(
        provider="Test",
        family="Gate",
        name=f"gate-model-{config_name}",
        display_name=f"Gate Model {config_name}",
        parameter_count_b=7,
        architecture_type="decoder-only",
        supports_text=True,
        supports_tool_calling=True,
        supports_structured_output=True,
        context_length=32768,
        commercial_use_allowed=True,
        primary_languages=["ko"],
    )
    db.add_all([hardware, model])
    db.flush()
    artifact = ModelArtifact(
        model_id=model.id,
        artifact_name=f"gate-artifact-{config_name}",
        format="gguf",
        quantization="Q4",
        precision="int4",
        context_limit=32768,
        runtime_compatibility=["llama.cpp"],
        is_active=True,
    )
    task = BenchmarkTask(
        name=f"Gate task {config_name}",
        category="acceptance",
        description="Gate acceptance task",
        task_type="acceptance",
        language="ko",
        input_format="json",
        expected_output_format="json",
        scoring_method="gate",
        dataset_version="gate-v1",
        is_active=True,
    )
    db.add_all([artifact, task])
    db.flush()
    prompt = PromptVersion(
        name=f"Gate prompt {config_name}",
        benchmark_task_id=task.id,
        system_prompt="Return grounded output.",
        user_template="{input}",
        output_schema={"type": "object"},
        prompt_hash=f"hash-{config_name}",
        version_label="v1",
        is_active=True,
    )
    workload = WorkloadProfile(
        name=f"Workload {config_name}",
        slug=f"workload-{config_name}",
        description="Local gate workload",
        domain="test",
        primary_language="ko",
        local_only_required=True,
        data_classification="internal",
        expected_output_modes_json=["json_object", "tool_call"],
        is_active=True,
    )
    db.add_all([prompt, workload])
    db.flush()
    suite_payload = {
        "workload_profile_id": workload.id,
        "name": f"Suite {config_name}",
        "version_label": "v1",
        "description": "Gate suite",
        "status": "active",
        "dataset_source": data_source,
        "is_synthetic": data_source == "synthetic_demo",
    }
    suite = EvaluationSuite(**suite_payload, suite_hash=stable_hash(suite_payload))
    db.add(suite)
    db.flush()
    metric_specs = {
        "mean_quality_score": ("quality", "mean", "higher_is_better"),
        "json_validity_rate": ("reliability", "rate", "higher_is_better"),
        "tool_call_validity_rate": ("reliability", "rate", "higher_is_better"),
        "critical_case_failure_rate": ("reliability", "rate", "lower_is_better"),
        "p95_end_to_end_latency_ms": ("performance", "p95", "lower_is_better"),
        "oom_rate": ("resource", "rate", "lower_is_better"),
        "real_case_count": ("evidence", "count", "higher_is_better"),
        "critical_case_count": ("evidence", "count", "higher_is_better"),
        "quality_regression_vs_baseline": ("quality", "mean", "higher_is_better"),
        "latency_regression_vs_baseline": ("performance", "mean", "lower_is_better"),
    }
    metrics: dict[str, MetricDefinition] = {}
    for key, (domain, aggregation, direction) in metric_specs.items():
        metric = db.scalar(select(MetricDefinition).where(MetricDefinition.key == key))
        if metric is None:
            metric = MetricDefinition(
                key=key,
                display_name=key,
                domain=domain,
                aggregation=aggregation,
                direction=direction,
                unit=None,
                description=key,
                calculation_version="test",
                is_active=True,
            )
            db.add(metric)
        metrics[key] = metric
    db.flush()
    policy_payload = {
        "workload_profile_id": workload.id,
        "name": f"Policy {config_name}",
        "version_label": "v1",
        "description": "Gate policy",
        "allow_conditional": allow_conditional,
        "is_active": True,
    }
    policy = AcceptancePolicy(**policy_payload, policy_hash=stable_hash(policy_payload))
    db.add(policy)
    db.flush()
    rule_specs = [
        ("mean_quality_score", "gte", 0.8, "blocker", 3),
        ("json_validity_rate", "gte", 1.0, "blocker", 1),
        ("tool_call_validity_rate", "gte", 1.0, "blocker", 1),
        ("critical_case_failure_rate", "eq", 0.0, "blocker", 1),
        ("oom_rate", "eq", 0.0, "blocker", 3),
        ("real_case_count", "gte", 3, "blocker", None),
        ("critical_case_count", "gte", 1, "blocker", None),
        ("p95_end_to_end_latency_ms", "lte", latency_threshold, "warning", 3),
    ]
    for metric_key, operator, threshold, severity, minimum_sample_size in rule_specs:
        db.add(
            AcceptancePolicyRule(
                acceptance_policy_id=policy.id,
                metric_definition_id=metrics[metric_key].id,
                rule_name=f"{metric_key} rule",
                operator=operator,
                threshold_value=threshold,
                severity=severity,
                minimum_sample_size=minimum_sample_size,
                required=True,
                enabled=True,
                message_on_fail=f"{metric_key} failed",
            )
        )
    deployment_payload = {
        "name": f"Deployment {config_name}",
        "workload_profile_id": workload.id,
        "hardware_profile_id": hardware.id,
        "model_artifact_id": artifact.id,
        "runtime_name": "llama.cpp",
        "runtime_version": "test",
        "runtime_config_json": {"local": True},
        "context_length": 4096,
        "generation_config_json": {"temperature": 0},
        "prompt_bundle_json": {"version": "v1"},
        "output_schema_version": "v1",
        "tool_schema_version": "v1",
        "retrieval_config_json": None,
        "concurrency_target": 1,
        "status": "ready",
        "notes": None,
    }
    deployment = DeploymentConfiguration(
        **deployment_payload,
        configuration_hash=deployment_configuration_hash(deployment_payload),
    )
    db.add(deployment)
    db.flush()
    cases = [
        EvaluationCase(
            evaluation_suite_id=suite.id,
            external_case_id=f"{config_name}-critical",
            category="grounded_answer",
            title="critical grounded answer",
            input_payload_json={"input": "critical"},
            expected_output_json=None,
            reference_context_json={"facts": ["a"]},
            expected_tool_schema_json=None,
            tags_json=["critical"],
            criticality="critical",
            weight=1,
            is_active=True,
            data_source=data_source,
        ),
        EvaluationCase(
            evaluation_suite_id=suite.id,
            external_case_id=f"{config_name}-json",
            category="json_extraction",
            title="json extraction",
            input_payload_json={"input": "json"},
            expected_output_json={"type": "object"},
            reference_context_json=None,
            expected_tool_schema_json=None,
            tags_json=["json"],
            criticality="standard",
            weight=1,
            is_active=True,
            data_source=data_source,
        ),
        EvaluationCase(
            evaluation_suite_id=suite.id,
            external_case_id=f"{config_name}-tool",
            category="tool_selection",
            title="tool selection",
            input_payload_json={"input": "tool"},
            expected_output_json=None,
            reference_context_json=None,
            expected_tool_schema_json={"tool_name": "lookup"},
            tags_json=["tool"],
            criticality="standard",
            weight=1,
            is_active=True,
            data_source=data_source,
        ),
    ]
    db.add_all(cases)
    db.flush()
    started = _now()
    run = BenchmarkRun(
        hardware_profile_id=hardware.id,
        model_artifact_id=artifact.id,
        benchmark_task_id=task.id,
        prompt_version_id=prompt.id,
        deployment_configuration_id=deployment.id,
        evaluation_suite_id=suite.id,
        runtime_name="llama.cpp",
        runtime_version="test",
        runtime_config_json={"local": True},
        dataset_version="gate-v1",
        started_at=started,
        completed_at=started + dt.timedelta(minutes=1),
        status="completed",
        data_source=data_source,
    )
    db.add(run)
    db.flush()
    for index, case in enumerate(cases):
        is_critical = case.criticality == "critical"
        sample_quality = 0.5 if is_critical and critical_fail else quality_base
        db.add(
            BenchmarkResult(
                benchmark_run_id=run.id,
                evaluation_case_id=case.id,
                sample_id=case.external_case_id,
                quality_score=sample_quality,
                exact_match=False if is_critical and critical_fail else True,
                json_valid=json_valid if case.category == "json_extraction" else False,
                tool_call_valid=True if case.category == "tool_selection" else False,
                groundedness_score=sample_quality,
                faithfulness_score=sample_quality,
                human_label="fail" if is_critical and critical_fail else "pass",
                error_type="critical_failure" if is_critical and critical_fail else None,
                normalized_output="{\"ok\": true}",
                metadata_json=(
                    {"judge_label": {"applied": True, "source": "human_review"}}
                    if reviewed_evidence
                    else {
                        "scorer": {
                            "scorer_id": "test_heuristic",
                            "scorer_version": "test-heuristic-v1",
                        }
                    }
                ),
                data_source=data_source,
            )
        )
        if include_metrics:
            db.add(
                InferenceMetric(
                    benchmark_run_id=run.id,
                    sample_id=case.external_case_id,
                    ttft_ms=100 + index,
                    end_to_end_latency_ms=3000 if warning_latency else latency_base + index,
                    prompt_tokens=100,
                    completion_tokens=50,
                    tokens_per_second=30,
                    gpu_vram_used_mb=8000,
                    oom_occurred=False,
                    retry_count=0,
                    data_source=data_source,
                )
            )
    db.commit()
    return {
        "deployment_configuration_id": deployment.id,
        "evaluation_suite_id": suite.id,
        "acceptance_policy_id": policy.id,
    }


def test_deployment_configuration_hash_is_stable_and_sensitive() -> None:
    payload = {
        "workload_profile_id": "11111111-1111-1111-1111-111111111111",
        "hardware_profile_id": "22222222-2222-2222-2222-222222222222",
        "model_artifact_id": "33333333-3333-3333-3333-333333333333",
        "runtime_name": "llama.cpp",
        "runtime_version": "1",
        "runtime_config_json": {"b": 2, "a": 1},
        "context_length": 4096,
        "generation_config_json": {"temperature": 0},
        "prompt_bundle_json": {"version": "v1"},
        "output_schema_version": "v1",
        "tool_schema_version": "v1",
        "retrieval_config_json": None,
        "concurrency_target": 1,
    }
    reordered = {**payload, "runtime_config_json": {"a": 1, "b": 2}}
    changed = {**payload, "context_length": 8192}

    assert deployment_configuration_hash(payload) == deployment_configuration_hash(reordered)
    assert deployment_configuration_hash(payload) != deployment_configuration_hash(changed)


def test_gate_evaluation_rejects_synthetic_only_evidence(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, data_source="synthetic_demo", config_name="synthetic")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    assert gate.verdict == "INSUFFICIENT_EVIDENCE"
    assert "not backed by non-synthetic evaluation cases" in gate.decision_summary


def test_seed_captured_local_suite_creates_gate_ready_case_mix(
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    summary = seed_captured_local_suite(db_session)

    assert summary["evaluation_suite_name"] == CAPTURED_SUITE_NAME
    assert summary["case_count"] == 40
    assert summary["critical_case_count"] == 10
    assert summary["json_case_count"] == 12
    assert summary["tool_case_count"] == 10
    assert summary["data_source"] == "captured_local"


def test_gate_evaluation_blocks_on_blocker_failure(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, json_valid=False, config_name="blocker")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    assert gate.verdict == "BLOCKED"
    assert any(
        result.status == "fail" and result.severity == "blocker"
        for result in gate.rule_results
    )


def test_gate_evaluation_blocks_on_critical_case_failure(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, critical_fail=True, config_name="critical")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    assert gate.verdict == "BLOCKED"
    failures = gate.scorecard_json["critical_case_outcomes"]
    assert any(item["status"] == "fail" for item in failures)


def test_gate_evaluation_conditional_on_warning_only(db_session: Session) -> None:
    ids = _build_gate_graph(
        db_session,
        warning_latency=True,
        latency_threshold=1000,
        config_name="warning",
    )
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    assert gate.verdict == "CONDITIONAL"


def test_gate_evaluation_approved_only_with_sufficient_real_evidence(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, config_name="approved")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    assert gate.verdict == "APPROVED"


def test_approved_gate_can_be_promoted_as_active_baseline(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, config_name="baseline-promotion")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    baseline = promote_gate_evaluation_as_baseline(
        db_session,
        gate_evaluation_id=gate.id,
        payload=BaselinePromotionCreate(
            promoted_by="test",
            promotion_reason="lock release baseline",
        ),
    )

    assert baseline.status == "active"
    assert baseline.gate_evaluation_id == gate.id
    assert baseline.deployment_configuration_id == ids["deployment_configuration_id"]
    assert baseline.evaluation_suite_id == ids["evaluation_suite_id"]
    assert baseline.acceptance_policy_id == ids["acceptance_policy_id"]
    assert baseline.baseline_hash


def test_promoting_new_baseline_supersedes_previous_active_baseline(
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="baseline-supersede")
    first_gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    first_baseline = promote_gate_evaluation_as_baseline(
        db_session,
        gate_evaluation_id=first_gate.id,
        payload=BaselinePromotionCreate(promoted_by="test"),
    )
    second_gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    second_baseline = promote_gate_evaluation_as_baseline(
        db_session,
        gate_evaluation_id=second_gate.id,
        payload=BaselinePromotionCreate(promoted_by="test"),
    )
    db_session.refresh(first_baseline)

    assert second_baseline.status == "active"
    assert first_baseline.status == "superseded"
    assert first_baseline.superseded_by_baseline_id == second_baseline.id
    assert first_baseline.superseded_at is not None


def test_gate_evaluation_uses_active_baseline_when_not_explicitly_provided(
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="baseline-default")
    baseline_gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    promote_gate_evaluation_as_baseline(
        db_session,
        gate_evaluation_id=baseline_gate.id,
        payload=BaselinePromotionCreate(promoted_by="test"),
    )

    current_gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    assert current_gate.baseline_gate_evaluation_id == baseline_gate.id
    assert (
        current_gate.scorecard_json["baseline_comparison"]["baseline_gate_evaluation_id"]
        == str(baseline_gate.id)
    )


def test_non_approved_gate_cannot_be_promoted_as_baseline(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, critical_fail=True, config_name="baseline-reject")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    with pytest.raises(DomainValidationError):
        promote_gate_evaluation_as_baseline(
            db_session,
            gate_evaluation_id=gate.id,
            payload=BaselinePromotionCreate(promoted_by="test"),
        )


def test_missing_required_metrics_return_insufficient_evidence(db_session: Session) -> None:
    ids = _build_gate_graph(db_session, include_metrics=False, config_name="missing")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    assert gate.verdict == "INSUFFICIENT_EVIDENCE"
    assert any(result.status == "insufficient" for result in gate.rule_results)


def test_baseline_regressions_are_calculated(db_session: Session) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="baseline",
        quality_base=0.95,
        latency_base=900,
    )
    baseline = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    for result in db_session.scalars(select(BenchmarkResult)).all():
        result.quality_score = 0.9
        result.groundedness_score = 0.9
        result.faithfulness_score = 0.9
    for metric in db_session.scalars(select(InferenceMetric)).all():
        metric.end_to_end_latency_ms = 1100
    db_session.commit()

    current = create_gate_evaluation(
        db_session,
        GateEvaluationCreate(
            **ids,
            baseline_gate_evaluation_id=baseline.id,
        ),
    )
    comparison = current.scorecard_json["baseline_comparison"]
    assert comparison["quality_regression_vs_baseline"] < 0
    assert comparison["latency_regression_vs_baseline"] > 0


def test_explicit_baseline_must_match_gate_scope(db_session: Session) -> None:
    baseline_ids = _build_gate_graph(db_session, config_name="baseline-scope-a")
    baseline = create_gate_evaluation(db_session, GateEvaluationCreate(**baseline_ids))
    current_ids = _build_gate_graph(db_session, config_name="baseline-scope-b")

    with pytest.raises(DomainValidationError):
        create_gate_evaluation(
            db_session,
            GateEvaluationCreate(
                **current_ids,
                baseline_gate_evaluation_id=baseline.id,
            ),
        )


def test_gate_api_and_reports_preserve_immutable_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="api")
    response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": str(ids["deployment_configuration_id"]),
            "evaluation_suite_id": str(ids["evaluation_suite_id"]),
            "acceptance_policy_id": str(ids["acceptance_policy_id"]),
            "baseline_gate_evaluation_id": None,
        },
    )
    assert response.status_code == 201
    gate = response.json()
    assert gate["verdict"] == "APPROVED"
    assert gate["evidence_snapshot_json"]["benchmark_run_ids"]
    assert gate["evidence_snapshot_json"]["configuration_hash"]
    assert gate["evidence_snapshot_json"]["suite_hash"]
    assert gate["evidence_snapshot_json"]["policy_hash"]
    assert gate["evidence_snapshot_json"]["schema_version"] == "gate-evidence-snapshot-v8"
    assert len(gate["evidence_snapshot_json"]["evidence_revision_hash"]) == 64
    assert gate["evidence_snapshot_json"]["evidence_trust_version"] == "evidence-trust-v1"
    assert gate["evidence_snapshot_json"]["policy_engine_version"] == "gate-policy-v1"
    assert "evidence_trust" in gate["evidence_snapshot_json"]
    assert gate["scorecard_json"]["evidence_trust"] == gate["evidence_snapshot_json"][
        "evidence_trust"
    ]
    assert gate["scorecard_json"]["decision_explanation"]["summary"]
    gate_lineage = client.get(
        "/api/v1/experiment-lineage/events"
        "?sync_missing=false&event_type=gate_evaluation_completed"
    ).json()
    assert any(event["gate_evaluation_id"] == gate["id"] for event in gate_lineage)

    baseline = client.post(
        f"/api/v1/deployment-gates/evaluations/{gate['id']}/promote-baseline",
        json={"promoted_by": "api-test", "promotion_reason": "approved release"},
    )
    assert baseline.status_code == 201
    baseline_payload = baseline.json()
    assert baseline_payload["gate_evaluation_id"] == gate["id"]
    assert baseline_payload["status"] == "active"
    baseline_lineage = client.get(
        "/api/v1/experiment-lineage/events"
        "?sync_missing=false&event_type=baseline_promoted"
    ).json()
    assert any(
        event["deployment_baseline_id"] == baseline_payload["id"]
        for event in baseline_lineage
    )

    baselines = client.get("/api/v1/deployment-gates/baselines?active_only=true")
    assert baselines.status_code == 200
    assert any(item["id"] == baseline_payload["id"] for item in baselines.json())

    markdown = client.get(f"/api/v1/deployment-gates/evaluations/{gate['id']}/report.md")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Model Atlas Deployment Gate Report" in markdown.text

    pdf = client.get(f"/api/v1/deployment-gates/evaluations/{gate['id']}/report.pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf.content)).pages)
    assert "Deployment Gate Report" in text
