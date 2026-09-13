from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import AgentExecutionJob, AgentTrafficReceipt
from app.schemas import AgentEvidenceImportCreate, AgentTrafficEvidenceBatchCreate
from app.services.agent_evidence_import import import_production_agent_evidence
from app.services.agent_jobs import enqueue_traffic_evidence_job
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

AGENT_TRAFFIC_BATCH_CONTRACT_VERSION = "production-agent-traffic-batch-v1"
AGENT_TRAFFIC_SIGNATURE_V1 = "hmac-sha256-v1"
AGENT_TRAFFIC_SIGNATURE_V2 = "hmac-sha256-v2"
AGENT_TRAFFIC_SOURCE_STATUS_VERSION = "agent-traffic-source-status-v1"


def queue_signed_traffic_batch(
    db: Session,
    *,
    payload: AgentTrafficEvidenceBatchCreate,
    supplied_signature: str,
    hmac_keys: dict[str, str],
    signature_version: str = AGENT_TRAFFIC_SIGNATURE_V1,
    key_id: str | None = None,
    nonce: str | None = None,
    sent_at: str | dt.datetime | None = None,
    allow_legacy_signatures: bool = True,
    max_clock_skew_seconds: int = 300,
    now: dt.datetime | None = None,
) -> AgentExecutionJob:
    normalized_version = signature_version.strip().lower()
    if normalized_version not in {
        AGENT_TRAFFIC_SIGNATURE_V1,
        AGENT_TRAFFIC_SIGNATURE_V2,
    }:
        raise DomainValidationError("traffic signature version is not supported")
    if normalized_version == AGENT_TRAFFIC_SIGNATURE_V1 and not allow_legacy_signatures:
        raise DomainValidationError("legacy traffic signatures are disabled")
    normalized_key_id = (key_id or "legacy").strip()
    normalized_nonce = (nonce or f"legacy:{payload.batch_id}").strip()
    if normalized_version == AGENT_TRAFFIC_SIGNATURE_V2:
        if not key_id or not normalized_key_id:
            raise DomainValidationError("traffic key id is required for signature v2")
        if not nonce or len(normalized_nonce) < 16 or len(normalized_nonce) > 160:
            raise DomainValidationError("traffic nonce must contain 16 to 160 characters")
        if sent_at is None:
            raise DomainValidationError("traffic sent-at timestamp is required")
    normalized_sent_at = _parse_timestamp(
        sent_at or payload.captured_at,
        field_name="traffic sent-at",
    )
    secret = _traffic_secret(
        hmac_keys,
        source_system=payload.source_system,
        key_id=normalized_key_id,
        signature_version=normalized_version,
    )
    canonical_payload = payload.model_dump(mode="json")
    expected_signature = traffic_batch_signature(
        canonical_payload,
        secret=secret,
        signature_version=normalized_version,
        key_id=normalized_key_id,
        nonce=normalized_nonce,
        sent_at=normalized_sent_at,
    )
    normalized_signature = _normalized_signature(supplied_signature)
    if not hmac.compare_digest(expected_signature, normalized_signature):
        raise DomainValidationError("traffic batch signature verification failed")
    signature_hash = hashlib.sha256(
        normalized_signature.encode("ascii")
    ).hexdigest()
    _validate_batch_provenance(payload)

    existing = _matching_receipt(
        db,
        source_system=payload.source_system,
        batch_id=payload.batch_id,
        nonce=normalized_nonce,
    )
    if existing is not None:
        return _record_idempotent_replay(
            db,
            existing=existing,
            batch_id=payload.batch_id,
            nonce=normalized_nonce,
            signature_hash=signature_hash,
        )

    observed_at = now or _utcnow()
    if normalized_version == AGENT_TRAFFIC_SIGNATURE_V2:
        skew = abs((observed_at - normalized_sent_at).total_seconds())
        if skew > max(1, int(max_clock_skew_seconds)):
            raise DomainValidationError("traffic sent-at timestamp is outside the allowed skew")

    machine_identity = SignerIdentity(
        subject_id=(
            f"traffic-collector:{payload.source_system}:{normalized_key_id}"
        ),
        display_name=f"Traffic collector {payload.source_system}",
        role="ML Ops Lead",
        identity_provider="traffic-hmac",
        auth_source="signed_traffic_batch",
        identity_verified=True,
        ticket_reference=payload.batch_id,
    )
    job_payload = {
        "schema_version": AGENT_TRAFFIC_BATCH_CONTRACT_VERSION,
        "signature_version": normalized_version,
        "signature_hash": signature_hash,
        "key_id": normalized_key_id,
        "nonce": normalized_nonce,
        "sent_at": normalized_sent_at.isoformat(),
        "batch": canonical_payload,
        "collector_identity": machine_identity.to_json(),
    }
    job = enqueue_traffic_evidence_job(
        db,
        source_system=payload.source_system,
        batch_id=payload.batch_id,
        payload_json=job_payload,
        signer_identity=machine_identity,
    )
    receipt = AgentTrafficReceipt(
        source_system=payload.source_system,
        batch_id=payload.batch_id,
        nonce=normalized_nonce,
        signature_version=normalized_version,
        signature_hash=signature_hash,
        key_id=normalized_key_id,
        collector_version=payload.collector_version,
        captured_at=payload.captured_at,
        sent_at=normalized_sent_at,
        received_at=observed_at,
        last_seen_at=observed_at,
        job_id=job.id,
    )
    db.add(receipt)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = _matching_receipt(
            db,
            source_system=payload.source_system,
            batch_id=payload.batch_id,
            nonce=normalized_nonce,
        )
        if existing is None:
            raise
        return _record_idempotent_replay(
            db,
            existing=existing,
            batch_id=payload.batch_id,
            nonce=normalized_nonce,
            signature_hash=signature_hash,
        )
    db.refresh(job)
    return job


def list_traffic_source_status(
    db: Session,
    *,
    hmac_keys: dict[str, str],
    stale_after_seconds: int = 300,
    now: dt.datetime | None = None,
) -> list[dict[str, Any]]:
    observed_at = now or _utcnow()
    receipts = list(
        db.scalars(
            select(AgentTrafficReceipt).order_by(
                AgentTrafficReceipt.last_seen_at.desc()
            )
        ).all()
    )
    configured_sources: dict[str, set[str]] = {}
    for compound_key in hmac_keys:
        source_system, separator, key_id = compound_key.partition(":")
        configured_sources.setdefault(source_system, set()).add(
            key_id if separator else "legacy"
        )
    source_names = sorted(
        set(configured_sources)
        | {receipt.source_system for receipt in receipts}
    )
    rows: list[dict[str, Any]] = []
    stale_cutoff = observed_at - dt.timedelta(
        seconds=max(10, int(stale_after_seconds))
    )
    for source_system in source_names:
        source_receipts = [
            receipt
            for receipt in receipts
            if receipt.source_system == source_system
        ]
        latest = source_receipts[0] if source_receipts else None
        if latest is None:
            health = "never_seen"
        elif latest.last_seen_at < stale_cutoff:
            health = "stale"
        else:
            health = "active"
        rows.append(
            {
                "schema_version": AGENT_TRAFFIC_SOURCE_STATUS_VERSION,
                "source_system": source_system,
                "health": health,
                "batch_count": len(source_receipts),
                "replay_count": sum(
                    receipt.replay_count for receipt in source_receipts
                ),
                "last_received_at": (
                    latest.last_seen_at if latest is not None else None
                ),
                "last_job_id": latest.job_id if latest is not None else None,
                "collector_versions": sorted(
                    {
                        receipt.collector_version
                        for receipt in source_receipts
                    }
                ),
                "observed_key_ids": sorted(
                    {receipt.key_id for receipt in source_receipts}
                ),
                "configured_key_ids": sorted(
                    configured_sources.get(source_system, set())
                ),
            }
        )
    return rows


def import_traffic_job_payload(
    db: Session,
    *,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("schema_version") != AGENT_TRAFFIC_BATCH_CONTRACT_VERSION:
        raise DomainValidationError("traffic job contract version is not supported")
    batch = AgentTrafficEvidenceBatchCreate.model_validate(payload.get("batch"))
    identity_payload = payload.get("collector_identity")
    if not isinstance(identity_payload, dict):
        raise DomainValidationError("traffic job is missing collector identity")
    identity = SignerIdentity(
        subject_id=str(identity_payload.get("subject_id") or ""),
        display_name=str(identity_payload.get("display_name") or ""),
        role=str(identity_payload.get("role") or ""),
        identity_provider=str(identity_payload.get("identity_provider") or ""),
        auth_source=str(identity_payload.get("auth_source") or ""),
        identity_verified=bool(identity_payload.get("identity_verified")),
        ticket_reference=(
            str(identity_payload["ticket_reference"])
            if identity_payload.get("ticket_reference")
            else None
        ),
    )
    imported: list[dict[str, Any]] = []
    for raw_event in batch.events:
        event = AgentEvidenceImportCreate.model_validate(raw_event)
        imported.append(
            import_production_agent_evidence(
                db,
                payload=event,
                signer_identity=identity,
                commit=False,
            )
        )
    db.commit()
    return {
        "schema_version": AGENT_TRAFFIC_BATCH_CONTRACT_VERSION,
        "source_system": batch.source_system,
        "batch_id": batch.batch_id,
        "imported_count": len(imported),
        "benchmark_result_ids": [
            str(item["benchmark_result_id"]) for item in imported
        ],
        "evidence_hashes": [str(item["evidence_hash"]) for item in imported],
    }


def traffic_batch_signature(
    payload: dict[str, Any],
    *,
    secret: str,
    signature_version: str = AGENT_TRAFFIC_SIGNATURE_V1,
    key_id: str | None = None,
    nonce: str | None = None,
    sent_at: str | dt.datetime | None = None,
) -> str:
    normalized_payload = AgentTrafficEvidenceBatchCreate.model_validate(
        payload
    ).model_dump(mode="json")
    if signature_version == AGENT_TRAFFIC_SIGNATURE_V2:
        if not key_id or not nonce or sent_at is None:
            raise DomainValidationError(
                "traffic signature v2 requires key_id, nonce, and sent_at"
            )
        canonical_payload: dict[str, Any] = {
            "signature_version": AGENT_TRAFFIC_SIGNATURE_V2,
            "key_id": key_id,
            "nonce": nonce,
            "sent_at": _parse_timestamp(
                sent_at,
                field_name="traffic sent-at",
            ).isoformat(),
            "batch": normalized_payload,
        }
    elif signature_version == AGENT_TRAFFIC_SIGNATURE_V1:
        canonical_payload = normalized_payload
    else:
        raise DomainValidationError("traffic signature version is not supported")
    canonical = json.dumps(
        canonical_payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def _traffic_secret(
    hmac_keys: dict[str, str],
    *,
    source_system: str,
    key_id: str,
    signature_version: str,
) -> str:
    secret = hmac_keys.get(f"{source_system}:{key_id}")
    if signature_version == AGENT_TRAFFIC_SIGNATURE_V1:
        secret = secret or hmac_keys.get(source_system)
    elif key_id == "legacy":
        secret = secret or hmac_keys.get(source_system)
    if not secret:
        raise DomainValidationError("traffic source key is not configured")
    return secret


def _validate_batch_provenance(
    payload: AgentTrafficEvidenceBatchCreate,
) -> None:
    for event in payload.events:
        if event.provenance.source_system != payload.source_system:
            raise DomainValidationError(
                "traffic event source_system does not match its batch"
            )
        if event.provenance.collector_version != payload.collector_version:
            raise DomainValidationError(
                "traffic event collector_version does not match its batch"
            )


def _matching_receipt(
    db: Session,
    *,
    source_system: str,
    batch_id: str,
    nonce: str,
) -> AgentTrafficReceipt | None:
    return db.scalar(
        select(AgentTrafficReceipt)
        .where(AgentTrafficReceipt.source_system == source_system)
        .where(
            or_(
                AgentTrafficReceipt.batch_id == batch_id,
                AgentTrafficReceipt.nonce == nonce,
            )
        )
        .with_for_update()
    )


def _record_idempotent_replay(
    db: Session,
    *,
    existing: AgentTrafficReceipt,
    batch_id: str,
    nonce: str,
    signature_hash: str,
) -> AgentExecutionJob:
    if (
        existing.batch_id != batch_id
        or existing.nonce != nonce
        or not hmac.compare_digest(existing.signature_hash, signature_hash)
    ):
        raise DomainValidationError("traffic replay identity conflicts with prior receipt")
    existing.replay_count += 1
    existing.last_seen_at = _utcnow()
    job = db.get(AgentExecutionJob, existing.job_id)
    if job is None:
        raise DomainValidationError("traffic replay receipt references a missing job")
    db.commit()
    db.refresh(job)
    return job


def _normalized_signature(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("sha256="):
        normalized = normalized[7:]
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise DomainValidationError("traffic signature must be a SHA-256 hex digest")
    return normalized


def _parse_timestamp(
    value: str | dt.datetime,
    *,
    field_name: str,
) -> dt.datetime:
    try:
        parsed = (
            dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if isinstance(value, str)
            else value
        )
    except ValueError as exc:
        raise DomainValidationError(f"{field_name} is invalid") from exc
    if parsed.tzinfo is None:
        raise DomainValidationError(f"{field_name} must include a timezone")
    return parsed.astimezone(dt.UTC).replace(microsecond=0)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)
