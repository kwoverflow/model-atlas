"""Audit saved v1 outputs against v2 without inference, tool execution, or DB writes."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.reference_workload.corpus import build_reference_corpus  # noqa: E402
from app.services.benchmark_execution import _available_tool_descriptors  # noqa: E402
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter  # noqa: E402
from app.services.tool_call_contract import (  # noqa: E402
    TOOL_CALL_CONTRACT_VERSION,
    compile_bounded_tool_call,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_saved_outputs(source: dict, *, document_context: dict) -> dict:
    if source.get("schema_version") != "tool-selection-challenge-result-v1":
        raise ValueError("unsupported saved diagnostic schema")
    entries = source.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("saved diagnostic has no entries")
    adapter = OpenAICompatibleAdapter()
    seen = set()
    rows = []
    counts = Counter()
    for entry in entries:
        if not isinstance(entry.get("rows"), list) or not entry["rows"]:
            raise ValueError("saved entry has no rows")
        for row in entry["rows"]:
            key = (entry["name"], row["id"], row["trial"])
            if key in seen:
                raise ValueError(f"duplicate observation: {key}")
            seen.add(key)
            for name in (
                "raw_selection_correct",
                "raw_arguments_valid",
                "normalized_arguments_valid",
                "normalized_execution_success",
            ):
                if type(row.get(name)) is not bool:
                    raise ValueError(f"missing/non-boolean metric {name}: {key}")
            old = row.get("metadata", {}).get("tool_call_contract", {})
            if old.get("compiler_version") != "bounded-tool-call-contract-v1":
                raise ValueError(f"observation was not produced by the v1 compiler: {key}")
            case = SimpleNamespace(
                category="tool_single_step",
                input_payload_json={"query": row["request"]},
                expected_tool_schema_json={"tool_name": row["expected_tool"]},
                expected_output_json=None,
                reference_context_json=None,
            )
            case.input_payload_json["available_tools"] = _available_tool_descriptors(case)
            extracted, _, _ = adapter._normalize_output(case, row["raw_output"])
            # Catalog membership is post-hoc: this catalog was not in the saved model prompt.
            result = compile_bounded_tool_call(
                extracted,
                input_payload=case.input_payload_json,
                document_context=document_context,
            )
            normalized = json.loads(row["normalized_output"])
            previous_arguments = normalized.get("arguments")
            current_arguments = (
                json.loads(result.normalized_output).get("arguments")
                if result.arguments_hash is not None
                else None
            )
            if result.arguments_hash is not None:
                canonical = json.dumps(
                    current_arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
                if hashlib.sha256(canonical.encode()).hexdigest() != result.arguments_hash:
                    raise ValueError(f"v2 changed argument values: {key}")
            flags = {
                "v1_raw_selection_correct": row["raw_selection_correct"],
                "v1_raw_arguments_valid": row["raw_arguments_valid"],
                "v1_normalized_arguments_valid": row["normalized_arguments_valid"],
                "v1_normalized_execution_success": row["normalized_execution_success"],
                "v1_arguments_changed": old.get("changed") is True,
                "v1_filled_document_id": "document_id" in old.get("filled_arguments", []),
                "v1_filled_query": "query" in old.get("filled_arguments", []),
                "v1_removed_failure_mode": "simulate_failure" in old.get("removed_arguments", []),
                "v1_filled_failure_mode": "simulate_failure" in old.get("filled_arguments", []),
                "v2_schema_valid": not result.schema_errors,
                "v2_execution_allowed": result.execution_allowed,
                "v2_selected_and_allowed": result.execution_allowed
                and row["raw_selection_correct"],
                "previous_success_now_blocked": (
                    row["normalized_execution_success"] and not result.execution_allowed
                ),
                "document_not_in_catalog": result.document_reference_status == "not_in_catalog",
                "unauthorized_failure_mode": (
                    "failure_simulation_not_authorized" in result.boundary_errors
                ),
                "missing_query": "$.query is required" in result.schema_errors,
                "missing_document_id": "$.document_id is required" in result.schema_errors,
            }
            counts.update({key: int(value) for key, value in flags.items()})
            rows.append(
                {
                    "entry": entry["name"],
                    "id": row["id"],
                    "trial": row["trial"],
                    "group": row["group"],
                    "request": row["request"],
                    "expected_tool": row["expected_tool"],
                    "raw_output": row["raw_output"],
                    "v1_normalized_arguments": previous_arguments,
                    "v2_preserved_arguments": current_arguments,
                    **flags,
                    "v2_audit": result.audit_record(),
                }
            )
    return {
        "observation_count": len(rows),
        "summary": dict(sorted(counts.items())),
        "entries": [
            {
                "name": entry["name"],
                "runtime": entry["runtime"],
                "observation_count": sum(row["entry"] == entry["name"] for row in rows),
                **{
                    key: sum(row["entry"] == entry["name"] and row[key] for row in rows)
                    for key in counts
                },
            }
            for entry in entries
        ],
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "reference_workload/revisions/1.0.4/manifest.json",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; use a new evidence path")
    if sha256(args.input) != args.expected_sha256:
        parser.error("input SHA-256 does not match the expected evidence")
    corpus = build_reference_corpus(args.manifest, repository_root=ROOT).corpus
    context = {
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_hash": corpus.corpus_hash,
        "document_ids": sorted({chunk.document_id for chunk in corpus.chunks}),
    }
    result = audit_saved_outputs(
        json.loads(args.input.read_text(encoding="utf-8")),
        document_context=context,
    )
    report = {
        "schema_version": "tool-argument-contract-audit-v1",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "authority": "non_authoritative_offline_diagnostic",
        "gate_evidence": False,
        "production_readiness": "not_production_ready",
        "compiler_version": TOOL_CALL_CONTRACT_VERSION,
        "input_file": args.input.name,
        "input_sha256": sha256(args.input),
        "manifest_sha256": sha256(args.manifest),
        "document_context": context,
        "failure_mode": None,
        "source_sha256": {
            name: sha256(ROOT / name)
            for name in (
                "tools/audit_tool_argument_contract.py",
                "backend/app/services/tool_call_contract.py",
                "backend/app/services/tool_execution.py",
                "backend/app/services/benchmark_execution.py",
                "backend/app/services/inference_adapters/openai_compatible.py",
            )
        },
        "limitations": [
            "Same saved outputs; no new inference, tool execution, or database writes.",
            "Unit: entry x case x trial; repeated cases across configurations are not independent.",
            "The reference document catalog was not supplied in these historical model prompts.",
            "Allowed is eligibility, not measured v2 execution success or query relevance.",
            "Historical raw argument validity used the old executor and evaluator schema.",
            "Block reasons overlap; their counts must not be added as exclusive categories.",
            "Local authored challenges are neither independently held-out nor human-reviewed.",
        ],
        **result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"observation_count": result["observation_count"], **result["summary"]}))
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
