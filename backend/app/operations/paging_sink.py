from __future__ import annotations

import hashlib
import hmac
import json
import os
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from app.core.secret_projection import read_projected_string_map

MAX_PAGING_BYTES = 65_536
MAX_RECEIPTS = 500
_lock = threading.Lock()
_event_ids: set[str] = set()
_receipts: list[dict[str, Any]] = []


class PagingSinkHandler(BaseHTTPRequestHandler):
    server_version = "ModelAtlasPagingSink/2"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._write_json(200, {"status": "ok"})
            return
        if self.path == "/receipts":
            with _lock:
                receipts = list(_receipts[-100:])
                total = len(_receipts)
            self._write_json(
                200,
                {
                    "schema_version": "model-atlas-paging-sink-receipts-v2",
                    "receipt_count": total,
                    "receipts": receipts,
                },
            )
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/page":
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("content-length", "0"))
        except ValueError:
            self.send_error(400, "invalid content length")
            return
        if content_length <= 0 or content_length > MAX_PAGING_BYTES:
            self.send_error(413, "paging payload is outside the allowed size")
            return
        event_id = (self.headers.get("x-model-atlas-event-id") or "").strip()
        timestamp = (self.headers.get("x-model-atlas-timestamp") or "").strip()
        key_id = (self.headers.get("x-model-atlas-key-id") or "legacy").strip()
        signature = (self.headers.get("x-model-atlas-signature") or "").strip()
        if not event_id or len(event_id) > 100:
            self.send_error(401, "paging event ID is missing")
            return
        try:
            timestamp_value = int(timestamp)
        except ValueError:
            self.send_error(401, "paging timestamp is invalid")
            return
        max_skew = max(
            30,
            int(os.getenv("MODEL_ATLAS_PAGING_MAX_CLOCK_SKEW_SECONDS", "300")),
        )
        if abs(int(time.time()) - timestamp_value) > max_skew:
            self.send_error(401, "paging timestamp is outside the allowed window")
            return
        body = self.rfile.read(content_length)
        try:
            keyring = _paging_keyring()
        except RuntimeError:
            self.send_error(503, "paging keyring is temporarily unavailable")
            return
        secret = keyring.get(key_id)
        if secret is None:
            self.send_error(401, "paging key ID is unknown")
            return
        expected = hmac.new(
            secret.encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        if not signature.startswith("sha256=") or not hmac.compare_digest(
            signature.removeprefix("sha256="),
            expected,
        ):
            self.send_error(401, "paging signature is invalid")
            return
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "paging payload must be JSON")
            return
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version")
            not in {"model-atlas-paging-event-v1", "model-atlas-paging-event-v2"}
            or payload.get("delivery_id") != event_id
        ):
            self.send_error(422, "paging payload contract is invalid")
            return

        provider = _provider_name()
        with _lock:
            replay = event_id in _event_ids
            if not replay:
                _event_ids.add(event_id)
                receipt = {
                    "event_id": event_id,
                    "provider": provider,
                    "provider_event_id": event_id,
                    "receipt_id": _receipt_id(event_id),
                    "incident_id": payload.get("incident_id"),
                    "transition_type": payload.get("transition_type"),
                    "severity": (payload.get("alert") or {}).get("severity"),
                    "signing_key_id": key_id,
                    "payload_hash": hashlib.sha256(body).hexdigest(),
                    "accepted_at": int(time.time()),
                }
                _receipts.append(receipt)
                if len(_receipts) > MAX_RECEIPTS:
                    removed = _receipts.pop(0)
                    _event_ids.discard(str(removed["event_id"]))
            else:
                receipt = next(item for item in _receipts if item["event_id"] == event_id)
        record = {
            "event": "model_atlas_owned_paging_delivery",
            "event_id": event_id,
            "signing_key_id": key_id,
            "payload_hash": hashlib.sha256(body).hexdigest(),
            "replay": replay,
        }
        print(json.dumps(record, sort_keys=True), flush=True)
        self._write_json(
            200 if replay else 202,
            {
                "schema_version": "model-atlas-paging-provider-receipt-v1",
                "accepted": True,
                "provider": provider,
                "provider_event_id": receipt["provider_event_id"],
                "receipt_id": receipt["receipt_id"],
                "accepted_at": receipt["accepted_at"],
                "replay": replay,
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        return

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _paging_keyring() -> dict[str, str]:
    projected_path = os.getenv(
        "MODEL_ATLAS_PAGING_HMAC_KEYS_FILE",
        "",
    ).strip()
    if projected_path:
        try:
            keyring = read_projected_string_map(
                projected_path,
                label="paging sink keyring projection",
            )
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
    else:
        raw_value = os.getenv("MODEL_ATLAS_PAGING_HMAC_KEYS_JSON", "").strip()
        keyring = {}
        if raw_value:
            try:
                parsed = json.loads(raw_value)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "MODEL_ATLAS_PAGING_HMAC_KEYS_JSON must be valid JSON"
                ) from exc
            if not isinstance(parsed, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in parsed.items()
            ):
                raise RuntimeError(
                    "MODEL_ATLAS_PAGING_HMAC_KEYS_JSON must map key IDs to secrets"
                )
            keyring.update(parsed)
        legacy_secret = os.getenv("MODEL_ATLAS_PAGING_HMAC_SECRET", "")
        if legacy_secret:
            keyring.setdefault("legacy", legacy_secret)
    if not keyring or any(len(secret) < 32 for secret in keyring.values()):
        raise RuntimeError("every configured paging HMAC key must contain at least 32 characters")
    return keyring


def _provider_name() -> str:
    value = os.getenv(
        "MODEL_ATLAS_PAGING_PROVIDER",
        "model-atlas-development-sink",
    ).strip()
    if (
        not value
        or len(value) > 80
        or any(not (character.isalnum() or character in "._-") for character in value)
    ):
        raise RuntimeError("MODEL_ATLAS_PAGING_PROVIDER is invalid")
    return value


def _receipt_id(event_id: str) -> str:
    return f"receipt-{hashlib.sha256(event_id.encode()).hexdigest()[:32]}"


def main() -> None:
    _paging_keyring()
    _provider_name()
    port = int(os.getenv("MODEL_ATLAS_PAGING_SINK_PORT", "9100"))
    server = ThreadingHTTPServer(("0.0.0.0", port), PagingSinkHandler)
    certificate_path = os.getenv("MODEL_ATLAS_PAGING_TLS_CERT_PATH", "").strip()
    private_key_path = os.getenv("MODEL_ATLAS_PAGING_TLS_KEY_PATH", "").strip()
    if bool(certificate_path) != bool(private_key_path):
        raise RuntimeError("both paging TLS certificate and key paths are required")
    if certificate_path and private_key_path:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certificate_path, private_key_path)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
