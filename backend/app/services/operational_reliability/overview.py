from __future__ import annotations

import datetime as dt
from collections import Counter
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    OperationalAlertDelivery,
    OperationalAlertIncident,
    OperationalAlertIncidentAction,
    OperationalMetricPoint,
    OperationalMetricSnapshot,
    OperationalSLOEvaluation,
)
from app.schemas import (
    OperationalReliabilityOverviewRead,
    OperationalReliabilityPolicyRead,
)
from app.services.operator_identity import SignerIdentity

from .contracts import (
    EMPTY_LABELS_HASH,
    OPERATIONAL_RELIABILITY_VERSION,
)
from .paging import (
    _paging_configuration_state,
    _paging_destination_label,
    _paging_provider,
)
from .permissions import (
    operational_reliability_permissions,
)
from .read_models import (
    _delivery_read,
    _incident_action_read,
    _incident_read,
    _slo_read,
    _snapshot_read,
)
from .readiness import _build_staging_readiness
from .utils import (
    _utc,
)


def build_operational_reliability_overview(
    db: Session,
    *,
    settings: Settings,
    signer_identity: SignerIdentity,
    snapshot_limit: int = 60,
    incident_limit: int = 100,
    action_limit: int = 200,
    delivery_limit: int = 100,
    now: dt.datetime | None = None,
) -> OperationalReliabilityOverviewRead:
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    snapshots = list(
        db.scalars(
            select(OperationalMetricSnapshot)
            .order_by(OperationalMetricSnapshot.generated_at.desc())
            .limit(max(1, min(snapshot_limit, 500)))
        ).all()
    )
    metric_names = (
        "model_atlas_worker_online",
        "model_atlas_job_queue_depth",
        "model_atlas_browser_session_retention_due",
        "model_atlas_browser_session_inactive_provider_token",
    )
    point_values: dict[UUID, dict[str, float]] = {}
    if snapshots:
        points = db.execute(
            select(
                OperationalMetricPoint.snapshot_id,
                OperationalMetricPoint.metric_name,
                OperationalMetricPoint.metric_value,
            ).where(
                OperationalMetricPoint.snapshot_id.in_([snapshot.id for snapshot in snapshots]),
                OperationalMetricPoint.metric_name.in_(metric_names),
                OperationalMetricPoint.labels_hash == EMPTY_LABELS_HASH,
            )
        ).all()
        for snapshot_id, metric_name, metric_value in points:
            point_values.setdefault(snapshot_id, {})[metric_name] = metric_value

    evaluations = list(
        db.scalars(
            select(OperationalSLOEvaluation).order_by(OperationalSLOEvaluation.evaluated_at.desc())
        ).all()
    )
    latest_evaluations: dict[str, OperationalSLOEvaluation] = {}
    for evaluation in evaluations:
        latest_evaluations.setdefault(evaluation.slo_key, evaluation)

    incidents = list(
        db.scalars(
            select(OperationalAlertIncident)
            .order_by(
                OperationalAlertIncident.last_seen_at.desc(),
                OperationalAlertIncident.created_at.desc(),
            )
            .limit(max(1, min(incident_limit, 500)))
        ).all()
    )
    incident_actions = list(
        db.scalars(
            select(OperationalAlertIncidentAction)
            .order_by(OperationalAlertIncidentAction.occurred_at.desc())
            .limit(max(1, min(action_limit, 1000)))
        ).all()
    )
    deliveries = list(
        db.scalars(
            select(OperationalAlertDelivery)
            .order_by(OperationalAlertDelivery.requested_at.desc())
            .limit(max(1, min(delivery_limit, 500)))
        ).all()
    )
    latest_receipt_delivery = db.scalar(
        select(OperationalAlertDelivery)
        .where(
            OperationalAlertDelivery.status == "delivered",
            OperationalAlertDelivery.provider_receipt_id.is_not(None),
        )
        .order_by(OperationalAlertDelivery.provider_accepted_at.desc())
        .limit(1)
    )
    snapshot_count = int(
        db.scalar(select(func.count()).select_from(OperationalMetricSnapshot)) or 0
    )
    open_incident_count = int(
        db.scalar(
            select(func.count())
            .select_from(OperationalAlertIncident)
            .where(OperationalAlertIncident.status == "open")
        )
        or 0
    )
    open_critical_incident_count = int(
        db.scalar(
            select(func.count())
            .select_from(OperationalAlertIncident)
            .where(
                OperationalAlertIncident.status == "open",
                OperationalAlertIncident.severity == "critical",
            )
        )
        or 0
    )
    delivery_counts = Counter(
        str(status) for status in db.scalars(select(OperationalAlertDelivery.status)).all()
    )
    latest_slo_rows = list(latest_evaluations.values())
    health = "healthy"
    if open_critical_incident_count or any(item.status == "breached" for item in latest_slo_rows):
        health = "critical"
    elif (
        open_incident_count
        or any(item.status == "insufficient" for item in latest_slo_rows)
        or delivery_counts["failed"]
    ):
        health = "degraded"

    snapshot_reads = [
        _snapshot_read(snapshot, point_values.get(snapshot.id, {})) for snapshot in snapshots
    ]
    paging_configuration = _paging_configuration_state(settings)
    staging_readiness = _build_staging_readiness(
        settings=settings,
        configuration=paging_configuration,
        latest_receipt_delivery=latest_receipt_delivery,
        observed_at=observed_at,
    )
    return OperationalReliabilityOverviewRead(
        schema_version=OPERATIONAL_RELIABILITY_VERSION,
        generated_at=observed_at,
        health=health,
        snapshot_count=snapshot_count,
        open_incident_count=open_incident_count,
        delivery_status_counts={
            status: delivery_counts[status] for status in ("queued", "delivered", "failed")
        },
        latest_snapshot=snapshot_reads[0] if snapshot_reads else None,
        latest_slo_evaluations=[
            _slo_read(item) for item in sorted(latest_slo_rows, key=lambda row: row.scope)
        ],
        snapshots=snapshot_reads,
        incidents=[_incident_read(item) for item in incidents],
        incident_actions=[_incident_action_read(item) for item in incident_actions],
        deliveries=[_delivery_read(item) for item in deliveries],
        policy=OperationalReliabilityPolicyRead(
            snapshot_enabled=settings.operational_snapshot_enabled,
            snapshot_interval_seconds=settings.operational_snapshot_interval_seconds,
            snapshot_retention_days=settings.operational_snapshot_retention_days,
            slo_window_seconds=settings.operational_slo_window_seconds,
            slo_short_window_seconds=(settings.operational_slo_short_window_seconds),
            slo_min_samples=settings.operational_slo_min_samples,
            identity_slo_target=settings.operational_identity_slo_target,
            worker_slo_target=settings.operational_worker_slo_target,
            slo_warning_burn_rate=settings.operational_slo_warning_burn_rate,
            slo_critical_burn_rate=settings.operational_slo_critical_burn_rate,
            incident_escalation_seconds=(settings.operational_incident_escalation_seconds),
            paging_enabled=settings.operational_paging_enabled,
            paging_destination=_paging_destination_label(settings.operational_paging_webhook_url),
            paging_transport=("TLS-verified HMAC-SHA256 webhook with provider receipt correlation"),
            paging_active_key_id=paging_configuration.active_key_id,
            paging_tls_verified=bool(
                settings.operational_paging_webhook_url
                and urlsplit(settings.operational_paging_webhook_url).scheme == "https"
                and not settings.operational_paging_allow_insecure_http
            ),
            paging_provider=_paging_provider(settings, required=False),
            paging_receipt_required=settings.operational_paging_require_receipt,
            paging_secret_source=paging_configuration.secret_source,
            paging_key_count=paging_configuration.key_count,
        ),
        staging_readiness=staging_readiness,
        permissions=operational_reliability_permissions(signer_identity),
    )
