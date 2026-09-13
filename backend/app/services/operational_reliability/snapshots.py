from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    OperationalMetricPoint,
    OperationalMetricSnapshot,
)
from app.services.operational_metrics import collect_operational_metrics
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

from .contracts import (
    OPERATIONAL_RELIABILITY_VERSION,
    SNAPSHOT_RETENTION_BATCH_SIZE,
)
from .incidents import (
    _reconcile_operational_incidents,
)
from .slo import (
    _evaluate_slos,
)
from .utils import (
    _bucket_start,
    _canonical_hash,
    _utc,
)


def capture_operational_reliability_cycle(
    db: Session,
    *,
    settings: Settings,
    collector_identity: SignerIdentity,
    reason: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    if not collector_identity.identity_verified:
        raise DomainValidationError(
            "operational metric capture requires a verified collector identity"
        )
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    interval_seconds = settings.operational_snapshot_interval_seconds
    bucket_started_at = _bucket_start(observed_at, interval_seconds)
    existing = db.scalar(
        select(OperationalMetricSnapshot).where(
            OperationalMetricSnapshot.bucket_started_at == bucket_started_at
        )
    )
    if existing is not None:
        return {
            "schema_version": OPERATIONAL_RELIABILITY_VERSION,
            "snapshot_id": str(existing.id),
            "bucket_started_at": existing.bucket_started_at.isoformat(),
            "created": False,
            "retained_snapshot_deleted_count": 0,
            "slo_evaluation_ids": [],
            "delivery_ids": [],
            "reason": reason,
        }

    expired_snapshots = list(
        db.scalars(
            select(OperationalMetricSnapshot)
            .where(OperationalMetricSnapshot.expires_at <= observed_at)
            .order_by(OperationalMetricSnapshot.expires_at)
            .limit(SNAPSHOT_RETENTION_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for expired_snapshot in expired_snapshots:
        db.delete(expired_snapshot)
    db.flush()

    metrics = collect_operational_metrics(db, settings=settings, now=observed_at)
    canonical_samples = [
        {
            "name": sample.name,
            "value": sample.value,
            "labels": dict(sorted(sample.labels.items())),
            "help": sample.help,
        }
        for sample in sorted(
            metrics.samples,
            key=lambda item: (
                item.name,
                json.dumps(item.labels, sort_keys=True, separators=(",", ":")),
            ),
        )
    ]
    snapshot_payload = {
        "bucket_started_at": bucket_started_at.isoformat(),
        "generated_at": metrics.generated_at.isoformat(),
        "health": metrics.health,
        "schema_version": metrics.schema_version,
        "samples": canonical_samples,
        "alerts": [
            alert.model_dump(mode="json")
            for alert in sorted(metrics.alerts, key=lambda item: item.key)
        ],
    }
    snapshot = OperationalMetricSnapshot(
        bucket_started_at=bucket_started_at,
        generated_at=metrics.generated_at,
        expires_at=metrics.generated_at
        + dt.timedelta(days=settings.operational_snapshot_retention_days),
        health=metrics.health,
        schema_version=metrics.schema_version,
        sample_count=len(metrics.samples),
        alert_count=len(metrics.alerts),
        content_hash=_canonical_hash(snapshot_payload),
        collected_by=collector_identity.subject_id[:160],
        created_at=observed_at,
    )
    db.add(snapshot)
    db.flush()
    for sample in metrics.samples:
        labels = dict(sorted(sample.labels.items()))
        db.add(
            OperationalMetricPoint(
                snapshot_id=snapshot.id,
                metric_name=sample.name,
                metric_value=sample.value,
                labels_json=labels,
                labels_hash=_canonical_hash(labels),
                help_text=sample.help,
                recorded_at=metrics.generated_at,
                created_at=observed_at,
            )
        )
    db.flush()

    slo_evaluations = _evaluate_slos(
        db,
        snapshot=snapshot,
        settings=settings,
        observed_at=observed_at,
    )
    db.flush()
    delivery_ids = _reconcile_operational_incidents(
        db,
        snapshot=snapshot,
        alerts=metrics.alerts,
        slo_evaluations=slo_evaluations,
        settings=settings,
        observed_at=observed_at,
    )
    db.commit()
    return {
        "schema_version": OPERATIONAL_RELIABILITY_VERSION,
        "snapshot_id": str(snapshot.id),
        "bucket_started_at": snapshot.bucket_started_at.isoformat(),
        "created": True,
        "retained_snapshot_deleted_count": len(expired_snapshots),
        "slo_evaluation_ids": [str(item.id) for item in slo_evaluations],
        "delivery_ids": [str(delivery_id) for delivery_id in delivery_ids],
        "reason": reason,
    }
