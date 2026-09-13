from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    AgentExecutionJob,
    EvidenceTrustSource,
    EvidenceTrustSourceSchedule,
)
from app.schemas import (
    EvidenceTrustSourceScheduleRead,
    EvidenceTrustSourceScheduleUpsert,
    EvidenceTrustSourceSyncCreate,
)
from app.services.deployment_gate.evidence import stable_hash
from app.services.operator_identity import SignerIdentity
from app.services.trust_registry import assert_governance_operator
from app.services.trust_source_sync import (
    JwksFetcher,
    TrustSourceSyncContext,
    fetch_remote_jwks,
    sync_evidence_trust_source,
)
from app.validators import DomainValidationError

TRUST_SOURCE_SCHEDULE_VERSION = "model-atlas-trust-source-schedule-v1"
TRUST_SOURCE_SCHEDULE_JOB_VERSION = "model-atlas-trust-source-schedule-job-v1"
TRUST_SOURCE_SCHEDULE_RESPONSE_VERSION = "model-atlas-trust-source-schedule-response-v1"
ACTIVE_JOB_STATUSES = frozenset({"queued", "leased", "running"})
RETRYABLE_SYNC_ERRORS = frozenset(
    {
        "transport_error",
        "http_error",
        "database_conflict",
    }
)


class TrustSourceSyncRetryableError(RuntimeError):
    pass


def upsert_evidence_trust_source_schedule(
    db: Session,
    *,
    trust_source_id: UUID,
    payload: EvidenceTrustSourceScheduleUpsert,
    signer_identity: SignerIdentity,
    now: dt.datetime | None = None,
) -> EvidenceTrustSourceScheduleRead:
    assert_governance_operator(signer_identity)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    trust_source = db.scalar(
        select(EvidenceTrustSource)
        .where(EvidenceTrustSource.id == trust_source_id)
        .with_for_update()
    )
    if trust_source is None:
        raise DomainValidationError("evidence trust source was not found")
    if payload.enabled and not trust_source.enabled:
        raise DomainValidationError("disabled trust sources cannot be scheduled")

    schedule = db.scalar(
        select(EvidenceTrustSourceSchedule)
        .where(EvidenceTrustSourceSchedule.trust_source_id == trust_source.id)
        .with_for_update()
    )
    if schedule is not None:
        _cancel_or_reject_active_job(db, schedule=schedule, now=observed_at)

    policy_hash = _policy_hash(payload)
    next_run_at = _next_policy_run_at(
        schedule=schedule,
        payload=payload,
        observed_at=observed_at,
        trust_source_id=trust_source.id,
    )
    if schedule is None:
        schedule = EvidenceTrustSourceSchedule(
            trust_source_id=trust_source.id,
            enabled=payload.enabled,
            interval_seconds=payload.interval_seconds,
            jitter_seconds=payload.jitter_seconds,
            max_attempts=payload.max_attempts,
            retry_base_seconds=payload.retry_base_seconds,
            retry_max_seconds=payload.retry_max_seconds,
            retry_jitter_seconds=payload.retry_jitter_seconds,
            next_run_at=next_run_at,
            policy_hash=policy_hash,
            configured_by_identity_json=signer_identity.to_json(),
            identity_verified=True,
        )
        db.add(schedule)
    else:
        schedule.enabled = payload.enabled
        schedule.interval_seconds = payload.interval_seconds
        schedule.jitter_seconds = payload.jitter_seconds
        schedule.max_attempts = payload.max_attempts
        schedule.retry_base_seconds = payload.retry_base_seconds
        schedule.retry_max_seconds = payload.retry_max_seconds
        schedule.retry_jitter_seconds = payload.retry_jitter_seconds
        schedule.next_run_at = next_run_at
        schedule.policy_hash = policy_hash
        schedule.configured_by_identity_json = signer_identity.to_json()
        schedule.identity_verified = True
        _clear_schedule_lease(schedule)
    db.commit()
    db.refresh(schedule)
    return evidence_trust_source_schedule_read(db, schedule, now=observed_at)


def request_evidence_trust_source_schedule_run(
    db: Session,
    *,
    trust_source_id: UUID,
    signer_identity: SignerIdentity,
    now: dt.datetime | None = None,
) -> EvidenceTrustSourceScheduleRead:
    assert_governance_operator(signer_identity)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    schedule = db.scalar(
        select(EvidenceTrustSourceSchedule)
        .where(EvidenceTrustSourceSchedule.trust_source_id == trust_source_id)
        .with_for_update()
    )
    if schedule is None:
        raise DomainValidationError("trust source schedule was not found")
    if not schedule.enabled:
        raise DomainValidationError("disabled trust source schedules cannot run")
    _cancel_or_reject_active_job(db, schedule=schedule, now=observed_at)
    schedule.next_run_at = observed_at
    _clear_schedule_lease(schedule)
    db.commit()
    db.refresh(schedule)
    return evidence_trust_source_schedule_read(db, schedule, now=observed_at)


def list_evidence_trust_source_schedules(
    db: Session,
    *,
    limit: int = 100,
    now: dt.datetime | None = None,
) -> list[EvidenceTrustSourceScheduleRead]:
    observed_at = _utc(now or dt.datetime.now(dt.UTC))
    schedules = list(
        db.scalars(
            select(EvidenceTrustSourceSchedule)
            .order_by(EvidenceTrustSourceSchedule.created_at.desc())
            .limit(limit)
        ).all()
    )
    return [
        evidence_trust_source_schedule_read(db, schedule, now=observed_at)
        for schedule in schedules
    ]


def evidence_trust_source_schedule_read(
    db: Session,
    schedule: EvidenceTrustSourceSchedule,
    *,
    now: dt.datetime | None = None,
) -> EvidenceTrustSourceScheduleRead:
    observed_at = _utc(now or dt.datetime.now(dt.UTC))
    last_job = db.get(AgentExecutionJob, schedule.last_job_id) if schedule.last_job_id else None
    status = _schedule_status(schedule, last_job=last_job, now=observed_at)
    values = {
        column.name: getattr(schedule, column.name)
        for column in EvidenceTrustSourceSchedule.__table__.columns
        if column.name != "lease_token_hash"
    }
    return EvidenceTrustSourceScheduleRead.model_validate(
        {
            **values,
            "status": status,
            "last_job_status": last_job.status if last_job is not None else None,
        }
    )


def trust_source_schedule_overview(
    db: Session,
    *,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    reads = list_evidence_trust_source_schedules(db, limit=10_000, now=now)
    return {
        "schedule_count": len(reads),
        "enabled_count": sum(item.enabled for item in reads),
        "due_count": sum(item.status == "due" for item in reads),
        "leased_count": sum(item.status == "leased" for item in reads),
        "retrying_count": sum(item.status == "retrying" for item in reads),
        "failed_count": sum(item.status == "failed" for item in reads),
    }


def enqueue_due_trust_source_sync_jobs(
    db: Session,
    *,
    scheduler_id: str,
    signer_identity: SignerIdentity,
    lease_seconds: int = 900,
    batch_size: int = 20,
    now: dt.datetime | None = None,
) -> list[AgentExecutionJob]:
    _assert_scheduler_identity(signer_identity)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    normalized_scheduler = scheduler_id.strip()
    if not normalized_scheduler:
        raise DomainValidationError("scheduler_id is required")
    bounded_lease = max(30, min(int(lease_seconds), 3600))
    bounded_batch = max(1, min(int(batch_size), 100))
    schedules = list(
        db.scalars(
            select(EvidenceTrustSourceSchedule)
            .where(EvidenceTrustSourceSchedule.enabled.is_(True))
            .where(EvidenceTrustSourceSchedule.next_run_at <= observed_at)
            .where(
                or_(
                    EvidenceTrustSourceSchedule.lease_expires_at.is_(None),
                    EvidenceTrustSourceSchedule.lease_expires_at <= observed_at,
                )
            )
            .order_by(
                EvidenceTrustSourceSchedule.next_run_at,
                EvidenceTrustSourceSchedule.created_at,
            )
            .with_for_update(skip_locked=True)
            .limit(bounded_batch)
        ).all()
    )
    enqueued: list[AgentExecutionJob] = []
    for schedule in schedules:
        trust_source = db.get(EvidenceTrustSource, schedule.trust_source_id)
        if trust_source is None or not trust_source.enabled:
            schedule.enabled = False
            _clear_schedule_lease(schedule)
            continue
        last_job = db.get(AgentExecutionJob, schedule.last_job_id) if schedule.last_job_id else None
        if last_job is not None and last_job.status in ACTIVE_JOB_STATUSES:
            lease_fingerprint = str(
                last_job.payload_json.get("schedule_lease_token_hash") or ""
            )
            if lease_fingerprint:
                schedule.lease_token_hash = lease_fingerprint
                schedule.lease_owner = last_job.lease_owner or normalized_scheduler[:160]
                schedule.lease_expires_at = observed_at + dt.timedelta(
                    seconds=bounded_lease
                )
            continue

        schedule.run_sequence += 1
        lease_token_hash = _token_hash(uuid.uuid4().hex + uuid.uuid4().hex)
        scheduled_for = _utc(schedule.next_run_at).replace(microsecond=0)
        job = AgentExecutionJob(
            job_type="trust_source_sync",
            status="queued",
            dedupe_key=f"trust-source-sync:{schedule.id}:run:{schedule.run_sequence}",
            payload_json={
                "schema_version": TRUST_SOURCE_SCHEDULE_JOB_VERSION,
                "schedule_id": str(schedule.id),
                "trust_source_id": str(schedule.trust_source_id),
                "policy_hash": schedule.policy_hash,
                "run_sequence": schedule.run_sequence,
                "scheduled_for": scheduled_for.isoformat(),
                "schedule_lease_token_hash": lease_token_hash,
                "schedule_lease_seconds": bounded_lease,
                "retry_policy": {
                    "base_seconds": schedule.retry_base_seconds,
                    "max_seconds": schedule.retry_max_seconds,
                    "jitter_seconds": schedule.retry_jitter_seconds,
                },
            },
            requested_by_identity_json=signer_identity.to_json(),
            priority=15,
            available_at=observed_at,
            max_attempts=schedule.max_attempts,
        )
        db.add(job)
        db.flush()
        schedule.last_job_id = job.id
        schedule.last_enqueued_at = observed_at
        schedule.lease_owner = normalized_scheduler[:160]
        schedule.lease_token_hash = lease_token_hash
        schedule.lease_expires_at = observed_at + dt.timedelta(seconds=bounded_lease)
        enqueued.append(job)
    db.commit()
    for job in enqueued:
        db.refresh(job)
    return enqueued


def execute_trust_source_sync_job(
    db: Session,
    *,
    job: AgentExecutionJob,
    executor_identity: SignerIdentity,
    allowed_hosts: list[str],
    allow_insecure_http: bool,
    timeout_seconds: float,
    max_bytes: int,
    fetcher: JwksFetcher | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    payload = job.payload_json
    if payload.get("schema_version") != TRUST_SOURCE_SCHEDULE_JOB_VERSION:
        raise DomainValidationError("trust source schedule job schema_version is not supported")
    schedule_id = _uuid_value(payload, "schedule_id")
    trust_source_id = _uuid_value(payload, "trust_source_id")
    schedule = db.scalar(
        select(EvidenceTrustSourceSchedule)
        .where(EvidenceTrustSourceSchedule.id == schedule_id)
        .with_for_update()
    )
    if schedule is None:
        raise DomainValidationError("trust source schedule was not found")
    scheduled_for = _datetime_value(payload, "scheduled_for")
    lease_token_hash = str(payload.get("schedule_lease_token_hash") or "")
    lineage_matches = bool(
        schedule.enabled
        and schedule.trust_source_id == trust_source_id
        and schedule.last_job_id == job.id
        and schedule.policy_hash == str(payload.get("policy_hash") or "")
        and schedule.run_sequence == int(payload.get("run_sequence") or -1)
        and schedule.lease_token_hash is not None
        and len(lease_token_hash) == 64
        and hmac.compare_digest(schedule.lease_token_hash, lease_token_hash)
    )
    if not lineage_matches:
        if schedule.last_job_id == job.id:
            schedule.next_run_at = observed_at
            _clear_schedule_lease(schedule)
            db.commit()
        return {
            "schema_version": TRUST_SOURCE_SCHEDULE_RESPONSE_VERSION,
            "outcome": "skipped",
            "reason": "schedule policy or lease changed before execution",
            "schedule_id": str(schedule.id),
            "job_id": str(job.id),
        }

    response = sync_evidence_trust_source(
        db,
        trust_source_id=trust_source_id,
        payload=EvidenceTrustSourceSyncCreate(
            mode="apply",
            notes=f"Scheduled trust-source sync run {schedule.run_sequence}",
        ),
        signer_identity=executor_identity,
        allowed_hosts=allowed_hosts,
        allow_insecure_http=allow_insecure_http,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        fetcher=fetcher or fetch_remote_jwks,
        execution_context=TrustSourceSyncContext(
            trigger="scheduled",
            schedule_id=schedule.id,
            job_id=job.id,
            attempt_number=job.attempt_count,
            scheduled_for=scheduled_for,
        ),
        now=observed_at,
    )
    completed_at = _utc(response.sync.completed_at).replace(microsecond=0)
    schedule = db.scalar(
        select(EvidenceTrustSourceSchedule)
        .where(EvidenceTrustSourceSchedule.id == schedule_id)
        .with_for_update()
    )
    if schedule is None:
        raise DomainValidationError("trust source schedule disappeared during execution")
    schedule.last_sync_id = response.sync.id
    schedule.last_completed_at = completed_at

    if response.sync.status == "succeeded":
        schedule.consecutive_failures = 0
        schedule.next_run_at = _next_scheduled_at(schedule, anchor=completed_at)
        _clear_schedule_lease(schedule)
        db.commit()
        return {
            "schema_version": TRUST_SOURCE_SCHEDULE_RESPONSE_VERSION,
            "outcome": "succeeded",
            "schedule_id": str(schedule.id),
            "trust_source_id": str(schedule.trust_source_id),
            "sync_id": str(response.sync.id),
            "attempt_number": job.attempt_count,
            "next_run_at": schedule.next_run_at.isoformat(),
            "imported_count": response.sync.imported_count,
            "unchanged_count": response.sync.unchanged_count,
        }

    schedule.consecutive_failures += 1
    retryable = response.sync.error_code in RETRYABLE_SYNC_ERRORS
    attempts_remaining = job.attempt_count < job.max_attempts
    if retryable and attempts_remaining:
        lease_seconds = max(30, min(int(payload.get("schedule_lease_seconds") or 900), 3600))
        schedule.lease_expires_at = completed_at + dt.timedelta(
            seconds=lease_seconds + schedule.retry_max_seconds
        )
        db.commit()
        raise TrustSourceSyncRetryableError(
            f"scheduled trust source sync failed with {response.sync.error_code}"
        )

    schedule.next_run_at = _next_scheduled_at(schedule, anchor=completed_at)
    _clear_schedule_lease(schedule)
    db.commit()
    message = f"scheduled trust source sync failed with {response.sync.error_code}"
    if retryable:
        raise TrustSourceSyncRetryableError(message)
    raise DomainValidationError(message)


def retry_delay_seconds(job: AgentExecutionJob) -> int:
    policy = job.payload_json.get("retry_policy")
    if not isinstance(policy, dict):
        return min(60, 2**job.attempt_count)
    base = max(1, min(int(policy.get("base_seconds") or 1), 3600))
    maximum = max(base, min(int(policy.get("max_seconds") or base), 3600))
    jitter = max(0, min(int(policy.get("jitter_seconds") or 0), maximum))
    delay = min(maximum, base * (2 ** max(0, job.attempt_count - 1)))
    return min(maximum, delay + _deterministic_jitter(f"{job.id}:{job.attempt_count}", jitter))


def _cancel_or_reject_active_job(
    db: Session,
    *,
    schedule: EvidenceTrustSourceSchedule,
    now: dt.datetime,
) -> None:
    if schedule.last_job_id is None:
        return
    job = db.get(AgentExecutionJob, schedule.last_job_id)
    if job is None or job.status not in ACTIVE_JOB_STATUSES:
        return
    if job.status in {"leased", "running"}:
        raise DomainValidationError(
            "trust source schedule cannot change while a sync job is active"
        )
    job.status = "cancelled"
    job.completed_at = now
    job.last_error = "Cancelled because the trust-source schedule changed."


def _next_policy_run_at(
    *,
    schedule: EvidenceTrustSourceSchedule | None,
    payload: EvidenceTrustSourceScheduleUpsert,
    observed_at: dt.datetime,
    trust_source_id: UUID,
) -> dt.datetime:
    if payload.run_immediately and payload.enabled:
        return observed_at
    if schedule is not None and schedule.enabled and payload.enabled:
        return max(_utc(schedule.next_run_at), observed_at)
    jitter = _deterministic_jitter(
        f"{trust_source_id}:{payload.interval_seconds}:initial",
        payload.jitter_seconds,
    )
    return observed_at + dt.timedelta(seconds=payload.interval_seconds + jitter)


def _next_scheduled_at(
    schedule: EvidenceTrustSourceSchedule,
    *,
    anchor: dt.datetime,
) -> dt.datetime:
    jitter = _deterministic_jitter(
        f"{schedule.id}:{schedule.run_sequence + 1}",
        schedule.jitter_seconds,
    )
    return _utc(anchor) + dt.timedelta(seconds=schedule.interval_seconds + jitter)


def _schedule_status(
    schedule: EvidenceTrustSourceSchedule,
    *,
    last_job: AgentExecutionJob | None,
    now: dt.datetime,
) -> str:
    if not schedule.enabled:
        return "disabled"
    if last_job is not None and last_job.status in ACTIVE_JOB_STATUSES:
        if last_job.status == "queued" and last_job.attempt_count > 0:
            return "retrying"
        return "leased"
    if _utc(schedule.next_run_at) <= now:
        return "due"
    if schedule.consecutive_failures > 0 and last_job is not None and last_job.status == "failed":
        return "failed"
    return "scheduled"


def _policy_hash(payload: EvidenceTrustSourceScheduleUpsert) -> str:
    return stable_hash(
        {
            "schema_version": TRUST_SOURCE_SCHEDULE_VERSION,
            **payload.model_dump(exclude={"run_immediately"}),
        }
    )


def _clear_schedule_lease(schedule: EvidenceTrustSourceSchedule) -> None:
    schedule.lease_owner = None
    schedule.lease_token_hash = None
    schedule.lease_expires_at = None


def _assert_scheduler_identity(identity: SignerIdentity) -> None:
    role = (identity.role or "").strip().lower()
    if not identity.identity_verified or role not in {"system worker", "admin", "sre lead"}:
        raise DomainValidationError(
            "trust source scheduling requires a verified System Worker, Admin, or SRE Lead"
        )


def _uuid_value(payload: dict[str, Any], key: str) -> UUID:
    try:
        return UUID(str(payload[key]))
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainValidationError(f"trust source schedule job {key} is invalid") from exc


def _datetime_value(payload: dict[str, Any], key: str) -> dt.datetime:
    try:
        value = dt.datetime.fromisoformat(str(payload[key]).replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise DomainValidationError(f"trust source schedule job {key} is invalid") from exc
    if value.tzinfo is None:
        raise DomainValidationError(f"trust source schedule job {key} requires timezone")
    return value.astimezone(dt.UTC)


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _deterministic_jitter(key: str, maximum: int) -> int:
    if maximum <= 0:
        return 0
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (maximum + 1)


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)
