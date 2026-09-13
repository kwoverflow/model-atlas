from __future__ import annotations

import json
from pathlib import Path

MAX_PROJECTED_SECRET_BYTES = 65_536


def read_projected_secret(
    path_value: str,
    *,
    label: str,
    max_bytes: int = MAX_PROJECTED_SECRET_BYTES,
) -> str:
    path = Path(path_value)
    try:
        if not path.is_file():
            raise ValueError(f"{label} does not reference a readable file")
        with path.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
    except OSError as exc:
        raise ValueError(f"{label} could not be read") from exc
    if not payload or len(payload) > max_bytes:
        raise ValueError(f"{label} is outside the allowed size")
    try:
        value = payload.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} must be UTF-8") from exc
    if not value:
        raise ValueError(f"{label} cannot be empty")
    return value


def read_projected_string_map(
    path_value: str,
    *,
    label: str,
) -> dict[str, str]:
    raw_value = read_projected_secret(path_value, label=label)
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} must contain valid JSON") from exc
    if not isinstance(parsed, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in parsed.items()
    ):
        raise ValueError(f"{label} must map string key IDs to string secrets")
    keyring: dict[str, str] = {}
    for key, value in parsed.items():
        normalized_key = key.strip()
        if not normalized_key or not value:
            raise ValueError(f"{label} cannot contain blank key IDs or secrets")
        if normalized_key in keyring:
            raise ValueError(f"{label} contains duplicate normalized key IDs")
        keyring[normalized_key] = value
    if not keyring:
        raise ValueError(f"{label} cannot be empty")
    return keyring
