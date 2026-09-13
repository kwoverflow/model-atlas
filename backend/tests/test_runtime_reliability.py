from __future__ import annotations

from dataclasses import replace

from app.models import EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult
from app.services.runtime_reliability import (
    attach_runtime_reliability,
    summarize_reliability_traces,
)


def _case(*, context_tokens: int = 900) -> EvaluationCase:
    return EvaluationCase(
        external_case_id="reliability-001",
        category="runtime_reliability",
        title="Repeated runtime trial",
        input_payload_json={
            "request": "Run a deterministic reliability probe",
            "reliability": {"context_tokens": context_tokens, "context_stress": True},
        },
        tags_json=["runtime", "reliability"],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="local_authored",
    )


def _result(**overrides: object) -> AdapterCaseResult:
    result = AdapterCaseResult(
        raw_output="ok",
        normalized_output="ok",
        quality_score=0.9,
        exact_match=True,
        json_valid=False,
        tool_call_valid=False,
        groundedness_score=0.9,
        faithfulness_score=0.9,
        human_label="pass",
        error_type=None,
        ttft_ms=100.0,
        end_to_end_latency_ms=800.0,
        prompt_tokens=900,
        completion_tokens=100,
        tokens_per_second=125.0,
        gpu_vram_used_mb=8000.0,
        gpu_utilization_pct=60.0,
        cpu_utilization_pct=20.0,
        peak_memory_mb=16000.0,
        oom_occurred=False,
        retry_count=0,
        metadata={},
    )
    return replace(result, **overrides)


def test_runtime_reliability_trace_captures_trial_contract() -> None:
    result = attach_runtime_reliability(
        _case(),
        _result(),
        trial_index=2,
        total_trials=5,
        concurrency=3,
        case_timeout_ms=2_000,
        context_window_tokens=1_000,
        seed=42,
    )

    trace = result.metadata["runtime_reliability"]
    assert trace["schema_version"] == "runtime-reliability-trace-v1"
    assert trace["status"] == "success"
    assert trace["trial_index"] == 2
    assert trace["concurrency"] == 3
    assert trace["context_stress"] is True
    assert trace["context_utilization_ratio"] == 0.9


def test_runtime_reliability_summary_separates_timeout_and_oom() -> None:
    case = _case()
    results = [
        _result(end_to_end_latency_ms=700.0),
        _result(
            error_type="timeout",
            end_to_end_latency_ms=2_000.0,
            raw_output="",
            normalized_output="",
        ),
        _result(
            error_type="out_of_memory",
            oom_occurred=True,
            raw_output="",
            normalized_output="",
        ),
    ]
    traces = []
    for index, result in enumerate(results, start=1):
        attached = attach_runtime_reliability(
            case,
            result,
            trial_index=index,
            total_trials=3,
            concurrency=2,
            case_timeout_ms=1_500,
            context_window_tokens=1_000,
            seed=7,
        )
        traces.append(attached.metadata["runtime_reliability"])

    summary = summarize_reliability_traces(traces)

    assert summary["trial_count"] == 3
    assert summary["expected_trial_count"] == 3
    assert summary["success_rate"] == 0.3333
    assert summary["timeout_rate"] == 0.3333
    assert summary["oom_rate"] == 0.3333
    assert summary["trial_coverage_rate"] == 1.0
    assert summary["context_stress_success_rate"] == 0.3333
    assert summary["p99_end_to_end_latency_ms"] == 2_000.0
