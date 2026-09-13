"""Freeze exact/default-equivalence criteria, then compare unchanged adapters on fresh requests."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path

from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root
from app.reference_workload.runtime_matrix import (
    load_runtime_matrix,
    probe_runtime,
    resolve_runtime_entry,
)
from app.reference_workload.tool_argument_equivalence import (
    compare_argument_contract,
    validate_default_policy,
)
from app.reference_workload.tool_fault_baseline import _sha256, summarize_rows
from app.reference_workload.tool_fault_cases import FaultBaselineCase, load_baseline_pack
from app.reference_workload.tool_two_stage_diagnostic import (
    configuration_for,
    observe,
    verify_baseline,
)
from app.services.tool_execution import build_fault_tool_registry

PREVIOUS_PATH = "artifacts/reference-workload/tool-two-stage-diagnostic-v1.json"
PREVIOUS_SHA256 = "f122e1e6cb38c349b00d8d35769f279a21786a16139f1ab4834eff36558f0ca8"
CASES_PATH = "reference_workload/diagnostics/tool-default-semantics-v1.json"
NEW_SOURCES = (
    "reference_workload/tool_argument_equivalence.py",
    "reference_workload/tool_default_semantics_diagnostic.py",
)


def case_stratum(item) -> str:
    if item.expected_tool != "create_ticket":
        return item.expected_tool
    priority = item.expected_arguments.get("priority")
    return "ticket_omitted_default" if priority is None else f"ticket_explicit_{priority}"


def attach_comparison(row, item, registry, context):
    comparison = compare_argument_contract(row.get("normalized_output"), item, registry, context)
    if "selection_and_arguments_exact" in row:
        if comparison["exact_call"] != row["selection_and_arguments_exact"]:
            raise ValueError("exact criterion disagrees with the frozen scorer")
    if "metadata" in row and comparison["guard"] != row["metadata"]["tool_call_contract"]:
        raise ValueError("equivalence guard disagrees with the captured adapter guard")
    return {**row, "argument_comparison": comparison, "stratum": case_stratum(item)}


def summary(rows):
    return {
        **summarize_rows(rows),
        "exact_call": sum(r["argument_comparison"]["exact_call"] for r in rows),
        "default_equivalent_call": sum(
            r["argument_comparison"]["default_equivalent_call"] for r in rows
        ),
        "default_only_difference": sum(
            r["argument_comparison"]["default_only_difference"] for r in rows
        ),
        "reason_counts": dict(Counter(r["argument_comparison"]["reason"] for r in rows)),
    }


def historical_addendum(previous, registry, context):
    cases = {
        (cohort, case["id"]): FaultBaselineCase.model_validate(case)
        for cohort, pack in previous["packs"].items()
        for case in pack["cases"]
    }
    rows = []
    for original in previous["rows"]:
        scored = attach_comparison(
            original, cases[original["cohort"], original["id"]], registry, context
        )
        rows.append(
            {
                **{
                    key: original[key]
                    for key in ("entry", "cohort", "variant", "id", "trial", "tool_order")
                },
                "argument_comparison": scored["argument_comparison"],
            }
        )
    return {
        "scope": "separate_posthoc_scoring_addendum_not_new_model_evidence",
        "model_inference_performed": False,
        "original_artifact_modified": False,
        "human_reviewed": False,
        "gate_evidence": False,
        "rows": rows,
    }


def load_previous(root):
    verify_baseline(root)
    path = root / PREVIOUS_PATH
    if _sha256(path) != PREVIOUS_SHA256:
        raise ValueError("previous two-stage evidence hash changed")
    previous = json.loads(path.read_text("utf-8"))
    for name, expected in previous["source_sha256"].items():
        if _sha256(root / "backend/app" / name) != expected:
            raise ValueError(f"frozen implementation changed: {name}")
    if _sha256(path.with_suffix(".observations.jsonl")) != previous["journal_sha256"]:
        raise ValueError("previous observation journal changed")
    return previous


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    journal_path = args.output.with_suffix(".observations.jsonl")
    if args.output.exists() or journal_path.exists():
        parser.error("output or observation journal already exists; use a new evidence path")
    root = args.repository_root
    previous = load_previous(root)
    corpus = build_reference_corpus(
        root / "reference_workload/revisions/1.0.4/manifest.json", repository_root=root
    ).corpus
    context = {
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_hash": corpus.corpus_hash,
        "document_ids": sorted({chunk.document_id for chunk in corpus.chunks}),
    }
    registry = build_fault_tool_registry()
    policy = validate_default_policy(registry)
    pack = load_baseline_pack(root / CASES_PATH, registry, context)
    old_requests = {c["request"] for p in previous["packs"].values() for c in p["cases"]}
    if any(case.request in old_requests for case in pack.cases):
        raise ValueError("new request pack overlaps the previous requests")
    matrix = load_runtime_matrix(root / "reference_workload/runtime_matrix.json")
    entry = next(e for e in matrix.entries if e.name == "medium-candidate" and e.enabled)
    environment = {
        "REFERENCE_RUNTIME_BASE_URL": args.base_url,
        "REFERENCE_MODEL_MEDIUM": "qwen2.5:1.5b",
    }
    resolved = resolve_runtime_entry(entry, environment=environment)
    runtime = probe_runtime(resolved, environment=environment).model_dump()
    if runtime != next(e["runtime"] for e in previous["entries"] if e["name"] == entry.name):
        raise ValueError("runtime identity changed")
    config = configuration_for(entry, resolved, context)
    report = {
        "schema_version": "tool-default-semantics-diagnostic-v1",
        "status": "running",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "human_reviewed": False,
        "gate_evidence": False,
        "database_writes_performed": False,
        "production_readiness": "not_production_ready",
        "previous_path": PREVIOUS_PATH,
        "previous_sha256": PREVIOUS_SHA256,
        "policy": policy,
        "case_pack": pack.model_dump(mode="json"),
        "case_pack_path": CASES_PATH,
        "case_pack_sha256": _sha256(root / CASES_PATH),
        "document_context": context,
        "runtime": runtime,
        "matrix_entry": entry.model_dump(),
        "runtime_config": config.runtime_config_json,
        "generation_config": config.generation_config_json,
        "source_sha256": {
            **previous["source_sha256"],
            **{name: _sha256(root / "backend/app" / name) for name in NEW_SOURCES},
        },
        "protocol": {
            "concurrency": 1,
            "adapters_and_prompts_unchanged": True,
            "labels_and_comparison_policy_available_to_adapter": False,
            "case_pack_and_policy_frozen_before_inference": True,
            "design": "paired baseline/candidate; alternating AB/BA; registered/reversed catalogs",
            "seeds": [41 + trial for trial in range(1, entry.trials + 1)],
            "expected_observations": len(pack.cases) * 2 * entry.trials * 2,
            "strata_case_counts": dict(Counter(case_stratum(item) for item in pack.cases)),
            "sampling_limit": (
                "new locally authored requests, not an independent human-reviewed holdout"
            ),
            "comparison_scope": (
                "optional priority default only; no fuzzy text or output equivalence"
            ),
        },
        "historical_addendum": historical_addendum(previous, registry, context),
        "rows": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    with journal_path.open("x", encoding="utf-8") as journal:
        for index, item in enumerate(pack.cases):
            for order_index, order in enumerate(("registered", "reversed")):
                for trial in range(1, entry.trials + 1):
                    variants = (
                        ("baseline", "candidate")
                        if (index + order_index + trial) % 2
                        else ("candidate", "baseline")
                    )
                    for variant in variants:
                        row = observe(
                            item,
                            config,
                            registry,
                            context,
                            variant=variant,
                            seed=41 + trial,
                            tool_order=order,
                        )
                        row.update(trial=trial, pair_execution_order=list(variants))
                        try:
                            row = attach_comparison(row, item, registry, context)
                        except Exception as exc:
                            row["comparison_error"] = {
                                "type": type(exc).__name__,
                                "message": str(exc),
                            }
                            raise
                        finally:
                            report["rows"].append(row)
                            journal.write(json.dumps(row, ensure_ascii=False) + "\n")
                            journal.flush()
                        print(
                            json.dumps(
                                {
                                    "id": item.id,
                                    "variant": variant,
                                    "order": order,
                                    "trial": trial,
                                    "reason": row["argument_comparison"]["reason"],
                                    "error": row.get("error"),
                                }
                            ),
                            flush=True,
                        )
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    report["summaries"] = {
        variant: summary([row for row in report["rows"] if row["variant"] == variant])
        for variant in ("baseline", "candidate")
    }
    errors = sum("error" in row for row in report["rows"])
    report["status"] = "complete_with_errors" if errors else "complete"
    report["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["journal_sha256"] = _sha256(journal_path)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "sha256": _sha256(args.output)}), flush=True)
    return int(errors > 0)


if __name__ == "__main__":
    raise SystemExit(main())
