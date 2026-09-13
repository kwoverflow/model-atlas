from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    body = None
    request_headers = {"accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload).encode()
        request_headers["content-type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {detail}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"expected a JSON object from {url}")
    return result


def verify_staging(
    base_url: str,
    *,
    trigger_test_page: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    operator_headers = {
        "x-model-atlas-operator-id": "staging-readiness-verifier",
        "x-model-atlas-operator-name": "Staging Readiness Verifier",
        "x-model-atlas-operator-role": "SRE Lead",
    }
    job_id = None
    if trigger_test_page:
        job = request_json(
            f"{base_url}/operations/reliability/test-pages",
            method="POST",
            payload={
                "severity": "warning",
                "reason": "Verify staging paging provider receipt correlation",
            },
            headers=operator_headers,
        )
        job_id = str(job.get("id") or "") or None

    deadline = time.monotonic() + max(5, timeout_seconds)
    overview: dict[str, Any] = {}
    job_status = None
    while time.monotonic() < deadline:
        overview = request_json(f"{base_url}/operations/reliability")
        readiness = overview.get("staging_readiness") or {}
        if job_id:
            job = request_json(f"{base_url}/agents/jobs/{job_id}")
            job_status = job.get("status")
            if job_status == "failed":
                break
        if readiness.get("ready") is True and (not job_id or job_status == "completed"):
            break
        time.sleep(1)

    readiness = overview.get("staging_readiness") or {}
    result = {
        "schema_version": "model-atlas-operational-staging-verification-v1",
        "ready": readiness.get("ready") is True,
        "operations_health": overview.get("health"),
        "open_incident_count": overview.get("open_incident_count"),
        "test_job_id": job_id,
        "test_job_status": job_status,
        "latest_receipt_delivery_id": readiness.get("latest_receipt_delivery_id"),
        "passed_count": readiness.get("passed_count"),
        "failed_count": readiness.get("failed_count"),
        "checks": readiness.get("checks") or [],
    }
    if not result["ready"]:
        raise RuntimeError(json.dumps(result, sort_keys=True))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify Model Atlas operational staging readiness"
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:18000/api/v1",
    )
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--skip-test-page", action="store_true")
    arguments = parser.parse_args()
    try:
        result = verify_staging(
            arguments.base_url,
            trigger_test_page=not arguments.skip_test_page,
            timeout_seconds=arguments.timeout_seconds,
        )
    except RuntimeError as exc:
        print(str(exc), flush=True)
        raise SystemExit(1) from exc
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
