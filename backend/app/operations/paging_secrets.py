from __future__ import annotations

import argparse
import json
import os
import secrets
import tempfile
from pathlib import Path

from app.core.secret_projection import (
    read_projected_secret,
    read_projected_string_map,
)

KEYRING_FILENAME = "hmac-keys.json"
ACTIVE_KEY_FILENAME = "active-key-id"


def initialize_paging_secrets(
    directory: Path,
    *,
    active_key_id: str = "development-primary",
    retiring_key_id: str = "development-retiring",
) -> dict[str, object]:
    directory.mkdir(parents=True, exist_ok=True)
    keyring_path = directory / KEYRING_FILENAME
    active_key_path = directory / ACTIVE_KEY_FILENAME
    if keyring_path.is_file() and active_key_path.is_file():
        keyring = read_projected_string_map(
            str(keyring_path),
            label="paging keyring projection",
        )
        active = read_projected_secret(
            str(active_key_path),
            label="paging active key projection",
        )
        if active not in keyring:
            raise RuntimeError("projected paging active key is not in the keyring")
        return _summary(directory, active, keyring, created=False)

    _validate_key_id(active_key_id)
    _validate_key_id(retiring_key_id)
    if active_key_id == retiring_key_id:
        raise ValueError("active and retiring paging key IDs must differ")
    keyring = {
        active_key_id: secrets.token_urlsafe(48),
        retiring_key_id: secrets.token_urlsafe(48),
    }
    _write_keyring(keyring_path, keyring)
    _atomic_write(active_key_path, f"{active_key_id}\n".encode())
    return _summary(directory, active_key_id, keyring, created=True)


def rotate_paging_secrets(
    directory: Path,
    *,
    new_key_id: str,
    retain: int = 2,
) -> dict[str, object]:
    _validate_key_id(new_key_id)
    retain = max(2, min(retain, 10))
    keyring_path = directory / KEYRING_FILENAME
    active_key_path = directory / ACTIVE_KEY_FILENAME
    keyring = read_projected_string_map(
        str(keyring_path),
        label="paging keyring projection",
    )
    previous_active = read_projected_secret(
        str(active_key_path),
        label="paging active key projection",
    )
    if previous_active not in keyring:
        raise RuntimeError("projected paging active key is not in the keyring")
    if new_key_id in keyring:
        raise ValueError("new paging key ID already exists")

    rotated = {new_key_id: secrets.token_urlsafe(48)}
    for key_id in (previous_active, *sorted(keyring)):
        if key_id not in rotated and len(rotated) < retain:
            rotated[key_id] = keyring[key_id]
    _write_keyring(keyring_path, rotated)
    _atomic_write(active_key_path, f"{new_key_id}\n".encode())
    result = _summary(directory, new_key_id, rotated, created=True)
    result["previous_active_key_id"] = previous_active
    result["operation"] = "rotated"
    return result


def _summary(
    directory: Path,
    active_key_id: str,
    keyring: dict[str, str],
    *,
    created: bool,
) -> dict[str, object]:
    return {
        "schema_version": "model-atlas-paging-secret-projection-v1",
        "operation": "initialized",
        "directory": str(directory),
        "created": created,
        "active_key_id": active_key_id,
        "key_ids": sorted(keyring),
        "key_count": len(keyring),
    }


def _validate_key_id(value: str) -> None:
    if (
        not value
        or len(value) > 120
        or any(not (character.isalnum() or character in "._-") for character in value)
    ):
        raise ValueError("paging key ID contains invalid characters")


def _write_keyring(path: Path, keyring: dict[str, str]) -> None:
    payload = json.dumps(keyring, sort_keys=True, separators=(",", ":")).encode()
    _atomic_write(path, payload + b"\n")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o600)
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage projected paging secrets")
    parser.add_argument(
        "operation",
        choices=("initialize", "rotate"),
        nargs="?",
        default="initialize",
    )
    parser.add_argument("--directory", default="/paging-secrets")
    parser.add_argument("--active-key-id", default="development-primary")
    parser.add_argument("--retiring-key-id", default="development-retiring")
    parser.add_argument("--new-key-id")
    parser.add_argument("--retain", type=int, default=2)
    arguments = parser.parse_args()
    directory = Path(arguments.directory)
    if arguments.operation == "rotate":
        if not arguments.new_key_id:
            parser.error("--new-key-id is required for rotate")
        result = rotate_paging_secrets(
            directory,
            new_key_id=arguments.new_key_id,
            retain=arguments.retain,
        )
    else:
        result = initialize_paging_secrets(
            directory,
            active_key_id=arguments.active_key_id,
            retiring_key_id=arguments.retiring_key_id,
        )
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
