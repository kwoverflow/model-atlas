from __future__ import annotations

import datetime as dt
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AgentApprovalCheckpoint,
    AgentExecutionJob,
    AgentWorkerState,
    OperationalAlertDelivery,
)
from app.schemas import ModelValidationCampaignCreate
from app.services.agent_approval_policy import (
    assert_agent_checkpoint_operation_allowed,
    checkpoint_policy_from_json,
)
from app.services.agent_control_plane import (
    reconcile_agent_approval_checkpoints,
    resume_agent_approval_checkpoint,
)
from app.services.deployment_gate.staleness import reconcile_all_gate_staleness
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

AGENT_JOB_CONTRACT_VERSION = "agent-durable-job-v1"
AGENT_JOB_OPERATIONS_VERSION = "agent-job-operations-v1"
DEFAULT_LEASE_SECONDS = 300
MAX_LEASE_SECONDS = 900
MAINTENANCE_ROLES = frozenset(
    {"release manager", "ml ops lead", "sre lead", "admin", "system worker"}
)


def enqueue_checkpoint_resume_job(
    db: Session,
    *,
    checkpoint_record_id: UUID,
    expected_version: int,
    signer_identity: SignerIdentity,
) -> AgentExecutionJob:
    checkpoint = db.get(AgentApprovalCheckpoint, checkpoint_record_id)
    if checkpoint is None:
        raise DomainValidationError("agent approval checkpoint was not found")
    if checkpoint.status == "resumed" and checkpoint.transition_benchmark_result_id:
        existing = db.scalar(
            select(AgentExecutionJob)
            .where(AgentExecutionJob.checkpoint_record_id == checkpoint.id)
            .where(AgentExecutionJob.job_type == "resume_checkpoint")
            .where(AgentExecutionJob.status == "completed")
            .order_by(AgentExecutionJob.created_at.desc())
        )
        if existing is not None:
            return existing
    if checkpoint.version != expected_version:
        raise DomainValidationError(
            "agent approval checkpoint version conflict: "
            f"expected {expected_version}, current {checkpoint.version}"
        )
    if checkpoint.status != "approved":
        raise DomainValidationError(
            f"agent approval checkpoint cannot queue resume from {checkpoint.status}"
        )
    policy = checkpoint_policy_from_json(checkpoint.approval_policy_json)
    assert_agent_checkpoint_operation_allowed(
        policy=policy,
        operation="resume",
        signer_identity=signer_identity,
        requester_subject_id=checkpoint.requested_by_subject_id,
    )
    dedupe_key = f"resume:{checkpoint.id}:v{expected_version}"
    return _enqueue_job(
        db,
        job_type="resume_checkpoint",
        dedupe_key=dedupe_key,
        payload_json={
            "schema_version": AGENT_JOB_CONTRACT_VERSION,
            "checkpoint_record_id": str(checkpoint.id),
            "expected_version": expected_version,
        },
        signer_identity=signer_identity,
        benchmark_run_id=checkpoint.benchmark_run_id,
        benchmark_result_id=checkpoint.benchmark_result_id,
        checkpoint_record_id=checkpoint.id,
        priority=20,
    )


def enqueue_checkpoint_reconciliation_job(
    db: Session,
    *,
    schedule_key: str,
    signer_identity: SignerIdentity,
) -> AgentExecutionJob:
    _assert_maintenance_identity(signer_identity)
    normalized_key = schedule_key.strip()
    if not normalized_key or len(normalized_key) > 120:
        raise DomainValidationError("reconciliation schedule_key is invalid")
    return _enqueue_job(
        db,
        job_type="checkpoint_reconciliation",
        dedupe_key=f"reconcile:{normalized_key}",
        payload_json={
            "schema_version": AGENT_JOB_CONTRACT_VERSION,
            "schedule_key": normalized_key,
        },
        signer_identity=signer_identity,
        priority=10,
    )


def enqueue_traffic_evidence_job(
    db: Session,
    *,
    source_system: str,
    batch_id: str,
    payload_json: dict[str, Any],
    signer_identity: SignerIdentity,
) -> AgentExecutionJob:
    if not signer_identity.identity_verified:
        raise DomainValidationError("traffic evidence ingestion requires verified identity")
    return _enqueue_job(
        db,
        job_type="traffic_evidence_import",
        dedupe_key=f"traffic:{source_system}:{batch_id}",
        payload_json=payload_json,
        signer_identity=signer_identity,
        priority=40,
        max_attempts=2,
    )


def enqueue_model_validation_job(
    db: Session,
    *,
    payload: ModelValidationCampaignCreate,
    signer_identity: SignerIdentity,
) -> AgentExecutionJob:
    from app.services.model_validation import (
        MODEL_VALIDATION_JOB_VERSION,
        validate_model_validation_campaign,
    )

    _assert_maintenance_identity(signer_identity)
    validate_model_validation_campaign(payload)
    campaign_key = (payload.campaign_key or uuid.uuid4().hex).strip()
    if not campaign_key or len(campaign_key) > 120:
        raise DomainValidationError("model validation campaign_key is invalid")
    execution_payload = payload.model_dump(
        mode="json",
        exclude={"campaign_key"},
    )
    return _enqueue_job(
        db,
        job_type="model_validation_campaign",
        dedupe_key=f"model-validation:{campaign_key}",
        payload_json={
            "schema_version": MODEL_VALIDATION_JOB_VERSION,
            "campaign_key": campaign_key,
            "execution": execution_payload,
        },
        signer_identity=signer_identity,
        priority=30,
        max_attempts=2,
    )


def enqueue_oidc_session_cleanup_job(
    db: Session,
    *,
    schedule_key: str,
    signer_identity: SignerIdentity,
    retention_days: int,
    batch_size: int,
    reason: str,
) -> AgentExecutionJob:
    return _enqueue_job(
        db,
        job_type="oidc_session_cleanup",
        dedupe_key=f"oidc-session-cleanup:{schedule_key}",
        payload_json={
            "schema_version": "oidc-session-cleanup-job-v1",
            "retention_days": max(1, min(int(retention_days), 3650)),
            "batch_size": max(1, min(int(batch_size), 1000)),
            "reason": reason[:160],
            "schedule_key": schedule_key,
        },
        signer_identity=signer_identity,
        priority=30,
        max_attempts=3,
    )


def enqueue_operational_observability_cycle_job(
    db: Session,
    *,
    schedule_key: str,
    signer_identity: SignerIdentity,
    reason: str,
) -> AgentExecutionJob:
    _assert_maintenance_identity(signer_identity)
    normalized_key = schedule_key.strip()
    if not normalized_key or len(normalized_key) > 120:
        raise DomainValidationError("operational cycle schedule_key is invalid")
    return _enqueue_job(
        db,
        job_type="operational_observability_cycle",
        dedupe_key=f"operational-observability:{normalized_key}",
        payload_json={
            "schema_version": "operational-observability-job-v1",
            "schedule_key": normalized_key,
            "reason": reason[:160],
        },
        signer_identity=signer_identity,
        priority=15,
        max_attempts=3,
    )


def enqueue_operational_alert_delivery_job(
    db: Session,
    *,
    delivery_id: UUID,
    signer_identity: SignerIdentity,
) -> AgentExecutionJob:
    _assert_maintenance_identity(signer_identity)
    delivery = db.get(OperationalAlertDelivery, delivery_id)
    if delivery is None:
        raise DomainValidationError("operational alert delivery was not found")
    if delivery.delivery_job_id is not None:
        return get_agent_job(db, delivery.delivery_job_id)
    job = _enqueue_job(
        db,
        job_type="operational_alert_delivery",
        dedupe_key=f"operational-alert-delivery:{delivery.id}",
        payload_json={
            "schema_version": "operational-alert-delivery-job-v1",
            "delivery_id": str(delivery.id),
        },
        signer_identity=signer_identity,
        priority=5,
        max_attempts=4,
    )
    delivery = db.get(OperationalAlertDelivery, delivery_id)
    if delivery is not None and delivery.delivery_job_id is None:
        delivery.delivery_job_id = job.id
        db.commit()
        db.refresh(delivery)
    return job


def list_agent_jobs(
    db: Session,
    *,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AgentExecutionJob]:
    query = select(AgentExecutionJob)
    if status:
        query = query.where(AgentExecutionJob.status == status)
    if job_type:
        query = query.where(AgentExecutionJob.job_type == job_type)
    return list(
        db.scalars(
            query.order_by(AgentExecutionJob.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )


def get_agent_job(db: Session, job_id: UUID) -> AgentExecutionJob:
    job = db.get(AgentExecutionJob, job_id)
    if job is None:
        raise DomainValidationError("agent execution job was not found")
    return job


def get_agent_job_overview(
    db: Session,
    *,
    worker_offline_seconds: int = 90,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    observed_at = now or _utcnow()
    jobs = list(db.scalars(select(AgentExecutionJob)).all())
    workers = list(
        db.scalars(
            select(AgentWorkerState).order_by(AgentWorkerState.last_seen_at.desc())
        ).all()
    )
    status_counts = {
        status: sum(1 for job in jobs if job.status == status)
        for status in (
            "queued",
            "leased",
            "running",
            "completed",
            "failed",
            "cancelled",
        )
    }
    type_counts = {
        job_type: sum(1 for job in jobs if job.job_type == job_type)
        for job_type in (
            "resume_checkpoint",
            "checkpoint_reconciliation",
            "traffic_evidence_import",
            "model_validation_campaign",
            "trust_source_sync",
            "oidc_session_cleanup",
            "operational_observability_cycle",
            "operational_alert_delivery",
        )
    }
    queued_jobs = [job for job in jobs if job.status == "queued"]
    active_jobs = [job for job in jobs if job.status in {"leased", "running"}]
    recent_cutoff = observed_at - dt.timedelta(hours=24)
    recent_terminal = [
        job
        for job in jobs
        if job.completed_at is not None and job.completed_at >= recent_cutoff
    ]
    recent_completed = sum(1 for job in recent_terminal if job.status == "completed")
    recent_failed = sum(1 for job in recent_terminal if job.status == "failed")
    queue_latencies = [
        (job.started_at - job.created_at).total_seconds() * 1000
        for job in jobs
        if job.started_at is not None
    ]
    execution_durations = [
        (job.completed_at - job.started_at).total_seconds() * 1000
        for job in recent_terminal
        if job.started_at is not None and job.completed_at is not None
    ]
    offline_threshold = observed_at - dt.timedelta(
        seconds=max(10, int(worker_offline_seconds))
    )
    worker_rows = []
    online_worker_count = 0
    for worker in workers:
        effective_status = (
            "online"
            if worker.status == "online" and worker.last_seen_at >= offline_threshold
            else worker.status if worker.status == "stopped" else "offline"
        )
        if effective_status == "online":
            online_worker_count += 1
        worker_rows.append(
            {
                "worker_id": worker.worker_id,
                "status": effective_status,
                "started_at": worker.started_at,
                "last_seen_at": worker.last_seen_at,
                "current_job_id": worker.current_job_id,
                "processed_count": worker.processed_count,
                "completed_count": worker.completed_count,
                "failed_count": worker.failed_count,
                "metadata_json": worker.metadata_json,
            }
        )
    expired_lease_count = sum(
        1
        for job in active_jobs
        if job.lease_expires_at is not None and job.lease_expires_at <= observed_at
    )
    dead_letter_count = status_counts["failed"]
    health = "healthy"
    if expired_lease_count or dead_letter_count:
        health = "degraded"
    elif queued_jobs and not online_worker_count:
        health = "blocked"
    elif not jobs:
        health = "idle"
    return {
        "schema_version": AGENT_JOB_OPERATIONS_VERSION,
        "generated_at": observed_at,
        "health": health,
        "total_job_count": len(jobs),
        "status_counts": status_counts,
        "job_type_counts": type_counts,
        "queue_depth": len(queued_jobs),
        "retrying_count": sum(
            1 for job in queued_jobs if job.attempt_count > 0 or job.requeue_count > 0
        ),
        "active_lease_count": len(active_jobs),
        "expired_lease_count": expired_lease_count,
        "dead_letter_count": dead_letter_count,
        "oldest_queued_age_seconds": (
            round(
                max(
                    0.0,
                    (observed_at - min(job.created_at for job in queued_jobs)).total_seconds(),
                ),
                3,
            )
            if queued_jobs
            else None
        ),
        "completed_last_24h": recent_completed,
        "failed_last_24h": recent_failed,
        "success_rate_last_24h": (
            round(recent_completed / len(recent_terminal), 4)
            if recent_terminal
            else None
        ),
        "average_queue_latency_ms": _average(queue_latencies),
        "average_execution_duration_ms": _average(execution_durations),
        "online_worker_count": online_worker_count,
        "workers": worker_rows,
    }


def requeue_agent_job(
    db: Session,
    *,
    job_id: UUID,
    reason: str,
    signer_identity: SignerIdentity,
    max_attempts: int | None = None,
) -> AgentExecutionJob:
    _assert_maintenance_identity(signer_identity)
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise DomainValidationError("requeue reason is required")
    job = db.scalar(
        select(AgentExecutionJob)
        .where(AgentExecutionJob.id == job_id)
        .with_for_update()
    )
    if job is None:
        raise DomainValidationError("agent execution job was not found")
    if job.status != "failed":
        raise DomainValidationError(f"agent job cannot requeue from {job.status}")
    requeued_at = _utcnow()
    job.status = "queued"
    job.available_at = requeued_at
    job.lease_owner = None
    job.lease_token = None
    job.lease_expires_at = None
    job.last_heartbeat_at = None
    job.heartbeat_count = 0
    job.attempt_count = 0
    job.completed_at = None
    job.result_json = None
    job.last_error = None
    job.requeue_count += 1
    job.last_requeued_at = requeued_at
    job.last_requeued_by_identity_json = {
        **signer_identity.to_json(),
        "reason": normalized_reason[:1000],
    }
    if max_attempts is not None:
        job.max_attempts = max(1, min(int(max_attempts), 10))
    db.commit()
    db.refresh(job)
    return job


def claim_agent_job(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: dt.datetime | None = None,
) -> AgentExecutionJob | None:
    claimed_at = now or _utcnow()
    normalized_worker = worker_id.strip()
    if not normalized_worker:
        raise DomainValidationError("worker_id is required")
    bounded_lease = max(5, min(int(lease_seconds), MAX_LEASE_SECONDS))
    _recover_expired_leases(db, now=claimed_at)
    db.flush()
    job = db.scalar(
        select(AgentExecutionJob)
        .where(AgentExecutionJob.status == "queued")
        .where(AgentExecutionJob.available_at <= claimed_at)
        .where(AgentExecutionJob.attempt_count < AgentExecutionJob.max_attempts)
        .order_by(
            AgentExecutionJob.priority,
            AgentExecutionJob.available_at,
            AgentExecutionJob.created_at,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        db.commit()
        return None
    job.status = "leased"
    job.lease_owner = normalized_worker[:160]
    job.lease_token = uuid.uuid4().hex
    job.lease_expires_at = claimed_at + dt.timedelta(seconds=bounded_lease)
    job.last_heartbeat_at = claimed_at
    job.heartbeat_count = 1
    job.attempt_count += 1
    job.started_at = job.started_at or claimed_at
    job.last_error = None
    db.commit()
    db.refresh(job)
    return job


def heartbeat_agent_job(
    db: Session,
    *,
    job_id: UUID,
    lease_token: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> AgentExecutionJob:
    job = db.scalar(
        select(AgentExecutionJob)
        .where(AgentExecutionJob.id == job_id)
        .with_for_update()
    )
    if job is None or job.lease_token != lease_token:
        raise DomainValidationError("agent job lease token is invalid")
    if job.status not in {"leased", "running"}:
        raise DomainValidationError(f"agent job cannot heartbeat from {job.status}")
    heartbeat_at = _utcnow()
    job.lease_expires_at = heartbeat_at + dt.timedelta(
        seconds=max(5, min(int(lease_seconds), MAX_LEASE_SECONDS))
    )
    job.last_heartbeat_at = heartbeat_at
    job.heartbeat_count += 1
    db.commit()
    db.refresh(job)
    return job


def process_claimed_agent_job(
    db: Session,
    *,
    job_id: UUID,
    lease_token: str,
) -> AgentExecutionJob:
    job = get_agent_job(db, job_id)
    if job.lease_token != lease_token or job.status != "leased":
        raise DomainValidationError("agent job is not held by this worker lease")
    job.status = "running"
    db.commit()
    try:
        result = _execute_job(db, job)
    except Exception as exc:
        db.rollback()
        failed_job = get_agent_job(db, job_id)
        failed_job.last_error = str(exc)[:4000]
        failed_job.lease_expires_at = None
        if isinstance(exc, DomainValidationError) or (
            failed_job.attempt_count >= failed_job.max_attempts
        ):
            _mark_dead_letter(
                failed_job,
                reason=failed_job.last_error or "Agent job failed.",
            )
        else:
            failed_job.status = "queued"
            failed_job.available_at = _utcnow() + dt.timedelta(
                seconds=_retry_delay_seconds(failed_job)
            )
            failed_job.lease_owner = None
            failed_job.lease_token = None
        db.commit()
        db.refresh(failed_job)
        return failed_job

    completed_job = get_agent_job(db, job_id)
    completed_job.status = "completed"
    completed_job.result_json = result
    completed_job.completed_at = _utcnow()
    completed_job.lease_expires_at = None
    completed_job.lease_token = None
    db.commit()
    db.refresh(completed_job)
    return completed_job


def run_agent_worker_once(
    db: Session,
    *,
    worker_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> AgentExecutionJob | None:
    job = claim_agent_job(
        db,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    if job is None or job.lease_token is None:
        return job
    return process_claimed_agent_job(
        db,
        job_id=job.id,
        lease_token=job.lease_token,
    )


def system_worker_identity(worker_id: str) -> SignerIdentity:
    normalized = worker_id.strip() or "model-atlas-worker"
    return SignerIdentity(
        subject_id=normalized,
        display_name=normalized,
        role="System Worker",
        identity_provider="model-atlas-worker",
        auth_source="durable_job_lease",
        identity_verified=True,
        ticket_reference=None,
    )


def register_agent_worker(
    db: Session,
    *,
    worker_id: str,
    metadata_json: dict[str, Any] | None = None,
) -> AgentWorkerState:
    normalized_worker = worker_id.strip()
    if not normalized_worker:
        raise DomainValidationError("worker_id is required")
    observed_at = _utcnow()
    worker = db.get(AgentWorkerState, normalized_worker)
    if worker is None:
        worker = AgentWorkerState(
            worker_id=normalized_worker[:160],
            status="online",
            started_at=observed_at,
            last_seen_at=observed_at,
            metadata_json=dict(metadata_json or {}),
        )
        db.add(worker)
    else:
        worker.status = "online"
        worker.started_at = observed_at
        worker.last_seen_at = observed_at
        worker.current_job_id = None
        worker.metadata_json = dict(metadata_json or worker.metadata_json)
    db.commit()
    db.refresh(worker)
    return worker


def heartbeat_agent_worker(
    db: Session,
    *,
    worker_id: str,
    current_job_id: UUID | None,
) -> AgentWorkerState:
    worker = db.scalar(
        select(AgentWorkerState)
        .where(AgentWorkerState.worker_id == worker_id)
        .with_for_update()
    )
    if worker is None:
        raise DomainValidationError("agent worker is not registered")
    worker.status = "online"
    worker.last_seen_at = _utcnow()
    worker.current_job_id = current_job_id
    db.commit()
    db.refresh(worker)
    return worker


def record_agent_worker_outcome(
    db: Session,
    *,
    worker_id: str,
    job_status: str,
) -> AgentWorkerState:
    worker = db.scalar(
        select(AgentWorkerState)
        .where(AgentWorkerState.worker_id == worker_id)
        .with_for_update()
    )
    if worker is None:
        raise DomainValidationError("agent worker is not registered")
    worker.last_seen_at = _utcnow()
    worker.current_job_id = None
    worker.processed_count += 1
    if job_status == "completed":
        worker.completed_count += 1
    elif job_status == "failed":
        worker.failed_count += 1
    db.commit()
    db.refresh(worker)
    return worker


def mark_agent_worker_stopped(
    db: Session,
    *,
    worker_id: str,
) -> AgentWorkerState | None:
    worker = db.get(AgentWorkerState, worker_id)
    if worker is None:
        return None
    worker.status = "stopped"
    worker.last_seen_at = _utcnow()
    worker.current_job_id = None
    db.commit()
    db.refresh(worker)
    return worker


def _enqueue_job(
    db: Session,
    *,
    job_type: str,
    dedupe_key: str,
    payload_json: dict[str, Any],
    signer_identity: SignerIdentity,
    priority: int,
    benchmark_run_id: UUID | None = None,
    benchmark_result_id: UUID | None = None,
    checkpoint_record_id: UUID | None = None,
    max_attempts: int = 3,
) -> AgentExecutionJob:
    existing = db.scalar(
        select(AgentExecutionJob).where(AgentExecutionJob.dedupe_key == dedupe_key)
    )
    if existing is not None:
        return existing
    job = AgentExecutionJob(
        job_type=job_type,
        status="queued",
        dedupe_key=dedupe_key,
        payload_json=payload_json,
        requested_by_identity_json=signer_identity.to_json(),
        benchmark_run_id=benchmark_run_id,
        benchmark_result_id=benchmark_result_id,
        checkpoint_record_id=checkpoint_record_id,
        priority=priority,
        available_at=_utcnow(),
        max_attempts=max_attempts,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(AgentExecutionJob).where(AgentExecutionJob.dedupe_key == dedupe_key)
        )
        if existing is None:
            raise
        return existing
    db.refresh(job)
    return job


def _execute_job(db: Session, job: AgentExecutionJob) -> dict[str, Any]:
    identity = _identity_from_json(job.requested_by_identity_json)
    if job.job_type == "resume_checkpoint":
        outcome = resume_agent_approval_checkpoint(
            db,
            checkpoint_record_id=UUID(str(job.payload_json["checkpoint_record_id"])),
            expected_version=int(job.payload_json["expected_version"]),
            signer_identity=identity,
        )
        return {
            "schema_version": AGENT_JOB_CONTRACT_VERSION,
            "checkpoint_record_id": str(outcome.checkpoint.id),
            "benchmark_run_id": str(outcome.benchmark_run_id),
            "benchmark_result_id": str(outcome.benchmark_result_id),
            "parent_benchmark_run_id": str(outcome.parent_benchmark_run_id),
            "parent_benchmark_result_id": str(outcome.parent_benchmark_result_id),
            "result_revision": outcome.result_revision,
            "trace_status": outcome.trace.get("status"),
        }
    if job.job_type == "checkpoint_reconciliation":
        checkpoint_outcome = reconcile_agent_approval_checkpoints(db)
        gate_outcome = reconcile_all_gate_staleness(db)
        return {
            "schema_version": AGENT_JOB_CONTRACT_VERSION,
            "checkpoint_reconciliation": checkpoint_outcome,
            "gate_staleness": gate_outcome.to_json(),
        }
    if job.job_type == "traffic_evidence_import":
        from app.services.agent_traffic_ingestion import import_traffic_job_payload

        return import_traffic_job_payload(db, payload=job.payload_json)
    if job.job_type == "model_validation_campaign":
        from app.services.model_validation import execute_model_validation_job

        return execute_model_validation_job(
            db,
            job=job,
            requester_identity=identity,
        )
    if job.job_type == "trust_source_sync":
        from app.core.config import get_settings
        from app.services.trust_source_scheduler import execute_trust_source_sync_job

        settings = get_settings()
        return execute_trust_source_sync_job(
            db,
            job=job,
            executor_identity=system_worker_identity(job.lease_owner or identity.subject_id),
            allowed_hosts=settings.trust_source_allowed_hosts,
            allow_insecure_http=settings.trust_source_allow_insecure_http,
            timeout_seconds=settings.trust_source_http_timeout_seconds,
            max_bytes=settings.trust_source_max_jwks_bytes,
        )
    if job.job_type == "oidc_session_cleanup":
        from app.services.oidc_session_administration import cleanup_browser_sessions

        return cleanup_browser_sessions(
            db,
            signer_identity=system_worker_identity(
                job.lease_owner or identity.subject_id
            ),
            retention_days=int(job.payload_json["retention_days"]),
            batch_size=int(job.payload_json["batch_size"]),
            reason=str(job.payload_json["reason"]),
        )
    if job.job_type == "operational_observability_cycle":
        from app.core.config import get_settings
        from app.services.operational_reliability import (
            capture_operational_reliability_cycle,
        )

        settings = get_settings()
        executor_identity = system_worker_identity(
            job.lease_owner or identity.subject_id
        )
        result = capture_operational_reliability_cycle(
            db,
            settings=settings,
            collector_identity=executor_identity,
            reason=str(job.payload_json["reason"]),
        )
        delivery_job_ids = [
            str(
                enqueue_operational_alert_delivery_job(
                    db,
                    delivery_id=UUID(delivery_id),
                    signer_identity=executor_identity,
                ).id
            )
            for delivery_id in result["delivery_ids"]
        ]
        return {**result, "delivery_job_ids": delivery_job_ids}
    if job.job_type == "operational_alert_delivery":
        from app.core.config import get_settings
        from app.services.operational_reliability import (
            execute_operational_alert_delivery,
        )

        return execute_operational_alert_delivery(
            db,
            delivery_id=UUID(str(job.payload_json["delivery_id"])),
            settings=get_settings(),
            attempt_number=job.attempt_count,
            max_attempts=job.max_attempts,
        )
    raise DomainValidationError(f"unsupported agent job type: {job.job_type}")


def _retry_delay_seconds(job: AgentExecutionJob) -> int:
    if job.job_type == "trust_source_sync":
        from app.services.trust_source_scheduler import retry_delay_seconds

        return retry_delay_seconds(job)
    return min(60, 2**job.attempt_count)


def _recover_expired_leases(db: Session, *, now: dt.datetime) -> None:
    expired = list(
        db.scalars(
            select(AgentExecutionJob)
            .where(AgentExecutionJob.status.in_(["leased", "running"]))
            .where(AgentExecutionJob.lease_expires_at <= now)
            .with_for_update(skip_locked=True)
        ).all()
    )
    for job in expired:
        job.last_error = "Worker lease expired before completion."
        job.lease_owner = None
        job.lease_token = None
        job.lease_expires_at = None
        if job.attempt_count >= job.max_attempts:
            _mark_dead_letter(
                job,
                reason=job.last_error,
                now=now,
            )
        else:
            job.status = "queued"
            job.available_at = now


def _mark_dead_letter(
    job: AgentExecutionJob,
    *,
    reason: str,
    now: dt.datetime | None = None,
) -> None:
    dead_lettered_at = now or _utcnow()
    job.status = "failed"
    job.completed_at = dead_lettered_at
    job.lease_expires_at = None
    job.lease_token = None
    job.dead_lettered_at = dead_lettered_at
    job.dead_letter_reason = reason[:4000]


def _assert_maintenance_identity(identity: SignerIdentity) -> None:
    role = (identity.role or "").strip().lower()
    if not identity.identity_verified or role not in MAINTENANCE_ROLES:
        raise DomainValidationError(
            "Agent maintenance requires a verified Release Manager, ML Ops Lead, "
            "SRE Lead, Admin, or System Worker identity"
        )


def _identity_from_json(payload: dict[str, Any]) -> SignerIdentity:
    return SignerIdentity(
        subject_id=str(payload.get("subject_id") or "unknown-job-requester"),
        display_name=str(payload.get("display_name") or "Unknown job requester"),
        role=str(payload["role"]) if payload.get("role") else None,
        identity_provider=str(payload.get("identity_provider") or "unknown"),
        auth_source=str(payload.get("auth_source") or "unknown"),
        identity_verified=bool(payload.get("identity_verified", False)),
        ticket_reference=(
            str(payload["ticket_reference"])
            if payload.get("ticket_reference")
            else None
        ),
    )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)
