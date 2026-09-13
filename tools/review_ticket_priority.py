"""Independent evidence audit for the diagnostic priority veto, including failed transport setup."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from review_tool_default_semantics import check_comparison, digest, sha
from review_tool_presence import audit as audit_previous

ROOT = Path(__file__).resolve().parents[1]
DEST = "docs/reports/2026-09-09_ticket_priority"
REPORTS = {
    "incompatible_schema_v1": "artifacts/reference-workload/ticket-priority-development-v1.json",
    "development_v1_1": "artifacts/reference-workload/ticket-priority-development-v1-1.json",
    "fresh_v1_1": "artifacts/reference-workload/ticket-priority-fresh-v1-1.json",
}


def independent_reason(raw, request, arguments):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result
            result[key] = value
        return result

    intent = json.loads(raw, object_pairs_hook=unique)
    assert set(intent) == {"action", "value", "evidence"}
    action, value, evidence = (intent[k] for k in ("action", "value", "evidence"))
    assert action in {"set", "omit", "unspecified", "clarify"}
    assert value in {"low", "normal", "high", "none"}
    assert isinstance(evidence, str) and len(evidence) <= 2000
    assert (action == "set") == (value != "none")
    assert evidence == "" if action == "unspecified" else bool(evidence.strip())
    assert evidence in request
    assert action != "set" or value in evidence
    if action == "clarify":
        reason = "priority_intent_requires_clarification"
    elif action == "set":
        reason = (
            None if arguments.get("priority") == value else "explicit_priority_mismatch"
        )
    else:
        reason = "priority_should_be_absent" if "priority" in arguments else None
    return intent, reason


def audit_one(label, relative, root=ROOT):
    path = root / relative
    report = json.loads(path.read_text("utf-8"))
    assert report["status"] in {"complete", "complete_with_errors"}
    assert not any(
        report[k]
        for k in ("human_reviewed", "gate_evidence", "database_writes_performed")
    )
    for name, expected in report["source_sha256"].items():
        source = root / "backend/app" / name
        source.resolve().relative_to((root / "backend/app").resolve())
        if sha(source) != expected:
            assert name == "services/ticket_priority_verification.py"
            assert (
                expected
                == "4e049337c7434bc6a7fdc51dc50145573851ca2af79d6df5ba65cda361c45422"
            )
            source = (
                root
                / "reference_workload/diagnostics/source_snapshots/ticket_priority_verification"
                / (expected + ".py")
            )
        assert sha(source) == expected
    assert sha(root / report["previous_path"]) == report["previous_sha256"]
    previous = json.loads((root / report["previous_path"]).read_text("utf-8"))
    assert report["runtime"] == previous["runtime"]
    assert sha(root / report["case_pack_path"]) == report["case_pack_sha256"]
    pack = json.loads((root / report["case_pack_path"]).read_text("utf-8"))
    cases = {c["id"]: c for c in report["cases"]}
    assert list(cases.values()) == [
        c for c in pack["cases"] if c["cohort"] == report["cohort"]
    ]
    journal = path.with_suffix(".observations.jsonl")
    assert sha(journal) == report["journal_sha256"]
    rows = report["rows"]
    assert [
        json.loads(line) for line in journal.read_text("utf-8").splitlines()
    ] == rows
    keys = {(r["id"], r["seed"], r["tool_order"]) for r in rows}
    assert keys == {
        (c, s, o) for c in cases for s in (42, 43) for o in ("registered", "reversed")
    }
    assert len(keys) == len(rows) == report["protocol"]["expected_observations"]
    assert report["summary"]["observations"] == len(rows)
    assert report["summary"]["actionable"] == sum(
        cases[r["id"]]["expected_action"] == "execute" for r in rows
    )
    assert report["summary"]["clarification_required"] == sum(
        cases[r["id"]]["expected_action"] == "clarify" for r in rows
    )
    assert report["summary"]["errors"] == sum("error" in r for r in rows)
    assert report["summary"]["verification_failures"] == sum(
        r.get("verification", {}).get("status") == "failed" for r in rows
    )
    counts = {v: Counter() for v in ("v3", "v3_verified")}
    strata = defaultdict(Counter)
    finishes, decisions = Counter(), Counter()
    tokens = {"proposal": 0, "verification": 0}
    usage_complete = {"proposal": True, "verification": True}
    http_calls = http_errors = 0
    failures = []
    for row in rows:
        case = cases[row["id"]]
        for prefix in tokens:
            requests = row[prefix + "_requests"]
            assert len(requests) <= (2 if prefix == "proposal" else 1)
            http_calls += len(requests)
            known_usage = []
            for request in requests:
                assert digest(request["body"]) == request["request_hash"]
                if "error" in request:
                    http_errors += 1
                response = request.get("response", {})
                if "usage" in response:
                    known_usage.append(response["usage"])
                for choice in response.get("choices", []):
                    finishes[choice.get("finish_reason")] += 1
            measured = row[prefix + "_tokens"]
            if measured is None:
                usage_complete[prefix] = False
            else:
                assert len(known_usage) == len(requests)
                assert measured == {
                    k: sum(u[k] for u in known_usage)
                    for k in ("prompt_tokens", "completion_tokens")
                }
                tokens[prefix] += sum(measured.values())
        if "error" in row:
            continue
        check = row["verification"]
        proposal = json.loads(row["proposal"])
        arguments = proposal["arguments"]
        assert (
            check["proposal_sha256"]
            == hashlib.sha256(row["proposal"].encode()).hexdigest()
        )
        assert not any(
            check[k]
            for k in (
                "argument_repair",
                "uses_expected_labels",
                "proposal_sent_to_classifier",
            )
        )
        generation = row["metadata"]["tool_argument_generation"]
        if generation["status"] == "generated":
            wire = json.loads(generation["second_stage"]["raw_output"])
            assert (
                generation["second_stage"]["raw_output"]
                == row["proposal_requests"][1]["response"]["choices"][0]["message"][
                    "content"
                ]
            )
            omitted = generation.get("presence_decoding", {}).get(
                "omitted_optional_fields", []
            )
            assert all(wire[k] is None for k in omitted)
            assert arguments == {k: v for k, v in wire.items() if k not in omitted}
        if row["verification_requests"]:
            request = row["verification_requests"][0]
            payload = json.loads(request["body"]["messages"][1]["content"])
            assert payload["request"] == case["request"]
            assert set(payload) == {"request", "instruction", "selected_tool"}
            assert payload["selected_tool"]["tool_name"] == "create_ticket"
            assert check["raw_output"] == request.get("response", {}).get(
                "choices", [{}]
            )[0].get("message", {}).get("content")
        if check["status"] == "checked":
            intent, reason = independent_reason(
                check["raw_output"], case["request"], arguments
            )
            assert intent == check["intent"] and reason == check["reason"]
            assert check["execution_allowed"] == (reason is None)
            assert check["finish_reason"] == "stop"
        elif check["status"] == "out_of_scope":
            assert (
                proposal["tool_name"] != "create_ticket" and check["execution_allowed"]
            )
        else:
            assert not check["execution_allowed"]
        comparison = (
            check_comparison(row["proposal"], case, row["comparison"])
            if case["expected_action"] == "execute"
            else {"exact": False, "equivalent": False}
        )
        decisions[check["reason"] or "allowed"] += 1
        base_allowed = row["public_guard"]["execution_allowed"]
        predicted = check["intent"]["action"] if check["intent"] else check["status"]
        for variant in counts:
            allowed = base_allowed and (variant == "v3" or check["execution_allowed"])
            values = {
                "accepted": int(allowed),
                "exact_completed": int(allowed and comparison["exact"]),
                "equivalent_completed": int(allowed and comparison["equivalent"]),
                "unsafe_accepted": int(allowed and not comparison["equivalent"]),
                "clarification_blocked": int(
                    case["expected_action"] == "clarify" and not allowed
                ),
                "correct_proposal_blocked": int(
                    base_allowed and comparison["exact"] and not allowed
                ),
                "wrong_proposal_blocked": int(
                    base_allowed and not comparison["equivalent"] and not allowed
                ),
                "intent_classification_correct": int(
                    variant == "v3_verified"
                    and predicted == case["expected_intent"]
                    and (
                        predicted != "set"
                        or check["intent"]["value"]
                        == case["expected_arguments"]["priority"]
                    )
                ),
            }
            counts[variant].update(values)
            strata[variant, case["stratum"]].update(n=1, **values)
            for mode, trace in row["traces"][variant].items():
                for step in trace["steps"]:
                    assert step["arguments"] == arguments
                    assert step["expected_tool_name"] == proposal["tool_name"]
                if not allowed:
                    assert trace["fault_scenario"]["handler_invocation_count"] == 0
                    assert trace["fault_scenario"]["injected_failure_count"] == 0
                elif mode == "normal":
                    assert trace["fault_scenario"]["handler_invocation_count"] == 1
            if variant == "v3_verified" and (
                values["unsafe_accepted"] or values["correct_proposal_blocked"]
            ):
                failures.append(
                    {
                        "id": row["id"],
                        "seed": row["seed"],
                        "order": row["tool_order"],
                        "reason": check["reason"],
                        "intent": check["intent"],
                        "proposal": proposal,
                        "unsafe_accepted": bool(values["unsafe_accepted"]),
                        "correct_proposal_blocked": bool(
                            values["correct_proposal_blocked"]
                        ),
                    }
                )
    for variant in counts:
        assert dict(counts[variant]) == report["summary"][variant]
    return {
        "label": label,
        "sha256": sha(path),
        "observations": len(rows),
        "summary": report["summary"],
        "http_calls": http_calls,
        "http_errors": http_errors,
        "finish_reasons": dict(finishes),
        "decisions": dict(decisions),
        "measured_tokens": {
            k: tokens[k] if usage_complete[k] else None for k in tokens
        },
        "known_token_subtotals": tokens,
        "median_proposal_ms": statistics.median(
            r["proposal_latency_ms"] for r in rows if "proposal_latency_ms" in r
        ),
        "median_verified_ms": statistics.median(
            r["proposal_latency_ms"] + r["verification"]["latency_ms"]
            for r in rows
            if "proposal_latency_ms" in r
        ),
        "strata": [{"variant": v, "stratum": s, **c} for (v, s), c in strata.items()],
        "residual_failures": failures,
    }


def audit(root=ROOT):
    audit_previous(root)
    return {
        "assessment": "diagnostic_only_with_false_block_and_false_allow_caveats",
        "experiments": [
            audit_one(label, path, root) for label, path in REPORTS.items()
        ],
    }


def notebook(result):
    import nbformat
    from nbclient import NotebookClient

    pins = {
        p: sha(ROOT / p)
        for p in (
            *REPORTS.values(),
            "tools/review_ticket_priority.py",
            "tools/review_tool_presence.py",
            "tools/review_tool_default_semantics.py",
        )
    }
    fresh = result["experiments"][-1]
    summary = fresh["summary"]
    base, candidate = summary["v3"], summary["v3_verified"]
    cells = [
        nbformat.v4.new_markdown_cell(
            f"# Ticket Priority Verification\n\n## tl;dr\n\nFresh cohort: unsafe accepted calls {base['unsafe_accepted']} -> {candidate['unsafe_accepted']}; exact task completions {base['exact_completed']} -> {candidate['exact_completed']}. The verifier blocks {candidate['correct_proposal_blocked']} previously exact proposals. This is an opt-in local diagnostic, not a production safety guarantee."
        ),
        nbformat.v4.new_markdown_cell(
            "## Context & Methods\n\nOne unchanged v3 proposal is replayed under two execution policies. A separate request-only model classification can veto, never repair, a call. Development and fresh cohorts are separate.\n\n### Key Assumptions\n\nCases are locally authored and not independently reviewed. Repeated orders/seeds are not independent requests. Literal evidence checks cannot prove semantic correctness. Correct execution and clarification are separate outcomes. Runtime schema failures are retained, not counted as model quality improvements."
        ),
        nbformat.v4.new_code_cell(
            f"from pathlib import Path\nimport hashlib, json, sys\nroot = Path.cwd()\npins = {pins!r}\nfor name, expected in pins.items():\n    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected, name\nsys.path.insert(0, str(root/'tools'))\nfrom review_ticket_priority import audit\nresult = audit(root)"
        ),
        nbformat.v4.new_markdown_cell(
            "## Data\n\n### 1. Source and Journal Checks\n\nThe audit verifies historical/source hashes, all paired condition keys, actual request/response usage, model-owned decisions and unchanged handler arguments. Actual fault fixtures bind to the proposed Tool, not private expected selection labels. Two manual transport probes used only a development request and are excluded from cohort denominators."
        ),
        nbformat.v4.new_code_cell(
            "for e in result['experiments']:\n    print(e['label'], e['observations'], 'pairs;', e['http_calls'], 'HTTP calls;', e['http_errors'], 'HTTP errors')"
        ),
        nbformat.v4.new_markdown_cell(
            "## Results\n\n### 2. Completion, Coverage and Safety Tradeoff\n\nUnsafe accepted means an accepted call that is not locally default-equivalent, or executes when clarification is required. A successful block is not a successful task completion."
        ),
        nbformat.v4.new_code_cell(
            "from IPython.display import Markdown, display\nlines=['| Cohort | Policy | Allowed | Exact completed | Unsafe allowed | Correct blocked | Clarification blocked |', '| --- | --- | ---: | ---: | ---: | ---: | ---: |']\nfor e in result['experiments']:\n    for policy in ('v3','v3_verified'):\n        c=e['summary'][policy]\n        values=[e['label'],policy]+[c[k] for k in ('accepted','exact_completed','unsafe_accepted','correct_proposal_blocked','clarification_blocked')]\n        lines.append('| '+' | '.join(map(str,values))+' |')\ndisplay(Markdown('\\n'.join(lines)))"
        ),
        nbformat.v4.new_markdown_cell(
            "### 3. Cost and Remaining Errors\n\nTiming is descriptive, not an SLA. Unknown HTTP usage is not converted to zero."
        ),
        nbformat.v4.new_code_cell(
            "for e in result['experiments']:\n    print(e['label'], e['measured_tokens'], e['decisions'])\nfresh=result['experiments'][-1]\nprint('Residual case IDs:', sorted({r['id'] for r in fresh['residual_failures']}))"
        ),
        nbformat.v4.new_markdown_cell(
            "## Takeaways\n\nKeep the candidate opt-in. Same-model interpretation can share generation errors; exact quotation is not proof of operative intent. Explicit structured user constraints and ambiguity confirmation remain possible next steps. Other Tool selection, query correctness, external content and authorization remain outside this priority-only veto. Official Gate and human reviews are unchanged."
        ),
    ]
    nb = nbformat.v4.new_notebook(
        cells=cells,
        metadata={
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            }
        },
    )
    nbformat.validate(nb)
    NotebookClient(
        nb, timeout=180, resources={"metadata": {"path": str(ROOT)}}
    ).execute()
    nbformat.write(nb, ROOT / DEST / "reproduce.ipynb")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", action="store_true")
    args = parser.parse_args()
    result = audit()
    target = ROOT / DEST
    target.mkdir(parents=True, exist_ok=True)
    (target / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.notebook:
        notebook(result)
    print(
        json.dumps(
            {
                "assessment": result["assessment"],
                "experiments": [
                    {
                        k: v
                        for k, v in e.items()
                        if k not in {"strata", "residual_failures"}
                    }
                    for e in result["experiments"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
