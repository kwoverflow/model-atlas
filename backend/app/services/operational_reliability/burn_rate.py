from __future__ import annotations

from app.core.config import Settings


def _burn_alert_level(
    *,
    status: str,
    long_burn_rate: float | None,
    short_burn_rate: float | None,
    short_sample_count: int,
    settings: Settings,
) -> str:
    if (
        status == "insufficient"
        or short_sample_count < settings.operational_slo_min_samples
        or long_burn_rate is None
        or short_burn_rate is None
    ):
        return "none"
    if (
        long_burn_rate >= settings.operational_slo_critical_burn_rate
        and short_burn_rate >= settings.operational_slo_critical_burn_rate
    ):
        return "critical"
    if (
        long_burn_rate >= settings.operational_slo_warning_burn_rate
        and short_burn_rate >= settings.operational_slo_warning_burn_rate
    ):
        return "warning"
    return "none"


def _error_budget_remaining(
    observed_ratio: float | None,
    target_ratio: float,
) -> float | None:
    if observed_ratio is None:
        return None
    allowed_bad_ratio = 1 - target_ratio
    if allowed_bad_ratio <= 0:
        return 1.0 if observed_ratio >= 1 else 0.0
    observed_bad_ratio = 1 - observed_ratio
    return round(
        max(0.0, min(1.0, (allowed_bad_ratio - observed_bad_ratio) / allowed_bad_ratio)),
        6,
    )


def _burn_rate(
    observed_ratio: float | None,
    target_ratio: float,
) -> float | None:
    if observed_ratio is None:
        return None
    allowed_bad_ratio = 1 - target_ratio
    if allowed_bad_ratio <= 0:
        return 0.0 if observed_ratio >= 1 else 1_000_000.0
    return round(max(0.0, (1 - observed_ratio) / allowed_bad_ratio), 6)
