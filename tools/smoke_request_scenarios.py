"""Local-only API QA. Persists synthetic reports/studies, never human review or official results."""

import argparse
import datetime as dt
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = "http://localhost:18000/api/v1"
OFFICIAL_FIELDS = (
    "gate_verdict",
    "critical_failure_count",
    "actual_runtime_result_count",
    "production_readiness",
    "review_coverage",
)


def call(path, method="GET", body=None, expected=200):
    request = Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"content-type": "application/json", "x-model-atlas-lab-action": "1"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            code, value = response.status, json.load(response)
    except HTTPError as exc:
        code, value = exc.code, json.load(exc)
    assert code == expected, (path, code, value)
    return value


def official():
    value = call("/reference-workload/overview")
    return {k: value[k] for k in OFFICIAL_FIELDS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("refusing to overwrite existing QA evidence")
    before = official()
    live_requests_before = call("/structured-requests?limit=50")
    run = call("/request-scenarios/runs", "POST", expected=201)
    assert run["report"]["counts"] == {
        "passed": 14,
        "known_limitation": 1,
        "regression": 0,
        "error": 0,
    }
    assert not run["report"]["gate_evidence"] and run["report"]["model_calls"] == 0
    attempts = []
    for scenario_id, value in (
        (
            "SRC-01",
            {
                "decision": "confirm",
                "query": "정기 점검 알림",
                "priority": {"mode": "set", "value": "low"},
            },
        ),
        (
            "SRC-04",
            {
                "decision": "confirm",
                "query": "정기 점검 알림",
                "priority": {"mode": "omit"},
            },
        ),
        (
            "SRC-09",
            {"decision": "clarify", "query": "", "priority": {"mode": "unresolved"}},
        ),
    ):
        attempt = call(
            "/request-scenarios/studies",
            "POST",
            {"scenario_id": scenario_id, "source": "automated_qa"},
            expected=201,
        )
        path = f"/request-scenarios/studies/{attempt['id']}"
        assert "expected" not in json.dumps(attempt)
        first = call(path, "PUT", {"expected_revision": 0, "answer": value})
        assert first["correction_count"] == 0 and first["revision"] == 1
        saved = first
        if scenario_id == "SRC-01":
            changed = {**value, "priority": {"mode": "set", "value": "high"}}
            saved = call(path, "PUT", {"expected_revision": 1, "answer": changed})
            assert saved["correction_count"] == 1
            call(
                path + "/submit",
                "POST",
                {
                    "expected_revision": 1,
                    "expected_hash": first["answer_hash"],
                    "acknowledged": True,
                },
                expected=409,
            )
        payload = {
            "expected_revision": saved["revision"],
            "expected_hash": saved["answer_hash"],
            "acknowledged": True,
        }
        result = call(path + "/submit", "POST", payload)
        assert result["result"]["matches_scenario_key"] == (scenario_id != "SRC-01")
        assert not result["human_review_verified"] and not result["gate_evidence"]
        replay = call(path + "/submit", "POST", payload)
        assert replay["replayed"] and replay["result"] == result["result"]
        attempts.append(result)
    after = official()
    assert before == after
    assert call("/structured-requests?limit=50") == live_requests_before
    report = {
        "created_at": dt.datetime.now(dt.UTC).isoformat(),
        "status": "passed",
        "scope": "automated_engineering_qa_not_human_review",
        "run": run,
        "attempts": attempts,
        "official_before": before,
        "official_after": after,
        "live_request_records_unchanged": True,
        "gate_evidence": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "status": "passed",
                "run_id": run["id"],
                "counts": run["report"]["counts"],
                "automated_studies": len(attempts),
                "official_unchanged": True,
                "output": str(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
