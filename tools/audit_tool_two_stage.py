"""Recompute two-stage diagnostic findings from captured outputs, without importing the scorer."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def audit(root: Path, report_path: Path) -> dict:
    report = json.loads(report_path.read_text("utf-8"))
    assert report["status"] in {"complete", "complete_with_errors"}
    baseline_path = root / report["baseline_path"]
    assert sha(baseline_path) == report["baseline_sha256"]
    baseline = json.loads(baseline_path.read_text("utf-8"))
    for path, key in (
        ("reference_workload/runtime_matrix.json", "matrix_sha256"),
        (
            "reference_workload/diagnostics/tool-fault-baseline-v1.json",
            "case_pack_sha256",
        ),
        ("reference_workload/revisions/1.0.4/manifest.json", "manifest_sha256"),
    ):
        assert sha(root / path) == baseline[key]
    journal = report_path.with_suffix(".observations.jsonl")
    assert sha(journal) == report["journal_sha256"]
    assert [
        json.loads(line) for line in journal.read_text("utf-8").splitlines()
    ] == report["rows"]
    for name, expected in report["source_sha256"].items():
        assert sha(root / "backend/app" / name) == expected, name
    assert (
        sha(root / "reference_workload/diagnostics/tool-two-stage-challenge-v1.json")
        == report["challenge_sha256"]
    )
    assert not report["human_reviewed"] and not report["gate_evidence"]
    assert not report["database_writes_performed"]
    rows = report["rows"]
    assert len(rows) == report["protocol"]["expected_observations"]
    keys = {
        (r["entry"], r["cohort"], r["variant"], r["id"], r["trial"], r["tool_order"])
        for r in rows
    }
    assert len(keys) == len(rows)
    expected_keys = set()
    for entry in report["entries"]:
        for case in report["packs"]["frozen"]["cases"]:
            for trial in range(1, entry["matrix_entry"]["trials"] + 1):
                expected_keys.add(
                    (
                        entry["name"],
                        "frozen",
                        "candidate",
                        case["id"],
                        trial,
                        "registered",
                    )
                )
        for case in report["packs"]["challenge"]["cases"]:
            for variant in ("baseline", "candidate"):
                for order in ("registered", "reversed"):
                    expected_keys.add(
                        (entry["name"], "challenge", variant, case["id"], 1, order)
                    )
    assert keys == expected_keys
    cases = {
        (cohort, item["id"]): item
        for cohort, pack in report["packs"].items()
        for item in pack["cases"]
    }
    old_rows = {
        (entry["name"], row["id"], row["trial"]): row
        for entry in baseline["entries"]
        for row in entry["rows"]
    }
    computed = defaultdict(list)
    transitions = Counter()
    first_selection_changes = 0
    http_calls = 0
    finish_reasons = Counter()
    failures = []
    for row in rows:
        case = cases[row["cohort"], row["id"]]
        requests = row["requests"]
        http_calls += len(requests)
        for request in requests:
            assert digest(request["body"]) == request["request_hash"]
            response = request.get("response", {})
            for choice in response.get("choices", []):
                finish_reasons[choice.get("finish_reason")] += 1
        if "normalized_output" not in row:
            assert "error" in row
            selected = exact = first_exact = False
        else:
            try:
                output = json.loads(row["normalized_output"])
            except ValueError:
                output = {"invalid_raw_output": row["normalized_output"]}
            if not isinstance(output, dict):
                output = {"invalid_output_shape": output}
            selected = output.get("tool_name") == case["expected_tool"]
            exact = selected and output.get("arguments") == case["expected_arguments"]
            assert selected == row["selection_correct"]
            assert exact == row["selection_and_arguments_exact"]
            generation = row["metadata"].get("tool_argument_generation")
            first_exact = exact
            if generation:
                first_guard = generation["first_stage"]["guard"]
                first_exact = first_guard["tool_name"] == case[
                    "expected_tool"
                ] and first_guard["raw_arguments_hash"] == digest(
                    case["expected_arguments"]
                )
                if generation["status"] == "generated":
                    assert output["tool_name"] == generation["selected_tool"]
                    args = json.loads(generation["second_stage"]["raw_output"])
                    assert output["arguments"] == args
                    assert row["metadata"]["tool_call_contract"][
                        "raw_arguments_hash"
                    ] == digest(args)
                    second_input = json.loads(
                        requests[1]["body"]["messages"][1]["content"]
                    )
                    assert second_input["request"] == case["request"]
                    assert set(second_input) <= {
                        "request",
                        "instruction",
                        "selected_tool",
                        "document_catalog",
                    }
                    assert (
                        second_input["selected_tool"]["tool_name"]
                        == output["tool_name"]
                    )
                transitions[f"{row['cohort']}/{int(first_exact)}->{int(exact)}"] += 1
            if row["cohort"] == "frozen":
                old = old_rows[row["entry"], row["id"], row["trial"]]
                assert requests[0]["request_hash"] == old["request_hash"]
                first_selection_changes += (
                    row["stage1_selected_tool"]
                    != old["metadata"]["tool_call_contract"]["tool_name"]
                )
            for trace in row["traces"].values():
                for step in trace["steps"]:
                    assert step["arguments"] == output.get("arguments")
                if not row["guard_eligible"]:
                    assert trace["fault_scenario"]["handler_invocation_count"] == 0
            if not exact:
                failures.append(
                    {
                        "entry": row["entry"],
                        "cohort": row["cohort"],
                        "variant": row["variant"],
                        "id": row["id"],
                        "trial": row["trial"],
                        "order": row["tool_order"],
                        "expected_tool": case["expected_tool"],
                        "expected_arguments": case["expected_arguments"],
                        "actual": output,
                    }
                )
        measured = row["measured_tokens"]
        if row["http_usage_complete"]:
            assert measured == {
                key: sum(request["response"]["usage"][key] for request in requests)
                for key in ("prompt_tokens", "completion_tokens")
            }
        else:
            assert measured is None
        computed[row["entry"], row["cohort"], row["variant"]].append(
            {
                "selected": selected,
                "exact": exact,
                "stage1_exact": first_exact,
                "error": "error" in row,
                "latency_ms": row.get("latency_ms"),
                "measured": measured,
                "http_calls": len(requests),
            }
        )
    summary = []
    for (entry, cohort, variant), values in computed.items():
        captured_summary = report["summaries"][f"{entry}/{cohort}/{variant}"]
        exact_count = sum(v["exact"] for v in values)
        assert exact_count == captured_summary["selection_and_arguments_exact"]
        assert len(values) == captured_summary["observation_count"]
        measured_values = [v["measured"] for v in values if v["measured"] is not None]
        latencies = [v["latency_ms"] for v in values if v["latency_ms"] is not None]
        result = {
            "entry": entry,
            "cohort": cohort,
            "variant": variant,
            "n": len(values),
            "selected": sum(v["selected"] for v in values),
            "exact": exact_count,
            "stage1_exact": sum(v["stage1_exact"] for v in values),
            "errors": sum(v["error"] for v in values),
            "http_calls": sum(v["http_calls"] for v in values),
            "measured_usage_n": len(measured_values),
            "prompt_tokens": sum(v["prompt_tokens"] for v in measured_values),
            "completion_tokens": sum(v["completion_tokens"] for v in measured_values),
            "median_latency_ms": statistics.median(latencies) if latencies else None,
        }
        if cohort == "frozen":
            result["historical_exact"] = sum(
                old_rows[entry, item["id"], trial]["selection_and_arguments_exact"]
                for item in report["packs"][cohort]["cases"]
                for trial in range(
                    1,
                    next(
                        item["matrix_entry"]["trials"]
                        for item in report["entries"]
                        if item["name"] == entry
                    )
                    + 1,
                )
            )
        summary.append(result)
    paired = defaultdict(dict)
    order_groups = defaultdict(dict)
    for row in rows:
        if row["cohort"] == "challenge":
            paired[row["entry"], row["id"], row["tool_order"]][row["variant"]] = row
            order_groups[row["entry"], row["id"], row["variant"]][row["tool_order"]] = (
                row
            )
    for pair in paired.values():
        assert (
            pair["baseline"]["requests"][0]["body"]
            == pair["candidate"]["requests"][0]["body"]
        )
    return {
        "assessment": "share_with_caveats_local_diagnostic_only",
        "report_sha256": sha(report_path),
        "baseline_sha256": sha(baseline_path),
        "observations": len(rows),
        "http_calls": http_calls,
        "trace_count": sum(len(row.get("traces", {})) for row in rows),
        "finish_reasons": dict(finish_reasons),
        "summary": summary,
        "within_candidate_exact_transitions": dict(transitions),
        "frozen_stage1_selection_changed_vs_historical": first_selection_changes,
        "challenge_pair_stage1_selection_changes": sum(
            pair["baseline"]["stage1_selected_tool"]
            != pair["candidate"]["stage1_selected_tool"]
            for pair in paired.values()
        ),
        "challenge_order_exact_changes": {
            variant: sum(
                group["registered"]["selection_and_arguments_exact"]
                != group["reversed"]["selection_and_arguments_exact"]
                for key, group in order_groups.items()
                if key[2] == variant
            )
            for variant in ("baseline", "candidate")
        },
        "failures": failures,
        "caveats": [
            "Locally authored explicit-value cases, not independent or human-reviewed evaluation.",
            "Historical timing is not a controlled latency comparison; live pairs also have cache effects.",
            "Stage1 is a full legacy tool-call response; only its selected tool is retained in stage2.",
            "Candidate raw schema metrics concern an assembled envelope, not a native model tool call.",
            "Replayed fault traces are not independent generations; handlers are local fixtures.",
            "Omitting explicitly requested priority=normal fails exact matching but the local ticket handler defaults to normal; this is not necessarily a semantic execution error.",
            "No Gate promotion, source approval, training, API integration or production readiness.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(
        args.repository_root,
        args.report
        or args.repository_root
        / "artifacts/reference-workload/tool-two-stage-diagnostic-v1.json",
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(
        json.dumps(
            {k: v for k, v in result.items() if k != "failures"},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
