from __future__ import annotations

import datetime as dt
import hashlib
import json
from typing import Any

from app.validators import DomainValidationError


def _bucket_start(value: dt.datetime, interval_seconds: int) -> dt.datetime:
    timestamp = int(value.timestamp())
    bucket_timestamp = timestamp - (timestamp % interval_seconds)
    return dt.datetime.fromtimestamp(bucket_timestamp, tz=dt.UTC)


def _canonical_hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise DomainValidationError("operational timestamps require a timezone")
    return value.astimezone(dt.UTC)
