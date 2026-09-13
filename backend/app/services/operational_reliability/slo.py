from __future__ import annotations

import datetime as dt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    OperationalMetricPoint,
    OperationalMetricSnapshot,
    OperationalSLOEvaluation,
)

from .burn_rate import _burn_alert_level, _burn_rate, _error_budget_remaining
from .contracts import (
    EMPTY_LABELS_HASH,
    SLODefinition,
    SLOWindowStats,
)
from .utils import (
    _canonical_hash,
    _utc,
)


def _evaluate_slos(
    db: Session,
    *,
    snapshot: OperationalMetricSnapshot,
    settings: Settings,
    observed_at: dt.datetime,
) -> list[OperationalSLOEvaluation]:
    definitions = (
        SLODefinition(
            key="identity_session_hygiene",
            scope="identity",
            target_ratio=settings.operational_identity_slo_target,
            metric_names=(
                "model_atlas_browser_session_retention_due",
                "model_atlas_browser_session_inactive_provider_token",
            ),
            good_condition=("retention_due == 0 AND inactive_provider_token == 0"),
            evaluator=lambda values: (
                values["model_atlas_browser_session_retention_due"] == 0
                and values["model_atlas_browser_session_inactive_provider_token"] == 0
            ),
        ),
        SLODefinition(
            key="worker_control_plane_availability",
            scope="worker",
            target_ratio=settings.operational_worker_slo_target,
            metric_names=(
                "model_atlas_worker_online",
                "model_atlas_job_expired_lease_count",
            ),
            good_condition="worker_online >= 1 AND expired_lease_count == 0",
            evaluator=lambda values: (
                values["model_atlas_worker_online"] >= 1
                and values["model_atlas_job_expired_lease_count"] == 0
            ),
        ),
    )
    window_started_at = observed_at - dt.timedelta(seconds=settings.operational_slo_window_seconds)
    short_window_started_at = observed_at - dt.timedelta(
        seconds=settings.operational_slo_short_window_seconds
    )
    required_names = sorted(
        {metric for definition in definitions for metric in definition.metric_names}
    )
    snapshot_rows = db.execute(
        select(
            OperationalMetricSnapshot.id,
            OperationalMetricSnapshot.generated_at,
        )
        .where(
            OperationalMetricSnapshot.generated_at >= window_started_at,
            OperationalMetricSnapshot.generated_at <= observed_at,
        )
        .order_by(OperationalMetricSnapshot.generated_at)
    ).all()
    values_by_snapshot: dict[UUID, dict[str, float]] = {
        snapshot_id: {} for snapshot_id, _generated_at in snapshot_rows
    }
    rows = db.execute(
        select(
            OperationalMetricPoint.snapshot_id,
            OperationalMetricPoint.metric_name,
            OperationalMetricPoint.metric_value,
        ).where(
            OperationalMetricPoint.snapshot_id.in_(values_by_snapshot),
            OperationalMetricPoint.metric_name.in_(required_names),
            OperationalMetricPoint.labels_hash == EMPTY_LABELS_HASH,
        )
    ).all()
    for snapshot_id, metric_name, metric_value in rows:
        values_by_snapshot.setdefault(snapshot_id, {})[metric_name] = metric_value
    samples_by_snapshot = [
        (_utc(generated_at), values_by_snapshot.get(snapshot_id, {}))
        for snapshot_id, generated_at in snapshot_rows
    ]

    evaluations: list[OperationalSLOEvaluation] = []
    for definition in definitions:
        long_window = _slo_window_stats(
            samples_by_snapshot,
            definition=definition,
            window_started_at=window_started_at,
            window_ended_at=observed_at,
            interval_seconds=settings.operational_snapshot_interval_seconds,
        )
        short_window = _slo_window_stats(
            samples_by_snapshot,
            definition=definition,
            window_started_at=short_window_started_at,
            window_ended_at=observed_at,
            interval_seconds=settings.operational_snapshot_interval_seconds,
        )
        error_budget_remaining_ratio = _error_budget_remaining(
            long_window.observed_ratio,
            definition.target_ratio,
        )
        burn_rate = _burn_rate(
            long_window.observed_ratio,
            definition.target_ratio,
        )
        short_burn_rate = _burn_rate(
            short_window.observed_ratio,
            definition.target_ratio,
        )
        status = (
            "insufficient"
            if long_window.sample_count < settings.operational_slo_min_samples
            else "met"
            if long_window.observed_ratio is not None
            and long_window.observed_ratio >= definition.target_ratio
            else "breached"
        )
        burn_alert_level = _burn_alert_level(
            status=status,
            long_burn_rate=burn_rate,
            short_burn_rate=short_burn_rate,
            short_sample_count=short_window.sample_count,
            settings=settings,
        )
        canonical = {
            "snapshot_id": str(snapshot.id),
            "slo_key": definition.key,
            "scope": definition.scope,
            "status": status,
            "target_ratio": definition.target_ratio,
            "observed_ratio": long_window.observed_ratio,
            "short_observed_ratio": short_window.observed_ratio,
            "error_budget_remaining_ratio": error_budget_remaining_ratio,
            "burn_rate": burn_rate,
            "short_burn_rate": short_burn_rate,
            "burn_alert_level": burn_alert_level,
            "window_seconds": settings.operational_slo_window_seconds,
            "short_window_seconds": settings.operational_slo_short_window_seconds,
            "sample_count": long_window.sample_count,
            "good_sample_count": long_window.good_sample_count,
            "actual_sample_count": long_window.actual_sample_count,
            "short_sample_count": short_window.sample_count,
            "short_good_sample_count": short_window.good_sample_count,
            "window_started_at": window_started_at.isoformat(),
            "window_ended_at": observed_at.isoformat(),
            "condition": definition.good_condition,
        }
        evaluation = OperationalSLOEvaluation(
            snapshot_id=snapshot.id,
            slo_key=definition.key,
            scope=definition.scope,
            status=status,
            target_ratio=definition.target_ratio,
            observed_ratio=long_window.observed_ratio,
            error_budget_remaining_ratio=error_budget_remaining_ratio,
            window_seconds=settings.operational_slo_window_seconds,
            short_window_seconds=settings.operational_slo_short_window_seconds,
            short_observed_ratio=short_window.observed_ratio,
            burn_rate=burn_rate,
            short_burn_rate=short_burn_rate,
            burn_alert_level=burn_alert_level,
            sample_count=long_window.sample_count,
            good_sample_count=long_window.good_sample_count,
            window_started_at=window_started_at,
            window_ended_at=observed_at,
            evaluated_at=observed_at,
            details_json={
                "metric_names": list(definition.metric_names),
                "good_condition": definition.good_condition,
                "minimum_samples": settings.operational_slo_min_samples,
                "actual_sample_count": long_window.actual_sample_count,
                "missing_sample_count": long_window.missing_sample_count,
                "effective_window_started_at": (
                    long_window.effective_window_started_at.isoformat()
                    if long_window.effective_window_started_at is not None
                    else None
                ),
                "short_window": {
                    "sample_count": short_window.sample_count,
                    "good_sample_count": short_window.good_sample_count,
                    "actual_sample_count": short_window.actual_sample_count,
                    "missing_sample_count": short_window.missing_sample_count,
                    "effective_window_started_at": (
                        short_window.effective_window_started_at.isoformat()
                        if short_window.effective_window_started_at is not None
                        else None
                    ),
                },
            },
            evaluation_hash=_canonical_hash(canonical),
            created_at=observed_at,
        )
        db.add(evaluation)
        evaluations.append(evaluation)
    return evaluations


def _slo_window_stats(
    samples_by_snapshot: list[tuple[dt.datetime, dict[str, float]]],
    *,
    definition: SLODefinition,
    window_started_at: dt.datetime,
    window_ended_at: dt.datetime,
    interval_seconds: int,
) -> SLOWindowStats:
    window_samples = [
        (generated_at, values)
        for generated_at, values in samples_by_snapshot
        if window_started_at <= generated_at <= window_ended_at
    ]
    complete_samples = [
        values
        for _generated_at, values in window_samples
        if all(metric_name in values for metric_name in definition.metric_names)
    ]
    effective_window_start = window_samples[0][0] if window_samples else None
    scheduled_sample_count = (
        int((window_ended_at - effective_window_start).total_seconds() // interval_seconds) + 1
        if effective_window_start is not None
        else 0
    )
    sample_count = max(len(window_samples), scheduled_sample_count)
    good_sample_count = sum(1 for values in complete_samples if definition.evaluator(values))
    observed_ratio = round(good_sample_count / sample_count, 6) if sample_count else None
    return SLOWindowStats(
        observed_ratio=observed_ratio,
        sample_count=sample_count,
        good_sample_count=good_sample_count,
        actual_sample_count=len(complete_samples),
        missing_sample_count=max(0, sample_count - len(complete_samples)),
        effective_window_started_at=effective_window_start,
    )
