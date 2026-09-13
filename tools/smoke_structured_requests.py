"""Exercise the local lab API, never official Gate approval or an external ticket service."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

GATE_FIELDS = (
    "gate_verdict",
    "critical_failure_count",
    "actual_runtime_result_count",
    "production_readiness",
    "review_coverage",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:18000/api/v1")
    parser.add_argument(
        "--generate", action="store_true", help="Also call the local model once"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite an existing QA report")
    url = urlparse(args.base_url)
    if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1"}:
        parser.error("this smoke test only supports a local HTTP API")
    if (
        url.username
        or url.password
        or url.query
        or url.fragment
        or url.path != "/api/v1"
    ):
        parser.error("expected an uncredentialed local /api/v1 base URL")

    def call(path, method="GET", body=None):
        request = Request(
            args.base_url + path,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "content-type": "application/json",
                "x-model-atlas-lab-action": "1",
            },
        )
        try:
            with urlopen(request, timeout=140) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def ok(path, method="GET", body=None, expected=200):
        code, value = call(path, method, body)
        assert code == expected, (path, code, value)
        return value

    def binding(record):
        return {
            "expected_revision": record["revision"],
            "expected_hash": record["contract_hash"],
        }

    def create(label):
        query = f"AUTOMATED QA - {label}"
        record = ok(
            "/structured-requests",
            "POST",
            {
                "original_request": (
                    "Automated QA, not human approval. Create a ticket. "
                    f"query='{query}'. priority=low. Do not omit priority."
                ),
                "query": query,
                "priority": {"mode": "set", "value": "low"},
            },
            expected=201,
        )
        return ok(
            f"/structured-requests/{record['id']}/confirm",
            "POST",
            {**binding(record), "acknowledged": True},
        )

    def check(record, priority):
        proposal = json.dumps(
            {
                "tool_name": "create_ticket",
                "arguments": {
                    "query": record["draft"]["query"],
                    "priority": priority,
                },
            }
        )
        return ok(
            f"/structured-requests/{record['id']}/checks",
            "POST",
            {**binding(record), "proposal": proposal},
            expected=201,
        )

    def execute_path(record, checked):
        return f"/structured-requests/{record['id']}/checks/{checked['id']}/execute"

    before = ok("/reference-workload/overview")
    record = create("concurrent execution")
    mismatch = check(record, "high")
    assert not mismatch["verdict"]["allowed"]
    blocked = ok(execute_path(record, mismatch), "POST", expected=409)
    assert "priority_mismatch" in blocked["detail"]["reasons"]
    checks = [check(record, "low"), check(record, "low")]
    barrier = threading.Barrier(2)

    def concurrent(checked):
        barrier.wait(timeout=10)
        return call(execute_path(record, checked), "POST")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(concurrent, checks))
    assert sorted(code for code, _ in results) == [200, 409], results
    winner = checks[next(i for i, (code, _) in enumerate(results) if code == 200)]
    replay = ok(execute_path(record, winner), "POST")
    assert replay["replayed"]
    stored = ok(f"/structured-requests/{record['id']}")
    executed = [item for item in stored["checks"] if item["execution"]]
    assert len(executed) == 1
    assert (
        executed[0]["execution"]["trace"]["fault_scenario"]["handler_invocation_count"]
        == 1
    )
    assert sum(e["event"] == "simulated_execution" for e in stored["events"]) == 1

    edit_record = create("revision invalidation")
    stale = check(edit_record, "low")
    changed = {**edit_record["draft"], "priority": {"mode": "omit"}}
    edited = ok(
        f"/structured-requests/{edit_record['id']}",
        "PUT",
        {**binding(edit_record), "draft": changed},
    )
    assert edited["revision"] == 2 and edited["confirmation"] is None
    stale_result = ok(execute_path(edit_record, stale), "POST", expected=409)
    assert stale_result["detail"] == "stale_proposal_check"

    generation = None
    if args.generate:
        model_record = create("model proposal")
        generated = ok(
            f"/structured-requests/{model_record['id']}/generate",
            "POST",
            binding(model_record),
            expected=201,
        )
        assert generated["source"] == "local_model_proposal"
        assert generated["execution"] is None
        assert not generated["generation"]["structured_constraints_sent_to_model"]
        generation = {"request_id": model_record["id"], "check": generated}

    after = ok("/reference-workload/overview")
    official_before = {k: before[k] for k in GATE_FIELDS}
    official_after = {k: after[k] for k in GATE_FIELDS}
    assert official_before == official_after, (official_before, official_after)
    report = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "automated_engineering_qa_not_human_approval_or_model_quality_evaluation",
        "gate_evidence": False,
        "status": "passed",
        "concurrency_request_id": record["id"],
        "concurrent_status_codes": [code for code, _ in results],
        "handler_invocation_count": 1,
        "replay_returned_existing_receipt": True,
        "wrong_priority_blocked": True,
        "edited_request_id": edit_record["id"],
        "old_revision_blocked": True,
        "generation": generation,
        "official_before": official_before,
        "official_after": official_after,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "output": str(args.output),
                "concurrent_status_codes": report["concurrent_status_codes"],
                "generation_allowed": generation["check"]["verdict"]["allowed"]
                if generation
                else None,
                "official_unchanged": True,
            }
        )
    )


if __name__ == "__main__":
    main()
