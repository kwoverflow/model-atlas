from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from app.models import BenchmarkResult, EvaluationCase
from app.services.agent_execution import summarize_agent_traces
from app.services.deployment_gate.evidence import SYNTHETIC_SOURCE, EvidenceBundle
from app.services.runtime_reliability import (
    reliability_trace,
    summarize_reliability_traces,
)


@dataclass(frozen=True)
class CalculatedMetric:
    key: str
    value: float | None
    sample_size: int
    details: dict[str, Any] = field(default_factory=dict)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, math.ceil(percentile * len(sorted_values)) - 1))
    return sorted_values[index]


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _case_for_result(bundle: EvidenceBundle, result: BenchmarkResult) -> EvaluationCase | None:
    return bundle.result_case_map.get(result.id)


def _is_json_case(case: EvaluationCase | None) -> bool:
    if case is None:
        return False
    return "json" in case.category.lower() or case.expected_output_json is not None


def _is_tool_case(case: EvaluationCase | None) -> bool:
    if case is None:
        return False
    return "tool" in case.category.lower() or case.expected_tool_schema_json is not None


def _tool_trace(result: BenchmarkResult) -> dict[str, Any] | None:
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    trace = metadata.get("tool_execution")
    return trace if isinstance(trace, dict) else None


def _rag_trace(result: BenchmarkResult) -> dict[str, Any] | None:
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    trace = metadata.get("rag_evaluation")
    return trace if isinstance(trace, dict) else None


def _runtime_reliability_trace(result: BenchmarkResult) -> dict[str, Any] | None:
    return reliability_trace(result.metadata_json)


def _agent_trace(result: BenchmarkResult) -> dict[str, Any] | None:
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    trace = metadata.get("agent_execution")
    return trace if isinstance(trace, dict) else None


def _is_critical_failure(
    result: BenchmarkResult,
    case: EvaluationCase | None,
    *,
    check_single_tool_flag: bool = True,
) -> bool:
    if case is None or case.criticality != "critical":
        return False
    if result.error_type:
        return True
    if result.exact_match is False:
        return True
    if result.human_label and "fail" in result.human_label.lower():
        return True
    if result.quality_score is not None and result.quality_score < 0.8:
        return True
    if _is_json_case(case) and not result.json_valid:
        return True
    if check_single_tool_flag and _is_tool_case(case) and not result.tool_call_valid:
        return True
    tool_trace = _tool_trace(result)
    if tool_trace is not None and (
        not bool(tool_trace.get("call_valid"))
        or not bool(tool_trace.get("successful"))
    ):
        return True
    rag_trace = _rag_trace(result)
    if rag_trace is not None and (
        not bool(rag_trace.get("successful"))
        or _rag_retrieval_recall(rag_trace) < 1.0
        or _metric_value(rag_trace, "citation_precision") < 1.0
        or _metric_value(rag_trace, "unsupported_claim_rate") > 0.0
    ):
        return True
    runtime_trace = _runtime_reliability_trace(result)
    if runtime_trace is not None and runtime_trace.get("status") != "success":
        return True
    agent_trace = _agent_trace(result)
    if agent_trace is not None and (
        not bool(agent_trace.get("successful"))
        or not bool(agent_trace.get("plan_valid"))
        or int(agent_trace.get("policy_violation_count") or 0) > 0
    ):
        return True
    if "ground" in case.category.lower() and (
        (result.groundedness_score is not None and result.groundedness_score < 0.8)
        or (result.faithfulness_score is not None and result.faithfulness_score < 0.8)
    ):
        return True
    return False


def critical_case_outcomes(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    outcomes: list[dict[str, Any]] = []
    for result in bundle.results:
        case = _case_for_result(bundle, result)
        if case is None or case.criticality != "critical":
            continue
        failed = _is_critical_failure(result, case)
        outcomes.append(
            {
                "case_id": str(case.id),
                "external_case_id": case.external_case_id,
                "title": case.title,
                "category": case.category,
                "benchmark_run_id": str(result.benchmark_run_id),
                "sample_id": result.sample_id,
                "status": "fail" if failed else "pass",
                "quality_score": result.quality_score,
                "error_type": result.error_type,
                "data_source": result.data_source,
                "tool_execution_status": (
                    _tool_trace(result).get("status") if _tool_trace(result) else None
                ),
                "rag_evaluation_status": (
                    _rag_trace(result).get("status") if _rag_trace(result) else None
                ),
                "runtime_reliability_status": (
                    _runtime_reliability_trace(result).get("status")
                    if _runtime_reliability_trace(result)
                    else None
                ),
                "agent_execution_status": (
                    _agent_trace(result).get("status")
                    if _agent_trace(result)
                    else None
                ),
                "agent_halt_reason": (
                    _agent_trace(result).get("halt_reason")
                    if _agent_trace(result)
                    else None
                ),
                "agent_replan_count": (
                    int(_agent_trace(result).get("replan_count") or 0)
                    if _agent_trace(result)
                    else 0
                ),
                "agent_pending_approval_count": (
                    int(_agent_trace(result).get("pending_checkpoint_count") or 0)
                    if _agent_trace(result)
                    else 0
                ),
            }
        )
    return outcomes


def calculate_metrics(bundle: EvidenceBundle) -> dict[str, CalculatedMetric]:
    quality_values = [r.quality_score for r in bundle.results if r.quality_score is not None]
    groundedness_values = [
        r.groundedness_score for r in bundle.results if r.groundedness_score is not None
    ]
    faithfulness_values = [
        r.faithfulness_score for r in bundle.results if r.faithfulness_score is not None
    ]

    json_results = [r for r in bundle.results if _is_json_case(_case_for_result(bundle, r))]
    tool_results = [r for r in bundle.results if _is_tool_case(_case_for_result(bundle, r))]
    tool_traces = [trace for result in tool_results if (trace := _tool_trace(result))]
    tool_steps = [
        step
        for trace in tool_traces
        for step in trace.get("steps", [])
        if isinstance(step, dict)
    ]
    retried_tool_steps = [
        step for step in tool_steps if int(step.get("retry_count") or 0) > 0
    ]
    rag_traces = [trace for result in bundle.results if (trace := _rag_trace(result))]
    rag_retrieval_recalls = [_rag_retrieval_recall(trace) for trace in rag_traces]
    rag_citation_precisions = [
        _metric_value(trace, "citation_precision") for trace in rag_traces
    ]
    rag_citation_recalls = [
        _metric_value(trace, "citation_recall") for trace in rag_traces
    ]
    rag_groundedness_scores = [
        _metric_value(trace, "groundedness_score") for trace in rag_traces
    ]
    rag_unsupported_claim_rates = [
        _metric_value(trace, "unsupported_claim_rate") for trace in rag_traces
    ]
    runtime_reliability_traces = [
        trace
        for result in bundle.results
        if (trace := _runtime_reliability_trace(result))
    ]
    runtime_reliability_summary = summarize_reliability_traces(
        runtime_reliability_traces
    )
    agent_traces = [
        trace for result in bundle.results if (trace := _agent_trace(result))
    ]
    agent_summary = summarize_agent_traces(agent_traces)
    critical_results = [
        r for r in bundle.results if (_case_for_result(bundle, r) or None) is not None
    ]
    critical_results = [
        r for r in critical_results if _case_for_result(bundle, r).criticality == "critical"  # type: ignore[union-attr]
    ]
    critical_failures = [
        r for r in critical_results if _is_critical_failure(r, _case_for_result(bundle, r))
    ]

    latencies = [m.end_to_end_latency_ms for m in bundle.metrics]
    ttfts = [m.ttft_ms for m in bundle.metrics]
    tokens_per_second = [m.tokens_per_second for m in bundle.metrics]
    vram_values = [m.gpu_vram_used_mb for m in bundle.metrics if m.gpu_vram_used_mb is not None]
    oom_count = sum(1 for metric in bundle.metrics if metric.oom_occurred)

    real_case_ids = {
        result.evaluation_case_id
        for result in bundle.results
        if result.evaluation_case_id is not None
        and result.data_source != SYNTHETIC_SOURCE
        and (case := _case_for_result(bundle, result)) is not None
        and case.data_source != SYNTHETIC_SOURCE
    }
    critical_case_ids = {
        result.evaluation_case_id
        for result in bundle.results
        if result.evaluation_case_id is not None
        and (case := _case_for_result(bundle, result)) is not None
        and case.criticality == "critical"
    }

    return {
        "mean_quality_score": CalculatedMetric(
            "mean_quality_score", _mean(quality_values), len(quality_values)
        ),
        "json_validity_rate": CalculatedMetric(
            "json_validity_rate",
            sum(1 for result in json_results if result.json_valid) / len(json_results)
            if json_results
            else None,
            len(json_results),
        ),
        "tool_call_validity_rate": CalculatedMetric(
            "tool_call_validity_rate",
            sum(1 for result in tool_results if result.tool_call_valid) / len(tool_results)
            if tool_results
            else None,
            len(tool_results),
        ),
        "tool_selection_accuracy": CalculatedMetric(
            "tool_selection_accuracy",
            (
                sum(1 for step in tool_steps if step.get("selection_valid"))
                / len(tool_steps)
                if tool_steps
                else None
            ),
            len(tool_steps),
        ),
        "tool_argument_validity_rate": CalculatedMetric(
            "tool_argument_validity_rate",
            (
                sum(1 for step in tool_steps if step.get("arguments_valid"))
                / len(tool_steps)
                if tool_steps
                else None
            ),
            len(tool_steps),
        ),
        "tool_execution_success_rate": CalculatedMetric(
            "tool_execution_success_rate",
            (
                sum(1 for step in tool_steps if step.get("execution_status") == "success")
                / len(tool_steps)
                if tool_steps
                else None
            ),
            len(tool_steps),
            {
                "failed_tool_calls": sum(
                    1 for step in tool_steps if step.get("execution_status") != "success"
                )
            },
        ),
        "tool_sequence_success_rate": CalculatedMetric(
            "tool_sequence_success_rate",
            (
                sum(1 for trace in tool_traces if trace.get("sequence_match"))
                / len(tool_traces)
                if tool_traces
                else None
            ),
            len(tool_traces),
        ),
        "tool_retry_recovery_rate": CalculatedMetric(
            "tool_retry_recovery_rate",
            (
                sum(1 for step in retried_tool_steps if step.get("recovered"))
                / len(retried_tool_steps)
                if retried_tool_steps
                else None
            ),
            len(retried_tool_steps),
            {"retried_tool_calls": len(retried_tool_steps)},
        ),
        "rag_retrieval_recall": CalculatedMetric(
            "rag_retrieval_recall",
            _mean(rag_retrieval_recalls),
            len(rag_retrieval_recalls),
        ),
        "rag_citation_precision": CalculatedMetric(
            "rag_citation_precision",
            _mean(rag_citation_precisions),
            len(rag_citation_precisions),
        ),
        "rag_citation_recall": CalculatedMetric(
            "rag_citation_recall",
            _mean(rag_citation_recalls),
            len(rag_citation_recalls),
        ),
        "rag_groundedness_score": CalculatedMetric(
            "rag_groundedness_score",
            _mean(rag_groundedness_scores),
            len(rag_groundedness_scores),
        ),
        "rag_unsupported_claim_rate": CalculatedMetric(
            "rag_unsupported_claim_rate",
            _mean(rag_unsupported_claim_rates),
            len(rag_unsupported_claim_rates),
            {
                "unsupported_claim_count": sum(
                    int(trace.get("unsupported_claim_count") or 0)
                    for trace in rag_traces
                )
            },
        ),
        "reliability_success_rate": CalculatedMetric(
            "reliability_success_rate",
            runtime_reliability_summary["success_rate"],
            runtime_reliability_summary["trial_count"],
            {
                "success_count": runtime_reliability_summary["success_count"],
                "expected_trial_count": runtime_reliability_summary[
                    "expected_trial_count"
                ],
            },
        ),
        "reliability_timeout_rate": CalculatedMetric(
            "reliability_timeout_rate",
            runtime_reliability_summary["timeout_rate"],
            runtime_reliability_summary["trial_count"],
            {"timeout_count": runtime_reliability_summary["timeout_count"]},
        ),
        "reliability_oom_rate": CalculatedMetric(
            "reliability_oom_rate",
            runtime_reliability_summary["oom_rate"],
            runtime_reliability_summary["trial_count"],
            {"oom_count": runtime_reliability_summary["oom_count"]},
        ),
        "p99_end_to_end_latency_ms": CalculatedMetric(
            "p99_end_to_end_latency_ms",
            runtime_reliability_summary["p99_end_to_end_latency_ms"],
            runtime_reliability_summary["trial_count"],
        ),
        "latency_variation_coefficient": CalculatedMetric(
            "latency_variation_coefficient",
            runtime_reliability_summary["latency_variation_coefficient"],
            runtime_reliability_summary["trial_count"],
        ),
        "trial_coverage_rate": CalculatedMetric(
            "trial_coverage_rate",
            runtime_reliability_summary["trial_coverage_rate"],
            runtime_reliability_summary["trial_count"],
            {
                "expected_trial_count": runtime_reliability_summary[
                    "expected_trial_count"
                ]
            },
        ),
        "context_stress_success_rate": CalculatedMetric(
            "context_stress_success_rate",
            runtime_reliability_summary["context_stress_success_rate"],
            runtime_reliability_summary["context_stress_trial_count"],
        ),
        "agent_task_success_rate": CalculatedMetric(
            "agent_task_success_rate",
            agent_summary["task_success_rate"],
            agent_summary["agent_case_count"],
            {
                "successful_case_count": agent_summary["successful_case_count"],
                "failed_case_count": agent_summary["failed_case_count"],
            },
        ),
        "agent_plan_validity_rate": CalculatedMetric(
            "agent_plan_validity_rate",
            agent_summary["plan_validity_rate"],
            agent_summary["agent_case_count"],
        ),
        "agent_step_success_rate": CalculatedMetric(
            "agent_step_success_rate",
            agent_summary["step_success_rate"],
            agent_summary["total_step_count"],
            {"failed_step_count": agent_summary["failed_step_count"]},
        ),
        "agent_action_sequence_accuracy": CalculatedMetric(
            "agent_action_sequence_accuracy",
            agent_summary["action_sequence_accuracy"],
            agent_summary["agent_case_count"],
        ),
        "agent_policy_violation_rate": CalculatedMetric(
            "agent_policy_violation_rate",
            agent_summary["policy_violation_rate"],
            agent_summary["agent_case_count"],
        ),
        "agent_final_response_rate": CalculatedMetric(
            "agent_final_response_rate",
            agent_summary["final_response_rate"],
            agent_summary["agent_case_count"],
        ),
        "agent_memory_provenance_rate": CalculatedMetric(
            "agent_memory_provenance_rate",
            agent_summary["memory_provenance_rate"],
            sum(int(trace.get("memory_action_count") or 0) for trace in agent_traces),
        ),
        "agent_tool_retry_recovery_rate": CalculatedMetric(
            "agent_tool_retry_recovery_rate",
            agent_summary["tool_retry_recovery_rate"],
            agent_summary["retried_tool_count"],
            {"recovered_tool_count": agent_summary["recovered_tool_count"]},
        ),
        "agent_replan_success_rate": CalculatedMetric(
            "agent_replan_success_rate",
            agent_summary["replan_success_rate"],
            agent_summary["replan_count"],
            {
                "successful_replan_count": agent_summary[
                    "successful_replan_count"
                ]
            },
        ),
        "agent_recovery_step_success_rate": CalculatedMetric(
            "agent_recovery_step_success_rate",
            agent_summary["recovery_step_success_rate"],
            agent_summary["recovery_step_count"],
            {
                "successful_recovery_step_count": agent_summary[
                    "successful_recovery_step_count"
                ]
            },
        ),
        "agent_approval_compliance_rate": CalculatedMetric(
            "agent_approval_compliance_rate",
            agent_summary["approval_compliance_rate"],
            agent_summary["approval_checkpoint_count"],
            {
                "approved_checkpoint_count": agent_summary[
                    "approved_checkpoint_count"
                ],
                "denied_checkpoint_count": agent_summary[
                    "denied_checkpoint_count"
                ],
            },
        ),
        "agent_approval_provenance_rate": CalculatedMetric(
            "agent_approval_provenance_rate",
            agent_summary["approval_provenance_rate"],
            agent_summary["approval_checkpoint_count"],
        ),
        "agent_pending_approval_rate": CalculatedMetric(
            "agent_pending_approval_rate",
            agent_summary["pending_approval_rate"],
            agent_summary["approval_checkpoint_count"],
            {
                "pending_checkpoint_count": agent_summary[
                    "pending_checkpoint_count"
                ]
            },
        ),
        "agent_observation_coverage_rate": CalculatedMetric(
            "agent_observation_coverage_rate",
            agent_summary["observation_coverage_rate"],
            agent_summary["total_step_count"],
        ),
        "agent_unrecovered_failure_rate": CalculatedMetric(
            "agent_unrecovered_failure_rate",
            agent_summary["unrecovered_failure_rate"],
            agent_summary["agent_case_count"],
        ),
        "groundedness_score": CalculatedMetric(
            "groundedness_score", _mean(groundedness_values), len(groundedness_values)
        ),
        "faithfulness_score": CalculatedMetric(
            "faithfulness_score", _mean(faithfulness_values), len(faithfulness_values)
        ),
        "critical_case_failure_rate": CalculatedMetric(
            "critical_case_failure_rate",
            len(critical_failures) / len(critical_results) if critical_results else None,
            len(critical_results),
            {"failed_critical_cases": len(critical_failures)},
        ),
        "p50_end_to_end_latency_ms": CalculatedMetric(
            "p50_end_to_end_latency_ms", median(latencies) if latencies else None, len(latencies)
        ),
        "p95_end_to_end_latency_ms": CalculatedMetric(
            "p95_end_to_end_latency_ms", _percentile(latencies, 0.95), len(latencies)
        ),
        "p95_ttft_ms": CalculatedMetric("p95_ttft_ms", _percentile(ttfts, 0.95), len(ttfts)),
        "mean_tokens_per_second": CalculatedMetric(
            "mean_tokens_per_second", _mean(tokens_per_second), len(tokens_per_second)
        ),
        "p95_gpu_vram_used_mb": CalculatedMetric(
            "p95_gpu_vram_used_mb", _percentile(vram_values, 0.95), len(vram_values)
        ),
        "oom_rate": CalculatedMetric(
            "oom_rate",
            oom_count / len(bundle.metrics) if bundle.metrics else None,
            len(bundle.metrics),
        ),
        "real_case_count": CalculatedMetric(
            "real_case_count", float(len(real_case_ids)), len(real_case_ids)
        ),
        "critical_case_count": CalculatedMetric(
            "critical_case_count", float(len(critical_case_ids)), len(critical_case_ids)
        ),
    }


def metrics_to_scorecard(metrics: dict[str, CalculatedMetric]) -> dict[str, dict[str, Any]]:
    return {
        key: {
            "value": metric.value,
            "sample_size": metric.sample_size,
            "details": metric.details,
        }
        for key, metric in metrics.items()
    }


def _metric_value(trace: dict[str, Any], key: str) -> float:
    value = trace.get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _rag_retrieval_recall(trace: dict[str, Any]) -> float:
    retrieval = trace.get("retrieval")
    return _metric_value(retrieval, "retrieval_recall") if isinstance(retrieval, dict) else 0.0
