from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AgentExecutionJobType = Literal[
    "resume_checkpoint",
    "checkpoint_reconciliation",
    "traffic_evidence_import",
    "model_validation_campaign",
    "trust_source_sync",
    "oidc_session_cleanup",
    "operational_observability_cycle",
    "operational_alert_delivery",
]
AgentExecutionJobStatus = Literal[
    "queued",
    "leased",
    "running",
    "completed",
    "failed",
    "cancelled",
]


class AgentCheckpointResumeJobCreate(BaseModel):
    expected_version: int = Field(ge=1)


class AgentExecutionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: AgentExecutionJobType
    status: AgentExecutionJobStatus
    dedupe_key: str
    payload_json: dict[str, Any]
    requested_by_identity_json: dict[str, Any]
    benchmark_run_id: UUID | None = None
    benchmark_result_id: UUID | None = None
    checkpoint_record_id: UUID | None = None
    priority: int
    available_at: datetime
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    heartbeat_count: int
    attempt_count: int
    max_attempts: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error: str | None = None
    result_json: dict[str, Any] | None = None
    dead_lettered_at: datetime | None = None
    dead_letter_reason: str | None = None
    requeue_count: int
    last_requeued_at: datetime | None = None
    last_requeued_by_identity_json: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class AgentReconciliationJobCreate(BaseModel):
    schedule_key: str | None = Field(default=None, max_length=120)


class AgentJobRequeueCreate(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)
    max_attempts: int | None = Field(default=None, ge=1, le=10)


class AgentWorkerStateRead(BaseModel):
    worker_id: str
    status: Literal["online", "offline", "stopped"]
    started_at: datetime
    last_seen_at: datetime
    current_job_id: UUID | None = None
    processed_count: int
    completed_count: int
    failed_count: int
    metadata_json: dict[str, Any]


class AgentJobOverviewRead(BaseModel):
    schema_version: str
    generated_at: datetime
    health: Literal["healthy", "degraded", "blocked", "idle"]
    total_job_count: int
    status_counts: dict[str, int]
    job_type_counts: dict[str, int]
    queue_depth: int
    retrying_count: int
    active_lease_count: int
    expired_lease_count: int
    dead_letter_count: int
    oldest_queued_age_seconds: float | None = None
    completed_last_24h: int
    failed_last_24h: int
    success_rate_last_24h: float | None = None
    average_queue_latency_ms: float | None = None
    average_execution_duration_ms: float | None = None
    online_worker_count: int
    workers: list[AgentWorkerStateRead]


class AgentTrafficSourceStatusRead(BaseModel):
    schema_version: str
    source_system: str
    health: Literal["active", "stale", "never_seen"]
    batch_count: int
    replay_count: int
    last_received_at: datetime | None = None
    last_job_id: UUID | None = None
    collector_versions: list[str]
    observed_key_ids: list[str]
    configured_key_ids: list[str]


class AgentJobWorkerRunRead(BaseModel):
    claimed: bool
    job: AgentExecutionJobRead | None = None
