from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.schemas import AgentTrafficEvidenceBatchCreate
from app.services.agent_traffic_ingestion import (
    AGENT_TRAFFIC_SIGNATURE_V2,
    traffic_batch_signature,
)

COLLECTOR_STATE_VERSION = "agent-traffic-collector-state-v1"


class CollectorDeliveryError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class CollectorConfig:
    endpoint: str
    key_id: str
    secret: str
    timeout_seconds: float = 10.0
    max_attempts: int = 4
    initial_backoff_seconds: float = 1.0
    gzip_enabled: bool = True


class AgentTrafficCollector:
    def __init__(self, config: CollectorConfig) -> None:
        self.config = config

    def deliver(
        self,
        payload: dict[str, Any],
        *,
        nonce: str,
        sent_at: str,
    ) -> dict[str, Any]:
        batch = AgentTrafficEvidenceBatchCreate.model_validate(payload)
        normalized_payload = batch.model_dump(mode="json")
        encoded = json.dumps(
            normalized_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        signature = traffic_batch_signature(
            normalized_payload,
            secret=self.config.secret,
            signature_version=AGENT_TRAFFIC_SIGNATURE_V2,
            key_id=self.config.key_id,
            nonce=nonce,
            sent_at=sent_at,
        )
        headers = {
            "content-type": "application/json",
            "accept": "application/json",
            "user-agent": "model-atlas-agent-traffic-collector/1",
            "x-model-atlas-traffic-signature": f"sha256={signature}",
            "x-model-atlas-traffic-signature-version": AGENT_TRAFFIC_SIGNATURE_V2,
            "x-model-atlas-traffic-key-id": self.config.key_id,
            "x-model-atlas-traffic-nonce": nonce,
            "x-model-atlas-traffic-sent-at": sent_at,
        }
        if self.config.gzip_enabled:
            encoded = gzip.compress(encoded)
            headers["content-encoding"] = "gzip"
        request = Request(
            self.config.endpoint,
            data=encoded,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(  # noqa: S310
                request,
                timeout=max(1.0, min(self.config.timeout_seconds, 60.0)),
            ) as response:
                response_body = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise CollectorDeliveryError(
                f"collector endpoint returned HTTP {exc.code}: {detail}",
                retryable=exc.code == 429 or exc.code >= 500,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise CollectorDeliveryError(
                "collector endpoint request failed",
                retryable=True,
            ) from exc
        try:
            payload_json = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CollectorDeliveryError(
                "collector endpoint response is not valid JSON",
                retryable=False,
            ) from exc
        if not isinstance(payload_json, dict):
            raise CollectorDeliveryError(
                "collector endpoint response must be an object",
                retryable=False,
            )
        return payload_json

    def deliver_with_retry(
        self,
        payload: dict[str, Any],
        *,
        nonce: str,
        sent_at: str,
    ) -> tuple[dict[str, Any], int]:
        max_attempts = max(1, min(int(self.config.max_attempts), 10))
        for attempt in range(1, max_attempts + 1):
            try:
                return self.deliver(
                    payload,
                    nonce=nonce,
                    sent_at=sent_at,
                ), attempt
            except CollectorDeliveryError as exc:
                if not exc.retryable or attempt >= max_attempts:
                    raise
                time.sleep(
                    min(
                        60.0,
                        max(0.0, self.config.initial_backoff_seconds)
                        * (2 ** (attempt - 1)),
                    )
                )
        raise CollectorDeliveryError(
            "collector exhausted its retry budget",
            retryable=False,
        )


def process_outbox_once(
    *,
    collector: AgentTrafficCollector,
    outbox: Path,
    state_file: Path,
) -> dict[str, int]:
    outbox.mkdir(parents=True, exist_ok=True)
    sent_directory = outbox / "sent"
    failed_directory = outbox / "failed"
    sent_directory.mkdir(exist_ok=True)
    failed_directory.mkdir(exist_ok=True)
    state = load_collector_state(state_file)
    summary = {"sent": 0, "failed": 0}
    for batch_file in sorted(outbox.glob("*.json")):
        try:
            payload = json.loads(batch_file.read_text(encoding="utf-8"))
            batch = AgentTrafficEvidenceBatchCreate.model_validate(payload)
        except Exception as exc:
            _record_failure(
                state,
                batch_id=batch_file.name,
                error=f"Invalid batch file: {exc}",
            )
            save_collector_state(state_file, state)
            batch_file.replace(failed_directory / batch_file.name)
            summary["failed"] += 1
            continue
        pending = state["pending"].setdefault(
            batch.batch_id,
            {
                "nonce": uuid.uuid4().hex,
                "sent_at": _utcnow().isoformat(),
            },
        )
        save_collector_state(state_file, state)
        try:
            response, attempts = collector.deliver_with_retry(
                batch.model_dump(mode="json"),
                nonce=str(pending["nonce"]),
                sent_at=str(pending["sent_at"]),
            )
        except CollectorDeliveryError as exc:
            _record_failure(
                state,
                batch_id=batch.batch_id,
                error=str(exc),
            )
            save_collector_state(state_file, state)
            batch_file.replace(failed_directory / batch_file.name)
            summary["failed"] += 1
            continue
        state["pending"].pop(batch.batch_id, None)
        state["sent_count"] += 1
        state["last_success_at"] = _utcnow().isoformat()
        state["last_error"] = None
        state["last_batch_id"] = batch.batch_id
        state["last_job_id"] = response.get("id")
        state["last_attempt_count"] = attempts
        save_collector_state(state_file, state)
        batch_file.replace(sent_directory / batch_file.name)
        summary["sent"] += 1
    return summary


def load_collector_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": COLLECTOR_STATE_VERSION,
            "sent_count": 0,
            "failed_count": 0,
            "last_success_at": None,
            "last_failure_at": None,
            "last_error": None,
            "last_batch_id": None,
            "last_job_id": None,
            "last_attempt_count": 0,
            "pending": {},
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        COLLECTOR_STATE_VERSION
    ):
        raise ValueError("collector state file is not supported")
    payload.setdefault("pending", {})
    return payload


def save_collector_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(state, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deliver signed Agent traffic evidence from an outbox."
    )
    parser.add_argument(
        "--endpoint",
        default=(
            "http://localhost:8000/api/v1/agents/evidence/traffic-batches"
        ),
    )
    parser.add_argument("--key-id", required=True)
    parser.add_argument(
        "--secret-env",
        default="AGENT_TRAFFIC_COLLECTOR_SECRET",
    )
    parser.add_argument("--outbox", type=Path, default=Path("data/traffic-outbox"))
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path("data/traffic-outbox/collector-state.json"),
    )
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--no-gzip", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if args.status:
        print(
            json.dumps(
                load_collector_state(args.state_file),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
        )
        return
    secret = os.getenv(args.secret_env)
    if not secret:
        raise SystemExit(f"{args.secret_env} is required")
    collector = AgentTrafficCollector(
        CollectorConfig(
            endpoint=args.endpoint,
            key_id=args.key_id,
            secret=secret,
            timeout_seconds=args.timeout_seconds,
            max_attempts=args.max_attempts,
            gzip_enabled=not args.no_gzip,
        )
    )
    while True:
        process_outbox_once(
            collector=collector,
            outbox=args.outbox,
            state_file=args.state_file,
        )
        if args.once:
            return
        time.sleep(max(0.5, args.poll_seconds))


def _record_failure(
    state: dict[str, Any],
    *,
    batch_id: str,
    error: str,
) -> None:
    state["failed_count"] += 1
    state["last_failure_at"] = _utcnow().isoformat()
    state["last_error"] = error[:2000]
    state["last_batch_id"] = batch_id


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


if __name__ == "__main__":
    main()
