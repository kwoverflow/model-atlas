from __future__ import annotations

from app.services.deployment_gate.metrics import CalculatedMetric


def apply_baseline_regressions(
    metrics: dict[str, CalculatedMetric],
    baseline_scorecard: dict[str, dict] | None,
) -> dict[str, CalculatedMetric]:
    if not baseline_scorecard:
        metrics["quality_regression_vs_baseline"] = CalculatedMetric(
            "quality_regression_vs_baseline",
            None,
            0,
            {"reason": "No baseline gate evaluation was provided."},
        )
        metrics["latency_regression_vs_baseline"] = CalculatedMetric(
            "latency_regression_vs_baseline",
            None,
            0,
            {"reason": "No baseline gate evaluation was provided."},
        )
        return metrics

    current_quality = metrics["mean_quality_score"].value
    baseline_quality = baseline_scorecard.get("mean_quality_score", {}).get("value")
    current_latency = metrics["p95_end_to_end_latency_ms"].value
    baseline_latency = baseline_scorecard.get("p95_end_to_end_latency_ms", {}).get("value")

    quality_delta = (
        current_quality - baseline_quality
        if current_quality is not None and baseline_quality is not None
        else None
    )
    latency_delta = (
        current_latency - baseline_latency
        if current_latency is not None and baseline_latency is not None
        else None
    )

    metrics["quality_regression_vs_baseline"] = CalculatedMetric(
        "quality_regression_vs_baseline",
        quality_delta,
        metrics["mean_quality_score"].sample_size if quality_delta is not None else 0,
        {"baseline_value": baseline_quality},
    )
    metrics["latency_regression_vs_baseline"] = CalculatedMetric(
        "latency_regression_vs_baseline",
        latency_delta,
        metrics["p95_end_to_end_latency_ms"].sample_size if latency_delta is not None else 0,
        {"baseline_value": baseline_latency},
    )
    return metrics
