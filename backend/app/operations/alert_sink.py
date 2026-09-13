from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MAX_ALERT_BYTES = 1_048_576


class AlertSinkHandler(BaseHTTPRequestHandler):
    server_version = "ModelAtlasAlertSink/1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self.send_error(404)
            return
        self._write_json(200, {"status": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/alerts":
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("content-length", "0"))
        except ValueError:
            self.send_error(400, "invalid content length")
            return
        if content_length <= 0 or content_length > MAX_ALERT_BYTES:
            self.send_error(413, "alert payload is outside the allowed size")
            return
        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.send_error(400, "alert payload must be JSON")
            return
        record: dict[str, Any] = {
            "event": "model_atlas_alertmanager_delivery",
            "payload": payload,
        }
        print(json.dumps(record, ensure_ascii=True, sort_keys=True), flush=True)
        self._write_json(202, {"accepted": True})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(os.getenv("MODEL_ATLAS_ALERT_SINK_PORT", "9099"))
    server = ThreadingHTTPServer(("0.0.0.0", port), AlertSinkHandler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
