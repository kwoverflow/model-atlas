from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import median
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import BenchmarkResult, BenchmarkRun, EvaluationCase, InferenceMetric
from app.schemas import PromptRegressionMetric, PromptRegressionReport, PromptRegressionRow
from app.services.deployment_gate.baselines import get_active_baseline_gate


@dataclass
class PromptEvidence:
    runs: list[BenchmarkRun] = field(default_factory=list)
    results: list[BenchmarkResult] = field(default_factory=list)
    metrics: list[InferenceMetric] = field(default_factory=list)


def build_prompt_regression_report(
    db: Session,
    *,
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
) -> PromptRegressionReport:
    runs = _completed_runs(
        db,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
    )
    baseline_gate = _baseline_gate(
        db,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
    )
    baseline_scorecard = (
        baseline_gate.scorecard_json.get("metrics", {}) if baseline_gate is not None else {}
    )
    baseline_prompt_version_id = _baseline_prompt_version_id(db, baseline_gate)
    grouped = _group_by_prompt(runs)
    rows = [
        _row(
            evidence=evidence,
            baseline_scorecard=baseline_scorecard,
            baseline_prompt_version_id=baseline_prompt_version_id,
        )
        for evidence in grouped.values()
    ]
    rows.sort(
        key=lambda row: (
            row.is_baseline_prompt is False,
            row.mean_quality_score.value is None,
            -(row.mean_quality_score.value or 0),
            row.prompt_name,
        )
    )
    return PromptRegressionReport(
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
        baseline_gate_evaluation_id=baseline_gate.id if baseline_gate else None,
        baseline_prompt_version_id=baseline_prompt_version_id,
        row_count=len(rows),
        rows=rows,
    )


def _completed_runs(
    db: Session,
    *,
    deployment_configuration_id: UUID | None,
    evaluation_suite_id: UUID | None,
) -> list[BenchmarkRun]:
    query = (
        select(BenchmarkRun)
        .options(
            selectinload(BenchmarkRun.prompt_version),
            selectinload(BenchmarkRun.results).selectinload(BenchmarkResult.evaluation_case),
            selectinload(BenchmarkRun.inference_metrics),
        )
        .where(BenchmarkRun.status == "completed")
    )
    if deployment_configuration_id is not None:
        query = query.where(BenchmarkRun.deployment_configuration_id == deployment_configuration_id)
    if evaluation_suite_id is not None:
        query = query.where(BenchmarkRun.evaluation_suite_id == evaluation_suite_id)
    return list(db.scalars(query.order_by(BenchmarkRun.started_at.desc())))


def _baseline_gate(
    db: Session,
    *,
    deployment_configuration_id: UUID | None,
    evaluation_suite_id: UUID | None,
    acceptance_policy_id: UUID | None,
):
    if (
        deployment_configuration_id is None
        or evaluation_suite_id is None
        or acceptance_policy_id is None
    ):
        return None
    return get_active_baseline_gate(
        db,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
    )


def _baseline_prompt_version_id(db: Session, baseline_gate) -> UUID | None:
    if baseline_gate is None:
        return None
    run_ids = baseline_gate.evidence_snapshot_json.get("benchmark_run_ids", [])
    if not run_ids:
        return None
    prompt_ids = set(
        db.scalars(
            select(BenchmarkRun.prompt_version_id).where(BenchmarkRun.id.in_(run_ids))
        )
    )
    return next(iter(prompt_ids)) if len(prompt_ids) == 1 else None


def _group_by_prompt(runs: list[BenchmarkRun]) -> dict[UUID, PromptEvidence]:
    grouped: dict[UUID, PromptEvidence] = defaultdict(PromptEvidence)
    for run in runs:
        evidence = grouped[run.prompt_version_id]
        evidence.runs.append(run)
        evidence.results.extend(run.results)
        evidence.metrics.extend(run.inference_metrics)
    return grouped


def _row(
    *,
    evidence: PromptEvidence,
    baseline_scorecard: dict,
    baseline_prompt_version_id: UUID | None,
) -> PromptRegressionRow:
    prompt = evidence.runs[0].prompt_version
    metrics = _metrics(evidence)
    return PromptRegressionRow(
        prompt_version_id=prompt.id,
        prompt_name=prompt.name,
        version_label=prompt.version_label,
        prompt_hash=prompt.prompt_hash,
        benchmark_run_ids=[run.id for run in evidence.runs],
        run_count=len(evidence.runs),
        result_count=len(evidence.results),
        metric_count=len(evidence.metrics),
        data_sources=sorted(
            {
                source
                for source in [
                    *[run.data_source for run in evidence.runs],
                    *[result.data_source for result in evidence.results],
                    *[metric.data_source for metric in evidence.metrics],
                ]
            }
        ),
        is_baseline_prompt=baseline_prompt_version_id == prompt.id,
        mean_quality_score=_metric_with_delta(
            metrics["mean_quality_score"],
            baseline_scorecard,
            "mean_quality_score",
        ),
        groundedness_score=_metric_with_delta(
            metrics["groundedness_score"],
            baseline_scorecard,
            "groundedness_score",
        ),
        faithfulness_score=_metric_with_delta(
            metrics["faithfulness_score"],
            baseline_scorecard,
            "faithfulness_score",
        ),
        json_validity_rate=_metric_with_delta(
            metrics["json_validity_rate"],
            baseline_scorecard,
            "json_validity_rate",
        ),
        tool_call_validity_rate=_metric_with_delta(
            metrics["tool_call_validity_rate"],
            baseline_scorecard,
            "tool_call_validity_rate",
        ),
        critical_case_failure_rate=_metric_with_delta(
            metrics["critical_case_failure_rate"],
            baseline_scorecard,
            "critical_case_failure_rate",
        ),
        p95_end_to_end_latency_ms=_metric_with_delta(
            metrics["p95_end_to_end_latency_ms"],
            baseline_scorecard,
            "p95_end_to_end_latency_ms",
        ),
        p95_ttft_ms=_metric_with_delta(metrics["p95_ttft_ms"], baseline_scorecard, "p95_ttft_ms"),
        mean_tokens_per_second=_metric_with_delta(
            metrics["mean_tokens_per_second"],
            baseline_scorecard,
            "mean_tokens_per_second",
        ),
        oom_rate=_metric_with_delta(metrics["oom_rate"], baseline_scorecard, "oom_rate"),
        risk_flags=_risk_flags(metrics, baseline_scorecard),
    )


def _metrics(evidence: PromptEvidence) -> dict[str, tuple[float | None, int]]:
    quality_values = [r.quality_score for r in evidence.results if r.quality_score is not None]
    groundedness_values = [
        r.groundedness_score for r in evidence.results if r.groundedness_score is not None
    ]
    faithfulness_values = [
        r.faithfulness_score for r in evidence.results if r.faithfulness_score is not None
    ]
    json_results = [result for result in evidence.results if _is_json_case(result.evaluation_case)]
    tool_results = [result for result in evidence.results if _is_tool_case(result.evaluation_case)]
    critical_results = [
        result
        for result in evidence.results
        if result.evaluation_case is not None and result.evaluation_case.criticality == "critical"
    ]
    critical_failures = [
        result
        for result in critical_results
        if _is_critical_failure(result, result.evaluation_case)
    ]
    latencies = [metric.end_to_end_latency_ms for metric in evidence.metrics]
    ttfts = [metric.ttft_ms for metric in evidence.metrics]
    tokens_per_second = [metric.tokens_per_second for metric in evidence.metrics]
    oom_count = sum(1 for metric in evidence.metrics if metric.oom_occurred)

    return {
        "mean_quality_score": (_mean(quality_values), len(quality_values)),
        "groundedness_score": (_mean(groundedness_values), len(groundedness_values)),
        "faithfulness_score": (_mean(faithfulness_values), len(faithfulness_values)),
        "json_validity_rate": (
            _rate(json_results, lambda result: result.json_valid),
            len(json_results),
        ),
        "tool_call_validity_rate": (
            _rate(tool_results, lambda result: result.tool_call_valid),
            len(tool_results),
        ),
        "critical_case_failure_rate": (
            len(critical_failures) / len(critical_results) if critical_results else None,
            len(critical_results),
        ),
        "p50_end_to_end_latency_ms": (median(latencies) if latencies else None, len(latencies)),
        "p95_end_to_end_latency_ms": (_percentile(latencies, 0.95), len(latencies)),
        "p95_ttft_ms": (_percentile(ttfts, 0.95), len(ttfts)),
        "mean_tokens_per_second": (_mean(tokens_per_second), len(tokens_per_second)),
        "oom_rate": (
            oom_count / len(evidence.metrics) if evidence.metrics else None,
            len(evidence.metrics),
        ),
    }


def _metric_with_delta(
    metric: tuple[float | None, int],
    baseline_scorecard: dict,
    key: str,
) -> PromptRegressionMetric:
    value, sample_size = metric
    baseline_value = baseline_scorecard.get(key, {}).get("value")
    delta = (
        value - baseline_value
        if value is not None and isinstance(baseline_value, int | float)
        else None
    )
    return PromptRegressionMetric(value=value, sample_size=sample_size, delta_vs_baseline=delta)


def _risk_flags(
    metrics: dict[str, tuple[float | None, int]],
    baseline_scorecard: dict,
) -> list[str]:
    flags: list[str] = []
    quality_delta = _delta(
        metrics["mean_quality_score"][0],
        baseline_scorecard,
        "mean_quality_score",
    )
    latency_delta = _delta(
        metrics["p95_end_to_end_latency_ms"][0],
        baseline_scorecard,
        "p95_end_to_end_latency_ms",
    )
    critical_failure_rate = metrics["critical_case_failure_rate"][0]
    oom_rate = metrics["oom_rate"][0]
    if quality_delta is not None and quality_delta <= -0.03:
        flags.append("quality_regression")
    if latency_delta is not None and latency_delta >= 500:
        flags.append("latency_regression")
    if critical_failure_rate is not None and critical_failure_rate > 0:
        flags.append("critical_failures")
    if oom_rate is not None and oom_rate > 0:
        flags.append("oom_risk")
    if metrics["mean_quality_score"][1] < 3:
        flags.append("low_sample_size")
    return flags


def _delta(value: float | None, baseline_scorecard: dict, key: str) -> float | None:
    baseline_value = baseline_scorecard.get(key, {}).get("value")
    if value is None or not isinstance(baseline_value, int | float):
        return None
    return value - baseline_value


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _rate(results: list[BenchmarkResult], predicate) -> float | None:
    if not results:
        return None
    return sum(1 for result in results if predicate(result)) / len(results)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(0, min(len(sorted_values) - 1, math.ceil(percentile * len(sorted_values)) - 1))
    return sorted_values[index]


def _is_json_case(case: EvaluationCase | None) -> bool:
    if case is None:
        return False
    return "json" in case.category.lower() or case.expected_output_json is not None


def _is_tool_case(case: EvaluationCase | None) -> bool:
    if case is None:
        return False
    return "tool" in case.category.lower() or case.expected_tool_schema_json is not None


def _is_critical_failure(result: BenchmarkResult, case: EvaluationCase | None) -> bool:
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
    if _is_tool_case(case) and not result.tool_call_valid:
        return True
    if "ground" in case.category.lower() and (
        (result.groundedness_score is not None and result.groundedness_score < 0.8)
        or (result.faithfulness_score is not None and result.faithfulness_score < 0.8)
    ):
        return True
    return False
