from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import replace
from statistics import mean, pstdev
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkResult, BenchmarkRun, EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult
from app.validators import DomainValidationError

RUNTIME_RELIABILITY_TRACE_VERSION = "runtime-reliability-trace-v1"
RUNTIME_RELIABILITY_SUMMARY_VERSION = "runtime-reliability-summary-v1"
RUNTIME_RELIABILITY_COMPARISON_VERSION = "runtime-reliability-comparison-v1"


def attach_runtime_reliability(
    evaluation_case: EvaluationCase,
    result: AdapterCaseResult,
    *,
    trial_index: int,
    total_trials: int,
    concurrency: int,
    case_timeout_ms: int,
    context_window_tokens: int,
    seed: int | None,
    benchmark_run_id: str | None = None,
) -> AdapterCaseResult:
    profile = _reliability_profile(evaluation_case)
    context_tokens = _number(profile.get("context_tokens"), result.prompt_tokens)
    context_ratio = (
        context_tokens / context_window_tokens if context_window_tokens > 0 else 0.0
    )
    status = _trial_status(result, case_timeout_ms)
    error_message = result.metadata.get("reliability_error_message")
    trace = {
        "schema_version": RUNTIME_RELIABILITY_TRACE_VERSION,
        "benchmark_run_id": benchmark_run_id,
        "external_case_id": evaluation_case.external_case_id,
        "trial_index": trial_index,
        "total_trials": total_trials,
        "concurrency": concurrency,
        "case_timeout_ms": case_timeout_ms,
        "status": status,
        "successful": status == "success",
        "within_timeout": status != "timeout",
        "ttft_ms": round(result.ttft_ms, 3),
        "end_to_end_latency_ms": round(result.end_to_end_latency_ms, 3),
        "tokens_per_second": round(result.tokens_per_second, 3),
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "gpu_vram_used_mb": result.gpu_vram_used_mb,
        "peak_memory_mb": result.peak_memory_mb,
        "oom_occurred": result.oom_occurred,
        "error_type": result.error_type,
        "error_message": str(error_message) if error_message else None,
        "seed": seed,
        "context_tokens": round(context_tokens, 3),
        "context_window_tokens": context_window_tokens,
        "context_utilization_ratio": round(context_ratio, 4),
        "context_stress": bool(profile.get("context_stress", context_ratio >= 0.8)),
    }
    return replace(
        result,
        metadata={**result.metadata, "runtime_reliability": trace},
    )


def summarize_reliability_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    valid_traces = [
        trace
        for trace in traces
        if trace.get("schema_version") == RUNTIME_RELIABILITY_TRACE_VERSION
    ]
    if not valid_traces:
        return _empty_summary()

    status_counts = Counter(str(trace.get("status", "error")) for trace in valid_traces)
    trials_by_group: dict[str, set[int]] = defaultdict(set)
    for trace in valid_traces:
        trials_by_group[_trial_group_key(trace)].add(
            int(trace.get("trial_index") or 0)
        )
    expected_trial_count = sum(
        max(int(trace.get("total_trials") or 1), 1)
        for trace in _first_trace_per_group(valid_traces).values()
    )
    observed_counts = [len(indices) for indices in trials_by_group.values()]
    latencies = _numeric_values(valid_traces, "end_to_end_latency_ms")
    latencies_by_group: dict[str, list[float]] = defaultdict(list)
    for trace in valid_traces:
        latency = trace.get("end_to_end_latency_ms")
        if isinstance(latency, int | float) and not isinstance(latency, bool):
            latencies_by_group[_trial_group_key(trace)].append(float(latency))
    ttfts = _numeric_values(valid_traces, "ttft_ms")
    throughputs = [
        float(trace["tokens_per_second"])
        for trace in valid_traces
        if trace.get("status") == "success"
        and isinstance(trace.get("tokens_per_second"), int | float)
    ]
    context_stress_traces = [trace for trace in valid_traces if trace.get("context_stress")]
    trial_count = len(valid_traces)
    success_count = status_counts["success"]
    case_variations = [
        pstdev(case_latencies) / mean(case_latencies)
        for case_latencies in latencies_by_group.values()
        if len(case_latencies) > 1 and mean(case_latencies) > 0
    ]
    latency_variation = mean(case_variations) if case_variations else None
    return {
        "schema_version": RUNTIME_RELIABILITY_SUMMARY_VERSION,
        "reliability_case_count": len(
            {str(trace.get("external_case_id", "unknown")) for trace in valid_traces}
        ),
        "trial_count": trial_count,
        "expected_trial_count": expected_trial_count,
        "success_count": success_count,
        "timeout_count": status_counts["timeout"],
        "oom_count": status_counts["oom"],
        "error_count": status_counts["error"],
        "success_rate": _rate(success_count, trial_count),
        "timeout_rate": _rate(status_counts["timeout"], trial_count),
        "oom_rate": _rate(status_counts["oom"], trial_count),
        "error_rate": _rate(status_counts["error"], trial_count),
        "p50_end_to_end_latency_ms": _percentile(latencies, 0.50),
        "p95_end_to_end_latency_ms": _percentile(latencies, 0.95),
        "p99_end_to_end_latency_ms": _percentile(latencies, 0.99),
        "p50_ttft_ms": _percentile(ttfts, 0.50),
        "p95_ttft_ms": _percentile(ttfts, 0.95),
        "mean_tokens_per_second": _rounded_mean(throughputs),
        "latency_variation_coefficient": _round_optional(latency_variation, 4),
        "trial_coverage_rate": _rate(trial_count, expected_trial_count),
        "minimum_trials_per_case": min(observed_counts),
        "maximum_trials_per_case": max(observed_counts),
        "context_stress_trial_count": len(context_stress_traces),
        "context_stress_success_rate": (
            _rate(
                sum(1 for trace in context_stress_traces if trace.get("status") == "success"),
                len(context_stress_traces),
            )
            if context_stress_traces
            else None
        ),
        "trace_versions": [RUNTIME_RELIABILITY_TRACE_VERSION],
    }


def reliability_trace(result_metadata: Any) -> dict[str, Any] | None:
    metadata = result_metadata if isinstance(result_metadata, dict) else {}
    trace = metadata.get("runtime_reliability")
    return trace if isinstance(trace, dict) else None


def compare_runtime_reliability_runs(
    db: Session,
    *,
    left_run_id: UUID,
    right_run_id: UUID,
) -> dict[str, Any]:
    left = _run_reliability_summary(db, left_run_id)
    right = _run_reliability_summary(db, right_run_id)
    if left["evaluation_suite_id"] != right["evaluation_suite_id"]:
        raise DomainValidationError(
            "runtime reliability comparison requires runs from the same evaluation suite"
        )

    comparison_keys = [
        "success_rate",
        "timeout_rate",
        "oom_rate",
        "p99_end_to_end_latency_ms",
        "latency_variation_coefficient",
        "mean_tokens_per_second",
    ]
    deltas = {
        key: _delta(right["summary"].get(key), left["summary"].get(key))
        for key in comparison_keys
    }
    winner, reason = _select_comparison_winner(left["summary"], right["summary"])
    recommended_run_id = None
    if winner == "left":
        recommended_run_id = left["benchmark_run_id"]
    elif winner == "right":
        recommended_run_id = right["benchmark_run_id"]
    return {
        "schema_version": RUNTIME_RELIABILITY_COMPARISON_VERSION,
        "left": _public_run_summary(left),
        "right": _public_run_summary(right),
        "right_minus_left": deltas,
        "winner": winner,
        "recommended_benchmark_run_id": recommended_run_id,
        "reason": reason,
    }


def _run_reliability_summary(db: Session, run_id: UUID) -> dict[str, Any]:
    run = db.get(BenchmarkRun, run_id)
    if run is None:
        raise DomainValidationError("benchmark_run was not found")
    results = list(
        db.scalars(
            select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id == run.id)
        ).all()
    )
    traces = [
        trace
        for result in results
        if (trace := reliability_trace(result.metadata_json)) is not None
    ]
    return {
        "benchmark_run_id": run.id,
        "deployment_configuration_id": run.deployment_configuration_id,
        "evaluation_suite_id": run.evaluation_suite_id,
        "runtime_name": run.runtime_name,
        "runtime_version": run.runtime_version,
        "dataset_version": run.dataset_version,
        "summary": summarize_reliability_traces(traces),
    }


def _public_run_summary(run_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in run_summary.items()
        if key != "evaluation_suite_id"
    }


def _select_comparison_winner(
    left: dict[str, Any],
    right: dict[str, Any],
) -> tuple[str, str]:
    if not left.get("trial_count") or not right.get("trial_count"):
        return (
            "insufficient_evidence",
            "Both benchmark runs must contain runtime reliability trial traces.",
        )
    ranking = [
        ("success_rate", "higher", "higher trial success rate"),
        ("timeout_rate", "lower", "lower timeout rate"),
        ("oom_rate", "lower", "lower OOM rate"),
        ("p99_end_to_end_latency_ms", "lower", "lower P99 latency"),
        (
            "latency_variation_coefficient",
            "lower",
            "more stable repeated-trial latency",
        ),
        ("mean_tokens_per_second", "higher", "higher mean throughput"),
    ]
    for key, direction, reason in ranking:
        left_value = left.get(key)
        right_value = right.get(key)
        if not isinstance(left_value, int | float) or not isinstance(
            right_value, int | float
        ):
            continue
        if math.isclose(float(left_value), float(right_value), rel_tol=1e-9, abs_tol=1e-9):
            continue
        left_wins = (
            left_value > right_value if direction == "higher" else left_value < right_value
        )
        return ("left" if left_wins else "right", reason)
    return "tie", "The runs are equal across the reliability ranking metrics."


def _delta(right: Any, left: Any) -> float | None:
    if not isinstance(right, int | float) or not isinstance(left, int | float):
        return None
    return round(float(right) - float(left), 4)


def _trial_status(result: AdapterCaseResult, case_timeout_ms: int) -> str:
    error_type = (result.error_type or "").lower()
    if result.oom_occurred or "out_of_memory" in error_type or error_type == "oom":
        return "oom"
    if "timeout" in error_type or result.end_to_end_latency_ms > case_timeout_ms:
        return "timeout"
    if result.error_type:
        return "error"
    return "success"


def _reliability_profile(evaluation_case: EvaluationCase) -> dict[str, Any]:
    payload = (
        evaluation_case.input_payload_json
        if isinstance(evaluation_case.input_payload_json, dict)
        else {}
    )
    profile = payload.get("reliability")
    return profile if isinstance(profile, dict) else {}


def _first_trace_per_group(
    traces: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    first: dict[str, dict[str, Any]] = {}
    for trace in traces:
        first.setdefault(_trial_group_key(trace), trace)
    return first


def _trial_group_key(trace: dict[str, Any]) -> str:
    return ":".join(
        [
            str(trace.get("benchmark_run_id") or "unscoped"),
            str(trace.get("external_case_id") or "unknown"),
        ]
    )


def _numeric_values(traces: list[dict[str, Any]], key: str) -> list[float]:
    return [
        float(trace[key])
        for trace in traces
        if isinstance(trace.get(key), int | float)
        and not isinstance(trace.get(key), bool)
    ]


def _number(value: Any, fallback: int | float) -> float:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return float(fallback)


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _rounded_mean(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def _round_optional(value: float | None, digits: int = 3) -> float | None:
    return round(value, digits) if value is not None else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(
        0,
        min(len(sorted_values) - 1, math.ceil(percentile * len(sorted_values)) - 1),
    )
    return round(sorted_values[index], 3)


def _empty_summary() -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_RELIABILITY_SUMMARY_VERSION,
        "reliability_case_count": 0,
        "trial_count": 0,
        "expected_trial_count": 0,
        "success_count": 0,
        "timeout_count": 0,
        "oom_count": 0,
        "error_count": 0,
        "success_rate": None,
        "timeout_rate": None,
        "oom_rate": None,
        "error_rate": None,
        "p50_end_to_end_latency_ms": None,
        "p95_end_to_end_latency_ms": None,
        "p99_end_to_end_latency_ms": None,
        "p50_ttft_ms": None,
        "p95_ttft_ms": None,
        "mean_tokens_per_second": None,
        "latency_variation_coefficient": None,
        "trial_coverage_rate": None,
        "minimum_trials_per_case": 0,
        "maximum_trials_per_case": 0,
        "context_stress_trial_count": 0,
        "context_stress_success_rate": None,
        "trace_versions": [],
    }
