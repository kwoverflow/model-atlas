from __future__ import annotations

import datetime as dt
import hashlib
from collections.abc import Callable
from dataclasses import dataclass

OPERATIONAL_RELIABILITY_VERSION = "model-atlas-operational-reliability-v3"


OPERATIONAL_RELIABILITY_POLICY_VERSION = "operational-reliability-rbac-v2"


PAGING_EVENT_VERSION = "model-atlas-paging-event-v2"


OPERATIONAL_AUDITOR_ROLES = ("Admin", "SRE Lead", "ML Ops Lead", "Release Manager")


OPERATIONAL_ADMINISTRATOR_ROLES = ("Admin", "SRE Lead")


EMPTY_LABELS_HASH = hashlib.sha256(b"{}").hexdigest()


SNAPSHOT_RETENTION_BATCH_SIZE = 1000


@dataclass(frozen=True)
class SLODefinition:
    key: str
    scope: str
    target_ratio: float
    metric_names: tuple[str, ...]
    good_condition: str
    evaluator: Callable[[dict[str, float]], bool]


@dataclass(frozen=True)
class SLOWindowStats:
    observed_ratio: float | None
    sample_count: int
    good_sample_count: int
    actual_sample_count: int
    missing_sample_count: int
    effective_window_started_at: dt.datetime | None


@dataclass(frozen=True)
class PagingConfigurationState:
    secret_source: str
    key_count: int
    active_key_id: str | None
    error: str | None


@dataclass(frozen=True)
class PagingProviderReceipt:
    provider: str
    event_id: str
    receipt_id: str
    accepted_at: dt.datetime


class PagingDeliveryError(RuntimeError):
    pass


class PagingReceiptError(PagingDeliveryError):
    pass
