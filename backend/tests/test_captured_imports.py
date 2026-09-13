import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkResult, BenchmarkRun, EvaluationCase, EvaluationSuite
from app.seed.demo import seed_demo_data
from app.services.captured_case_import import (
    CapturedCaseImportOptions,
    import_captured_cases,
)
from app.services.judge_label_import import import_judge_labels
from app.validators import DomainValidationError


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    return path


def test_import_captured_cases_creates_non_synthetic_suite(
    db_session: Session,
    tmp_path: Path,
) -> None:
    seed_demo_data(db_session)
    path = _write_jsonl(
        tmp_path / "production_cases.jsonl",
        [
            {
                "external_case_id": "prod-json-001",
                "category": "json_extraction",
                "title": "Production JSON case",
                "input": {"document": "Ticket owner is Ops-1."},
                "expected_output": {
                    "type": "object",
                    "required": ["answer", "confidence", "evidence"],
                    "properties": {
                        "answer": {"type": "string"},
                        "confidence": {"type": "number"},
                        "evidence": {"type": "string"},
                    },
                },
                "reference_context": {"required_keys": ["answer", "confidence", "evidence"]},
                "criticality": "critical",
                "tags": ["production_captured", "json"],
                "judge_labels": {"quality_score": 0.94, "human_label": "pass"},
            },
            {
                "external_case_id": "prod-tool-001",
                "category": "tool_selection",
                "title": "Production tool case",
                "input": {"request": "Look up the policy."},
                "expected_tool_schema": {
                    "tool_name": "lookup_policy",
                    "arguments": {"required": ["query"]},
                },
                "criticality": "standard",
                "tags": "production,tool",
            },
            {
                "external_case_id": "prod-qa-001",
                "category": "grounded_answer",
                "title": "Production grounded answer case",
                "input": {"document": "Owner is the platform team."},
                "reference_context": {"facts": ["platform team"]},
                "criticality": "exploratory",
            },
        ],
    )

    summary = import_captured_cases(
        db_session,
        path=path,
        options=CapturedCaseImportOptions(
            suite_name="Production Captured Suite",
            suite_version="v2026-07-07",
        ),
    )

    assert summary.case_count == 3
    assert summary.critical_case_count == 1
    assert summary.json_case_count == 1
    assert summary.tool_case_count == 1
    assert summary.grounded_case_count == 1
    assert summary.judge_label_case_count == 1
    suite = db_session.get(EvaluationSuite, summary.evaluation_suite_id)
    assert suite is not None
    assert suite.is_synthetic is False
    assert suite.dataset_source == "production_captured"
    cases = list(
        db_session.scalars(
            select(EvaluationCase).where(EvaluationCase.evaluation_suite_id == suite.id)
        )
    )
    assert len(cases) == 3
    json_case = next(case for case in cases if case.external_case_id == "prod-json-001")
    assert json_case.reference_context_json["judge_labels"]["quality_score"] == 0.94


def test_import_captured_cases_requires_replace_for_existing_suite(
    db_session: Session,
    tmp_path: Path,
) -> None:
    seed_demo_data(db_session)
    path = _write_jsonl(
        tmp_path / "case.jsonl",
        [
            {
                "external_case_id": "prod-json-001",
                "category": "json_extraction",
                "input": {"document": "Ticket owner is Ops-1."},
                "expected_output": {"type": "object"},
            }
        ],
    )
    options = CapturedCaseImportOptions(
        suite_name="Production Captured Suite",
        suite_version="v2026-07-07",
    )
    import_captured_cases(db_session, path=path, options=options)

    with pytest.raises(DomainValidationError):
        import_captured_cases(db_session, path=path, options=options)

    replaced = import_captured_cases(
        db_session,
        path=path,
        options=CapturedCaseImportOptions(
            suite_name="Production Captured Suite",
            suite_version="v2026-07-07",
            replace_existing=True,
        ),
    )
    assert replaced.case_count == 1


def test_import_judge_labels_can_dry_run_and_apply(
    db_session: Session,
    tmp_path: Path,
) -> None:
    seed_demo_data(db_session)
    result = db_session.scalars(select(BenchmarkResult)).first()
    assert result is not None
    original_quality = result.quality_score
    path = _write_jsonl(
        tmp_path / "labels.jsonl",
        [
            {
                "sample_id": result.sample_id,
                "quality_score": 0.73,
                "groundedness_score": 0.74,
                "faithfulness_score": 0.75,
                "human_label": "reviewed-pass",
                "judge_source": "human_review",
            }
        ],
    )

    dry_run = import_judge_labels(
        db_session,
        benchmark_run_id=result.benchmark_run_id,
        path=path,
        apply_labels=False,
    )
    db_session.refresh(result)
    assert dry_run.matched_label_count == 1
    assert dry_run.applied is False
    assert result.quality_score == original_quality

    applied = import_judge_labels(
        db_session,
        benchmark_run_id=result.benchmark_run_id,
        path=path,
        apply_labels=True,
    )
    db_session.refresh(result)
    assert applied.applied is True
    assert result.quality_score == 0.73
    assert result.groundedness_score == 0.74
    assert result.faithfulness_score == 0.75
    assert result.human_label == "reviewed-pass"
    assert result.metadata_json["judge_label"]["source"] == "human_review"


def test_judge_label_review_api_summarizes_candidate_and_applied_labels(
    client,
    db_session: Session,
    tmp_path: Path,
) -> None:
    seed_demo_data(db_session)
    path = _write_jsonl(
        tmp_path / "production_cases.jsonl",
        [
            {
                "external_case_id": "prod-json-001",
                "category": "json_extraction",
                "title": "Production JSON case",
                "input": {"document": "Ticket owner is Ops-1."},
                "expected_output": {"type": "object"},
                "reference_context": {"required_keys": ["answer"]},
                "criticality": "critical",
                "judge_labels": {
                    "quality_score": 0.94,
                    "groundedness_score": 0.95,
                    "faithfulness_score": 0.96,
                    "human_label": "reviewed-pass",
                },
            }
        ],
    )
    summary = import_captured_cases(
        db_session,
        path=path,
        options=CapturedCaseImportOptions(
            suite_name="Review Suite",
            suite_version="v2026-07-07",
        ),
    )
    base_run = db_session.scalars(select(BenchmarkRun)).first()
    assert base_run is not None
    case = db_session.scalars(
        select(EvaluationCase).where(
            EvaluationCase.evaluation_suite_id == summary.evaluation_suite_id
        )
    ).one()
    run = BenchmarkRun(
        hardware_profile_id=base_run.hardware_profile_id,
        model_artifact_id=base_run.model_artifact_id,
        benchmark_task_id=base_run.benchmark_task_id,
        prompt_version_id=base_run.prompt_version_id,
        deployment_configuration_id=None,
        evaluation_suite_id=summary.evaluation_suite_id,
        runtime_name="review-fixture",
        runtime_version="test",
        runtime_config_json={"local": True},
        dataset_version="review-v1",
        started_at=base_run.started_at,
        completed_at=base_run.completed_at,
        status="completed",
        data_source="captured_review",
    )
    db_session.add(run)
    db_session.flush()
    result = BenchmarkResult(
        benchmark_run_id=run.id,
        evaluation_case_id=case.id,
        sample_id=case.external_case_id,
        quality_score=0.8,
        groundedness_score=0.81,
        faithfulness_score=0.82,
        human_label="heuristic-pass",
        normalized_output='{"answer":"Ops-1"}',
        metadata_json={"scorer": {"version": "test-scorer"}},
        data_source="captured_review",
    )
    db_session.add(result)
    db_session.commit()

    response = client.get(f"/api/v1/judge-labels/review?benchmark_run_id={run.id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["result_count"] == 1
    assert payload["candidate_label_count"] == 1
    assert payload["reviewed_count"] == 0
    assert payload["needs_review_count"] == 1
    assert payload["rows"][0]["score_source"] == "candidate_judge_label"
    assert payload["rows"][0]["quality_delta_vs_candidate"] == pytest.approx(0.14)

    focused = client.get(
        "/api/v1/judge-labels/review",
        params={"benchmark_run_id": run.id, "benchmark_result_id": result.id},
    )
    assert focused.status_code == 200
    assert focused.json()["benchmark_result_id"] == str(result.id)
    assert focused.json()["result_count"] == 1

    label_path = _write_jsonl(
        tmp_path / "labels.jsonl",
        [
            {
                "sample_id": case.external_case_id,
                "quality_score": 0.94,
                "groundedness_score": 0.95,
                "faithfulness_score": 0.96,
                "human_label": "reviewed-pass",
                "judge_source": "human_review",
            }
        ],
    )
    import_judge_labels(
        db_session,
        benchmark_run_id=run.id,
        path=label_path,
        apply_labels=True,
    )

    applied_response = client.get(f"/api/v1/judge-labels/review?benchmark_run_id={run.id}")
    assert applied_response.status_code == 200
    applied_payload = applied_response.json()
    assert applied_payload["reviewed_count"] == 1
    assert applied_payload["needs_review_count"] == 0
    assert applied_payload["rows"][0]["score_source"] == "applied_judge_label"


def test_judge_label_import_api_can_dry_run_and_apply(
    client,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    result = db_session.scalars(select(BenchmarkResult)).first()
    assert result is not None
    original_quality = result.quality_score
    content = json.dumps(
        {
            "sample_id": result.sample_id,
            "quality_score": 0.77,
            "groundedness_score": 0.78,
            "faithfulness_score": 0.79,
            "human_label": "api-reviewed-pass",
            "judge_source": "ui_upload",
        }
    )

    dry_run = client.post(
        "/api/v1/judge-labels/import",
        json={
            "benchmark_run_id": str(result.benchmark_run_id),
            "filename": "labels.jsonl",
            "content": content,
            "apply_labels": False,
        },
    )
    assert dry_run.status_code == 200
    dry_run_payload = dry_run.json()
    assert dry_run_payload["matched_label_count"] == 1
    assert dry_run_payload["applied"] is False
    db_session.refresh(result)
    assert result.quality_score == original_quality

    applied = client.post(
        "/api/v1/judge-labels/import",
        headers={
            "x-model-atlas-operator-id": "judge-import-reviewer",
            "x-model-atlas-operator-name": "Judge Import Reviewer",
            "x-model-atlas-operator-role": "QA Lead",
        },
        json={
            "benchmark_run_id": str(result.benchmark_run_id),
            "filename": "labels.jsonl",
            "content": content,
            "apply_labels": True,
        },
    )
    assert applied.status_code == 200
    assert applied.json()["applied"] is True
    db_session.refresh(result)
    assert result.quality_score == 0.77
    assert result.groundedness_score == 0.78
    assert result.faithfulness_score == 0.79
    assert result.human_label == "api-reviewed-pass"
    assert result.metadata_json["judge_label"]["source"] == "ui_upload"
    assert result.metadata_json["judge_label"]["human_reviewed"] is True
