import datetime as dt
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.seed.demo import seed_demo_data


def _utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()


def _create_core_graph(client: TestClient) -> dict[str, str]:
    hardware = client.post(
        "/api/v1/hardware-profiles",
        json={
            "name": "Test Workstation",
            "cpu_name": "Test CPU",
            "cpu_cores": 16,
            "ram_gb": 64,
            "gpu_name": "RTX 4080 Super",
            "gpu_vram_gb": 16,
            "gpu_count": 1,
            "os_name": "Test OS",
            "cuda_version": "12.4",
            "driver_version": "test",
            "notes": "test hardware",
        },
    )
    assert hardware.status_code == 201

    model = client.post(
        "/api/v1/models",
        json={
            "provider": "Test Provider",
            "family": "Test Family",
            "name": "test-model",
            "display_name": "Test Model",
            "parameter_count_b": 7,
            "architecture_type": "decoder-only transformer",
            "supports_text": True,
            "supports_vision": False,
            "supports_tool_calling": True,
            "supports_structured_output": True,
            "context_length": 32768,
            "license_name": "Apache-2.0",
            "commercial_use_allowed": True,
            "primary_languages": ["en", "ko"],
            "source_url": "https://example.com/model",
            "notes": "test model",
        },
    )
    assert model.status_code == 201

    artifact = client.post(
        "/api/v1/model-artifacts",
        json={
            "model_id": model.json()["id"],
            "artifact_name": "test-model-q4",
            "format": "gguf",
            "quantization": "Q4_K_M",
            "precision": "int4",
            "file_size_gb": 4.5,
            "minimum_vram_gb": 6,
            "recommended_vram_gb": 8,
            "context_limit": 32768,
            "runtime_compatibility": ["llama.cpp"],
            "checksum": "synthetic-test",
            "is_active": True,
            "notes": "test artifact",
        },
    )
    assert artifact.status_code == 201

    task = client.post(
        "/api/v1/benchmark-tasks",
        json={
            "name": "Test JSON generation",
            "category": "format_following",
            "description": "Generate JSON",
            "task_type": "json_generation",
            "language": "en",
            "input_format": "instruction",
            "expected_output_format": "json_object",
            "scoring_method": "json validity",
            "dataset_version": "test-json-v1",
            "is_active": True,
        },
    )
    assert task.status_code == 201

    prompt = client.post(
        "/api/v1/prompt-versions",
        json={
            "name": "Test prompt",
            "benchmark_task_id": task.json()["id"],
            "system_prompt": "Return JSON.",
            "user_template": "{input}",
            "output_schema": {"type": "object"},
            "prompt_hash": "abc123",
            "version_label": "v1",
            "is_active": True,
            "notes": "test prompt",
        },
    )
    assert prompt.status_code == 201

    run = client.post(
        "/api/v1/benchmark-runs",
        json={
            "hardware_profile_id": hardware.json()["id"],
            "model_artifact_id": artifact.json()["id"],
            "benchmark_task_id": task.json()["id"],
            "prompt_version_id": prompt.json()["id"],
            "runtime_name": "pytest-runtime",
            "runtime_version": "0.1",
            "runtime_config_json": {"temperature": 0},
            "dataset_version": "test-json-v1",
            "seed": 1,
            "started_at": _utc_now(),
            "completed_at": _utc_now(),
            "status": "completed",
            "failure_reason": None,
            "data_source": "synthetic_demo",
        },
    )
    assert run.status_code == 201

    return {
        "hardware_id": hardware.json()["id"],
        "model_id": model.json()["id"],
        "artifact_id": artifact.json()["id"],
        "task_id": task.json()["id"],
        "prompt_id": prompt.json()["id"],
        "run_id": run.json()["id"],
    }


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_core_crud_creation_and_metric_flow(client: TestClient) -> None:
    ids = _create_core_graph(client)
    result = client.post(
        "/api/v1/benchmark-results",
        json={
            "benchmark_run_id": ids["run_id"],
            "sample_id": "sample-1",
            "quality_score": 0.91,
            "exact_match": True,
            "json_valid": True,
            "tool_call_valid": False,
            "groundedness_score": 0.9,
            "faithfulness_score": 0.89,
            "human_label": "pass",
            "error_type": None,
            "raw_output": "{\"answer\": \"ok\"}",
            "normalized_output": "{\"answer\": \"ok\"}",
            "metadata_json": {"synthetic": True},
            "data_source": "synthetic_demo",
        },
    )
    assert result.status_code == 201

    metric = client.post(
        "/api/v1/inference-metrics",
        json={
            "benchmark_run_id": ids["run_id"],
            "sample_id": "sample-1",
            "ttft_ms": 120,
            "end_to_end_latency_ms": 900,
            "prompt_tokens": 100,
            "completion_tokens": 80,
            "tokens_per_second": 42,
            "gpu_vram_used_mb": 7800,
            "gpu_utilization_pct": 78,
            "cpu_utilization_pct": 20,
            "peak_memory_mb": 20000,
            "oom_occurred": False,
            "retry_count": 0,
            "data_source": "synthetic_demo",
        },
    )
    assert metric.status_code == 201

    filtered_runs = client.get(f"/api/v1/benchmark-runs?model_artifact_id={ids['artifact_id']}")
    assert filtered_runs.status_code == 200
    assert len(filtered_runs.json()) == 1

    filtered_metrics = client.get(f"/api/v1/inference-metrics?benchmark_run_id={ids['run_id']}")
    assert filtered_metrics.status_code == 200
    assert len(filtered_metrics.json()) == 1


def test_seed_script_and_analytics(client: TestClient, db_session: Session) -> None:
    summary = seed_demo_data(db_session)
    assert summary.models == 3
    assert summary.model_artifacts == 5
    assert summary.benchmark_runs == 7
    assert summary.benchmark_results == 70
    assert summary.evaluation_cases == 40
    assert summary.gate_evaluations == 1

    overview = client.get("/api/v1/analytics/overview")
    assert overview.status_code == 200
    assert overview.json()["model_count"] == 3
    assert overview.json()["synthetic_record_count"] == 147

    comparison = client.get("/api/v1/analytics/model-comparison")
    assert comparison.status_code == 200
    assert len(comparison.json()) >= 4
    assert comparison.json()[0]["benchmark_coverage_count"] >= 1


def test_inactive_artifact_rejection(client: TestClient) -> None:
    ids = _create_core_graph(client)
    inactive = client.post(
        "/api/v1/model-artifacts",
        json={
            "model_id": ids["model_id"],
            "artifact_name": "inactive-artifact",
            "format": "gguf",
            "quantization": "Q8_0",
            "precision": "int8",
            "file_size_gb": 8,
            "minimum_vram_gb": 10,
            "recommended_vram_gb": 12,
            "context_limit": 32768,
            "runtime_compatibility": ["llama.cpp"],
            "checksum": "inactive",
            "is_active": False,
            "notes": "inactive",
        },
    )
    assert inactive.status_code == 201
    response = client.post(
        "/api/v1/benchmark-runs",
        json={
            "hardware_profile_id": ids["hardware_id"],
            "model_artifact_id": inactive.json()["id"],
            "benchmark_task_id": ids["task_id"],
            "prompt_version_id": ids["prompt_id"],
            "runtime_name": "pytest-runtime",
            "runtime_version": "0.1",
            "runtime_config_json": {"temperature": 0},
            "dataset_version": "test-json-v1",
            "seed": 2,
            "started_at": _utc_now(),
            "completed_at": _utc_now(),
            "status": "completed",
            "failure_reason": None,
            "data_source": "synthetic_demo",
        },
    )
    assert response.status_code == 422
    assert "inactive model artifacts" in response.text


def test_negative_latency_rejection(client: TestClient) -> None:
    ids = _create_core_graph(client)
    response = client.post(
        "/api/v1/inference-metrics",
        json={
            "benchmark_run_id": ids["run_id"],
            "sample_id": "sample-negative",
            "ttft_ms": 10,
            "end_to_end_latency_ms": -1,
            "prompt_tokens": 100,
            "completion_tokens": 80,
            "tokens_per_second": 42,
            "gpu_vram_used_mb": 7800,
            "gpu_utilization_pct": 78,
            "cpu_utilization_pct": 20,
            "peak_memory_mb": 20000,
            "oom_occurred": False,
            "retry_count": 0,
            "data_source": "synthetic_demo",
        },
    )
    assert response.status_code == 422


def test_json_valid_output_validation(client: TestClient) -> None:
    ids = _create_core_graph(client)
    response = client.post(
        "/api/v1/benchmark-results",
        json={
            "benchmark_run_id": ids["run_id"],
            "sample_id": "bad-json",
            "quality_score": 0.7,
            "exact_match": False,
            "json_valid": True,
            "tool_call_valid": False,
            "normalized_output": "not json",
        },
    )
    assert response.status_code == 422
    assert "valid JSON" in response.text


def test_tool_call_valid_output_validation(client: TestClient) -> None:
    ids = _create_core_graph(client)
    response = client.post(
        "/api/v1/benchmark-results",
        json={
            "benchmark_run_id": ids["run_id"],
            "sample_id": "bad-tool",
            "quality_score": 0.7,
            "exact_match": False,
            "json_valid": True,
            "tool_call_valid": True,
            "normalized_output": "{\"answer\": \"missing tool\"}",
        },
    )
    assert response.status_code == 422
    assert "tool_name" in response.text


def test_recommendation_report_from_seed_data(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get("/api/v1/recommendations/report")

    assert response.status_code == 200
    report = response.json()
    assert report["candidate_count"] == 5
    assert report["eligible_count"] > 0
    assert report["recommended_candidate"]["recommendation_score"] > 0
    assert len(report["pareto_frontier"]) > 0
    assert report["recommended_candidate"]["rank"] == 1


def test_recommendation_report_applies_coverage_confidence_penalty(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get("/api/v1/recommendations/report")

    assert response.status_code == 200
    report = response.json()
    top = report["recommended_candidate"]
    assert top["raw_recommendation_score"] >= top["recommendation_score"]
    assert 0 < top["evidence_confidence"] <= 1
    assert top["confidence_penalty"] == round(1 - top["evidence_confidence"], 4)
    assert any("Evidence confidence" in item for item in top["rationale"])
    assert any(candidate["evidence_confidence"] < 1 for candidate in report["candidates"])


def test_recommendation_report_markdown_export(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get("/api/v1/recommendations/report/export.md?top_k=3")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "model-atlas-recommendation-report.md" in response.headers["content-disposition"]
    assert "# Model Atlas Recommendation Report" in response.text
    assert "## Ranked Candidates" in response.text
    assert "Evidence confidence" in response.text
    assert "Final score equals raw weighted score" in response.text


def test_recommendation_report_pdf_export(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get("/api/v1/recommendations/report/export.pdf?top_k=3")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "model-atlas-recommendation-report.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

    reader = PdfReader(BytesIO(response.content))
    assert len(reader.pages) >= 1
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Model Atlas Recommendation Report" in text
    assert "Ranked Candidates" in text
    assert "Evidence confidence" in text


def test_recommendation_report_filters_by_tool_calling_task(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    tasks = client.get("/api/v1/benchmark-tasks").json()
    tool_task_id = next(task["id"] for task in tasks if task["name"] == "Tool calling")

    response = client.get(
        f"/api/v1/recommendations/report?benchmark_task_id={tool_task_id}"
        "&require_tool_calling=true"
    )

    assert response.status_code == 200
    report = response.json()
    assert report["benchmark_task_name"] == "Tool calling"
    assert report["eligible_count"] == 1
    assert report["recommended_candidate"]["artifact_name"] == "qwen2.5-7b-instruct-int4"


def test_recommendation_report_hard_filter_can_exclude_all(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get("/api/v1/recommendations/report?min_context_length=200000")

    assert response.status_code == 200
    report = response.json()
    assert report["eligible_count"] == 0
    assert report["recommended_candidate"] is None
    assert any(issue["reason_code"] == "insufficient_context" for issue in report["excluded"])


def test_recommendation_report_accepts_weight_query_params(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get(
        "/api/v1/recommendations/report"
        "?quality_weight=1"
        "&latency_weight=0"
        "&throughput_weight=0"
        "&vram_efficiency_weight=0"
    )

    assert response.status_code == 200
    report = response.json()
    assert report["request"]["weights"] == {
        "quality": 1.0,
        "latency": 0.0,
        "throughput": 0.0,
        "vram_efficiency": 0.0,
    }
    assert report["recommended_candidate"]["rank"] == 1


def test_recommendation_report_rejects_zero_total_query_weights(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get(
        "/api/v1/recommendations/report"
        "?quality_weight=0"
        "&latency_weight=0"
        "&throughput_weight=0"
        "&vram_efficiency_weight=0"
    )

    assert response.status_code == 422
    assert "at least one recommendation weight" in response.text


def test_recommendation_scenario_round_trip(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    tasks = client.get("/api/v1/benchmark-tasks").json()
    hardware = client.get("/api/v1/hardware-profiles").json()
    task_id = next(task["id"] for task in tasks if task["name"] == "Tool calling")

    payload = {
        "name": "Tool-heavy local deployment",
        "description": "Favor tool calling quality on the local workstation.",
        "request": {
            "hardware_profile_id": hardware[0]["id"],
            "benchmark_task_id": task_id,
            "require_tool_calling": True,
            "commercial_use_required": True,
            "min_context_length": 16000,
            "top_k": 3,
            "weights": {
                "quality": 0.7,
                "latency": 0.1,
                "throughput": 0.1,
                "vram_efficiency": 0.1,
            },
        },
    }

    created = client.post("/api/v1/recommendations/scenarios", json=payload)
    assert created.status_code == 201
    scenario = created.json()
    assert scenario["name"] == payload["name"]
    assert scenario["request"]["benchmark_task_id"] == task_id

    listed = client.get("/api/v1/recommendations/scenarios")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == scenario["id"]

    report = client.get(f"/api/v1/recommendations/scenarios/{scenario['id']}/report")
    assert report.status_code == 200
    report_json = report.json()
    assert report_json["request"]["top_k"] == 3
    assert report_json["benchmark_task_name"] == "Tool calling"

    export = client.get(f"/api/v1/recommendations/scenarios/{scenario['id']}/report/export.md")
    assert export.status_code == 200
    assert "Model Atlas Recommendation Report: Tool-heavy local deployment" in export.text
    assert "## Recommended Candidate" in export.text

    pdf_export = client.get(
        f"/api/v1/recommendations/scenarios/{scenario['id']}/report/export.pdf"
    )
    assert pdf_export.status_code == 200
    assert pdf_export.content.startswith(b"%PDF")
    pdf_text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(pdf_export.content)).pages
    )
    assert "Tool-heavy local deployment" in pdf_text


def test_recommendation_scenario_update_and_delete(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    created = client.post(
        "/api/v1/recommendations/scenarios",
        json={
            "name": "Draft scenario",
            "description": "Initial notes",
            "request": {"top_k": 5},
        },
    )
    assert created.status_code == 201
    scenario_id = created.json()["id"]

    updated = client.patch(
        f"/api/v1/recommendations/scenarios/{scenario_id}",
        json={
            "name": "Curated scenario",
            "description": "Updated notes",
            "request": {"top_k": 2},
        },
    )
    assert updated.status_code == 200
    updated_json = updated.json()
    assert updated_json["name"] == "Curated scenario"
    assert updated_json["description"] == "Updated notes"
    assert updated_json["request"]["top_k"] == 2

    report = client.get(f"/api/v1/recommendations/scenarios/{scenario_id}/report")
    assert report.status_code == 200
    assert len(report.json()["candidates"]) == 2

    deleted = client.delete(f"/api/v1/recommendations/scenarios/{scenario_id}")
    assert deleted.status_code == 204

    listed = client.get("/api/v1/recommendations/scenarios")
    assert listed.status_code == 200
    assert all(item["id"] != scenario_id for item in listed.json())

    missing = client.get(f"/api/v1/recommendations/scenarios/{scenario_id}")
    assert missing.status_code == 422
