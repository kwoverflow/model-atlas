"""Compare explicit evaluator versions over immutable canary evidence, without inference."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from app.reference_workload.critical_canary import _verify, summarize_rows
from app.reference_workload.runtime_matrix import DIAGNOSTIC_RUNTIME_DATA_SOURCE
from app.services.deployment_gate.critical_evaluation import (
    AGENT_AWARE_VERSION,
    LEGACY_VERSION,
    evaluate_critical_result,
)
from app.services.deployment_gate.evidence import stable_hash


def compare_saved_canary(source: dict) -> dict:
    _verify(source)
    if (
        source.get("kind") != "audit"
        or source.get("gate_evidence") is not False
        or source.get("human_reviewed") is not False
        or source.get("production_readiness") != "not_production_ready"
    ):
        raise ValueError("expected non-authoritative, unreviewed canary evidence")
    cases = {}
    runs = {}
    for stored in source["stored_runs"]:
        run = stored["run"]
        if run["id"] in runs or run["data_source"] != DIAGNOSTIC_RUNTIME_DATA_SOURCE:
            raise ValueError("duplicate or non-diagnostic run")
        runs[run["id"]] = run
        for case in stored["cases"]:
            if case["id"] in cases and cases[case["id"]] != case:
                raise ValueError("conflicting case snapshots")
            cases[case["id"]] = case
    rows = source["rows"]
    if not rows:
        raise ValueError("empty canary")
    case_ids = sorted({case["external_case_id"] for case in cases.values()})
    summary = source["summary"]
    entry_names = [item["entry"] for item in summary["by_entry"]]
    if (
        len(rows) != summary["observation_count"]
        or len(case_ids) != summary["unique_case_count"]
        or len(set(entry_names)) != len(entry_names)
    ):
        raise ValueError("frozen summary coverage mismatch")
    summarize_rows(rows, case_ids=case_ids, entry_names=entry_names)
    entry_runs = {
        entry: {row["benchmark_run_id"] for row in rows if row["entry"] == entry}
        for entry in entry_names
    }
    if (
        any(len(ids) != 1 for ids in entry_runs.values())
        or len(runs) != len(entry_names)
        or {run_id for ids in entry_runs.values() for run_id in ids} != runs.keys()
    ):
        raise ValueError("run/entry coverage mismatch")
    compared = []
    for row in rows:
        record = row["stored_result"]
        case = cases.get(row["case_id"])
        run = runs.get(row["benchmark_run_id"])
        if (
            case is None
            or run is None
            or case["criticality"] != "critical"
            or case["evaluation_suite_id"] != run["evaluation_suite_id"]
            or record["evaluation_case_id"] != case["id"]
            or record["id"] != row["benchmark_result_id"]
            or record["benchmark_run_id"] != run["id"]
            or record["sample_id"] != row["sample_id"]
            or record["data_source"] != DIAGNOSTIC_RUNTIME_DATA_SOURCE
            or row["external_case_id"] != case["external_case_id"]
            or row["category"] != case["category"]
        ):
            raise ValueError("case/result/run identity or provenance mismatch")
        result_object = SimpleNamespace(**record)
        case_object = SimpleNamespace(**case)
        legacy = evaluate_critical_result(result_object, case_object, version=LEGACY_VERSION)
        candidate = evaluate_critical_result(
            result_object, case_object, version=AGENT_AWARE_VERSION
        )
        if legacy.status != row["status"]:
            raise ValueError("legacy evaluator no longer matches frozen outcomes")
        compared.append(
            {
                "entry": row["entry"],
                "external_case_id": row["external_case_id"],
                "category": row["category"],
                "benchmark_result_id": record["id"],
                "source_result_sha256": stable_hash(record),
                "source_case_sha256": stable_hash(case),
                "legacy": legacy.to_dict(),
                "candidate": candidate.to_dict(),
                "changed": legacy.status != candidate.status,
            }
        )
    changed = [row for row in compared if row["changed"]]
    return {
        "schema_version": "critical-evaluator-comparison-v1",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "source_content_sha256": source["content_sha256"],
        "legacy_version": LEGACY_VERSION,
        "candidate_version": AGENT_AWARE_VERSION,
        "authority": "non_authoritative_offline_evaluator_comparison",
        "gate_evidence": False,
        "human_reviewed": False,
        "production_readiness": "not_production_ready",
        "model_calls": 0,
        "database_writes": 0,
        "summary": {
            "observation_count": len(compared),
            "changed_count": len(changed),
            "legacy": dict(Counter(row["legacy"]["status"] for row in compared)),
            "candidate": dict(Counter(row["candidate"]["status"] for row in compared)),
            "non_agent_changed_count": sum(
                row["candidate"]["output_kind"] != "agent_plan" for row in changed
            ),
            "pass_to_fail_count": sum(row["legacy"]["status"] == "pass" for row in changed),
            "remaining_case_ids": sorted(
                {
                    row["external_case_id"]
                    for row in compared
                    if row["candidate"]["status"] == "fail"
                }
            ),
        },
        "rows": compared,
        "limitations": [
            "Same stored outputs, different evaluator; not model improvement or fresh inference.",
            "Only the per-result critical predicate is compared; "
            "no Gate or aggregate metric migration.",
            "Agent trace checks test structural consistency, "
            "not reviewer identity or semantic truth.",
            "Candidate v2 requires current Agent v2 traces and explicit expected plan steps.",
            "Existing compiler-produced plans remain system behavior, not raw-model accuracy.",
        ],
    }


def compare_snapshots(before: dict, after: dict) -> dict:
    for state in (before, after):
        _verify(state)
        if state.get("kind") != "snapshot":
            raise ValueError("expected protected-state snapshot")
    if before["official"] != after["official"]:
        raise ValueError("official evidence or verdict changed")
    old, new = before["source_sha256"], after["source_sha256"]
    return {
        "official_unchanged": True,
        "before_content_sha256": before["content_sha256"],
        "after_content_sha256": after["content_sha256"],
        "changed_source_paths": sorted(
            path for path in old.keys() & new.keys() if old[path] != new[path]
        ),
        "added_source_paths": sorted(new.keys() - old.keys()),
        "removed_source_paths": sorted(old.keys() - new.keys()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new evidence path")
    raw = args.input.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != args.expected_sha256:
        parser.error("input SHA-256 differs from pinned evidence")
    report = compare_saved_canary(json.loads(raw))
    report["source_file_sha256"] = digest
    report["protected_state"] = compare_snapshots(
        json.loads(args.before.read_text(encoding="utf-8")),
        json.loads(args.after.read_text(encoding="utf-8")),
    )
    root = Path(__file__).resolve().parents[1]
    report["implementation_sha256"] = {
        path: hashlib.sha256((root / path).read_bytes()).hexdigest()
        for path in (
            "reference_workload/critical_evaluator_comparison.py",
            "services/deployment_gate/critical_evaluation.py",
            "services/deployment_gate/metrics.py",
            "schemas/agent_execution.py",
        )
    }
    report["content_sha256"] = stable_hash(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"output": str(args.output), "summary": report["summary"]}))


if __name__ == "__main__":
    main()
