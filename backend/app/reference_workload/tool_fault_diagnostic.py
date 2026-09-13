"""Check executor fault fixtures with fixed calls; no inference or database writes."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root
from app.services.benchmark_execution import _available_tool_descriptors
from app.services.tool_call_contract import compile_bounded_tool_call
from app.services.tool_execution import (
    build_fault_tool_registry,
    execute_tool_calls,
    tool_argument_block_reason,
)
from app.services.tool_fault_scenarios import ToolFaultScenario


def run_fixture_checks(*, document_context: dict, trials: int = 3) -> dict:
    if type(trials) is not int or not 1 <= trials <= 10:
        raise ValueError("fixture trials must be an integer from 1 to 10")
    if not document_context.get("document_ids"):
        raise ValueError("a nonempty trusted corpus catalog is required for the document fixture")
    registry = build_fault_tool_registry()
    rows = []
    for tool_name in sorted(registry.tools):
        arguments = (
            {"document_id": document_context["document_ids"][0]}
            if tool_name == "lookup_internal_document"
            else {"query": "fixed fixture input"}
        )
        scripted_output = json.dumps(
            {"tool_name": tool_name, "arguments": arguments}, sort_keys=True
        )
        case = SimpleNamespace(
            external_case_id=f"FIXTURE-{tool_name}",
            category="tool_single_step",
            title="Fixture",
            expected_tool_schema_json={"tool_name": tool_name},
            reference_context_json=None,
            input_payload_json={"query": "fixed fixture input"},
            expected_output_json=None,
        )
        case.input_payload_json["available_tools"] = _available_tool_descriptors(case, registry)
        for mode in ("normal", "transient_once", "permanent"):
            scenario = ToolFaultScenario(mode)
            for trial in range(1, trials + 1):
                guard = compile_bounded_tool_call(
                    scripted_output,
                    input_payload=case.input_payload_json,
                    document_context=document_context,
                )
                trace = execute_tool_calls(
                    case,
                    guard.normalized_output,
                    registry,
                    fault_scenario=scenario,
                    execution_block_reason=tool_argument_block_reason(
                        {"tool_call_contract": guard.audit_record()}
                    ),
                )
                rows.append(
                    {
                        "tool_name": tool_name,
                        "trial": trial,
                        "mode": mode,
                        "scripted_output": scripted_output,
                        "guard": guard.audit_record(),
                        "trace": trace.to_dict(),
                    }
                )
    return {
        "schema_version": "tool-fault-fixture-check-v1",
        "authority": "scripted_executor_fixture_diagnostic",
        "gate_evidence": False,
        "model_inference_performed": False,
        "database_writes_performed": False,
        "production_readiness": "not_production_ready",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "registry": registry.descriptor(),
        "document_context": document_context,
        "summary": {
            "observation_count": len(rows),
            "fixture_passed_count": sum(r["trace"]["fault_scenario"]["passed"] for r in rows),
            "tool_success_count": sum(r["trace"]["successful"] for r in rows),
            "injected_failure_count": sum(
                r["trace"]["fault_scenario"]["injected_failure_count"] for r in rows
            ),
            "handler_invocation_count": sum(
                r["trace"]["fault_scenario"]["handler_invocation_count"] for r in rows
            ),
            "mode_outcomes": {
                mode: {
                    "observations": sum(r["mode"] == mode for r in rows),
                    "fixture_passed": sum(
                        r["mode"] == mode and r["trace"]["fault_scenario"]["passed"] for r in rows
                    ),
                    "tool_succeeded": sum(
                        r["mode"] == mode and r["trace"]["successful"] for r in rows
                    ),
                }
                for mode in ("normal", "transient_once", "permanent")
            },
        },
        "rows": rows,
        "limitations": [
            "Scripted valid calls test executor behavior, not model generation or reasoning.",
            "Retries are controlled by the executor, not a model feedback loop.",
            "A passed permanent-failure scenario is still an unsuccessful Tool execution.",
            "Faults are injected before local handlers; partial external writes are not tested.",
            "Legacy recovery cases and historical evidence are not migrated by this command.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--trials", type=int, choices=range(1, 11), default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; use a new evidence path")
    manifest = (
        args.manifest or args.repository_root / "reference_workload/revisions/1.0.4/manifest.json"
    )
    corpus = build_reference_corpus(manifest, repository_root=args.repository_root).corpus
    context = {
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_hash": corpus.corpus_hash,
        "document_ids": sorted({chunk.document_id for chunk in corpus.chunks}),
    }
    report = run_fixture_checks(document_context=context, trials=args.trials)
    app = Path(__file__).resolve().parents[1]
    report["source_sha256"] = {
        name: hashlib.sha256((app / name).read_bytes()).hexdigest()
        for name in (
            "reference_workload/tool_fault_diagnostic.py",
            "services/tool_fault_scenarios.py",
            "services/tool_execution.py",
            "services/tool_call_contract.py",
            "services/benchmark_execution.py",
        )
    }
    report["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(report["summary"]))
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            }
        )
    )
    return int(report["summary"]["fixture_passed_count"] != report["summary"]["observation_count"])


if __name__ == "__main__":
    raise SystemExit(main())
