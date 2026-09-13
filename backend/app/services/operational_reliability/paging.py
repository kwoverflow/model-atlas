from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.secret_projection import (
    read_projected_secret,
    read_projected_string_map,
)
from app.models import (
    OperationalAlertDelivery,
    OperationalAlertIncident,
)
from app.validators import DomainValidationError

from .contracts import (
    PAGING_EVENT_VERSION,
    PagingConfigurationState,
    PagingDeliveryError,
    PagingProviderReceipt,
    PagingReceiptError,
)
from .read_models import (
    _delivery_result,
)
from .utils import (
    _canonical_hash,
    _utc,
)


def execute_operational_alert_delivery(
    db: Session,
    *,
    delivery_id: UUID,
    settings: Settings,
    attempt_number: int,
    max_attempts: int,
    now: dt.datetime | None = None,
    transport: httpx.BaseTransport | None = None,
) -> dict[str, Any]:
    delivery = db.scalar(
        select(OperationalAlertDelivery)
        .where(OperationalAlertDelivery.id == delivery_id)
        .with_for_update()
    )
    if delivery is None:
        raise DomainValidationError("operational alert delivery was not found")
    if delivery.status == "delivered":
        return _delivery_result(delivery, replay=True)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    if not settings.operational_paging_enabled:
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message="operational paging delivery is disabled",
            observed_at=observed_at,
            permanent=True,
        )
        raise DomainValidationError("operational paging delivery is disabled")

    try:
        endpoint = _validated_paging_endpoint(settings)
    except DomainValidationError as exc:
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message=exc.message,
            observed_at=observed_at,
            permanent=True,
        )
        raise
    try:
        expected_provider = delivery.provider_name or _paging_provider(
            settings,
            required=True,
        )
    except DomainValidationError as exc:
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message=exc.message,
            observed_at=observed_at,
            permanent=True,
        )
        raise
    try:
        secret = _paging_signing_secret(settings, delivery.signing_key_id)
        tls_verify = _paging_tls_verification(settings, endpoint)
    except DomainValidationError as exc:
        message = "operational paging credential or CA projection is unavailable"
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message=message,
            observed_at=observed_at,
        )
        raise PagingDeliveryError(message) from exc

    payload_bytes = json.dumps(
        delivery.payload_json,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(observed_at.timestamp()))
    signature = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + payload_bytes,
        hashlib.sha256,
    ).hexdigest()
    response_status: int | None = None
    response_body = b""
    try:
        with httpx.Client(
            timeout=settings.operational_paging_timeout_seconds,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            verify=tls_verify,
        ) as client:
            with client.stream(
                "POST",
                endpoint,
                content=payload_bytes,
                headers={
                    "content-type": "application/json",
                    "user-agent": "model-atlas-operational-paging/1",
                    "idempotency-key": str(delivery.id),
                    "x-model-atlas-event-id": str(delivery.id),
                    "x-model-atlas-timestamp": timestamp,
                    "x-model-atlas-key-id": delivery.signing_key_id,
                    "x-model-atlas-signature": f"sha256={signature}",
                },
            ) as response:
                response_status = response.status_code
                chunks: list[bytes] = []
                response_size = 0
                for chunk in response.iter_bytes():
                    response_size += len(chunk)
                    if response_size > settings.operational_paging_max_response_bytes:
                        raise DomainValidationError(
                            "operational paging response exceeds the configured size limit"
                        )
                    chunks.append(chunk)
                response_body = b"".join(chunks)
    except DomainValidationError as exc:
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message=exc.message,
            observed_at=observed_at,
            response_status=response_status,
            response_body=response_body,
            permanent=True,
        )
        raise
    except (httpx.HTTPError, OSError) as exc:
        message = "operational paging destination could not be reached"
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message=message,
            observed_at=observed_at,
            response_status=response_status,
            response_body=response_body,
            permanent=(
                response_status is not None
                and 400 <= response_status < 500
                and response_status not in {408, 429}
            ),
        )
        raise PagingDeliveryError(message) from exc

    if response_status is None or not 200 <= response_status < 300:
        message = f"operational paging destination returned HTTP {response_status}"
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message=message,
            observed_at=observed_at,
            response_status=response_status,
            response_body=response_body,
        )
        if response_status is not None and (
            400 <= response_status < 500 and response_status not in {408, 429}
        ):
            raise DomainValidationError(message)
        raise PagingDeliveryError(message)

    try:
        provider_receipt = _parse_provider_receipt(
            response_body,
            delivery=delivery,
            expected_provider=expected_provider,
            settings=settings,
            observed_at=observed_at,
        )
    except PagingReceiptError as exc:
        _record_delivery_failure(
            db,
            delivery=delivery,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            error_message=str(exc),
            observed_at=observed_at,
            response_status=response_status,
            response_body=response_body,
        )
        raise

    delivery.status = "delivered"
    delivery.last_attempt_at = observed_at
    delivery.attempt_count += 1
    delivery.response_status = response_status
    delivery.response_hash = hashlib.sha256(response_body).hexdigest()
    delivery.provider_name = expected_provider
    if provider_receipt is not None:
        delivery.provider_name = provider_receipt.provider
        delivery.provider_event_id = provider_receipt.event_id
        delivery.provider_receipt_id = provider_receipt.receipt_id
        delivery.provider_accepted_at = provider_receipt.accepted_at
    delivery.error_message = None
    delivery.delivered_at = observed_at
    db.commit()
    db.refresh(delivery)
    return _delivery_result(delivery, replay=False)


def _create_delivery(
    db: Session,
    *,
    incident: OperationalAlertIncident,
    transition_type: str,
    settings: Settings,
    observed_at: dt.datetime,
) -> OperationalAlertDelivery:
    delivery_id = uuid.uuid4()
    signing_key_id = _active_paging_key_id(settings, required=True)
    if signing_key_id is None:
        raise DomainValidationError("operational paging signing key is not configured")
    payload = {
        "schema_version": PAGING_EVENT_VERSION,
        "delivery_id": str(delivery_id),
        "incident_id": str(incident.id),
        "transition_type": transition_type,
        "transition_version": incident.transition_version,
        "occurred_at": observed_at.isoformat(),
        "alert": {
            "key": incident.alert_key,
            "source_type": incident.source_type,
            "severity": incident.severity,
            "route": incident.route,
            "summary": incident.summary,
            "metric_name": incident.metric_name,
            "current_value": incident.current_value,
            "threshold": incident.threshold,
        },
        "response": {
            "acknowledged_at": (
                incident.acknowledged_at.isoformat()
                if incident.acknowledged_at is not None
                else None
            ),
            "assigned_to": incident.assigned_to,
            "escalation_level": incident.escalation_level,
        },
    }
    delivery = OperationalAlertDelivery(
        id=delivery_id,
        incident_id=incident.id,
        transition_type=transition_type,
        transition_version=incident.transition_version,
        destination_hash=hashlib.sha256(
            (settings.operational_paging_webhook_url or "unconfigured").encode()
        ).hexdigest(),
        signing_key_id=signing_key_id,
        provider_name=_paging_provider(settings, required=True),
        status="queued",
        payload_json=payload,
        payload_hash=_canonical_hash(payload),
        requested_at=observed_at,
    )
    db.add(delivery)
    db.flush()
    return delivery


def _record_delivery_failure(
    db: Session,
    *,
    delivery: OperationalAlertDelivery,
    attempt_number: int,
    max_attempts: int,
    error_message: str,
    observed_at: dt.datetime,
    response_status: int | None = None,
    response_body: bytes = b"",
    permanent: bool = False,
) -> None:
    delivery.status = "failed" if permanent or attempt_number >= max_attempts else "queued"
    delivery.last_attempt_at = observed_at
    delivery.attempt_count += 1
    delivery.response_status = response_status
    delivery.response_hash = hashlib.sha256(response_body).hexdigest() if response_body else None
    delivery.error_message = error_message[:4000]
    db.commit()


def _validated_paging_endpoint(settings: Settings) -> str:
    value = (settings.operational_paging_webhook_url or "").strip()
    if not value:
        raise DomainValidationError("operational paging webhook URL is not configured")
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if parsed.username or parsed.password:
        raise DomainValidationError("operational paging URLs cannot contain credentials")
    if parsed.query or parsed.fragment:
        raise DomainValidationError(
            "operational paging URLs cannot contain query strings or fragments"
        )
    if not host or not _host_is_allowed(
        host,
        settings.operational_paging_allowed_hosts,
    ):
        raise DomainValidationError(
            "operational paging host is not in OPERATIONAL_PAGING_ALLOWED_HOSTS"
        )
    if parsed.scheme == "https":
        return value
    if parsed.scheme == "http" and settings.operational_paging_allow_insecure_http:
        return value
    raise DomainValidationError("operational paging delivery requires HTTPS")


def _paging_keyring(settings: Settings) -> dict[str, str]:
    projected_path = (settings.operational_paging_hmac_keys_file or "").strip()
    if projected_path:
        try:
            return read_projected_string_map(
                projected_path,
                label="operational paging keyring projection",
            )
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc
    keyring = {
        key_id.strip(): secret
        for key_id, secret in settings.operational_paging_hmac_keys.items()
        if key_id.strip() and secret
    }
    if settings.operational_paging_hmac_secret:
        keyring.setdefault("legacy", settings.operational_paging_hmac_secret)
    return keyring


def _active_paging_key_id(
    settings: Settings,
    *,
    required: bool,
) -> str | None:
    keyring = _paging_keyring(settings)
    configured = _configured_paging_active_key_id(settings)
    if configured:
        valid_identifier = len(configured) <= 120 and all(
            character.isalnum() or character in "._-" for character in configured
        )
        if not valid_identifier:
            if required:
                raise DomainValidationError(
                    "operational paging active key ID contains invalid characters"
                )
            return None
        if configured not in keyring:
            if required:
                raise DomainValidationError(
                    "operational paging active key ID is not present in the keyring"
                )
            return configured
        return configured
    if len(keyring) == 1:
        return next(iter(keyring))
    if required:
        if not keyring:
            raise DomainValidationError("operational paging HMAC keyring is unavailable")
        raise DomainValidationError(
            "operational paging active key ID is required for a multi-key keyring"
        )
    return None


def _configured_paging_active_key_id(settings: Settings) -> str:
    projected_path = (settings.operational_paging_active_key_id_file or "").strip()
    if projected_path:
        try:
            return read_projected_secret(
                projected_path,
                label="operational paging active key projection",
            )
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc
    return (settings.operational_paging_active_key_id or "").strip()


def _paging_signing_secret(settings: Settings, key_id: str) -> str:
    secret = _paging_keyring(settings).get(key_id)
    if secret is None or len(secret) < 32:
        raise DomainValidationError("operational paging signing key is unavailable or too short")
    return secret


def _paging_tls_verification(settings: Settings, endpoint: str) -> bool | str:
    if urlsplit(endpoint).scheme != "https":
        return True
    bundle = (settings.operational_paging_ca_bundle_path or "").strip()
    if not bundle:
        return True
    path = Path(bundle)
    if not path.is_file():
        raise DomainValidationError("operational paging CA bundle path does not reference a file")
    return str(path)


def _paging_provider(settings: Settings, *, required: bool) -> str:
    value = settings.operational_paging_provider.strip()
    valid = (
        bool(value)
        and len(value) <= 80
        and all(character.isalnum() or character in "._-" for character in value)
    )
    if valid:
        return value
    if required:
        raise DomainValidationError("operational paging provider is invalid")
    return "invalid"


def _paging_configuration_state(settings: Settings) -> PagingConfigurationState:
    if settings.operational_paging_hmac_keys_file:
        secret_source = "projected_file"
    elif settings.operational_paging_hmac_keys:
        secret_source = "environment_keyring"
    elif settings.operational_paging_hmac_secret:
        secret_source = "legacy_environment"
    else:
        secret_source = "unconfigured"
    try:
        keyring = _paging_keyring(settings)
        active_key_id = _active_paging_key_id(settings, required=False)
    except DomainValidationError as exc:
        return PagingConfigurationState(
            secret_source="invalid",
            key_count=0,
            active_key_id=None,
            error=exc.message,
        )
    error = None
    if any(len(secret) < 32 for secret in keyring.values()):
        error = "operational paging keyring contains a short signing key"
        active_key_id = None
    elif active_key_id is None:
        error = "operational paging active key could not be selected"
    elif active_key_id not in keyring:
        error = "operational paging active key is not present in the keyring"
        active_key_id = None
    return PagingConfigurationState(
        secret_source=secret_source,
        key_count=len(keyring),
        active_key_id=active_key_id,
        error=error,
    )


def _parse_provider_receipt(
    response_body: bytes,
    *,
    delivery: OperationalAlertDelivery,
    expected_provider: str,
    settings: Settings,
    observed_at: dt.datetime,
) -> PagingProviderReceipt | None:
    required = settings.operational_paging_require_receipt
    try:
        payload = json.loads(response_body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("response is not a JSON object")
        if payload.get("schema_version") != "model-atlas-paging-provider-receipt-v1":
            raise ValueError("provider receipt schema is unsupported")
        if payload.get("accepted") is not True:
            raise ValueError("provider did not confirm acceptance")
        provider = _provider_identifier(payload.get("provider"), "provider")
        event_id = _provider_identifier(
            payload.get("provider_event_id"),
            "provider event ID",
        )
        receipt_id = _provider_identifier(
            payload.get("receipt_id"),
            "provider receipt ID",
        )
        if provider != expected_provider:
            raise ValueError("provider identity does not match configuration")
        if event_id != str(delivery.id):
            raise ValueError("provider event ID does not match the delivery")
        accepted_at = _provider_accepted_at(payload.get("accepted_at"))
        age_seconds = (observed_at - accepted_at).total_seconds()
        if age_seconds > settings.operational_paging_receipt_max_age_seconds:
            raise ValueError("provider receipt is stale")
        if age_seconds < -300:
            raise ValueError("provider receipt acceptance time is in the future")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        if required:
            raise PagingReceiptError("operational paging provider receipt is invalid") from exc
        return None
    return PagingProviderReceipt(
        provider=provider,
        event_id=event_id,
        receipt_id=receipt_id,
        accepted_at=accepted_at,
    )


def _provider_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} is missing")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 200
        or any(ord(character) < 33 or ord(character) > 126 for character in normalized)
    ):
        raise ValueError(f"{label} is invalid")
    return normalized


def _provider_accepted_at(value: Any) -> dt.datetime:
    if isinstance(value, int):
        return dt.datetime.fromtimestamp(value, tz=dt.UTC)
    if not isinstance(value, str):
        raise ValueError("provider acceptance time is missing")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("provider acceptance time is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("provider acceptance time requires a timezone")
    return parsed.astimezone(dt.UTC)


def _paging_destination_label(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if not parsed.hostname:
        return "invalid"
    return (
        f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        if parsed.port
        else f"{parsed.scheme}://{parsed.hostname}"
    )


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
