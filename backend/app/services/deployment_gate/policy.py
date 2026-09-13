from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models import AcceptancePolicyRule
from app.services.deployment_gate.metrics import CalculatedMetric

POLICY_ENGINE_VERSION = "gate-policy-v1"


@dataclass(frozen=True)
class EvaluatedRule:
    rule: AcceptancePolicyRule
    metric_key: str
    metric_value: float | None
    sample_size: int
    status: str
    severity: str
    details: dict[str, Any]


def _compare(value: float, operator: str, threshold: float) -> bool:
    match operator:
        case "gte":
            return value >= threshold
        case "lte":
            return value <= threshold
        case "eq":
            return value == threshold
        case "gt":
            return value > threshold
        case "lt":
            return value < threshold
        case _:
            raise ValueError(f"Unsupported policy operator: {operator}")


def evaluate_policy_rules(
    rules: list[AcceptancePolicyRule],
    metrics: dict[str, CalculatedMetric],
) -> list[EvaluatedRule]:
    evaluated: list[EvaluatedRule] = []
    for rule in rules:
        if not rule.enabled:
            continue
        metric_key = rule.metric_definition.key
        metric = metrics.get(metric_key)
        if metric is None or metric.value is None:
            evaluated.append(
                EvaluatedRule(
                    rule=rule,
                    metric_key=metric_key,
                    metric_value=None,
                    sample_size=0,
                    status="insufficient",
                    severity=rule.severity,
                    details={
                        "reason": "Required metric was not available.",
                        "required": rule.required,
                    },
                )
            )
            continue
        if rule.minimum_sample_size is not None and metric.sample_size < rule.minimum_sample_size:
            evaluated.append(
                EvaluatedRule(
                    rule=rule,
                    metric_key=metric_key,
                    metric_value=metric.value,
                    sample_size=metric.sample_size,
                    status="insufficient",
                    severity=rule.severity,
                    details={
                        "reason": "Minimum sample size was not met.",
                        "minimum_sample_size": rule.minimum_sample_size,
                    },
                )
            )
            continue
        passed = _compare(metric.value, rule.operator, rule.threshold_value)
        evaluated.append(
            EvaluatedRule(
                rule=rule,
                metric_key=metric_key,
                metric_value=metric.value,
                sample_size=metric.sample_size,
                status="pass" if passed else "fail",
                severity=rule.severity,
                details={
                    "operator": rule.operator,
                    "threshold_value": rule.threshold_value,
                    "message_on_fail": None if passed else rule.message_on_fail,
                    **metric.details,
                },
            )
        )
    return evaluated
