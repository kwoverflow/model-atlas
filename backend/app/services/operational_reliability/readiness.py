from __future__ import annotations

import datetime as dt
from urllib.parse import urlsplit

from app.core.config import Settings
from app.models import (
    OperationalAlertDelivery,
)
from app.schemas import (
    OperationalReadinessCheckRead,
    OperationalStagingReadinessRead,
)
from app.validators import DomainValidationError

from .contracts import (
    PagingConfigurationState,
)
from .paging import (
    _paging_destination_label,
    _paging_provider,
    _paging_tls_verification,
    _validated_paging_endpoint,
)
from .utils import (
    _utc,
)


def _build_staging_readiness(
    *,
    settings: Settings,
    configuration: PagingConfigurationState,
    latest_receipt_delivery: OperationalAlertDelivery | None,
    observed_at: dt.datetime,
) -> OperationalStagingReadinessRead:
    checks: list[OperationalReadinessCheckRead] = []

    def add(key: str, passed: bool, summary: str, evidence: str | None = None) -> None:
        checks.append(
            OperationalReadinessCheckRead(
                key=key,
                status="passed" if passed else "failed",
                summary=summary,
                evidence=evidence,
            )
        )

    add(
        "paging_enabled",
        settings.operational_paging_enabled,
        "Durable paging delivery is enabled.",
    )
    try:
        endpoint = _validated_paging_endpoint(settings)
        transport_ready = urlsplit(endpoint).scheme == "https"
    except DomainValidationError:
        endpoint = ""
        transport_ready = False
    add(
        "secure_destination",
        transport_ready,
        "The paging destination uses an allowlisted HTTPS endpoint.",
        _paging_destination_label(endpoint) if endpoint else None,
    )
    ca_ready = False
    ca_evidence = None
    if transport_ready:
        try:
            verification = _paging_tls_verification(settings, endpoint)
            ca_ready = True
            ca_evidence = (
                "projected CA bundle" if isinstance(verification, str) else "system trust store"
            )
        except DomainValidationError:
            pass
    add(
        "ca_verification",
        ca_ready,
        "The HTTPS certificate chain has a configured verification source.",
        ca_evidence,
    )
    add(
        "projected_keyring",
        configuration.secret_source == "projected_file" and not configuration.error,
        "Paging signing keys are supplied through a projected file.",
        f"{configuration.key_count} key(s) available",
    )
    add(
        "rolling_key_rotation",
        configuration.key_count >= 2 and configuration.active_key_id is not None,
        "An active key and at least one retiring verification key are available.",
        configuration.active_key_id,
    )
    provider = _paging_provider(settings, required=False)
    add(
        "provider_receipt_contract",
        settings.operational_paging_require_receipt and provider != "invalid",
        "Provider acceptance receipts are mandatory and correlated.",
        provider,
    )
    receipt_ready = False
    receipt_evidence = None
    if (
        latest_receipt_delivery is not None
        and latest_receipt_delivery.provider_accepted_at is not None
        and latest_receipt_delivery.provider_event_id == str(latest_receipt_delivery.id)
    ):
        receipt_age = (
            observed_at - _utc(latest_receipt_delivery.provider_accepted_at)
        ).total_seconds()
        receipt_ready = 0 <= receipt_age <= settings.operational_paging_receipt_max_age_seconds
        receipt_evidence = (
            latest_receipt_delivery.provider_receipt_id[:24]
            if latest_receipt_delivery.provider_receipt_id
            else None
        )
    add(
        "recent_provider_receipt",
        receipt_ready,
        "A recent end-to-end provider receipt is stored for this deployment.",
        receipt_evidence,
    )
    passed_count = sum(check.status == "passed" for check in checks)
    return OperationalStagingReadinessRead(
        ready=passed_count == len(checks),
        passed_count=passed_count,
        failed_count=len(checks) - passed_count,
        latest_receipt_delivery_id=(
            latest_receipt_delivery.id if latest_receipt_delivery else None
        ),
        checks=checks,
    )
