from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class OperationalReliabilityPermissionRead(BaseModel):
    policy_version: str
    can_audit: bool
    can_administer: bool
    auditor_roles: list[str]
    administrator_roles: list[str]
    identity_verified: bool
    signer_role: str | None


class OperationalReliabilityPolicyRead(BaseModel):
    snapshot_enabled: bool
    snapshot_interval_seconds: int
    snapshot_retention_days: int
    slo_window_seconds: int
    slo_short_window_seconds: int
    slo_min_samples: int
    identity_slo_target: float
    worker_slo_target: float
    slo_warning_burn_rate: float
    slo_critical_burn_rate: float
    incident_escalation_seconds: int
    paging_enabled: bool
    paging_destination: str | None
    paging_transport: str
    paging_active_key_id: str | None
    paging_tls_verified: bool
    paging_provider: str
    paging_receipt_required: bool
    paging_secret_source: Literal[
        "projected_file",
        "environment_keyring",
        "legacy_environment",
        "unconfigured",
        "invalid",
    ]
    paging_key_count: int


class OperationalReadinessCheckRead(BaseModel):
    key: str
    status: Literal["passed", "failed"]
    summary: str
    evidence: str | None = None


class OperationalStagingReadinessRead(BaseModel):
    schema_version: str = "model-atlas-operational-staging-readiness-v1"
    ready: bool
    passed_count: int
    failed_count: int
    latest_receipt_delivery_id: UUID | None
    checks: list[OperationalReadinessCheckRead]


class OperationalSnapshotSummaryRead(BaseModel):
    id: UUID
    bucket_started_at: dt.datetime
    generated_at: dt.datetime
    expires_at: dt.datetime
    health: Literal["healthy", "degraded", "critical"]
    sample_count: int
    alert_count: int
    content_hash: str
    worker_online: float
    queue_depth: float
    identity_retention_due: float
    identity_inactive_provider_token: float


class OperationalSLOEvaluationRead(BaseModel):
    id: UUID
    snapshot_id: UUID
    slo_key: str
    scope: Literal["identity", "worker"]
    status: Literal["met", "breached", "insufficient"]
    target_ratio: float
    observed_ratio: float | None
    error_budget_remaining_ratio: float | None
    window_seconds: int
    short_window_seconds: int
    short_observed_ratio: float | None
    burn_rate: float | None
    short_burn_rate: float | None
    burn_alert_level: Literal["none", "warning", "critical"]
    sample_count: int
    good_sample_count: int
    window_started_at: dt.datetime
    window_ended_at: dt.datetime
    evaluated_at: dt.datetime
    details_json: dict[str, Any]
    evaluation_hash: str


class OperationalAlertIncidentRead(BaseModel):
    id: UUID
    alert_key: str
    source_type: Literal["derived_alert", "slo", "test"]
    severity: Literal["warning", "critical"]
    route: str
    summary: str
    metric_name: str | None
    current_value: float | None
    threshold: float | None
    slo_evaluation_id: UUID | None
    status: Literal["open", "resolved"]
    opened_at: dt.datetime
    last_seen_at: dt.datetime
    resolved_at: dt.datetime | None
    acknowledged_at: dt.datetime | None
    acknowledged_by_identity_json: dict[str, Any] | None
    assigned_to: str | None
    escalation_level: int
    occurrence_count: int
    transition_version: int


class OperationalAlertIncidentActionRead(BaseModel):
    id: UUID
    incident_id: UUID
    action_type: Literal["acknowledged", "assigned", "note", "escalated"]
    reason: str
    assignee: str | None
    actor_identity_json: dict[str, Any]
    identity_verified: bool
    occurred_at: dt.datetime
    previous_action_hash: str | None
    action_hash: str


class OperationalAlertDeliveryRead(BaseModel):
    id: UUID
    incident_id: UUID
    delivery_job_id: UUID | None
    transition_type: Literal["opened", "resolved", "test", "escalated"]
    transition_version: int
    destination_fingerprint: str
    signing_key_id: str
    status: Literal["queued", "delivered", "failed"]
    payload_hash: str
    requested_at: dt.datetime
    last_attempt_at: dt.datetime | None
    attempt_count: int
    response_status: int | None
    response_hash: str | None
    provider_name: str | None
    provider_event_id: str | None
    provider_receipt_id: str | None
    provider_accepted_at: dt.datetime | None
    error_message: str | None
    delivered_at: dt.datetime | None


class OperationalReliabilityOverviewRead(BaseModel):
    schema_version: str
    generated_at: dt.datetime
    health: Literal["healthy", "degraded", "critical"]
    snapshot_count: int
    open_incident_count: int
    delivery_status_counts: dict[str, int]
    latest_snapshot: OperationalSnapshotSummaryRead | None
    latest_slo_evaluations: list[OperationalSLOEvaluationRead]
    snapshots: list[OperationalSnapshotSummaryRead]
    incidents: list[OperationalAlertIncidentRead]
    incident_actions: list[OperationalAlertIncidentActionRead]
    deliveries: list[OperationalAlertDeliveryRead]
    policy: OperationalReliabilityPolicyRead
    staging_readiness: OperationalStagingReadinessRead
    permissions: OperationalReliabilityPermissionRead


class OperationalCycleCreate(BaseModel):
    reason: str = Field(
        default="Operator requested observability capture",
        min_length=8,
        max_length=160,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 8:
            raise ValueError("reason must contain at least 8 non-whitespace characters")
        return normalized


class OperationalTestPageCreate(BaseModel):
    severity: Literal["warning", "critical"] = "warning"
    reason: str = Field(
        default="Operator requested paging delivery test",
        min_length=8,
        max_length=160,
    )

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return OperationalCycleCreate.normalize_reason(value)


class OperationalIncidentActionCreate(BaseModel):
    action_type: Literal["acknowledged", "assigned", "note"]
    reason: str = Field(min_length=8, max_length=500)
    assignee: str | None = Field(default=None, max_length=160)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        return OperationalCycleCreate.normalize_reason(value)

    @field_validator("assignee")
    @classmethod
    def normalize_assignee(cls, value: str | None) -> str | None:
        normalized = " ".join((value or "").strip().split())
        return normalized or None

    @model_validator(mode="after")
    def validate_assignment(self) -> OperationalIncidentActionCreate:
        if self.action_type == "assigned" and self.assignee is None:
            raise ValueError("assignee is required for assigned actions")
        if self.action_type != "assigned" and self.assignee is not None:
            raise ValueError("assignee is only valid for assigned actions")
        return self
