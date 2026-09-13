"""Exercise only an explicitly selected, isolated local review deployment."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler


def validate_target(url: str, confirmed: bool) -> str:
    parsed = urlsplit(url)
    if (
        not confirmed
        or parsed.scheme != "http"
        or parsed.hostname not in {"localhost", "127.0.0.1"}
        or parsed.port in {None, 8000, 18000}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path.rstrip("/") != "/api/v1"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Select a separate local review API and pass --confirm-isolated-review."
        )
    return url.rstrip("/")


def run(base: str) -> dict:
    checks = []
    opener = build_opener(ProxyHandler({}))

    def request(path, payload=None, *, expected=200, headers=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(
            base + path,
            data=data,
            headers={"Content-Type": "application/json", **(headers or {})},
        )
        try:
            response = opener.open(req, timeout=120)
        except HTTPError as error:
            response = error
        with response:
            body = response.read().decode("utf-8")
            if response.status != expected:
                raise RuntimeError(
                    f"{req.get_method()} {path}: expected {expected}, got {response.status}: {body[:800]}"
                )
            checks.append(
                {"method": req.get_method(), "path": path, "status": response.status}
            )
            return (
                json.loads(body)
                if "json" in response.headers.get("Content-Type", "")
                else body
            )

    def check(condition, name):
        if not condition:
            raise RuntimeError(f"Invariant failed: {name}")
        checks.append({"invariant": name, "passed": True})

    def named(path, name):
        return next(item for item in request(path) if item["name"] == name)

    request("/health")
    config = named("/deployment-configurations", "Qwen2.5 7B Local Document Assistant")
    suite = named("/evaluation-suites", "Korean Operations Assistant Acceptance Suite")
    task = named("/benchmark-tasks", "Korean document QA")
    prompt = next(
        item
        for item in request("/prompt-versions")
        if item["benchmark_task_id"] == task["id"]
    )
    policy = named("/acceptance-policies", "Strict Local Release Policy")
    ids = {
        "deployment_configuration_id": config["id"],
        "evaluation_suite_id": suite["id"],
    }
    request("/benchmark-executions", {}, expected=422)
    execution = request(
        "/benchmark-executions",
        {
            **ids,
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "synthetic_demo",
            "max_cases": 3,
            "seed": 42,
        },
        expected=201,
    )
    run_id = execution["benchmark_run"]["id"]
    check(execution["benchmark_run"]["status"] == "completed", "mock run completed")
    check(
        execution["benchmark_run"]["data_source"] == "synthetic_demo",
        "mock provenance is explicit",
    )
    check(
        execution["result_count"] == execution["metric_count"] == 3,
        "three results and metrics",
    )
    results = request("/benchmark-results?limit=200")
    own_results = [row for row in results if row["benchmark_run_id"] == run_id]
    check(
        len(own_results) == 3 and all(row["raw_output"] for row in own_results),
        "raw outputs persisted",
    )
    metrics = request(f"/inference-metrics?benchmark_run_id={run_id}")
    check(len(metrics) == 3, "metrics readable")
    logs = request(f"/benchmark-executions/{run_id}/logs")
    check(
        logs[0]["event_type"] == "run_started"
        and logs[-1]["event_type"] == "run_completed",
        "run log lifecycle",
    )
    gate_request = {**ids, "acceptance_policy_id": policy["id"]}
    preflight = request("/deployment-gates/preflight", gate_request)
    check(
        preflight["evidence"]["production_readiness"] == "not_production_ready",
        "synthetic evidence is not production ready",
    )
    gate = request("/deployment-gates/evaluations", gate_request, expected=201)
    check(bool(gate["decision_hash"]), "gate decision is hash bound")
    request(f"/deployment-gates/evaluations/{gate['id']}")
    gate_report = request(f"/deployment-gates/evaluations/{gate['id']}/report.md")
    check(len(gate_report) > 100, "gate report exported")
    decision = request(
        "/release-decisions",
        {
            "gate_evaluation_id": gate["id"],
            "decision": "REQUEST_CHANGES",
            "decided_by": "Automated MVP QA (synthetic)",
            "decision_reason": "Automated smoke test only. Synthetic evidence cannot authorize production release.",
            "signature_statement": "Synthetic QA record, not human review or approval.",
            "ticket_reference": "MVP-AUTOMATED-QA",
        },
        expected=201,
        headers={
            "x-model-atlas-operator-id": "mvp-automated-qa",
            "x-model-atlas-operator-name": "Automated MVP QA (synthetic)",
            "x-model-atlas-operator-role": "Release Manager",
            "x-model-atlas-identity-provider": "local-review-test-proxy",
        },
    )
    check(decision["decision"] == "REQUEST_CHANGES", "no release approval created")
    check(
        all(
            decision[key]
            for key in ("snapshot_hash", "decision_hash", "signature_hash")
        ),
        "release hashes persisted",
    )
    detail = request(f"/release-decisions/{decision['id']}")
    check(
        detail["snapshot_hash"] == decision["snapshot_hash"],
        "release snapshot stable on read",
    )
    request(f"/release-decisions/{decision['id']}/snapshot.json")
    request(f"/release-decisions/{decision['id']}/snapshot-diff")
    report = request(f"/release-decisions/{decision['id']}/report.md")
    check("REQUEST_CHANGES" in report, "release report preserves change request")
    return {
        "schema_version": "mvp-review-smoke-v1",
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_url": base,
        "status": "passed",
        "checks": checks,
        "benchmark_run_id": run_id,
        "gate_evaluation_id": gate["id"],
        "release_decision_id": decision["id"],
        "gate_verdict": gate["verdict"],
        "production_readiness": preflight["evidence"]["production_readiness"],
        "data_source": "synthetic_demo",
        "human_review_performed": False,
        "release_decision": "REQUEST_CHANGES",
        "external_review": "pending",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://localhost:18010/api/v1")
    parser.add_argument("--confirm-isolated-review", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = validate_target(args.api_url, args.confirm_isolated_review)
    if args.output.exists():
        parser.error("Output exists; use a fresh receipt path.")
    receipt = run(base)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
