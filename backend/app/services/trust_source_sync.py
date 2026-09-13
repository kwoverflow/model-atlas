from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import EvidenceTrustRoot, EvidenceTrustSource, EvidenceTrustSourceSync
from app.schemas import (
    EvidenceTrustRootCreate,
    EvidenceTrustSourceCreate,
    EvidenceTrustSourceCreateRead,
    EvidenceTrustSourceSyncCreate,
    EvidenceTrustSourceSyncCreateRead,
)
from app.services.deployment_gate.evidence import stable_hash
from app.services.operator_identity import SignerIdentity
from app.services.trust_registry import (
    assert_governance_operator,
    evidence_trust_source_read,
    reconcile_existing_evidence,
    validated_public_jwk,
)
from app.validators import DomainValidationError

TRUST_SOURCE_SCHEMA_VERSION = "model-atlas-evidence-trust-source-v1"
TRUST_SOURCE_RESPONSE_VERSION = "model-atlas-evidence-trust-source-response-v1"
TRUST_SOURCE_SYNC_VERSION = "model-atlas-evidence-trust-source-sync-v2"
TRUST_SOURCE_SYNC_RESPONSE_VERSION = "model-atlas-evidence-trust-source-sync-response-v2"
JWKS_CONTENT_TYPES = frozenset({"application/json", "application/jwk-set+json"})
MAX_JWKS_KEYS = 100


@dataclass(frozen=True)
class FetchedJwksPayload:
    payload: dict[str, Any]
    http_status: int
    fetched_at: dt.datetime


@dataclass(frozen=True)
class ValidatedRemoteKey:
    key_id: str
    algorithm: str
    fingerprint: str
    public_jwk: dict[str, Any]


@dataclass(frozen=True)
class TrustSourceSyncContext:
    trigger: str = "manual"
    schedule_id: UUID | None = None
    job_id: UUID | None = None
    attempt_number: int = 1
    scheduled_for: dt.datetime | None = None


class JwksFetcher(Protocol):
    def __call__(
        self,
        trust_source: EvidenceTrustSource,
        *,
        timeout_seconds: float,
        max_bytes: int,
        now: dt.datetime,
    ) -> FetchedJwksPayload: ...


class TrustSourceFetchError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def create_evidence_trust_source(
    db: Session,
    *,
    payload: EvidenceTrustSourceCreate,
    signer_identity: SignerIdentity,
    allowed_hosts: list[str],
    allow_insecure_http: bool,
    now: dt.datetime | None = None,
) -> EvidenceTrustSourceCreateRead:
    assert_governance_operator(signer_identity)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    endpoint_url = payload.endpoint_url.strip()
    algorithms = sorted(set(payload.allowed_algorithms))
    _validate_trust_source_url(
        endpoint_url,
        trust_tier=payload.trust_tier,
        source_allows_insecure=payload.allow_insecure_http,
        globally_allows_insecure=allow_insecure_http,
        allowed_hosts=allowed_hosts,
    )
    if payload.allow_insecure_http and payload.trust_tier != "development":
        raise DomainValidationError(
            "insecure HTTP trust sources are limited to the development tier"
        )
    configuration_hash = stable_hash(
        {
            "schema_version": TRUST_SOURCE_SCHEMA_VERSION,
            "name": payload.name.strip(),
            "source_kind": payload.source_kind,
            "purpose": payload.purpose,
            "issuer": payload.issuer.strip(),
            "trust_tier": payload.trust_tier,
            "endpoint_url": endpoint_url,
            "allowed_algorithms": algorithms,
            "allow_insecure_http": payload.allow_insecure_http,
            "freshness_seconds": payload.freshness_seconds,
            "enabled": payload.enabled,
        }
    )
    existing = db.scalar(
        select(EvidenceTrustSource).where(
            EvidenceTrustSource.name == payload.name.strip()
        )
    )
    if existing is not None:
        if existing.configuration_hash != configuration_hash:
            raise DomainValidationError(
                "trust source name was already registered with different configuration"
            )
        return EvidenceTrustSourceCreateRead(
            schema_version=TRUST_SOURCE_RESPONSE_VERSION,
            created=False,
            trust_source=evidence_trust_source_read(db, existing, now=observed_at),
        )
    endpoint_owner = db.scalar(
        select(EvidenceTrustSource)
        .where(EvidenceTrustSource.purpose == payload.purpose)
        .where(EvidenceTrustSource.issuer == payload.issuer.strip())
        .where(EvidenceTrustSource.endpoint_url == endpoint_url)
    )
    if endpoint_owner is not None:
        raise DomainValidationError(
            "trust source purpose, issuer, and endpoint are already registered"
        )
    trust_source = EvidenceTrustSource(
        name=payload.name.strip(),
        source_kind=payload.source_kind,
        purpose=payload.purpose,
        issuer=payload.issuer.strip(),
        trust_tier=payload.trust_tier,
        endpoint_url=endpoint_url,
        allowed_algorithms_json=algorithms,
        allow_insecure_http=payload.allow_insecure_http,
        freshness_seconds=payload.freshness_seconds,
        enabled=payload.enabled,
        registered_at=observed_at,
        registered_by_identity_json=signer_identity.to_json(),
        identity_verified=True,
        configuration_hash=configuration_hash,
        notes=_optional_text(payload.notes),
    )
    db.add(trust_source)
    db.commit()
    db.refresh(trust_source)
    return EvidenceTrustSourceCreateRead(
        schema_version=TRUST_SOURCE_RESPONSE_VERSION,
        created=True,
        trust_source=evidence_trust_source_read(db, trust_source, now=observed_at),
    )


def sync_evidence_trust_source(
    db: Session,
    *,
    trust_source_id: UUID,
    payload: EvidenceTrustSourceSyncCreate,
    signer_identity: SignerIdentity,
    allowed_hosts: list[str],
    allow_insecure_http: bool,
    timeout_seconds: float,
    max_bytes: int,
    fetcher: JwksFetcher | None = None,
    execution_context: TrustSourceSyncContext | None = None,
    now: dt.datetime | None = None,
) -> EvidenceTrustSourceSyncCreateRead:
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    context = execution_context or TrustSourceSyncContext()
    if context.trigger not in {"manual", "scheduled"}:
        raise DomainValidationError("trust source sync trigger is invalid")
    if context.attempt_number < 1:
        raise DomainValidationError("trust source sync attempt_number must be positive")
    if context.trigger == "scheduled" and (
        context.schedule_id is None or context.job_id is None
    ):
        raise DomainValidationError("scheduled trust source sync requires schedule and job lineage")
    if context.trigger == "scheduled":
        role = (signer_identity.role or "").strip().lower()
        if not signer_identity.identity_verified or role != "system worker":
            raise DomainValidationError(
                "scheduled trust source sync requires a verified System Worker"
            )
    else:
        assert_governance_operator(signer_identity)
    trust_source = db.get(EvidenceTrustSource, trust_source_id)
    if trust_source is None:
        raise DomainValidationError("evidence trust source was not found")
    if not trust_source.enabled:
        raise DomainValidationError("disabled trust sources cannot be synchronized")
    _validate_trust_source_url(
        trust_source.endpoint_url,
        trust_tier=trust_source.trust_tier,
        source_allows_insecure=trust_source.allow_insecure_http,
        globally_allows_insecure=allow_insecure_http,
        allowed_hosts=allowed_hosts,
    )

    selected_fetcher = fetcher or fetch_remote_jwks
    fetched_at = observed_at
    http_status: int | None = None
    payload_hash: str | None = None
    key_count = 0
    observed_keys: list[dict[str, Any]] = []
    try:
        fetched = selected_fetcher(
            trust_source,
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes,
            now=observed_at,
        )
        fetched_at = _utc(fetched.fetched_at).replace(microsecond=0)
        http_status = fetched.http_status
        payload_hash = stable_hash(fetched.payload)
        keys = _validated_remote_keys(fetched.payload, trust_source=trust_source)
        key_count = len(keys)
        observed_keys = [
            {
                "key_id": key.key_id,
                "algorithm": key.algorithm,
                "fingerprint": key.fingerprint,
            }
            for key in keys
        ]
        candidates, unchanged = _classify_remote_keys(
            db,
            trust_source=trust_source,
            keys=keys,
        )
    except TrustSourceFetchError as exc:
        return _record_failed_sync(
            db,
            trust_source=trust_source,
            mode=payload.mode,
            signer_identity=signer_identity,
            observed_at=observed_at,
            fetched_at=fetched_at,
            http_status=exc.http_status,
            payload_hash=payload_hash,
            key_count=key_count,
            observed_keys=observed_keys,
            error_code=exc.code,
            error_message=str(exc),
            notes=payload.notes,
            execution_context=context,
        )
    except DomainValidationError as exc:
        return _record_failed_sync(
            db,
            trust_source=trust_source,
            mode=payload.mode,
            signer_identity=signer_identity,
            observed_at=observed_at,
            fetched_at=fetched_at,
            http_status=http_status,
            payload_hash=payload_hash,
            key_count=key_count,
            observed_keys=observed_keys,
            error_code=(
                "key_collision"
                if "different fingerprint" in str(exc)
                else "invalid_jwks"
            ),
            error_message=str(exc),
            notes=payload.notes,
            execution_context=context,
        )

    sync_id = uuid4()
    completed_at = observed_at
    sync = EvidenceTrustSourceSync(
        id=sync_id,
        trust_source_id=trust_source.id,
        mode=payload.mode,
        status="succeeded",
        trigger=context.trigger,
        schedule_id=context.schedule_id,
        job_id=context.job_id,
        attempt_number=context.attempt_number,
        scheduled_for=(
            _utc(context.scheduled_for).replace(microsecond=0)
            if context.scheduled_for is not None
            else None
        ),
        http_status=http_status,
        fetched_at=fetched_at,
        completed_at=completed_at,
        payload_hash=payload_hash,
        key_count=key_count,
        candidate_count=len(candidates),
        imported_count=0,
        unchanged_count=len(unchanged),
        rejected_count=0,
        observed_keys_json=observed_keys,
        error_code=None,
        error_message=None,
        actor_identity_json=signer_identity.to_json(),
        identity_verified=True,
        sync_hash=_sync_hash(
            sync_id=sync_id,
            trust_source=trust_source,
            mode=payload.mode,
            status="succeeded",
            observed_at=observed_at,
            payload_hash=payload_hash,
            signer_identity=signer_identity,
            execution_context=context,
        ),
        notes=_optional_text(payload.notes),
    )
    db.add(sync)
    try:
        if payload.mode == "apply":
            db.flush()
            for key in candidates:
                root = _import_remote_key(
                    trust_source=trust_source,
                    sync=sync,
                    key=key,
                    signer_identity=signer_identity,
                    observed_at=observed_at,
                )
                db.add(root)
                db.flush()
                reconcile_existing_evidence(db, root)
            sync.imported_count = len(candidates)
        db.commit()
    except IntegrityError:
        db.rollback()
        return _record_failed_sync(
            db,
            trust_source=trust_source,
            mode=payload.mode,
            signer_identity=signer_identity,
            observed_at=observed_at,
            fetched_at=fetched_at,
            http_status=http_status,
            payload_hash=payload_hash,
            key_count=key_count,
            observed_keys=observed_keys,
            error_code="database_conflict",
            error_message="trust source apply conflicted with an existing registry record",
            notes=payload.notes,
            execution_context=context,
        )
    db.refresh(sync)
    db.refresh(trust_source)
    return EvidenceTrustSourceSyncCreateRead(
        schema_version=TRUST_SOURCE_SYNC_RESPONSE_VERSION,
        sync=sync,
        trust_source=evidence_trust_source_read(db, trust_source, now=observed_at),
    )


def fetch_remote_jwks(
    trust_source: EvidenceTrustSource,
    *,
    timeout_seconds: float,
    max_bytes: int,
    now: dt.datetime,
) -> FetchedJwksPayload:
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            with client.stream(
                "GET",
                trust_source.endpoint_url,
                headers={
                    "accept": "application/jwk-set+json, application/json",
                    "user-agent": "model-atlas-trust-source/1",
                },
            ) as response:
                if response.status_code != 200:
                    raise TrustSourceFetchError(
                        "http_status",
                        f"trust source returned HTTP {response.status_code}",
                        http_status=response.status_code,
                    )
                content_type = response.headers.get("content-type", "").split(";", 1)[0]
                if content_type.strip().lower() not in JWKS_CONTENT_TYPES:
                    raise TrustSourceFetchError(
                        "content_type",
                        "trust source response is not a JWKS JSON content type",
                        http_status=response.status_code,
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise TrustSourceFetchError(
                            "payload_too_large",
                            "trust source JWKS exceeds the configured size limit",
                            http_status=response.status_code,
                        )
                    chunks.append(chunk)
    except TrustSourceFetchError:
        raise
    except (httpx.HTTPError, OSError) as exc:
        raise TrustSourceFetchError(
            "transport_error",
            "trust source could not be reached",
        ) from exc
    try:
        parsed = json.loads(b"".join(chunks).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustSourceFetchError(
            "invalid_json",
            "trust source response is not valid UTF-8 JSON",
            http_status=200,
        ) from exc
    if not isinstance(parsed, dict):
        raise TrustSourceFetchError(
            "invalid_jwks",
            "trust source JWKS must be a JSON object",
            http_status=200,
        )
    return FetchedJwksPayload(
        payload=parsed,
        http_status=200,
        fetched_at=_utc(now),
    )


def _validated_remote_keys(
    payload: dict[str, Any],
    *,
    trust_source: EvidenceTrustSource,
) -> list[ValidatedRemoteKey]:
    values = payload.get("keys")
    if not isinstance(values, list) or not values:
        raise DomainValidationError("trust source JWKS must contain a non-empty keys list")
    if len(values) > MAX_JWKS_KEYS:
        raise DomainValidationError("trust source JWKS contains too many keys")
    allowed_algorithms = {str(value) for value in trust_source.allowed_algorithms_json}
    keys: list[ValidatedRemoteKey] = []
    seen_key_ids: set[str] = set()
    for value in values:
        if not isinstance(value, dict):
            raise DomainValidationError("trust source JWKS keys must be JSON objects")
        key_id = str(value.get("kid") or "").strip()
        algorithm = str(value.get("alg") or "").strip()
        if not key_id or len(key_id) > 200:
            raise DomainValidationError("trust source JWK kid is invalid")
        if key_id in seen_key_ids:
            raise DomainValidationError("trust source JWKS contains duplicate key ids")
        if algorithm not in allowed_algorithms:
            raise DomainValidationError(
                "trust source JWK algorithm is not allowed by the source policy"
            )
        jwk = validated_public_jwk(value, key_id=key_id, algorithm=algorithm)
        keys.append(
            ValidatedRemoteKey(
                key_id=key_id,
                algorithm=algorithm,
                fingerprint=stable_hash(jwk),
                public_jwk=jwk,
            )
        )
        seen_key_ids.add(key_id)
    return sorted(keys, key=lambda item: item.key_id)


def _classify_remote_keys(
    db: Session,
    *,
    trust_source: EvidenceTrustSource,
    keys: list[ValidatedRemoteKey],
) -> tuple[list[ValidatedRemoteKey], list[ValidatedRemoteKey]]:
    candidates: list[ValidatedRemoteKey] = []
    unchanged: list[ValidatedRemoteKey] = []
    for key in keys:
        existing = db.scalar(
            select(EvidenceTrustRoot)
            .where(EvidenceTrustRoot.purpose == trust_source.purpose)
            .where(EvidenceTrustRoot.issuer == trust_source.issuer)
            .where(EvidenceTrustRoot.key_id == key.key_id)
        )
        if existing is None:
            candidates.append(key)
            continue
        if existing.key_fingerprint != key.fingerprint:
            raise DomainValidationError(
                f"trust source key {key.key_id} collides with a different fingerprint"
            )
        unchanged.append(key)
    return candidates, unchanged


def _import_remote_key(
    *,
    trust_source: EvidenceTrustSource,
    sync: EvidenceTrustSourceSync,
    key: ValidatedRemoteKey,
    signer_identity: SignerIdentity,
    observed_at: dt.datetime,
) -> EvidenceTrustRoot:
    source_type = (
        "development"
        if trust_source.trust_tier == "development"
        else "internal_ca"
        if trust_source.trust_tier == "internal_ca"
        else "transparency_log"
        if trust_source.purpose == "transparency_log"
        else "external_registry"
    )
    name = f"{trust_source.name} / {key.key_id}"[:180]
    registration_payload = EvidenceTrustRootCreate(
        name=name,
        purpose=trust_source.purpose,
        issuer=trust_source.issuer,
        key_id=key.key_id,
        algorithm=key.algorithm,
        public_key_jwk_json=key.public_jwk,
        trust_tier=trust_source.trust_tier,
        source_type=source_type,
        source_uri=trust_source.endpoint_url,
        valid_from=observed_at,
        notes=f"Imported from trust source {trust_source.id}",
    )
    registration_hash = stable_hash(
        {
            "schema_version": TRUST_SOURCE_SYNC_VERSION,
            "trust_source_id": str(trust_source.id),
            "trust_source_sync_id": str(sync.id),
            "name": registration_payload.name,
            "purpose": registration_payload.purpose,
            "issuer": registration_payload.issuer,
            "key_id": registration_payload.key_id,
            "algorithm": registration_payload.algorithm,
            "public_key_jwk": key.public_jwk,
            "trust_tier": registration_payload.trust_tier,
            "source_type": registration_payload.source_type,
            "source_uri": registration_payload.source_uri,
            "valid_from": observed_at.isoformat(),
        }
    )
    return EvidenceTrustRoot(
        name=name,
        purpose=trust_source.purpose,
        issuer=trust_source.issuer,
        key_id=key.key_id,
        algorithm=key.algorithm,
        key_fingerprint=key.fingerprint,
        public_key_jwk_json=key.public_jwk,
        trust_tier=trust_source.trust_tier,
        source_type=source_type,
        source_uri=trust_source.endpoint_url,
        valid_from=observed_at,
        valid_until=None,
        supersedes_trust_root_id=None,
        trust_source_id=trust_source.id,
        trust_source_sync_id=sync.id,
        registered_at=observed_at,
        registered_by_identity_json=signer_identity.to_json(),
        identity_verified=True,
        registration_hash=registration_hash,
        notes=f"Imported from trust source {trust_source.id}",
    )


def _record_failed_sync(
    db: Session,
    *,
    trust_source: EvidenceTrustSource,
    mode: str,
    signer_identity: SignerIdentity,
    observed_at: dt.datetime,
    fetched_at: dt.datetime,
    http_status: int | None,
    payload_hash: str | None,
    key_count: int,
    observed_keys: list[dict[str, Any]],
    error_code: str,
    error_message: str,
    notes: str | None,
    execution_context: TrustSourceSyncContext,
) -> EvidenceTrustSourceSyncCreateRead:
    sync_id = uuid4()
    sync = EvidenceTrustSourceSync(
        id=sync_id,
        trust_source_id=trust_source.id,
        mode=mode,
        status="failed",
        trigger=execution_context.trigger,
        schedule_id=execution_context.schedule_id,
        job_id=execution_context.job_id,
        attempt_number=execution_context.attempt_number,
        scheduled_for=(
            _utc(execution_context.scheduled_for).replace(microsecond=0)
            if execution_context.scheduled_for is not None
            else None
        ),
        http_status=http_status,
        fetched_at=fetched_at,
        completed_at=observed_at,
        payload_hash=payload_hash,
        key_count=key_count,
        candidate_count=0,
        imported_count=0,
        unchanged_count=0,
        rejected_count=max(1, key_count) if payload_hash else 0,
        observed_keys_json=observed_keys,
        error_code=error_code,
        error_message=error_message[:4000],
        actor_identity_json=signer_identity.to_json(),
        identity_verified=True,
        sync_hash=_sync_hash(
            sync_id=sync_id,
            trust_source=trust_source,
            mode=mode,
            status="failed",
            observed_at=observed_at,
            payload_hash=payload_hash,
            signer_identity=signer_identity,
            execution_context=execution_context,
        ),
        notes=_optional_text(notes),
    )
    db.add(sync)
    db.commit()
    db.refresh(sync)
    db.refresh(trust_source)
    return EvidenceTrustSourceSyncCreateRead(
        schema_version=TRUST_SOURCE_SYNC_RESPONSE_VERSION,
        sync=sync,
        trust_source=evidence_trust_source_read(db, trust_source, now=observed_at),
    )


def _sync_hash(
    *,
    sync_id: UUID,
    trust_source: EvidenceTrustSource,
    mode: str,
    status: str,
    observed_at: dt.datetime,
    payload_hash: str | None,
    signer_identity: SignerIdentity,
    execution_context: TrustSourceSyncContext,
) -> str:
    return stable_hash(
        {
            "schema_version": TRUST_SOURCE_SYNC_VERSION,
            "sync_id": str(sync_id),
            "trust_source_id": str(trust_source.id),
            "configuration_hash": trust_source.configuration_hash,
            "mode": mode,
            "status": status,
            "observed_at": observed_at.isoformat(),
            "payload_hash": payload_hash,
            "trigger": execution_context.trigger,
            "schedule_id": (
                str(execution_context.schedule_id)
                if execution_context.schedule_id is not None
                else None
            ),
            "job_id": (
                str(execution_context.job_id)
                if execution_context.job_id is not None
                else None
            ),
            "attempt_number": execution_context.attempt_number,
            "scheduled_for": (
                _utc(execution_context.scheduled_for).replace(microsecond=0).isoformat()
                if execution_context.scheduled_for is not None
                else None
            ),
            "actor": signer_identity.to_json(),
        }
    )


def _validate_trust_source_url(
    value: str,
    *,
    trust_tier: str,
    source_allows_insecure: bool,
    globally_allows_insecure: bool,
    allowed_hosts: list[str],
) -> None:
    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password:
        raise DomainValidationError("trust source URLs cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise DomainValidationError("trust source URLs cannot contain query strings or fragments")
    if not host or not _host_is_allowed(host, allowed_hosts):
        raise DomainValidationError("trust source host is not in TRUST_SOURCE_ALLOWED_HOSTS")
    if scheme == "https":
        return
    if (
        scheme == "http"
        and trust_tier == "development"
        and source_allows_insecure
        and globally_allows_insecure
    ):
        return
    raise DomainValidationError("trust sources require HTTPS")


def _host_is_allowed(host: str, allowed_hosts: list[str]) -> bool:
    for raw_value in allowed_hosts:
        value = raw_value.strip().lower()
        if not value:
            continue
        if value.startswith("*.") and host.endswith(value[1:]) and host != value[2:]:
            return True
        if host == value:
            return True
    return False


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise DomainValidationError("trust source timestamps require a timezone")
    return value.astimezone(dt.UTC)


def _optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None
