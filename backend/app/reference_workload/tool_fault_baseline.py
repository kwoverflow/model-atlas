"""Measure fresh Tool generation, then replay each output under three environment faults."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root, stable_hash
from app.reference_workload.runtime_matrix import (
    PROMPT_BUNDLES,
    load_runtime_matrix,
    probe_runtime,
    resolve_runtime_entry,
)
from app.reference_workload.tool_fault_cases import load_baseline_pack, prepare_baseline_cases
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.tool_call_contract import compile_bounded_tool_call
from app.services.tool_execution import (
    build_fault_tool_registry,
    execute_tool_calls,
    tool_argument_block_reason,
)
from app.services.tool_fault_scenarios import ToolFaultScenario

MODES = ("normal", "transient_once", "permanent")
METRICS = (
    "selection_correct",
    "raw_schema_valid",
    "normalized_schema_valid",
    "guard_eligible",
    "arguments_exact",
    "selection_and_arguments_exact",
    "argument_preservation_verified",
    "normal_tool_success",
)


class CapturingToolAdapter(OpenAICompatibleAdapter):
    """Capture the actual request body, without changing prompts or the inference contract."""

    def reset_capture(self):
        self.request_body = None
        self.finish_reason = None
        self.usage = None

    def _post_json(self, configuration, base_url, path, body, *, deadline):
        self.request_body = copy.deepcopy(body)
        payload = super()._post_json(configuration, base_url, path, body, deadline=deadline)
        self.finish_reason = payload["choices"][0].get("finish_reason")
        self.usage = copy.deepcopy(payload.get("usage"))
        return payload


def measure_generation(item, public, evaluator, result, registry, context) -> dict:
    raw = compile_bounded_tool_call(
        result.raw_output, input_payload=public.input_payload_json, document_context=context
    )
    normalized = compile_bounded_tool_call(
        result.normalized_output, input_payload=public.input_payload_json, document_context=context
    )
    guard = result.metadata.get("tool_call_contract")
    if not isinstance(guard, dict) or guard != normalized.audit_record():
        raise ValueError("adapter guard audit is missing or disagrees with the captured output")
    traces = {
        mode: execute_tool_calls(
            evaluator,
            result.normalized_output,
            registry,
            execution_block_reason=tool_argument_block_reason(result.metadata),
            fault_scenario=ToolFaultScenario(mode),
        ).to_dict()
        for mode in MODES
    }
    arguments_exact = normalized.arguments_hash == stable_hash(item.expected_arguments)
    selected = normalized.tool_name == item.expected_tool
    return {
        "raw_output": result.raw_output,
        "normalized_output": result.normalized_output,
        "raw_guard": raw.audit_record(),
        "metadata": result.metadata,
        "selection_correct": selected,
        "raw_schema_valid": not raw.schema_errors,
        "normalized_schema_valid": not normalized.schema_errors,
        "guard_eligible": normalized.execution_allowed,
        "arguments_exact": arguments_exact,
        "selection_and_arguments_exact": selected and arguments_exact,
        "argument_preservation_verified": (
            raw.arguments_hash is not None and raw.arguments_hash == normalized.arguments_hash
        ),
        "normal_tool_success": traces["normal"]["successful"],
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "latency_ms": result.end_to_end_latency_ms,
        "traces": traces,
    }


def summarize_rows(rows: list[dict]) -> dict:
    return {
        "observation_count": len(rows),
        "generated_count": sum("raw_output" in row for row in rows),
        "error_count": sum("error" in row for row in rows),
        **{key: sum(row.get(key) is True for row in rows) for key in METRICS},
        "mode_outcomes": {
            mode: {
                "observation_count": len(rows),
                "trace_count": len(traces := [r["traces"][mode] for r in rows if "traces" in r]),
                "fixture_passed": sum(t["fault_scenario"]["passed"] for t in traces),
                "not_exercised": sum(
                    t["fault_scenario"]["status"] == "not_exercised" for t in traces
                ),
                "tool_succeeded": sum(t["successful"] for t in traces),
                "injected_failures": sum(
                    t["fault_scenario"]["injected_failure_count"] for t in traces
                ),
                "handler_invocations": sum(
                    t["fault_scenario"]["handler_invocation_count"] for t in traces
                ),
            }
            for mode in MODES
        },
    }


def run_entry(entry, resolved, pack, registry, context, *, adapter, on_row=None) -> dict:
    configuration = SimpleNamespace(
        runtime_config_json={
            "base_url": resolved.base_url,
            "model": resolved.model_name,
            "prompt_bundle": {"system_prompt": PROMPT_BUNDLES[entry.prompt_bundle]},
            "_case_timeout_ms": 120000,
            "_tool_document_context": context,
            "tool_selection_prompt": "legacy",
        },
        generation_config_json=entry.generation.model_dump(),
        model_artifact=SimpleNamespace(artifact_name=resolved.model_name),
    )
    rows = []
    for item in pack.cases:
        for trial in range(1, entry.trials + 1):
            public, evaluator = prepare_baseline_cases(item, registry, context)
            seed = 41 + trial
            row = {"id": item.id, "trial": trial, "seed": seed, "expected_tool": item.expected_tool}
            adapter.reset_capture()
            try:
                result = adapter.run_case(
                    configuration=configuration, evaluation_case=public, seed=seed
                )
                row.update(
                    raw_output=result.raw_output,
                    normalized_output=result.normalized_output,
                    metadata=result.metadata,
                )
                row.update(measure_generation(item, public, evaluator, result, registry, context))
            except Exception as exc:
                row["error"] = {"type": type(exc).__name__, "message": str(exc)}
            row["request_body"] = adapter.request_body
            row["request_hash"] = (
                stable_hash(adapter.request_body) if adapter.request_body else None
            )
            row["finish_reason"] = adapter.finish_reason
            row["runtime_usage"] = adapter.usage
            rows.append(row)
            if on_row is not None:
                on_row(row)
    return {
        "name": entry.name,
        "runtime_config": configuration.runtime_config_json,
        "generation_config": configuration.generation_config_json,
        "matrix_entry": entry.model_dump(),
        "summary": summarize_rows(rows),
        "rows": rows,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--small-model", default="qwen2.5:0.5b")
    parser.add_argument("--medium-model", default="qwen2.5:1.5b")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    journal_path = args.output.with_suffix(".observations.jsonl")
    if args.output.exists() or journal_path.exists():
        parser.error("output or observation journal already exists; use a new evidence path")
    root = args.repository_root
    manifest_path = root / "reference_workload/revisions/1.0.4/manifest.json"
    matrix_path = root / "reference_workload/runtime_matrix.json"
    cases_path = root / "reference_workload/diagnostics/tool-fault-baseline-v1.json"
    corpus = build_reference_corpus(manifest_path, repository_root=root).corpus
    context = {
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_hash": corpus.corpus_hash,
        "document_ids": sorted({chunk.document_id for chunk in corpus.chunks}),
    }
    registry = build_fault_tool_registry()
    pack = load_baseline_pack(cases_path, registry, context)
    matrix = load_runtime_matrix(matrix_path)
    environment = {
        "REFERENCE_RUNTIME_BASE_URL": args.base_url,
        "REFERENCE_MODEL_SMALL": args.small_model,
        "REFERENCE_MODEL_MEDIUM": args.medium_model,
    }
    prepared = []
    for entry in matrix.entries:
        if entry.enabled:
            resolved = resolve_runtime_entry(entry, environment=environment)
            prepared.append((entry, resolved, probe_runtime(resolved, environment=environment)))
    if not prepared:
        parser.error("the matrix has no enabled entries")
    app = Path(__file__).resolve().parents[1]
    report = {
        "schema_version": "tool-fault-model-baseline-v1",
        "status": "running",
        "authority": "local_actual_runtime_paired_fault_diagnostic",
        "human_reviewed": False,
        "gate_evidence": False,
        "database_writes_performed": False,
        "model_inference_performed": True,
        "production_readiness": "not_production_ready",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "protocol": {
            "sampling_unit": "runtime_entry_x_case_x_trial",
            "design": "one_fresh_generation_replayed_unchanged_in_three_fault_modes",
            "modes": [ToolFaultScenario(mode).to_dict() for mode in MODES],
            "seeds": "41 + trial (42, 43 for the current matrix)",
            "concurrency": 1,
            "tool_order": "registered",
            "tool_prompt": "legacy",
            "expected_observations": sum(e.trials * len(pack.cases) for e, _, _ in prepared),
            "labels_available_to_adapter": False,
            "fault_mode_available_to_adapter": False,
        },
        "case_pack": pack.model_dump(mode="json"),
        "document_context": context,
        "registry": registry.descriptor(),
        "adapter_descriptor": OpenAICompatibleAdapter.descriptor.to_dict(),
        "case_pack_sha256": _sha256(cases_path),
        "matrix_sha256": _sha256(matrix_path),
        "manifest_sha256": _sha256(manifest_path),
        "source_sha256": {
            name: _sha256(app / name)
            for name in (
                "reference_workload/tool_fault_baseline.py",
                "reference_workload/tool_fault_cases.py",
                "reference_workload/runtime_matrix.py",
                "services/inference_adapters/openai_compatible.py",
                "services/tool_call_contract.py",
                "services/tool_execution.py",
                "services/tool_fault_scenarios.py",
                "services/benchmark_execution.py",
            )
        },
        "entries": [],
        "limitations": [
            "These local exact-literal cases are not human-reviewed or independently held out.",
            "Paired traces reuse one generation; they are not three independent model responses.",
            "Retries are executor-controlled, not model-driven recovery.",
            "Exact arguments measure explicit value preservation, not broad semantic correctness.",
            "Tool execution uses deterministic local fixtures, not real external services or ACLs.",
            "Two trials at temperature zero do not establish statistical model superiority.",
            "Matrix context length is declared metadata, not an enforced OpenAI request parameter.",
            "No comparison with legacy recovery totals is valid after this case/schema change.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    with journal_path.open("x", encoding="utf-8") as journal:
        for entry, resolved, observation in prepared:

            def record(row, entry_name=entry.name):
                journal.write(json.dumps({"entry": entry_name, **row}, ensure_ascii=False) + "\n")
                journal.flush()
                print(
                    json.dumps(
                        {
                            "entry": entry_name,
                            "id": row["id"],
                            "trial": row["trial"],
                            "error": row.get("error"),
                            "selection": row.get("selection_correct"),
                            "exact": row.get("selection_and_arguments_exact"),
                        }
                    ),
                    flush=True,
                )

            result = run_entry(
                entry,
                resolved,
                pack,
                registry,
                context,
                adapter=CapturingToolAdapter(),
                on_row=record,
            )
            result["runtime"] = observation.model_dump()
            report["entries"].append(result)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    rows = [row for entry in report["entries"] for row in entry["rows"]]
    report["summary"] = summarize_rows(rows)
    report["status"] = "complete_with_errors" if report["summary"]["error_count"] else "complete"
    report["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["journal_sha256"] = _sha256(journal_path)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"summary": report["summary"], "sha256": _sha256(args.output)}), flush=True)
    return int(report["summary"]["error_count"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
