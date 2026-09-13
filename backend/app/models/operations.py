from __future__ import annotations

from app.models.base import (
    GUID,
    JSON,
    Any,
    Base,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    Mapped,
    String,
    Text,
    TimestampMixin,
    UniqueConstraint,
    UTCDateTime,
    dt,
    mapped_column,
    utcnow,
    uuid,
)


class OperationalMetricSnapshot(Base):
    __tablename__ = "operational_metric_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    bucket_started_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, unique=True, index=True
    )
    generated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    health: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    alert_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    collected_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "health IN ('healthy', 'degraded', 'critical')",
            name="ck_operational_metric_snapshots_health",
        ),
        CheckConstraint(
            "sample_count >= 0 AND alert_count >= 0",
            name="ck_operational_metric_snapshots_counts",
        ),
        CheckConstraint(
            "expires_at > generated_at",
            name="ck_operational_metric_snapshots_expiry",
        ),
    )

class OperationalMetricPoint(Base):
    __tablename__ = "operational_metric_points"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("operational_metric_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    labels_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    labels_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    help_text: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "metric_name",
            "labels_hash",
            name="uq_operational_metric_points_snapshot_metric_labels",
        ),
    )

class OperationalSLOEvaluation(Base):
    __tablename__ = "operational_slo_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("operational_metric_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slo_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    observed_ratio: Mapped[float | None] = mapped_column(Float)
    error_budget_remaining_ratio: Mapped[float | None] = mapped_column(Float)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    short_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    short_observed_ratio: Mapped[float | None] = mapped_column(Float)
    burn_rate: Mapped[float | None] = mapped_column(Float)
    short_burn_rate: Mapped[float | None] = mapped_column(Float)
    burn_alert_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none", index=True
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    good_sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    window_ended_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    evaluated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    evaluation_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "slo_key",
            name="uq_operational_slo_evaluations_snapshot_key",
        ),
        CheckConstraint(
            "scope IN ('identity', 'worker')",
            name="ck_operational_slo_evaluations_scope",
        ),
        CheckConstraint(
            "status IN ('met', 'breached', 'insufficient')",
            name="ck_operational_slo_evaluations_status",
        ),
        CheckConstraint(
            "burn_alert_level IN ('none', 'warning', 'critical')",
            name="ck_operational_slo_evaluations_burn_alert_level",
        ),
        CheckConstraint(
            "target_ratio >= 0 AND target_ratio <= 1 "
            "AND (observed_ratio IS NULL OR "
            "(observed_ratio >= 0 AND observed_ratio <= 1)) "
            "AND (short_observed_ratio IS NULL OR "
            "(short_observed_ratio >= 0 AND short_observed_ratio <= 1)) "
            "AND (error_budget_remaining_ratio IS NULL OR "
            "(error_budget_remaining_ratio >= 0 "
            "AND error_budget_remaining_ratio <= 1)) "
            "AND (burn_rate IS NULL OR burn_rate >= 0) "
            "AND (short_burn_rate IS NULL OR short_burn_rate >= 0)",
            name="ck_operational_slo_evaluations_ratios",
        ),
        CheckConstraint(
            "window_seconds > 0 AND short_window_seconds > 0 "
            "AND short_window_seconds <= window_seconds AND sample_count >= 0 "
            "AND good_sample_count >= 0 AND good_sample_count <= sample_count",
            name="ck_operational_slo_evaluations_counts",
        ),
    )

class OperationalAlertIncident(TimestampMixin, Base):
    __tablename__ = "operational_alert_incidents"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    active_key: Mapped[str | None] = mapped_column(String(180), unique=True, index=True)
    alert_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    route: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(180), index=True)
    current_value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    slo_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("operational_slo_evaluations.id", ondelete="SET NULL"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    opened_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    acknowledged_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    acknowledged_by_identity_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    assigned_to: Mapped[str | None] = mapped_column(String(160), index=True)
    escalation_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    transition_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    latest_context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "source_type IN ('derived_alert', 'slo', 'test')",
            name="ck_operational_alert_incidents_source",
        ),
        CheckConstraint(
            "severity IN ('warning', 'critical')",
            name="ck_operational_alert_incidents_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'resolved')",
            name="ck_operational_alert_incidents_status",
        ),
        CheckConstraint(
            "occurrence_count > 0 AND transition_version > 0 "
            "AND escalation_level >= 0 AND escalation_level <= 3",
            name="ck_operational_alert_incidents_counts",
        ),
        CheckConstraint(
            "(status = 'open' AND active_key IS NOT NULL "
            "AND resolved_at IS NULL) OR "
            "(status = 'resolved' AND active_key IS NULL "
            "AND resolved_at IS NOT NULL)",
            name="ck_operational_alert_incidents_lifecycle",
        ),
    )

class OperationalAlertIncidentAction(Base):
    __tablename__ = "operational_alert_incident_actions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("operational_alert_incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(160))
    actor_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurred_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    previous_action_hash: Mapped[str | None] = mapped_column(String(64))
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('acknowledged', 'assigned', 'note', 'escalated')",
            name="ck_operational_alert_incident_actions_type",
        ),
    )

class OperationalAlertDelivery(TimestampMixin, Base):
    __tablename__ = "operational_alert_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("operational_alert_incidents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    delivery_job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("agent_execution_jobs.id", ondelete="SET NULL"),
        unique=True,
        index=True,
    )
    transition_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    transition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    destination_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    requested_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    last_attempt_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_hash: Mapped[str | None] = mapped_column(String(64))
    provider_name: Mapped[str | None] = mapped_column(String(80), index=True)
    provider_event_id: Mapped[str | None] = mapped_column(String(200), index=True)
    provider_receipt_id: Mapped[str | None] = mapped_column(String(200), index=True)
    provider_accepted_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)

    __table_args__ = (
        UniqueConstraint(
            "incident_id",
            "transition_type",
            "transition_version",
            name="uq_operational_alert_deliveries_transition",
        ),
        CheckConstraint(
            "transition_type IN ('opened', 'resolved', 'test', 'escalated')",
            name="ck_operational_alert_deliveries_transition",
        ),
        CheckConstraint(
            "status IN ('queued', 'delivered', 'failed')",
            name="ck_operational_alert_deliveries_status",
        ),
        CheckConstraint(
            "transition_version > 0 AND attempt_count >= 0",
            name="ck_operational_alert_deliveries_attempts",
        ),
    )
