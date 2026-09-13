from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    EvaluationCase,
    ModelArtifactAttestation,
)
from app.services.agent_jobs import run_agent_worker_once
from app.services.model_validation import (
    build_model_validation_report,
    render_model_validation_markdown,
)
from tests.test_deployment_gate import _build_gate_graph


def _operator_headers() -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": "validation-operator",
        "x-model-atlas-operator-name": "Validation Operator",
        "x-model-atlas-operator-role": "SRE Lead",
    }


def test_model_validation_report_distinguishes_actual_runtime_from_release(
    db_session: Session,
) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="model-validation-report",
    )
    run = db_session.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id
            == ids["deployment_configuration_id"]
        )
    )
    assert run is not None
    digest = f"sha256:{'a' * 64}"
    run.runtime_config_json = {
        "adapter_name": "openai_compatible",
        "model": "local-validation-model",
        "model_digest": digest,
    }
    run.model_artifact.checksum = digest
    db_session.add(
        ModelArtifactAttestation(
            model_artifact_id=run.model_artifact_id,
            manifest_version="model-artifact-manifest-v1",
            runtime_provider="test-runtime",
            runtime_model_name="local-validation-model",
            source_uri="http://testserver",
            digest_algorithm="sha256",
            digest_value=digest,
            manifest_hash="b" * 64,
            manifest_json={"digest_value": digest},
            verification_method="test_fixture",
            status="verified",
            attested_at=dt.datetime.now(dt.UTC),
            attested_by_identity_json={"subject_id": "test-reviewer"},
            identity_verified=True,
            attestation_hash="c" * 64,
        )
    )
    results = list(
        db_session.scalars(
            select(BenchmarkResult).where(
                BenchmarkResult.benchmark_run_id == run.id
            )
        )
    )
    for result in results:
        evaluation_case = db_session.get(
            EvaluationCase,
            result.evaluation_case_id,
        )
        assert evaluation_case is not None
        context = dict(evaluation_case.reference_context_json or {})
        context["judge_labels"] = {
            "quality_score": result.quality_score,
            "judge_source": "test-review",
        }
        evaluation_case.reference_context_json = context
    db_session.commit()

    report = build_model_validation_report(
        db_session,
        deployment_configuration_id=ids["deployment_configuration_id"],
        evaluation_suite_id=ids["evaluation_suite_id"],
        focus_benchmark_run_id=run.id,
    )

    assert report.status == "validated"
    assert report.actual_runtime_validated is True
    assert report.release_authorized is False
    assert report.configuration_model_match is None
    assert report.artifact_attestation_status == "verified"
    assert report.configured_artifact_digest == digest
    assert report.observed_model_digests == [digest]
    assert report.judge_calibration.status == "calibrated"
    assert report.judge_calibration.candidate_label_count == 3
    assert report.cohorts[0].adapter_names == ["openai_compatible"]
    assert report.cohorts[0].model_names == ["local-validation-model"]
    assert report.cohorts[0].actual_runtime_result_count == 3
    assert len(report.evidence_revision_hash) == 64
    assert len(report.report_hash) == 64

    markdown = render_model_validation_markdown(report)
    assert "# Model Atlas Local Model Validation Report" in markdown
    assert report.report_hash in markdown
    assert "Release authorized: `no`" in markdown


def test_model_validation_report_flags_model_size_mismatch(
    db_session: Session,
) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="model-validation-mismatch",
    )
    run = db_session.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id
            == ids["deployment_configuration_id"]
        )
    )
    assert run is not None
    run.model_artifact.artifact_name = "qwen2.5-7b-instruct-int4"
    run.runtime_config_json = {
        "adapter_name": "openai_compatible",
        "model": "qwen2.5:0.5b",
    }
    db_session.commit()

    report = build_model_validation_report(
        db_session,
        deployment_configuration_id=ids["deployment_configuration_id"],
        evaluation_suite_id=ids["evaluation_suite_id"],
        focus_benchmark_run_id=run.id,
    )

    assert report.configuration_model_match is False
    assert report.status == "needs_attention"
    assert "qwen2.5:0.5b" in report.observed_model_names
    assert any(
        "separate deployment configuration" in recommendation
        for recommendation in report.recommendations
    )


def test_model_validation_campaign_runs_as_durable_job_and_blocks_secrets(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="model-validation-campaign",
    )
    source_run = db_session.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id
            == ids["deployment_configuration_id"]
        )
    )
    assert source_run is not None
    payload = {
        "deployment_configuration_id": str(
            ids["deployment_configuration_id"]
        ),
        "evaluation_suite_id": str(ids["evaluation_suite_id"]),
        "benchmark_task_id": str(source_run.benchmark_task_id),
        "prompt_version_id": str(source_run.prompt_version_id),
        "adapter_name": "mock",
        "adapter_config_json": {},
        "data_source": "local_authored",
        "max_cases": 2,
        "campaign_key": "test-model-validation-campaign",
    }

    forbidden = client.post(
        "/api/v1/model-validation/campaigns",
        headers=_operator_headers(),
        json={
            **payload,
            "adapter_name": "openai_compatible",
            "adapter_config_json": {
                "base_url": "http://localhost:11434",
                "api_key": "must-not-be-persisted",
            },
        },
    )
    assert forbidden.status_code == 422
    assert "cannot persist credentials" in forbidden.text

    invalid_env = client.post(
        "/api/v1/model-validation/campaigns",
        headers=_operator_headers(),
        json={
            **payload,
            "adapter_name": "openai_compatible",
            "adapter_config_json": {
                "base_url": "http://localhost:11434",
                "api_key_env": "UNAPPROVED_SECRET_ENV",
            },
        },
    )
    assert invalid_env.status_code == 422
    assert "OPENAI_COMPATIBLE_API_KEY" in invalid_env.text

    queued = client.post(
        "/api/v1/model-validation/campaigns",
        headers=_operator_headers(),
        json=payload,
    )
    assert queued.status_code == 202
    assert queued.json()["job_type"] == "model_validation_campaign"
    assert queued.json()["status"] == "queued"

    processed = run_agent_worker_once(
        db_session,
        worker_id="model-validation-test-worker",
    )
    assert processed is not None
    assert processed.status == "completed"
    assert processed.benchmark_run_id is not None
    assert processed.result_json is not None
    assert processed.result_json["result_count"] == 2
    assert processed.result_json["report"]["status"] == "fixture_only"
    assert (
        processed.result_json["report"]["focus_benchmark_run_id"]
        == str(processed.benchmark_run_id)
    )

    report_response = client.get(
        "/api/v1/model-validation/report",
        params={
            "deployment_configuration_id": str(
                ids["deployment_configuration_id"]
            ),
            "evaluation_suite_id": str(ids["evaluation_suite_id"]),
            "focus_benchmark_run_id": str(processed.benchmark_run_id),
        },
    )
    assert report_response.status_code == 200
    assert report_response.json()["status"] == "fixture_only"

    markdown_response = client.get(
        "/api/v1/model-validation/report.md",
        params={
            "deployment_configuration_id": str(
                ids["deployment_configuration_id"]
            ),
            "evaluation_suite_id": str(ids["evaluation_suite_id"]),
            "focus_benchmark_run_id": str(processed.benchmark_run_id),
        },
    )
    assert markdown_response.status_code == 200
    assert "fixture_only" in markdown_response.text
