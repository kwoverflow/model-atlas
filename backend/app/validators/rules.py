from __future__ import annotations

import datetime as dt
import json
from typing import Any


class DomainValidationError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def ensure_utc_datetime(value: dt.datetime | None, field_name: str) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() != dt.timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value


def _loads_json_object(value: str | None) -> Any:
    if not value:
        raise ValueError("normalized_output must contain JSON")
    return json.loads(value)


def ensure_json_output_when_marked_valid(json_valid: bool, normalized_output: str | None) -> None:
    if not json_valid:
        return
    try:
        json.loads(normalized_output or "")
    except json.JSONDecodeError as exc:
        raise ValueError("normalized_output must be valid JSON when json_valid is true") from exc


def ensure_tool_call_output_when_marked_valid(
    tool_call_valid: bool, normalized_output: str | None
) -> None:
    if not tool_call_valid:
        return
    try:
        parsed = _loads_json_object(normalized_output)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "normalized_output must be a valid JSON object when tool_call_valid is true"
        ) from exc
    if not isinstance(parsed, dict):
        raise ValueError("tool_call_valid output must be a JSON object")
    has_tool_shape = any(key in parsed for key in ("tool_name", "tool_call", "tool_calls"))
    if not has_tool_shape:
        raise ValueError(
            "tool_call_valid output must include tool_name, tool_call, or tool_calls"
        )


def validate_vram_within_hardware(
    gpu_vram_used_mb: float | None,
    hardware_vram_gb: int,
    tolerance: float = 1.10,
) -> None:
    if gpu_vram_used_mb is None:
        return
    max_allowed_mb = hardware_vram_gb * 1024 * tolerance
    if gpu_vram_used_mb > max_allowed_mb:
        raise DomainValidationError(
            "GPU VRAM usage significantly exceeds the registered hardware VRAM"
        )
