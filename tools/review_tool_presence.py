"""Audit preserved unsuccessful and successful optional-presence experiments independently."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from review_tool_default_semantics import check_comparison, digest, recompute, sha

ROOT = Path(__file__).resolve().parents[1]
REPORTS = {
    "development_v2": "artifacts/reference-workload/tool-presence-development-v2.json",
    "development_v3": "artifacts/reference-workload/tool-presence-development-v3.json",
    "fresh_v3": "artifacts/reference-workload/tool-presence-fresh-v3.json",
}
DESTINATION = "docs/reports/2026-09-09_tool_presence"


def verify_source(root, name, expected):
    current = root / "backend/app" / name
    current.resolve().relative_to((root / "backend/app").resolve())
    if sha(current) == expected:
        return str(current.relative_to(root))
    assert name == "reference_workload/tool_presence_diagnostic.py"
    assert len(expected) == 64 and all(c in "0123456789abcdef" for c in expected)
    snapshot = (
        root
        / "reference_workload/diagnostics/source_snapshots/tool_presence_diagnostic"
        / (expected + ".py")
    )
    assert sha(snapshot) == expected
    return str(snapshot.relative_to(root))


def audit_one(root, label, path):
    report = json.loads(path.read_text("utf-8"))
    assert report["status"] in {"complete", "complete_with_errors"}
    assert not report["human_reviewed"] and not report["gate_evidence"]
    assert not report["database_writes_performed"]
    verified_sources = {
        name: verify_source(root, name, expected)
        for name, expected in report["source_sha256"].items()
    }
    assert sha(root / report["previous_path"]) == report["previous_sha256"]
    previous = json.loads((root / report["previous_path"]).read_text("utf-8"))
    assert report["runtime"] == previous["runtime"]
    case_path = root / report["case_pack_path"]
    assert sha(case_path) == report["case_pack_sha256"]
    source_cases = {
        c["id"]: c for c in json.loads(case_path.read_text("utf-8"))["cases"]
    }
    cases = {c["id"]: c for c in report["cases"]}
    assert len(cases) == len(report["cases"])
    assert all(c == source_cases[key] for key, c in cases.items())
    journal = path.with_suffix(".observations.jsonl")
    assert sha(journal) == report["journal_sha256"]
    rows = report["rows"]
    assert [
        json.loads(line) for line in journal.read_text("utf-8").splitlines()
    ] == rows
    variants = report["protocol"]["variants"]
    expected_keys = {
        (case_id, trial, order, variant)
        for case_id in cases
        for trial in range(1, report["matrix_entry"]["trials"] + 1)
        for order in ("registered", "reversed")
        for variant in variants
    }
    actual_keys = {(r["id"], r["trial"], r["tool_order"], r["variant"]) for r in rows}
    assert actual_keys == expected_keys and len(rows) == len(expected_keys)
    assert len(rows) == report["protocol"]["expected_observations"]
    groups = defaultdict(list)
    strata = defaultdict(Counter)
    paired = defaultdict(dict)
    finishes = Counter()
    errors = []
    failures = []
    omissions = Counter()
    transitions = Counter()
    for row in rows:
        case = cases[row["id"]]
        score = check_comparison(
            row.get("normalized_output"), case, row["argument_comparison"]
        )
        requests = row["requests"]
        assert len(requests) <= (1 if row["variant"] == "baseline" else 2)
        for request in requests:
            assert digest(request["body"]) == request["request_hash"]
            assert "local-tool-default-equivalence" not in json.dumps(request["body"])
            for choice in request.get("response", {}).get("choices", []):
                finishes[choice.get("finish_reason")] += 1
        measured = row["measured_tokens"]
        if row["http_usage_complete"]:
            assert measured == {
                key: sum(r["response"]["usage"][key] for r in requests)
                for key in ("prompt_tokens", "completion_tokens")
            }
        else:
            assert measured is None
        if "error" in row:
            errors.append(
                {"id": row["id"], "variant": row["variant"], "error": row["error"]}
            )
        generation = row.get("metadata", {}).get("tool_argument_generation", {})
        if generation.get("status") == "generated":
            actual = json.loads(row["normalized_output"])
            wire = json.loads(generation["second_stage"]["raw_output"])
            assert actual["tool_name"] == generation["selected_tool"]
            decoding = generation.get("presence_decoding")
            if decoding:
                public = json.loads(requests[1]["body"]["messages"][1]["content"])[
                    "selected_tool"
                ]["argument_schema"]
                optional = set(public["properties"]) - set(public.get("required", []))
                assert set(wire) == set(public["properties"])
                omitted = sorted(k for k in optional if wire[k] is None)
                assert omitted == decoding["omitted_optional_fields"]
                assert actual["arguments"] == {
                    k: v for k, v in wire.items() if k not in omitted
                }
                assert decoding["values_repaired"] is False
                omissions[row["variant"]] += len(omitted)
            else:
                assert actual["arguments"] == wire
            first = recompute(generation["first_stage"]["normalized_output"], case)
            transitions[
                f"{row['variant']}/equivalent:{int(first['equivalent'])}->{int(score['equivalent'])}"
            ] += 1
        for trace in row.get("traces", {}).values():
            actual = json.loads(row["normalized_output"])
            for step in trace["steps"]:
                assert step["arguments"] == actual.get("arguments")
            if not row["argument_comparison"]["execution_eligible"]:
                assert trace["fault_scenario"]["handler_invocation_count"] == 0
        groups[row["variant"]].append(
            {**score, "measured": measured, "latency": row.get("latency_ms")}
        )
        strata[row["variant"], row["stratum"]].update(
            n=1, exact=int(score["exact"]), equivalent=int(score["equivalent"])
        )
        paired[row["id"], row["trial"], row["tool_order"]][row["variant"]] = row
        if not score["equivalent"]:
            failures.append(
                {
                    "id": row["id"],
                    "variant": row["variant"],
                    "trial": row["trial"],
                    "order": row["tool_order"],
                    "output": row.get("normalized_output"),
                    "reason": row["argument_comparison"]["reason"],
                }
            )
    required_only_pairs = 0
    for pair in paired.values():
        available = [r for r in pair.values() if r["requests"]]
        assert all(
            r["requests"][0]["body"] == available[0]["requests"][0]["body"]
            for r in available
        )
        v1 = pair["candidate_v1"]
        successor = next(
            r for v, r in pair.items() if v not in {"baseline", "candidate_v1"}
        )
        if len(v1["requests"]) == len(successor["requests"]) == 2:
            first_body = v1["requests"][1]["body"]
            next_body = successor["requests"][1]["body"]
            first_payload = json.loads(first_body["messages"][1]["content"])
            next_payload = json.loads(next_body["messages"][1]["content"])
            if (
                first_payload["selected_tool"]["tool_name"]
                == next_payload["selected_tool"]["tool_name"]
            ):
                schema = first_payload["selected_tool"]["argument_schema"]
                assert schema == next_payload["selected_tool"]["argument_schema"]
                if not set(schema["properties"]) - set(schema.get("required", [])):
                    assert first_body == next_body
                    required_only_pairs += 1
    result_summary = []
    for variant, values in groups.items():
        measured = [v["measured"] for v in values if v["measured"] is not None]
        latency = [v["latency"] for v in values if v["latency"] is not None]
        result = {
            "variant": variant,
            "n": len(values),
            **{
                key: sum(v[key] for v in values)
                for key in ("selection", "exact", "equivalent", "default_only")
            },
            "measured_usage_n": len(measured),
            "total_tokens": sum(
                v["prompt_tokens"] + v["completion_tokens"] for v in measured
            ),
            "median_latency_ms": statistics.median(latency) if latency else None,
        }
        assert result["exact"] == report["summaries"][variant]["exact_call"]
        assert (
            result["equivalent"]
            == report["summaries"][variant]["default_equivalent_call"]
        )
        result_summary.append(result)
    return {
        "label": label,
        "sha256": sha(path),
        "source_paths_verified": verified_sources,
        "started_at": report["started_at"],
        "completed_at": report["completed_at"],
        "observations": len(rows),
        "http_calls": sum(len(r["requests"]) for r in rows),
        "replay_traces": sum(len(r.get("traces", {})) for r in rows),
        "summary": result_summary,
        "strata": [{"variant": k[0], "stratum": k[1], **v} for k, v in strata.items()],
        "required_only_stage2_body_matches": required_only_pairs,
        "model_null_omission_count": dict(omissions),
        "within_candidate_transitions": dict(transitions),
        "finish_reasons": dict(finishes),
        "errors": errors,
        "non_equivalent_rows": failures,
    }


def audit(root=ROOT):
    results = [audit_one(root, label, root / path) for label, path in REPORTS.items()]
    return {
        "assessment": "share_with_caveats_local_diagnostic_only",
        "experiments": results,
        "caveats": [
            "Prompt-only v2 failure is retained; v3 was selected on development cases before fresh evaluation.",
            "Null is a model-owned omission marker in v3, not a repaired argument or expected-value fallback.",
            "Fresh cases are locally authored and unreviewed; repeated trials are not independent requests.",
            "Stage1 and required-only stage2 requests are unchanged, but repeated model outputs can vary.",
            "Local default equivalence does not establish real content, authorization or general semantic correctness.",
            "Latency is descriptive and cache/host-dependent; no default or Gate promotion occurred.",
        ],
    }


def build_notebook(result):
    import nbformat
    from nbclient import NotebookClient

    hashes = {label: sha(ROOT / path) for label, path in REPORTS.items()}
    helpers = {
        name: sha(ROOT / "tools" / name)
        for name in (
            "review_tool_presence.py",
            "review_tool_default_semantics.py",
        )
    }
    fresh = next(e for e in result["experiments"] if e["label"] == "fresh_v3")
    headline = "; ".join(
        f"{r['variant']}: exact {r['exact']}/{r['n']}, default-equivalent {r['equivalent']}/{r['n']}"
        for r in fresh["summary"]
    )
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                "# Explicit Optional-Argument Presence\n\n## tl;dr\n\nFresh cohort: "
                + headline
                + ".\n\nThe failed prompt-only v2 experiment remains part of the evidence. No default or Gate promotion."
            ),
            nbformat.v4.new_markdown_cell(
                "## Context & Methods\n\nThe known high-priority omission is a development regression. "
                "V2 changes the optional-field prompt only. V3 requires every optional field in a separate "
                "wire schema, using model-generated null to mean omit. Supplied values are copied unchanged.\n\n"
                "### Key Assumptions\n\nFour development requests and fourteen locally authored fresh requests, "
                "two catalog orders, two seeds, and three variants per run. The fresh cohort compares baseline, "
                "v1 and v3 only, after v2 failed on development. Cases are not independently reviewed. "
                "Trials/orders repeat the same requests. No production semantic guarantee or latency SLA is claimed."
            ),
            nbformat.v4.new_markdown_cell(
                "## Data\n\n### 1. Verify Inputs and Recompute\n\nThe old v2 runner is preserved as a "
                "hash-addressed source snapshot. The audit reads source bytes but never executes snapshots. "
                "Model inference is not repeated by this notebook."
            ),
            nbformat.v4.new_code_cell(
                "import hashlib, json, sys\nfrom pathlib import Path\nroot = Path.cwd()\n"
                "while not (root / 'reference_workload/runtime_matrix.json').exists():\n"
                "    assert root != root.parent\n    root = root.parent\n"
                f"paths = {REPORTS!r}\nhashes = {hashes!r}\nhelpers = {helpers!r}\n"
                "for label, path in paths.items():\n"
                "    assert hashlib.sha256((root / path).read_bytes()).hexdigest() == hashes[label]\n"
                "for name, expected in helpers.items():\n"
                "    assert hashlib.sha256((root / 'tools' / name).read_bytes()).hexdigest() == expected\n"
                "sys.path.insert(0, str(root / 'tools'))\nfrom review_tool_presence import audit\n"
                "result = audit(root)\nprint(result['assessment'])"
            ),
            nbformat.v4.new_markdown_cell(
                "## Results\n\n### 2. Development and Fresh Results\n\nExact and default-equivalent "
                "criteria are unchanged. Token totals require complete captured HTTP usage. Median wall time is descriptive."
            ),
            nbformat.v4.new_code_cell(
                "from IPython.display import Markdown, display\n"
                "headers = ['cohort', 'variant', 'n', 'selection', 'exact', 'equivalent', 'total_tokens', 'median_ms']\n"
                "table = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']\n"
                "for experiment in result['experiments']:\n"
                "    for row in experiment['summary']:\n"
                "        values = [experiment['label'], row['variant'], row['n'], row['selection'], row['exact'], "
                "row['equivalent'], row['total_tokens'], round(row['median_latency_ms'], 1)]\n"
                "        table.append('| ' + ' | '.join(map(str, values)) + ' |')\n"
                "display(Markdown('\\n'.join(table)))"
            ),
            nbformat.v4.new_markdown_cell(
                "### 3. Priority-Specific Checks\n\nFresh priority rows each represent two authored requests "
                "in two orders and two seeds, not eight independent requests."
            ),
            nbformat.v4.new_code_cell(
                "fresh = next(e for e in result['experiments'] if e['label'] == 'fresh_v3')\n"
                "print(json.dumps([r for r in fresh['strata'] if r['stratum'].startswith('ticket_')], indent=2))"
            ),
            nbformat.v4.new_markdown_cell(
                "### 4. Protocol Fidelity and Remaining Errors\n\nNull omissions are model decisions. "
                "Exact values of all included fields must match the original wire response."
            ),
            nbformat.v4.new_code_cell(
                "for experiment in result['experiments']:\n"
                "    print(experiment['label'], {k: experiment[k] for k in (\n"
                "        'observations', 'http_calls', 'replay_traces', 'required_only_stage2_body_matches',\n"
                "        'model_null_omission_count', 'finish_reasons')})\n"
                "print('Fresh non-equivalent observations:', len(fresh['non_equivalent_rows']))"
            ),
            nbformat.v4.new_markdown_cell(
                "## Takeaways\n\nKeep development and fresh conclusions separate. Null improves the explicitness "
                "of a model's decision but does not make that decision infallible. A wrong null can still lose "
                "a user requirement. Real Tool content, authorization, independent review and runtime intent "
                "validation remain outside this diagnostic. Historical evidence and strict scores are unchanged."
            ),
            nbformat.v4.new_code_cell(
                f"target = root / {DESTINATION!r} / 'audit.json'\n"
                "target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\\n', encoding='utf-8')\n"
                "print('Audit saved')"
            ),
        ],
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            }
        },
    )
    nbformat.validate(notebook)
    NotebookClient(
        notebook, timeout=120, resources={"metadata": {"path": str(ROOT)}}
    ).execute()
    nbformat.write(notebook, ROOT / DESTINATION / "reproduce.ipynb")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", action="store_true")
    args = parser.parse_args()
    result = audit()
    target = ROOT / DESTINATION
    target.mkdir(parents=True, exist_ok=True)
    (target / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.notebook:
        build_notebook(result)
    print(
        json.dumps(
            {
                "assessment": result["assessment"],
                "experiments": [
                    {
                        k: v
                        for k, v in experiment.items()
                        if k
                        not in {
                            "source_paths_verified",
                            "non_equivalent_rows",
                            "strata",
                        }
                    }
                    for experiment in result["experiments"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
