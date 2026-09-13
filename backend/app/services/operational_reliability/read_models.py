from __future__ import annotations

from typing import Any

from app.models import (
    OperationalAlertDelivery,
    OperationalAlertIncident,
    OperationalAlertIncidentAction,
    OperationalMetricSnapshot,
    OperationalSLOEvaluation,
)
from app.schemas import (
    OperationalAlertDeliveryRead,
    OperationalAlertIncidentActionRead,
    OperationalAlertIncidentRead,
    OperationalSLOEvaluationRead,
    OperationalSnapshotSummaryRead,
)

from .contracts import (
    PAGING_EVENT_VERSION,
)


def _snapshot_read(
    snapshot: OperationalMetricSnapshot,
    values: dict[str, float],
) -> OperationalSnapshotSummaryRead:
    return OperationalSnapshotSummaryRead(
        id=snapshot.id,
        bucket_started_at=snapshot.bucket_started_at,
        generated_at=snapshot.generated_at,
        expires_at=snapshot.expires_at,
        health=snapshot.health,
        sample_count=snapshot.sample_count,
        alert_count=snapshot.alert_count,
        content_hash=snapshot.content_hash,
        worker_online=values.get("model_atlas_worker_online", 0),
        queue_depth=values.get("model_atlas_job_queue_depth", 0),
        identity_retention_due=values.get(
            "model_atlas_browser_session_retention_due",
            0,
        ),
        identity_inactive_provider_token=values.get(
            "model_atlas_browser_session_inactive_provider_token",
            0,
        ),
    )


def _slo_read(row: OperationalSLOEvaluation) -> OperationalSLOEvaluationRead:
    return OperationalSLOEvaluationRead(
        id=row.id,
        snapshot_id=row.snapshot_id,
        slo_key=row.slo_key,
        scope=row.scope,
        status=row.status,
        target_ratio=row.target_ratio,
        observed_ratio=row.observed_ratio,
        error_budget_remaining_ratio=row.error_budget_remaining_ratio,
        window_seconds=row.window_seconds,
        short_window_seconds=row.short_window_seconds,
        short_observed_ratio=row.short_observed_ratio,
        burn_rate=row.burn_rate,
        short_burn_rate=row.short_burn_rate,
        burn_alert_level=row.burn_alert_level,
        sample_count=row.sample_count,
        good_sample_count=row.good_sample_count,
        window_started_at=row.window_started_at,
        window_ended_at=row.window_ended_at,
        evaluated_at=row.evaluated_at,
        details_json=row.details_json,
        evaluation_hash=row.evaluation_hash,
    )


def _incident_read(row: OperationalAlertIncident) -> OperationalAlertIncidentRead:
    return OperationalAlertIncidentRead(
        id=row.id,
        alert_key=row.alert_key,
        source_type=row.source_type,
        severity=row.severity,
        route=row.route,
        summary=row.summary,
        metric_name=row.metric_name,
        current_value=row.current_value,
        threshold=row.threshold,
        slo_evaluation_id=row.slo_evaluation_id,
        status=row.status,
        opened_at=row.opened_at,
        last_seen_at=row.last_seen_at,
        resolved_at=row.resolved_at,
        acknowledged_at=row.acknowledged_at,
        acknowledged_by_identity_json=row.acknowledged_by_identity_json,
        assigned_to=row.assigned_to,
        escalation_level=row.escalation_level,
        occurrence_count=row.occurrence_count,
        transition_version=row.transition_version,
    )


def _incident_action_read(
    row: OperationalAlertIncidentAction,
) -> OperationalAlertIncidentActionRead:
    return OperationalAlertIncidentActionRead(
        id=row.id,
        incident_id=row.incident_id,
        action_type=row.action_type,
        reason=row.reason,
        assignee=row.assignee,
        actor_identity_json=row.actor_identity_json,
        identity_verified=row.identity_verified,
        occurred_at=row.occurred_at,
        previous_action_hash=row.previous_action_hash,
        action_hash=row.action_hash,
    )


def _delivery_read(row: OperationalAlertDelivery) -> OperationalAlertDeliveryRead:
    return OperationalAlertDeliveryRead(
        id=row.id,
        incident_id=row.incident_id,
        delivery_job_id=row.delivery_job_id,
        transition_type=row.transition_type,
        transition_version=row.transition_version,
        destination_fingerprint=row.destination_hash[:16],
        signing_key_id=row.signing_key_id,
        status=row.status,
        payload_hash=row.payload_hash,
        requested_at=row.requested_at,
        last_attempt_at=row.last_attempt_at,
        attempt_count=row.attempt_count,
        response_status=row.response_status,
        response_hash=row.response_hash,
        provider_name=row.provider_name,
        provider_event_id=row.provider_event_id,
        provider_receipt_id=row.provider_receipt_id,
        provider_accepted_at=row.provider_accepted_at,
        error_message=row.error_message,
        delivered_at=row.delivered_at,
    )


def _delivery_result(
    delivery: OperationalAlertDelivery,
    *,
    replay: bool,
) -> dict[str, Any]:
    return {
        "schema_version": PAGING_EVENT_VERSION,
        "delivery_id": str(delivery.id),
        "incident_id": str(delivery.incident_id),
        "status": delivery.status,
        "response_status": delivery.response_status,
        "response_hash": delivery.response_hash,
        "provider_name": delivery.provider_name,
        "provider_event_id": delivery.provider_event_id,
        "provider_receipt_id": delivery.provider_receipt_id,
        "provider_accepted_at": (
            delivery.provider_accepted_at.isoformat() if delivery.provider_accepted_at else None
        ),
        "delivered_at": (delivery.delivered_at.isoformat() if delivery.delivered_at else None),
        "replay": replay,
    }
