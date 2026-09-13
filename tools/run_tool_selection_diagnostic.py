"""Run non-authoritative Tool selection challenges without changing the database."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.reference_workload.corpus import build_reference_corpus  # noqa: E402
from app.reference_workload.runtime_matrix import (  # noqa: E402
    PROMPT_BUNDLES,
    load_runtime_matrix,
    probe_runtime,
    resolve_runtime_entry,
)
from app.services.benchmark_execution import _available_tool_descriptors  # noqa: E402
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter  # noqa: E402
from app.services.tool_execution import execute_tool_calls, tool_argument_block_reason  # noqa: E402


class LegacyToolPromptAdapter(OpenAICompatibleAdapter):
    descriptor = replace(
        OpenAICompatibleAdapter.descriptor,
        adapter_version="openai-compatible-v18-prompt-replay",
        capabilities=OpenAICompatibleAdapter.descriptor.capabilities
        - {"public_tool_selection_prompt"},
    )

    @staticmethod
    def _tool_selection_prompt(evaluation_case, configuration=None):
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["legacy", "current"], required=True)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--small-model", default="qwen2.5:0.5b")
    parser.add_argument("--medium-model", default="qwen2.5:1.5b")
    parser.add_argument(
        "--tool-order", choices=["registered", "reversed"], default="registered"
    )
    parser.add_argument("--trials", type=int, choices=range(1, 6), default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "reference_workload/revisions/1.0.4/manifest.json",
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; use a new evidence path")
    fixture = ROOT / "backend/tests/fixtures/tool_selection_challenge.json"
    challenge = json.loads(fixture.read_text(encoding="utf-8"))
    matrix_path = ROOT / "reference_workload/runtime_matrix.json"
    matrix = load_runtime_matrix(matrix_path)
    corpus = build_reference_corpus(args.manifest, repository_root=ROOT).corpus
    document_context = {
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_hash": corpus.corpus_hash,
        "document_ids": sorted({chunk.document_id for chunk in corpus.chunks}),
    }
    adapter = (
        LegacyToolPromptAdapter()
        if args.variant == "legacy"
        else OpenAICompatibleAdapter()
    )
    environment = {
        "REFERENCE_RUNTIME_BASE_URL": args.base_url,
        "REFERENCE_MODEL_SMALL": args.small_model,
        "REFERENCE_MODEL_MEDIUM": args.medium_model,
    }
    report = {
        "schema_version": "tool-selection-challenge-result-v1",
        "authority": "non_authoritative_local_diagnostic",
        "human_reviewed": False,
        "gate_evidence": False,
        "production_readiness": "not_production_ready",
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "variant": args.variant,
        "tool_order": args.tool_order,
        "trials": args.trials,
        "seed": 42,
        "challenge_sha256": _sha256(fixture),
        "matrix_sha256": _sha256(matrix_path),
        "manifest_sha256": _sha256(args.manifest),
        "runner_sha256": _sha256(Path(__file__)),
        "adapter_descriptor": adapter.descriptor.to_dict(),
        "source_sha256": {
            name: _sha256(ROOT / "backend/app/services" / name)
            for name in [
                "inference_adapters/openai_compatible.py",
                "tool_selection_prompt.py",
                "tool_call_contract.py",
                "tool_execution.py",
            ]
        },
        "entries": [],
    }
    errors = 0
    for entry in matrix.entries:
        if not entry.enabled:
            continue
        resolved = resolve_runtime_entry(entry, environment=environment)
        observation = probe_runtime(resolved, environment=environment)
        configuration = SimpleNamespace(
            runtime_config_json={
                "base_url": resolved.base_url,
                "model": resolved.model_name,
                "prompt_bundle": {"system_prompt": PROMPT_BUNDLES[entry.prompt_bundle]},
                "_case_timeout_ms": 120000,
                "_tool_document_context": document_context,
                "tool_selection_prompt": (
                    "public-tool-selection-prompt-v1"
                    if args.variant == "current"
                    else "legacy"
                ),
            },
            generation_config_json={"temperature": 0, "max_tokens": 384},
            model_artifact=SimpleNamespace(artifact_name=resolved.model_name),
        )
        rows = []
        for item in challenge["cases"]:
            for trial in range(1, args.trials + 1):
                case = SimpleNamespace(
                    external_case_id=item["id"],
                    category="tool_single_step",
                    title=item["id"],
                    input_payload_json={
                        "query": item["request"],
                        "instruction": "Use only the registered local tools.",
                        "_execution_trial": trial,
                        "_case_timeout_ms": 120000,
                        "available_document_ids": document_context["document_ids"],
                        "document_catalog_provenance": {
                            key: value
                            for key, value in document_context.items()
                            if key != "document_ids"
                        },
                    },
                    expected_tool_schema_json={"tool_name": item["expected_tool"]},
                    expected_output_json=None,
                    reference_context_json=None,
                )
                descriptors = _available_tool_descriptors(case)
                if args.tool_order == "reversed":
                    descriptors.reverse()
                case.input_payload_json["available_tools"] = descriptors
                row = {
                    "id": item["id"],
                    "group": item["group"],
                    "trial": trial,
                    "request": item["request"],
                    "expected_tool": item["expected_tool"],
                }
                try:
                    result = adapter.run_case(
                        configuration=configuration,
                        evaluation_case=case,
                        seed=42,
                    )
                    raw = execute_tool_calls(case, result.raw_output)
                    normalized = execute_tool_calls(
                        case,
                        result.normalized_output,
                        execution_block_reason=tool_argument_block_reason(
                            result.metadata
                        ),
                    )
                    row.update(
                        raw_output=result.raw_output,
                        normalized_output=result.normalized_output,
                        raw_selection_correct=raw.sequence_match
                        and raw.selection_accuracy == 1,
                        selection_correct=normalized.sequence_match
                        and normalized.selection_accuracy == 1,
                        raw_arguments_valid=raw.argument_validity_rate == 1,
                        normalized_arguments_valid=normalized.argument_validity_rate
                        == 1,
                        normalized_execution_success=normalized.execution_success_rate
                        == 1,
                        actual_tool_sequence=normalized.actual_tool_sequence,
                        prompt_tokens=result.prompt_tokens,
                        completion_tokens=result.completion_tokens,
                        latency_ms=result.end_to_end_latency_ms,
                        metadata=result.metadata,
                    )
                except Exception as exc:
                    errors += 1
                    row.update(
                        selection_correct=False, error=f"{type(exc).__name__}: {exc}"
                    )
                rows.append(row)
        summary = {
            "case_count": len(rows),
            **{
                key: sum(row.get(key) is True for row in rows)
                for key in [
                    "raw_selection_correct",
                    "selection_correct",
                    "raw_arguments_valid",
                    "normalized_arguments_valid",
                    "normalized_execution_success",
                ]
            },
            "errors": sum("error" in row for row in rows),
        }
        report["entries"].append(
            {
                "name": entry.name,
                "runtime": observation.model_dump(),
                "runtime_config": configuration.runtime_config_json,
                "generation_config": configuration.generation_config_json,
                "summary": summary,
                "rows": rows,
            }
        )
        print(json.dumps({"entry": entry.name, **summary}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(
        json.dumps({"output": str(args.output), "sha256": _sha256(args.output)}),
        flush=True,
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
