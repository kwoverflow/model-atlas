from __future__ import annotations

import datetime as dt
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    GateEvaluation,
    JudgeLabelReviewDecision,
    ModelArtifactAttestation,
    OIDCBrowserSession,
    OIDCBrowserSessionEvent,
    OIDCCacheEntry,
    OperationalAlertDelivery,
    OperationalAlertIncident,
    OperationalMetricSnapshot,
    OperationalSLOEvaluation,
    ReleaseDecision,
    ReleaseDecisionAction,
)
from app.schemas import (
    OperationalAlertRead,
    OperationalMetricSampleRead,
    OperationalMetricsRead,
)
from app.services.agent_jobs import get_agent_job_overview
from app.services.agent_traffic_ingestion import list_traffic_source_status
from app.services.release_decisions import release_decision_read
from app.services.supply_chain import build_supply_chain_overview
from app.services.trust_registry import build_trust_registry_overview

OPERATIONAL_METRICS_VERSION = "model-atlas-operational-metrics-v1"


def collect_operational_metrics(
    db: Session,
    *,
    settings: Settings,
    now: dt.datetime | None = None,
) -> OperationalMetricsRead:
    observed_at = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    worker_overview = get_agent_job_overview(
        db,
        worker_offline_seconds=settings.agent_worker_offline_seconds,
        now=observed_at,
    )
    traffic_sources = list_traffic_source_status(
        db,
        hmac_keys=settings.agent_traffic_hmac_keys,
        stale_after_seconds=settings.agent_traffic_source_stale_seconds,
        now=observed_at,
    )
    release_decisions = list(db.scalars(select(ReleaseDecision)).all())
    release_statuses = Counter(
        release_decision_read(db, decision).operational_status
        for decision in release_decisions
    )
    release_actions = list(db.scalars(select(ReleaseDecisionAction)).all())
    release_action_counts = Counter(action.action_type for action in release_actions)
    worker_status_counts = Counter(
        str(worker["status"]) for worker in worker_overview["workers"]
    )
    traffic_health_counts = Counter(str(source["health"]) for source in traffic_sources)
    stale_gate_total = len(
        list(
            db.scalars(
                select(GateEvaluation.id).where(GateEvaluation.status == "stale")
            ).all()
        )
    )
    stale_gate_count = len(
        list(
            db.scalars(
                select(GateEvaluation.id)
                .where(GateEvaluation.status == "stale")
                .where(GateEvaluation.superseded_by_gate_evaluation_id.is_(None))
            ).all()
        )
    )
    verified_attestation_count = len(
        list(
            db.scalars(
                select(ModelArtifactAttestation.id)
                .where(ModelArtifactAttestation.status == "verified")
                .where(ModelArtifactAttestation.identity_verified.is_(True))
            ).all()
        )
    )
    applied_review_count = len(
        list(
            db.scalars(
                select(JudgeLabelReviewDecision.id)
                .where(JudgeLabelReviewDecision.applied.is_(True))
                .where(JudgeLabelReviewDecision.identity_verified.is_(True))
            ).all()
        )
    )
    supply_chain_overview = build_supply_chain_overview(db, settings=settings)
    trust_registry_overview = build_trust_registry_overview(db, now=observed_at)
    active_browser_session_count = int(
        db.scalar(
            select(func.count()).select_from(OIDCBrowserSession).where(
                OIDCBrowserSession.revoked_at.is_(None),
                OIDCBrowserSession.expires_at > observed_at,
            )
        )
        or 0
    )
    revoked_browser_session_count = int(
        db.scalar(
            select(func.count()).select_from(OIDCBrowserSession).where(
                OIDCBrowserSession.revoked_at.is_not(None)
            )
        )
        or 0
    )
    expired_browser_session_count = int(
        db.scalar(
            select(func.count()).select_from(OIDCBrowserSession).where(
                OIDCBrowserSession.revoked_at.is_(None),
                OIDCBrowserSession.expires_at <= observed_at,
            )
        )
        or 0
    )
    retention_cutoff = observed_at - dt.timedelta(
        days=settings.oidc_session_retention_days
    )
    browser_session_retention_due_count = int(
        db.scalar(
            select(func.count()).select_from(OIDCBrowserSession).where(
                (
                    OIDCBrowserSession.revoked_at.is_not(None)
                    & (OIDCBrowserSession.revoked_at <= retention_cutoff)
                )
                | (
                    OIDCBrowserSession.revoked_at.is_(None)
                    & (OIDCBrowserSession.expires_at <= retention_cutoff)
                )
            )
        )
        or 0
    )
    inactive_browser_session_provider_token_count = int(
        db.scalar(
            select(func.count()).select_from(OIDCBrowserSession).where(
                OIDCBrowserSession.provider_id_token_ciphertext.is_not(None),
                (OIDCBrowserSession.revoked_at.is_not(None))
                | (OIDCBrowserSession.expires_at <= observed_at),
            )
        )
        or 0
    )
    browser_session_audit_event_count = int(
        db.scalar(select(func.count()).select_from(OIDCBrowserSessionEvent)) or 0
    )
    operational_snapshot_count = int(
        db.scalar(select(func.count()).select_from(OperationalMetricSnapshot)) or 0
    )
    latest_operational_snapshot_at = db.scalar(
        select(func.max(OperationalMetricSnapshot.generated_at))
    )
    operational_snapshot_age_seconds = (
        max(
            0.0,
            (observed_at - latest_operational_snapshot_at).total_seconds(),
        )
        if latest_operational_snapshot_at is not None
        else 0.0
    )
    open_operational_incident_count = int(
        db.scalar(
            select(func.count())
            .select_from(OperationalAlertIncident)
            .where(OperationalAlertIncident.status == "open")
        )
        or 0
    )
    queued_operational_delivery_count = int(
        db.scalar(
            select(func.count())
            .select_from(OperationalAlertDelivery)
            .where(OperationalAlertDelivery.status == "queued")
        )
        or 0
    )
    failed_operational_delivery_count = int(
        db.scalar(
            select(func.count())
            .select_from(OperationalAlertDelivery)
            .where(OperationalAlertDelivery.status == "failed")
        )
        or 0
    )
    slo_rows = list(
        db.scalars(
            select(OperationalSLOEvaluation).order_by(
                OperationalSLOEvaluation.evaluated_at.desc()
            )
        ).all()
    )
    latest_slo_rows: dict[str, OperationalSLOEvaluation] = {}
    for slo_row in slo_rows:
        latest_slo_rows.setdefault(slo_row.slo_key, slo_row)
    breached_slo_count = sum(
        1 for slo_row in latest_slo_rows.values() if slo_row.status == "breached"
    )
    insufficient_slo_count = sum(
        1
        for slo_row in latest_slo_rows.values()
        if slo_row.status == "insufficient"
    )
    fresh_oidc_cache_count = int(
        db.scalar(
            select(func.count()).select_from(OIDCCacheEntry).where(
                OIDCCacheEntry.expires_at > observed_at
            )
        )
        or 0
    )
    stale_oidc_cache_count = int(
        db.scalar(
            select(func.count()).select_from(OIDCCacheEntry).where(
                OIDCCacheEntry.expires_at <= observed_at
            )
        )
        or 0
    )
    samples = [
        _sample(
            "model_atlas_browser_session_active",
            active_browser_session_count,
            "Number of active database-backed browser sessions.",
        ),
        _sample(
            "model_atlas_browser_session_revoked",
            revoked_browser_session_count,
            "Number of server-side browser session revocations.",
        ),
        _sample(
            "model_atlas_browser_session_expired",
            expired_browser_session_count,
            "Number of expired browser sessions retained for audit.",
        ),
        _sample(
            "model_atlas_browser_session_retention_due",
            browser_session_retention_due_count,
            "Number of inactive browser sessions beyond the configured retention period.",
        ),
        _sample(
            "model_atlas_browser_session_inactive_provider_token",
            inactive_browser_session_provider_token_count,
            "Number of inactive sessions that still retain encrypted provider token material.",
        ),
        _sample(
            "model_atlas_browser_session_audit_event_total",
            browser_session_audit_event_count,
            "Cumulative append-only browser session lifecycle events.",
        ),
        _sample(
            "model_atlas_oidc_shared_cache_fresh",
            fresh_oidc_cache_count,
            "Number of fresh shared OIDC discovery and JWKS documents.",
        ),
        _sample(
            "model_atlas_oidc_shared_cache_stale",
            stale_oidc_cache_count,
            "Number of expired shared OIDC discovery and JWKS documents.",
        ),
        _sample(
            "model_atlas_observability_snapshot_total",
            operational_snapshot_count,
            "Number of retained durable operational metric snapshots.",
        ),
        _sample(
            "model_atlas_observability_snapshot_age_seconds",
            operational_snapshot_age_seconds,
            "Age in seconds of the latest durable operational metric snapshot.",
        ),
        _sample(
            "model_atlas_operational_incident_open",
            open_operational_incident_count,
            "Number of active durable operational alert incidents.",
        ),
        _sample(
            "model_atlas_operational_delivery_queued",
            queued_operational_delivery_count,
            "Number of paging deliveries waiting for durable execution.",
        ),
        _sample(
            "model_atlas_operational_delivery_failed",
            failed_operational_delivery_count,
            "Number of paging deliveries that exhausted or permanently failed.",
        ),
        _sample(
            "model_atlas_slo_breached",
            breached_slo_count,
            "Number of latest identity or worker SLO evaluations below objective.",
        ),
        _sample(
            "model_atlas_slo_insufficient",
            insufficient_slo_count,
            "Number of latest SLO evaluations without the minimum retained samples.",
        ),
        _sample(
            "model_atlas_worker_online",
            worker_overview["online_worker_count"],
            "Number of workers currently within the heartbeat window.",
        ),
        _sample(
            "model_atlas_worker_offline",
            worker_status_counts["offline"],
            "Number of workers outside the heartbeat window.",
        ),
        _sample(
            "model_atlas_job_queue_depth",
            worker_overview["queue_depth"],
            "Number of durable jobs waiting for a lease.",
        ),
        _sample(
            "model_atlas_job_dead_letter_count",
            worker_overview["dead_letter_count"],
            "Number of jobs currently in terminal failed state.",
        ),
        _sample(
            "model_atlas_job_expired_lease_count",
            worker_overview["expired_lease_count"],
            "Number of active jobs whose leases have expired.",
        ),
        _sample(
            "model_atlas_job_oldest_queued_age_seconds",
            worker_overview["oldest_queued_age_seconds"] or 0,
            "Age in seconds of the oldest queued durable job.",
        ),
        _sample(
            "model_atlas_collector_source_active",
            traffic_health_counts["active"],
            "Number of traffic collector sources currently active.",
        ),
        _sample(
            "model_atlas_collector_source_stale",
            traffic_health_counts["stale"],
            "Number of traffic collector sources beyond the staleness window.",
        ),
        _sample(
            "model_atlas_collector_source_never_seen",
            traffic_health_counts["never_seen"],
            "Number of configured traffic collector sources never observed.",
        ),
        _sample(
            "model_atlas_collector_replay_count",
            sum(int(source["replay_count"]) for source in traffic_sources),
            "Cumulative idempotent traffic batch replay receipts.",
        ),
        _sample(
            "model_atlas_release_needs_review",
            release_statuses["needs_review"],
            "Number of release decisions requiring operational review.",
        ),
        _sample(
            "model_atlas_release_revoked",
            release_statuses["revoked"],
            "Number of revoked release decisions.",
        ),
        _sample(
            "model_atlas_gate_stale",
            stale_gate_count,
            "Number of stale Gate evaluations without a replacement evaluation.",
        ),
        _sample(
            "model_atlas_gate_stale_total",
            stale_gate_total,
            "Historical number of Gate evaluations marked stale.",
        ),
        _sample(
            "model_atlas_artifact_attestation_verified",
            verified_attestation_count,
            "Number of verified model artifact manifest attestations.",
        ),
        _sample(
            "model_atlas_judge_review_applied",
            applied_review_count,
            "Number of verified reviewed-label decisions applied to evidence.",
        ),
        _sample(
            "model_atlas_supply_chain_attestation_verified",
            supply_chain_overview.verified_attestation_count,
            "Number of active publisher-signed model supply-chain attestations.",
        ),
        _sample(
            "model_atlas_supply_chain_attestation_revoked",
            supply_chain_overview.revoked_attestation_count,
            "Number of model supply-chain attestations with append-only revocation records.",
        ),
        _sample(
            "model_atlas_production_evidence_receipt_verified",
            supply_chain_overview.production_receipt_count,
            "Number of verified signed production-capture receipts.",
        ),
        _sample(
            "model_atlas_production_run_unverified",
            supply_chain_overview.unverified_production_run_count,
            "Number of production-labeled runs without an active signed receipt chain.",
        ),
        _sample(
            "model_atlas_trust_root_active",
            trust_registry_overview.active_root_count,
            "Number of signing trust roots currently active.",
        ),
        _sample(
            "model_atlas_trust_source_registered",
            trust_registry_overview.trust_source_count,
            "Number of configured remote evidence trust sources.",
        ),
        _sample(
            "model_atlas_trust_source_healthy",
            trust_registry_overview.healthy_source_count,
            "Number of trust sources with a fresh successful apply snapshot.",
        ),
        _sample(
            "model_atlas_trust_source_degraded",
            trust_registry_overview.degraded_source_count,
            "Number of trust sources with fresh keys but a newer failed attempt.",
        ),
        _sample(
            "model_atlas_trust_source_stale",
            trust_registry_overview.stale_source_count,
            "Number of trust sources whose last successful apply is outside freshness policy.",
        ),
        _sample(
            "model_atlas_trust_source_failed",
            trust_registry_overview.failed_source_count,
            "Number of trust sources that have never completed a successful apply.",
        ),
        _sample(
            "model_atlas_trust_source_unsynced",
            trust_registry_overview.unsynced_source_count,
            "Number of enabled trust sources without an applied key snapshot.",
        ),
        _sample(
            "model_atlas_trust_source_schedule_enabled",
            trust_registry_overview.automatic_schedule_enabled_count,
            "Number of enabled automatic trust-source synchronization policies.",
        ),
        _sample(
            "model_atlas_trust_source_schedule_due",
            trust_registry_overview.automatic_schedule_due_count,
            "Number of automatic trust-source synchronization policies currently due.",
        ),
        _sample(
            "model_atlas_trust_source_schedule_retrying",
            trust_registry_overview.automatic_schedule_retrying_count,
            "Number of trust-source synchronization jobs waiting for a retry.",
        ),
        _sample(
            "model_atlas_trust_source_schedule_failed",
            trust_registry_overview.automatic_schedule_failed_count,
            "Number of automatic trust-source policies whose latest run exhausted retries.",
        ),
        _sample(
            "model_atlas_trust_root_production_eligible",
            trust_registry_overview.production_eligible_root_count,
            "Number of active internal-CA or external signing trust roots.",
        ),
        _sample(
            "model_atlas_trust_root_revoked",
            trust_registry_overview.revoked_root_count,
            "Number of signing trust roots with append-only revocation actions.",
        ),
        _sample(
            "model_atlas_transparency_proof_production_eligible",
            trust_registry_overview.production_eligible_proof_count,
            "Number of transparency proofs backed by active production-tier log keys.",
        ),
        _sample(
            "model_atlas_supply_chain_production_eligible",
            supply_chain_overview.production_eligible_attestation_count,
            "Number of supply-chain attestations eligible for production evidence.",
        ),
        _sample(
            "model_atlas_production_receipt_production_eligible",
            supply_chain_overview.production_eligible_receipt_count,
            "Number of production receipts with a complete active managed trust chain.",
        ),
        _sample(
            "model_atlas_transparency_proof_pending",
            trust_registry_overview.production_tier_attestation_pending_count,
            "Number of production-tier attestations missing active transparency evidence.",
        ),
    ]
    samples.extend(
        _sample(
            "model_atlas_slo_compliance_ratio",
            slo_row.observed_ratio if slo_row.observed_ratio is not None else 0,
            "Latest rolling compliance ratio for an explicit operational SLO.",
            labels={
                "slo_key": slo_row.slo_key,
                "scope": slo_row.scope,
                "status": slo_row.status,
            },
        )
        for slo_row in sorted(latest_slo_rows.values(), key=lambda item: item.slo_key)
    )
    samples.extend(
        _sample(
            "model_atlas_slo_target_ratio",
            slo_row.target_ratio,
            "Configured objective ratio for an explicit operational SLO.",
            labels={
                "slo_key": slo_row.slo_key,
                "scope": slo_row.scope,
            },
        )
        for slo_row in sorted(latest_slo_rows.values(), key=lambda item: item.slo_key)
    )
    samples.extend(
        _sample(
            "model_atlas_release_action_count",
            count,
            "Number of append-only release operations by action type.",
            labels={"action_type": action_type},
        )
        for action_type, count in sorted(release_action_counts.items())
    )
    samples.extend(
        _sample(
            "model_atlas_collector_source_health",
            1,
            "Current health state for a configured traffic source.",
            labels={
                "source_system": str(source["source_system"]),
                "health": str(source["health"]),
            },
        )
        for source in traffic_sources
    )
    alerts = _alerts(samples)
    health = (
        "critical"
        if any(alert.severity == "critical" for alert in alerts)
        else "degraded"
        if alerts
        else "healthy"
    )
    return OperationalMetricsRead(
        schema_version=OPERATIONAL_METRICS_VERSION,
        generated_at=observed_at,
        health=health,
        samples=samples,
        alerts=alerts,
    )


def render_prometheus_metrics(metrics: OperationalMetricsRead) -> str:
    lines = [
        "# Model Atlas operational metrics",
        f'# schema_version {metrics.schema_version}',
    ]
    described: set[str] = set()
    for sample in metrics.samples:
        if sample.name not in described:
            lines.append(f"# HELP {sample.name} {sample.help}")
            lines.append(f"# TYPE {sample.name} gauge")
            described.add(sample.name)
        labels = _prometheus_labels(sample.labels)
        lines.append(f"{sample.name}{labels} {sample.value:g}")
    lines.extend(
        [
            "# HELP model_atlas_operational_alert_active Active derived operational alert.",
            "# TYPE model_atlas_operational_alert_active gauge",
        ]
    )
    for alert in metrics.alerts:
        labels = _prometheus_labels(
            {
                "alert_key": alert.key,
                "severity": alert.severity,
                "route": alert.route,
            }
        )
        lines.append(f"model_atlas_operational_alert_active{labels} 1")
    if not metrics.alerts:
        lines.append(
            'model_atlas_operational_alert_active{alert_key="none",severity="none",route="none"} 0'
        )
    return "\n".join(lines) + "\n"


def _alerts(samples: list[OperationalMetricSampleRead]) -> list[OperationalAlertRead]:
    values = {sample.name: sample.value for sample in samples if not sample.labels}
    alerts: list[OperationalAlertRead] = []
    queue_depth = values.get("model_atlas_job_queue_depth", 0)
    online_workers = values.get("model_atlas_worker_online", 0)
    if queue_depth > 0 and online_workers < 1:
        alerts.append(
            _alert(
                "worker_queue_blocked",
                "critical",
                "model_atlas_worker_online",
                online_workers,
                1,
                "Durable jobs are queued but no worker is online.",
            )
        )
    _append_threshold_alert(
        alerts,
        key="browser_session_retention_due",
        severity="warning",
        metric_name="model_atlas_browser_session_retention_due",
        value=values.get("model_atlas_browser_session_retention_due", 0),
        threshold=0,
        summary="Inactive browser sessions are beyond the configured retention period.",
    )
    _append_threshold_alert(
        alerts,
        key="browser_session_inactive_provider_token",
        severity="critical",
        metric_name="model_atlas_browser_session_inactive_provider_token",
        value=values.get(
            "model_atlas_browser_session_inactive_provider_token",
            0,
        ),
        threshold=0,
        summary="Inactive browser sessions still retain encrypted provider token material.",
    )
    _append_threshold_alert(
        alerts,
        key="operational_delivery_failed",
        severity="critical",
        metric_name="model_atlas_operational_delivery_failed",
        value=values.get("model_atlas_operational_delivery_failed", 0),
        threshold=0,
        summary="A durable operational paging delivery failed permanently.",
    )
    _append_threshold_alert(
        alerts,
        key="dead_letter_present",
        severity="warning",
        metric_name="model_atlas_job_dead_letter_count",
        value=values.get("model_atlas_job_dead_letter_count", 0),
        threshold=0,
        summary="One or more durable jobs are dead-lettered.",
    )
    _append_threshold_alert(
        alerts,
        key="expired_lease_present",
        severity="critical",
        metric_name="model_atlas_job_expired_lease_count",
        value=values.get("model_atlas_job_expired_lease_count", 0),
        threshold=0,
        summary="One or more durable job leases have expired.",
    )
    _append_threshold_alert(
        alerts,
        key="collector_source_stale",
        severity="warning",
        metric_name="model_atlas_collector_source_stale",
        value=values.get("model_atlas_collector_source_stale", 0),
        threshold=0,
        summary="A production traffic collector source is stale.",
    )
    _append_threshold_alert(
        alerts,
        key="release_review_required",
        severity="critical",
        metric_name="model_atlas_release_needs_review",
        value=values.get("model_atlas_release_needs_review", 0),
        threshold=0,
        summary="A release decision requires operational review.",
    )
    _append_threshold_alert(
        alerts,
        key="stale_gate_present",
        severity="warning",
        metric_name="model_atlas_gate_stale",
        value=values.get("model_atlas_gate_stale", 0),
        threshold=0,
        summary="A Gate evaluation is stale and must be reevaluated.",
    )
    _append_threshold_alert(
        alerts,
        key="production_run_unverified",
        severity="critical",
        metric_name="model_atlas_production_run_unverified",
        value=values.get("model_atlas_production_run_unverified", 0),
        threshold=0,
        summary="A production-labeled run does not have an active signed receipt chain.",
    )
    _append_threshold_alert(
        alerts,
        key="supply_chain_attestation_revoked",
        severity="warning",
        metric_name="model_atlas_supply_chain_attestation_revoked",
        value=values.get("model_atlas_supply_chain_attestation_revoked", 0),
        threshold=0,
        summary="A model supply-chain attestation has been revoked.",
    )
    _append_threshold_alert(
        alerts,
        key="trust_root_revoked",
        severity="warning",
        metric_name="model_atlas_trust_root_revoked",
        value=values.get("model_atlas_trust_root_revoked", 0),
        threshold=0,
        summary="An evidence signing trust root has been revoked.",
    )
    _append_threshold_alert(
        alerts,
        key="trust_source_failed",
        severity="critical",
        metric_name="model_atlas_trust_source_failed",
        value=values.get("model_atlas_trust_source_failed", 0),
        threshold=0,
        summary="A remote trust source has no successful applied key snapshot.",
    )
    _append_threshold_alert(
        alerts,
        key="trust_source_stale",
        severity="warning",
        metric_name="model_atlas_trust_source_stale",
        value=values.get("model_atlas_trust_source_stale", 0),
        threshold=0,
        summary="A remote trust source key snapshot is stale.",
    )
    _append_threshold_alert(
        alerts,
        key="trust_source_degraded",
        severity="warning",
        metric_name="model_atlas_trust_source_degraded",
        value=values.get("model_atlas_trust_source_degraded", 0),
        threshold=0,
        summary="A remote trust source has a newer failed synchronization attempt.",
    )
    _append_threshold_alert(
        alerts,
        key="trust_source_unsynced",
        severity="warning",
        metric_name="model_atlas_trust_source_unsynced",
        value=values.get("model_atlas_trust_source_unsynced", 0),
        threshold=0,
        summary="A remote trust source is configured but has not applied a key snapshot.",
    )
    _append_threshold_alert(
        alerts,
        key="trust_source_schedule_retrying",
        severity="warning",
        metric_name="model_atlas_trust_source_schedule_retrying",
        value=values.get("model_atlas_trust_source_schedule_retrying", 0),
        threshold=0,
        summary="An automatic trust-source synchronization job is retrying.",
    )
    _append_threshold_alert(
        alerts,
        key="trust_source_schedule_failed",
        severity="critical",
        metric_name="model_atlas_trust_source_schedule_failed",
        value=values.get("model_atlas_trust_source_schedule_failed", 0),
        threshold=0,
        summary="An automatic trust-source synchronization policy exhausted its retries.",
    )
    _append_threshold_alert(
        alerts,
        key="transparency_proof_pending",
        severity="warning",
        metric_name="model_atlas_transparency_proof_pending",
        value=values.get("model_atlas_transparency_proof_pending", 0),
        threshold=0,
        summary="A production-tier supply-chain attestation lacks active transparency evidence.",
    )
    return alerts


def _append_threshold_alert(
    alerts: list[OperationalAlertRead],
    *,
    key: str,
    severity: str,
    metric_name: str,
    value: float,
    threshold: float,
    summary: str,
) -> None:
    if value > threshold:
        alerts.append(
            _alert(
                key,
                severity,
                metric_name,
                value,
                threshold,
                summary,
            )
        )


def _alert(
    key: str,
    severity: str,
    metric_name: str,
    current_value: float,
    threshold: float,
    summary: str,
) -> OperationalAlertRead:
    return OperationalAlertRead(
        key=key,
        severity=severity,
        metric_name=metric_name,
        current_value=current_value,
        threshold=threshold,
        summary=summary,
        route=(
            "model-atlas-critical"
            if severity == "critical"
            else "model-atlas-warning"
        ),
    )


def _sample(
    name: str,
    value: Any,
    help_text: str,
    *,
    labels: dict[str, str] | None = None,
) -> OperationalMetricSampleRead:
    return OperationalMetricSampleRead(
        name=name,
        value=float(value),
        help=help_text,
        labels=labels or {},
    )


def _prometheus_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    rendered = ",".join(
        f'{key}="{_escape_prometheus_label(value)}"'
        for key, value in sorted(labels.items())
    )
    return f"{{{rendered}}}"


def _escape_prometheus_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
