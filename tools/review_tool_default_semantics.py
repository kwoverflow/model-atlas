"""Independently recompute exact/default-only comparisons and optionally execute a review notebook."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "artifacts/reference-workload/tool-default-semantics-diagnostic-v1.json"
DESTINATION = "docs/reports/2026-09-09_tool_default_semantics"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def recompute(output, case):
    try:
        parsed = json.loads(output or "")
    except ValueError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    arguments = parsed.get("arguments")
    selected = parsed.get("tool_name") == case["expected_tool"]
    exact = selected and arguments == case["expected_arguments"]
    equivalent = False
    if selected and isinstance(arguments, dict):
        defaults = (
            {"priority": "normal"} if case["expected_tool"] == "create_ticket" else {}
        )
        equivalent = {**defaults, **arguments} == {
            **defaults,
            **case["expected_arguments"],
        }
    return {
        "selection": selected,
        "exact": exact,
        "equivalent": equivalent,
        "default_only": equivalent and not exact,
    }


def check_comparison(output, case, comparison):
    independent = recompute(output, case)
    assert comparison["exact_call"] == independent["exact"]
    assert comparison["default_equivalent_call"] == independent["equivalent"]
    assert comparison["default_only_difference"] == independent["default_only"]
    assert (
        comparison["applied_to_execution"] is False
        and comparison["comparison_only"] is True
    )
    if independent["equivalent"]:
        assert comparison["execution_eligible"]
    return independent


def audit(root=ROOT):
    path = root / SOURCE
    report = json.loads(path.read_text("utf-8"))
    assert report["status"] == "complete", (
        "partial/error runs require explicit separate review"
    )
    assert not report["human_reviewed"] and not report["gate_evidence"]
    assert not report["database_writes_performed"]
    for name, expected in report["source_sha256"].items():
        assert sha(root / "backend/app" / name) == expected, name
    assert sha(root / report["case_pack_path"]) == report["case_pack_sha256"]
    assert (
        json.loads((root / report["case_pack_path"]).read_text("utf-8"))
        == report["case_pack"]
    )
    assert report["policy"]["defaults"] == {"create_ticket": {"priority": "normal"}}
    assert report["policy"]["scope"] == "local_registered_optional_defaults_only"
    assert not report["policy"]["applied_to_execution"]
    journal = path.with_suffix(".observations.jsonl")
    assert sha(journal) == report["journal_sha256"]
    rows = report["rows"]
    assert [
        json.loads(line) for line in journal.read_text("utf-8").splitlines()
    ] == rows
    cases = {case["id"]: case for case in report["case_pack"]["cases"]}
    keys = {(r["id"], r["trial"], r["tool_order"], r["variant"]) for r in rows}
    expected_keys = {
        (case_id, trial, order, variant)
        for case_id in cases
        for trial in range(1, report["matrix_entry"]["trials"] + 1)
        for order in ("registered", "reversed")
        for variant in ("baseline", "candidate")
    }
    assert (
        keys == expected_keys
        and len(keys) == len(rows) == report["protocol"]["expected_observations"]
    )
    groups = defaultdict(list)
    strata = defaultdict(Counter)
    pairs = defaultdict(dict)
    failures = []
    default_only_rows = []
    finish = Counter()
    transitions = Counter()
    for row in rows:
        assert "error" not in row and "comparison_error" not in row
        case = cases[row["id"]]
        score = check_comparison(
            row["normalized_output"], case, row["argument_comparison"]
        )
        assert score["exact"] == row["selection_and_arguments_exact"]
        assert score["selection"] == row["selection_correct"]
        requests = row["requests"]
        assert len(requests) == (2 if row["variant"] == "candidate" else 1)
        for request in requests:
            assert digest(request["body"]) == request["request_hash"]
            assert "local-tool-default-equivalence" not in json.dumps(request["body"])
            for choice in request["response"]["choices"]:
                finish[choice.get("finish_reason")] += 1
        assert row["http_usage_complete"]
        measured = {
            key: sum(r["response"]["usage"][key] for r in requests)
            for key in ("prompt_tokens", "completion_tokens")
        }
        assert measured == row["measured_tokens"]
        actual = json.loads(row["normalized_output"])
        for trace in row["traces"].values():
            for step in trace["steps"]:
                assert step["arguments"] == actual["arguments"]
            if not row["argument_comparison"]["execution_eligible"]:
                assert trace["fault_scenario"]["handler_invocation_count"] == 0
        if row["variant"] == "candidate":
            generation = row["metadata"]["tool_argument_generation"]
            assert actual["tool_name"] == generation["selected_tool"]
            assert actual["arguments"] == json.loads(
                generation["second_stage"]["raw_output"]
            )
            first = recompute(generation["first_stage"]["normalized_output"], case)
            transitions[f"exact:{int(first['exact'])}->{int(score['exact'])}"] += 1
            transitions[
                f"equivalent:{int(first['equivalent'])}->{int(score['equivalent'])}"
            ] += 1
        groups[row["variant"]].append(
            {**score, **measured, "latency_ms": row["latency_ms"]}
        )
        strata[row["variant"], row["stratum"]].update(
            n=1, exact=int(score["exact"]), equivalent=int(score["equivalent"])
        )
        pairs[row["id"], row["trial"], row["tool_order"]][row["variant"]] = row
        compact = {key: row[key] for key in ("id", "variant", "trial", "tool_order")}
        compact.update(
            actual=actual,
            expected=case["expected_arguments"],
            reason=row["argument_comparison"]["reason"],
        )
        if score["default_only"]:
            default_only_rows.append(compact)
        if not score["equivalent"]:
            failures.append(compact)
    for pair in pairs.values():
        assert (
            pair["baseline"]["requests"][0]["body"]
            == pair["candidate"]["requests"][0]["body"]
        )
    summary = []
    for variant, values in groups.items():
        result = {
            "variant": variant,
            "n": len(values),
            **{
                metric: sum(v[metric] for v in values)
                for metric in (
                    "selection",
                    "exact",
                    "equivalent",
                    "default_only",
                    "prompt_tokens",
                    "completion_tokens",
                )
            },
            "median_latency_ms": statistics.median(v["latency_ms"] for v in values),
        }
        captured = report["summaries"][variant]
        assert result["exact"] == captured["exact_call"]
        assert result["equivalent"] == captured["default_equivalent_call"]
        assert result["default_only"] == captured["default_only_difference"]
        summary.append(result)
    previous_path = root / report["previous_path"]
    assert sha(previous_path) == report["previous_sha256"]
    previous = json.loads(previous_path.read_text("utf-8"))
    assert (
        sha(previous_path.with_suffix(".observations.jsonl"))
        == previous["journal_sha256"]
    )
    old_cases = {
        (cohort, c["id"]): c
        for cohort, pack in previous["packs"].items()
        for c in pack["cases"]
    }
    key_fields = ("entry", "cohort", "variant", "id", "trial", "tool_order")
    old_rows = {tuple(row[key] for key in key_fields): row for row in previous["rows"]}
    addendum = report["historical_addendum"]
    assert (
        not addendum["model_inference_performed"]
        and not addendum["original_artifact_modified"]
    )
    assert len(addendum["rows"]) == len(old_rows)
    assert {tuple(row[key] for key in key_fields) for row in addendum["rows"]} == set(
        old_rows
    )
    historical = defaultdict(Counter)
    for row in addendum["rows"]:
        original = old_rows[tuple(row[key] for key in key_fields)]
        score = check_comparison(
            original["normalized_output"],
            old_cases[row["cohort"], row["id"]],
            row["argument_comparison"],
        )
        historical[row["entry"], row["cohort"], row["variant"]].update(
            n=1, exact=int(score["exact"]), equivalent=int(score["equivalent"])
        )
    return {
        "assessment": "share_with_caveats_local_default_equivalence_only",
        "source_sha256": sha(path),
        "previous_sha256": sha(previous_path),
        "started_at": report["started_at"],
        "completed_at": report["completed_at"],
        "observations": len(rows),
        "http_calls": sum(len(r["requests"]) for r in rows),
        "fault_replay_traces": sum(len(r["traces"]) for r in rows),
        "summary": summary,
        "strata": [{"variant": k[0], "stratum": k[1], **v} for k, v in strata.items()],
        "historical_addendum_summary": [
            {"entry": k[0], "cohort": k[1], "variant": k[2], **v}
            for k, v in historical.items()
        ],
        "within_candidate_transitions": dict(transitions),
        "paired_stage1_selection_changes": sum(
            pair["baseline"]["stage1_selected_tool"]
            != pair["candidate"]["stage1_selected_tool"]
            for pair in pairs.values()
        ),
        "finish_reasons": dict(finish),
        "default_only_rows": default_only_rows,
        "non_equivalent_rows": failures,
        "caveats": [
            "Only omitted create_ticket.priority versus explicit normal is treated as equivalent.",
            "Exact fidelity is retained separately; model outputs and execution arguments are never repaired.",
            "Fresh requests are locally authored and unreviewed, not an independent holdout.",
            "Orders and zero-temperature trials repeat 14 authored cases; observations are not independent.",
            "Historical additive rescoring is post hoc, not new model evidence or a replacement score.",
            "Local fixture equivalence says nothing about real external content, authorization, or general semantics.",
            "Latency includes uncontrolled cache, request order and host effects; not an SLA estimate.",
        ],
    }


def build_notebook(result):
    import nbformat
    from nbclient import NotebookClient

    summary = "; ".join(
        f"{r['variant']}: exact {r['exact']}/{r['n']}, default-equivalent {r['equivalent']}/{r['n']}"
        for r in result["summary"]
    )
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_markdown_cell(
                "# Exact Fidelity and Local Default Equivalence\n\n## tl;dr\n\n"
                + summary
                + ".\n\nDiagnostic only; defaults and the official Gate remain unchanged."
            ),
            nbformat.v4.new_markdown_cell(
                "## Context & Methods\n\n14 new local requests, two catalog orders, two trials, two unchanged adapters. "
                "Only the 1.5B/v1 setting is evaluated. Exact matching and default-equivalence were frozen before inference.\n\n"
                "### Key Assumptions\n\nThe only allowed equivalence is optional priority omission versus normal in the "
                "pinned local ticket handler. No query translation, fuzzy matching, field removal or output-based matching. "
                "Source cases are not independently reviewed. Repeated orders/trials are not independent samples. "
                "Historical rescoring is a separate post-hoc addendum, not overwritten evidence."
            ),
            nbformat.v4.new_markdown_cell(
                "## Data\n\n### 1. Validate Sources and Recompute\n\nSource: `"
                + SOURCE
                + "`. The independent audit imports no application scoring code and does not run models."
            ),
            nbformat.v4.new_code_cell(
                "import hashlib, json, sys\nfrom pathlib import Path\nroot = Path.cwd()\n"
                "while not (root / 'reference_workload/runtime_matrix.json').exists():\n"
                "    assert root != root.parent\n    root = root.parent\n"
                f"assert hashlib.sha256((root / {SOURCE!r}).read_bytes()).hexdigest() == {result['source_sha256']!r}\n"
                f"assert hashlib.sha256((root / 'tools/review_tool_default_semantics.py').read_bytes()).hexdigest() == {sha(Path(__file__))!r}\n"
                "sys.path.insert(0, str(root / 'tools'))\nfrom review_tool_default_semantics import audit\n"
                "result = audit(root)\nprint({k: result[k] for k in ('assessment', 'observations', 'http_calls', 'fault_replay_traces')})"
            ),
            nbformat.v4.new_markdown_cell(
                "## Results\n\n### 2. Fresh Requests, Accuracy and Costs\n\n"
                "Token values are measured HTTP totals. Local median latency is descriptive, not an SLA."
            ),
            nbformat.v4.new_code_cell(
                "print(json.dumps(result['summary'], indent=2))\n"
                "print(json.dumps(result['within_candidate_transitions'], indent=2))"
            ),
            nbformat.v4.new_markdown_cell(
                "### 3. Explicit and Omitted Priorities\n\n"
                "Keep default-only differences visible alongside strict mismatches."
            ),
            nbformat.v4.new_code_cell(
                "print(json.dumps([r for r in result['strata'] if r['stratum'].startswith('ticket_')], indent=2))"
            ),
            nbformat.v4.new_markdown_cell(
                "### 4. Historical Addendum\n\nNo original metric is overwritten."
            ),
            nbformat.v4.new_code_cell(
                "print(json.dumps(result['historical_addendum_summary'], indent=2))"
            ),
            nbformat.v4.new_markdown_cell(
                "## Takeaways\n\nDefault equivalence avoids conflating an omitted default with a "
                "different execution value; it does not certify general semantic correctness. "
                "Real content, authorization and independent review remain future work. "
                "Do not promote the candidate automatically or hide exact-fidelity regressions."
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
                k: v
                for k, v in result.items()
                if k not in {"default_only_rows", "non_equivalent_rows"}
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
