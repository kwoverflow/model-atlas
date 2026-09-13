from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    OperationalAlertIncident,
    OperationalMetricSnapshot,
    OperationalSLOEvaluation,
)
from app.schemas import (
    OperationalAlertRead,
)

from .escalation import _maybe_escalate_incident
from .paging import (
    _create_delivery,
)


def _reconcile_operational_incidents(
    db: Session,
    *,
    snapshot: OperationalMetricSnapshot,
    alerts: list[OperationalAlertRead],
    slo_evaluations: list[OperationalSLOEvaluation],
    settings: Settings,
    observed_at: dt.datetime,
) -> list[UUID]:
    current: dict[str, dict[str, Any]] = {
        alert.key: {
            "alert_key": alert.key,
            "source_type": "derived_alert",
            "severity": alert.severity,
            "route": alert.route,
            "summary": alert.summary,
            "metric_name": alert.metric_name,
            "current_value": alert.current_value,
            "threshold": alert.threshold,
            "slo_evaluation_id": None,
            "context": {
                "snapshot_id": str(snapshot.id),
                "metric_name": alert.metric_name,
                "current_value": alert.current_value,
                "threshold": alert.threshold,
            },
        }
        for alert in alerts
    }
    for evaluation in slo_evaluations:
        if evaluation.status != "breached":
            continue
        alert_key = f"slo:{evaluation.slo_key}"
        severity = "critical" if evaluation.burn_alert_level == "critical" else "warning"
        burn_summary = (
            f"{evaluation.burn_alert_level} multi-window burn"
            if evaluation.burn_alert_level != "none"
            else "no elevated multi-window burn"
        )
        current[alert_key] = {
            "alert_key": alert_key,
            "source_type": "slo",
            "severity": severity,
            "route": f"model-atlas-{severity}",
            "summary": (
                f"{evaluation.scope.title()} SLO is below its configured objective "
                f"with {burn_summary}."
            ),
            "metric_name": "model_atlas_slo_compliance_ratio",
            "current_value": evaluation.observed_ratio,
            "threshold": evaluation.target_ratio,
            "slo_evaluation_id": evaluation.id,
            "context": {
                "snapshot_id": str(snapshot.id),
                "slo_key": evaluation.slo_key,
                "sample_count": evaluation.sample_count,
                "good_sample_count": evaluation.good_sample_count,
                "error_budget_remaining_ratio": (evaluation.error_budget_remaining_ratio),
                "burn_rate": evaluation.burn_rate,
                "short_burn_rate": evaluation.short_burn_rate,
                "burn_alert_level": evaluation.burn_alert_level,
            },
        }

    open_incidents = list(
        db.scalars(
            select(OperationalAlertIncident)
            .where(OperationalAlertIncident.status == "open")
            .with_for_update(skip_locked=True)
        ).all()
    )
    open_by_key = {incident.alert_key: incident for incident in open_incidents}
    delivery_ids: list[UUID] = []
    for alert_key, state in current.items():
        incident = open_by_key.get(alert_key)
        if incident is None:
            incident = OperationalAlertIncident(
                active_key=alert_key,
                alert_key=alert_key,
                source_type=state["source_type"],
                severity=state["severity"],
                route=state["route"],
                summary=state["summary"],
                metric_name=state["metric_name"],
                current_value=state["current_value"],
                threshold=state["threshold"],
                slo_evaluation_id=state["slo_evaluation_id"],
                status="open",
                opened_at=observed_at,
                last_seen_at=observed_at,
                occurrence_count=1,
                transition_version=1,
                latest_context_json=state["context"],
            )
            db.add(incident)
            db.flush()
            if settings.operational_paging_enabled:
                delivery = _create_delivery(
                    db,
                    incident=incident,
                    transition_type="opened",
                    settings=settings,
                    observed_at=observed_at,
                )
                delivery_ids.append(delivery.id)
            continue
        incident.last_seen_at = observed_at
        incident.occurrence_count += 1
        incident.severity = state["severity"]
        incident.route = state["route"]
        incident.summary = state["summary"]
        incident.metric_name = state["metric_name"]
        incident.current_value = state["current_value"]
        incident.threshold = state["threshold"]
        incident.slo_evaluation_id = state["slo_evaluation_id"]
        incident.latest_context_json = state["context"]
        escalation_delivery = _maybe_escalate_incident(
            db,
            incident=incident,
            settings=settings,
            observed_at=observed_at,
        )
        if escalation_delivery is not None:
            delivery_ids.append(escalation_delivery.id)

    for incident in open_incidents:
        if incident.alert_key in current:
            continue
        incident.active_key = None
        incident.status = "resolved"
        incident.resolved_at = observed_at
        incident.last_seen_at = observed_at
        incident.transition_version += 1
        if settings.operational_paging_enabled:
            delivery = _create_delivery(
                db,
                incident=incident,
                transition_type="resolved",
                settings=settings,
                observed_at=observed_at,
            )
            delivery_ids.append(delivery.id)
    return delivery_ids
