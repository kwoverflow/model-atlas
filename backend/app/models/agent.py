from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.base import (
    GUID,
    JSON,
    Any,
    Base,
    Boolean,
    CheckConstraint,
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
    relationship,
    utcnow,
    uuid,
)

if TYPE_CHECKING:

    from app.models.evaluation import (
        BenchmarkResult,
        BenchmarkRun,
    )



class AgentApprovalCheckpoint(TimestampMixin, Base):
    __tablename__ = "agent_approval_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    benchmark_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    benchmark_result_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("benchmark_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    checkpoint_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    requested_by_subject_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    requested_by_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    request_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    approval_policy_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(20))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    approver_identity_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    decision_hash: Mapped[str | None] = mapped_column(String(64))
    revoked_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    revocation_reason: Mapped[str | None] = mapped_column(Text)
    revoked_by_identity_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    revocation_hash: Mapped[str | None] = mapped_column(String(64))
    resumed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    resumed_by_identity_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resume_hash: Mapped[str | None] = mapped_column(String(64))
    transition_benchmark_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("benchmark_runs.id", ondelete="SET NULL"),
        index=True,
    )
    transition_benchmark_result_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("benchmark_results.id", ondelete="SET NULL"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    benchmark_run: Mapped[BenchmarkRun] = relationship(foreign_keys=[benchmark_run_id])
    benchmark_result: Mapped[BenchmarkResult] = relationship(
        back_populates="agent_approval_checkpoints",
        foreign_keys=[benchmark_result_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "benchmark_result_id",
            "checkpoint_id",
            name="uq_agent_approval_checkpoint_result_key",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'denied', 'revoked', 'expired', 'resumed')",
            name="ck_agent_approval_checkpoints_status",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('approved', 'denied')",
            name="ck_agent_approval_checkpoints_decision",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_agent_approval_checkpoints_version_positive",
        ),
    )

class AgentExecutionJob(TimestampMixin, Base):
    __tablename__ = "agent_execution_jobs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    job_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    requested_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    benchmark_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("benchmark_runs.id", ondelete="SET NULL"), index=True
    )
    benchmark_result_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("benchmark_results.id", ondelete="SET NULL"), index=True
    )
    checkpoint_record_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("agent_approval_checkpoints.id", ondelete="SET NULL"),
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    available_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    lease_owner: Mapped[str | None] = mapped_column(String(160), index=True)
    lease_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    last_heartbeat_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    heartbeat_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    started_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    last_error: Mapped[str | None] = mapped_column(Text)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    dead_lettered_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    dead_letter_reason: Mapped[str | None] = mapped_column(Text)
    requeue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_requeued_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    last_requeued_by_identity_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        CheckConstraint(
            "job_type IN ('resume_checkpoint', 'checkpoint_reconciliation', "
            "'traffic_evidence_import', 'model_validation_campaign', "
            "'trust_source_sync', 'oidc_session_cleanup', "
            "'operational_observability_cycle', 'operational_alert_delivery')",
            name="ck_agent_execution_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'leased', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_agent_execution_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts > 0 AND heartbeat_count >= 0 "
            "AND requeue_count >= 0",
            name="ck_agent_execution_jobs_attempts",
        ),
    )

class AgentWorkerState(TimestampMixin, Base):
    __tablename__ = "agent_worker_states"

    worker_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="online", index=True)
    started_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    current_job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("agent_execution_jobs.id", ondelete="SET NULL"),
        index=True,
    )
    processed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint(
            "status IN ('online', 'stopped')",
            name="ck_agent_worker_states_status",
        ),
        CheckConstraint(
            "processed_count >= 0 AND completed_count >= 0 AND failed_count >= 0",
            name="ck_agent_worker_states_counts",
        ),
    )

class AgentTrafficReceipt(TimestampMixin, Base):
    __tablename__ = "agent_traffic_receipts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source_system: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    signature_version: Mapped[str] = mapped_column(String(60), nullable=False)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    collector_version: Mapped[str] = mapped_column(String(120), nullable=False)
    captured_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    sent_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    received_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    last_seen_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    job_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("agent_execution_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "batch_id",
            name="uq_agent_traffic_receipts_source_batch",
        ),
        UniqueConstraint(
            "source_system",
            "nonce",
            name="uq_agent_traffic_receipts_source_nonce",
        ),
        CheckConstraint(
            "replay_count >= 0",
            name="ck_agent_traffic_receipts_replay_count",
        ),
    )
