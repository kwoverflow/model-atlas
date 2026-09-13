"""Compare an opt-in two-stage candidate against immutable and contemporaneous baselines."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import time
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
from app.reference_workload.tool_fault_baseline import _sha256, measure_generation, summarize_rows
from app.reference_workload.tool_fault_cases import load_baseline_pack, prepare_baseline_cases
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.inference_adapters.two_stage_tool import TwoStageToolAdapter
from app.services.tool_execution import build_fault_tool_registry

BASELINE_PATH = "artifacts/reference-workload/tool-fault-model-baseline-v1.json"
BASELINE_SHA256 = "27975681d2f2b53bad53c44d19346e5d9d7a47fa28f32a7d226faeecd388497f"
NEW_SOURCES = (
    "services/tool_argument_generation.py",
    "services/inference_adapters/two_stage_tool.py",
    "reference_workload/tool_two_stage_diagnostic.py",
)


class RequestCapture:
    """Serial diagnostic instrumentation, not a shared production adapter instance."""

    def reset_capture(self):
        self.requests = []

    def _post_json(self, configuration, base_url, path, body, *, deadline):
        started = time.perf_counter()
        record = {"body": copy.deepcopy(body), "request_hash": stable_hash(body)}
        self.requests.append(record)
        try:
            response = super()._post_json(configuration, base_url, path, body, deadline=deadline)
            record["response"] = copy.deepcopy(response)
            return response
        except Exception as exc:
            record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            raise
        finally:
            record["latency_ms"] = (time.perf_counter() - started) * 1000


class CapturedBaseline(RequestCapture, OpenAICompatibleAdapter):
    pass


class CapturedCandidate(RequestCapture, TwoStageToolAdapter):
    pass


def configuration_for(entry, resolved, context):
    return SimpleNamespace(
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


def observe(item, configuration, registry, context, *, variant, seed, tool_order):
    public, evaluator = prepare_baseline_cases(item, registry, context)
    if tool_order == "reversed":
        public.input_payload_json["available_tools"].reverse()
    elif tool_order != "registered":
        raise ValueError("unknown tool order")
    if variant not in {"baseline", "candidate"}:
        raise ValueError("unknown variant")
    adapter = CapturedCandidate() if variant == "candidate" else CapturedBaseline()
    adapter.reset_capture()
    row = {"id": item.id, "variant": variant, "seed": seed, "tool_order": tool_order}
    try:
        result = adapter.run_case(configuration=configuration, evaluation_case=public, seed=seed)
        row.update(measure_generation(item, public, evaluator, result, registry, context))
        audit = result.metadata.get("tool_argument_generation", {})
        row["stage1_selected_tool"] = audit.get(
            "selected_tool", result.metadata["tool_call_contract"]["tool_name"]
        )
        row["stage1_selection_correct"] = row["stage1_selected_tool"] == item.expected_tool
        row["output_representation"] = audit.get("output_representation", "native_stage1_output")
        if audit.get("status") == "failed":
            row["error"] = audit["error"]
    except Exception as exc:
        row["error"] = {"type": type(exc).__name__, "message": str(exc)}
    row["requests"] = adapter.requests
    usages = [record.get("response", {}).get("usage") for record in adapter.requests]
    row["http_usage_complete"] = bool(usages) and all(
        isinstance(usage, dict)
        and all(
            type(usage.get(key)) is int and usage[key] >= 0
            for key in ("prompt_tokens", "completion_tokens")
        )
        for usage in usages
    )
    row["measured_tokens"] = (
        {key: sum(usage[key] for usage in usages) for key in ("prompt_tokens", "completion_tokens")}
        if row["http_usage_complete"]
        else None
    )
    return row


def verify_baseline(root: Path) -> dict:
    path = root / BASELINE_PATH
    if _sha256(path) != BASELINE_SHA256:
        raise ValueError("frozen baseline artifact hash changed")
    baseline = json.loads(path.read_text(encoding="utf-8"))
    for name, digest in baseline["source_sha256"].items():
        if _sha256(root / "backend/app" / name) != digest:
            raise ValueError(f"frozen baseline source changed: {name}")
    for path, key in (
        ("reference_workload/runtime_matrix.json", "matrix_sha256"),
        ("reference_workload/diagnostics/tool-fault-baseline-v1.json", "case_pack_sha256"),
        ("reference_workload/revisions/1.0.4/manifest.json", "manifest_sha256"),
    ):
        if _sha256(root / path) != baseline[key]:
            raise ValueError(f"frozen baseline input changed: {path}")
    return baseline


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
    baseline = verify_baseline(root)
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
    packs = {
        cohort: load_baseline_pack(root / path, registry, context)
        for cohort, path in (
            ("frozen", "reference_workload/diagnostics/tool-fault-baseline-v1.json"),
            ("challenge", "reference_workload/diagnostics/tool-two-stage-challenge-v1.json"),
        )
    }
    matrix = load_runtime_matrix(root / "reference_workload/runtime_matrix.json")
    environment = {
        "REFERENCE_RUNTIME_BASE_URL": args.base_url,
        "REFERENCE_MODEL_SMALL": "qwen2.5:0.5b",
        "REFERENCE_MODEL_MEDIUM": "qwen2.5:1.5b",
    }
    old_entries = {entry["name"]: entry for entry in baseline["entries"]}
    prepared = []
    for entry in matrix.entries:
        if not entry.enabled:
            continue
        resolved = resolve_runtime_entry(entry, environment=environment)
        runtime = probe_runtime(resolved, environment=environment).model_dump()
        if runtime != old_entries[entry.name]["runtime"]:
            raise ValueError(f"runtime identity changed: {entry.name}")
        prepared.append((entry, resolved, runtime))
    if not prepared:
        parser.error("no enabled runtime entries")
    report = {
        "schema_version": "tool-two-stage-diagnostic-v1",
        "status": "running",
        "human_reviewed": False,
        "gate_evidence": False,
        "database_writes_performed": False,
        "production_readiness": "not_production_ready",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "baseline_path": BASELINE_PATH,
        "baseline_sha256": BASELINE_SHA256,
        "source_sha256": {
            **baseline["source_sha256"],
            **{name: _sha256(root / "backend/app" / name) for name in NEW_SOURCES},
        },
        "challenge_sha256": _sha256(
            root / "reference_workload/diagnostics/tool-two-stage-challenge-v1.json"
        ),
        "packs": {name: pack.model_dump(mode="json") for name, pack in packs.items()},
        "document_context": context,
        "protocol": {
            "concurrency": 1,
            "labels_available_to_adapter": False,
            "fault_mode_available_to_adapter": False,
            "default_adapter_changed": False,
            "stage1": "unchanged legacy generation; discard its arguments for candidate stage2",
            "stage2": "one fresh argument-object generation with selected schema; no value repair",
            "frozen_comparison": "historical baseline, identical stage1 body checked per row",
            "challenge_comparison": "paired baseline/candidate; alternating AB/BA execution order",
            "challenge_orders": ["registered", "reversed"],
            "challenge_seed": 42,
            "expected_observations": sum(
                e.trials * len(packs["frozen"].cases) + 4 * len(packs["challenge"].cases)
                for e, _, _ in prepared
            ),
            "faults": "each final output replayed unchanged under normal/transient_once/permanent",
            "raw_schema_metric": (
                "candidate schema metrics refer to composed envelope, not native output"
            ),
            "cost": (
                "captured HTTP token usage; local wall time includes cache and runtime variability"
            ),
        },
        "entries": [],
        "rows": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    with journal_path.open("x", encoding="utf-8") as journal:

        def record(row):
            report["rows"].append(row)
            journal.write(json.dumps(row, ensure_ascii=False) + "\n")
            journal.flush()
            print(
                json.dumps(
                    {
                        key: row.get(key)
                        for key in (
                            "entry",
                            "cohort",
                            "variant",
                            "id",
                            "trial",
                            "tool_order",
                            "selection_and_arguments_exact",
                            "error",
                        )
                    }
                ),
                flush=True,
            )

        for entry, resolved, runtime in prepared:
            config = configuration_for(entry, resolved, context)
            report["entries"].append(
                {
                    "name": entry.name,
                    "runtime": runtime,
                    "matrix_entry": entry.model_dump(),
                    "runtime_config": config.runtime_config_json,
                    "generation_config": config.generation_config_json,
                }
            )
            old_rows = {(r["id"], r["trial"]): r for r in old_entries[entry.name]["rows"]}
            for item in packs["frozen"].cases:
                for trial in range(1, entry.trials + 1):
                    row = observe(
                        item,
                        config,
                        registry,
                        context,
                        variant="candidate",
                        seed=41 + trial,
                        tool_order="registered",
                    )
                    row.update(entry=entry.name, cohort="frozen", trial=trial)
                    old = old_rows[(item.id, trial)]
                    row["baseline_exact"] = old["selection_and_arguments_exact"]
                    row["stage1_request_matches_baseline"] = bool(row["requests"]) and (
                        row["requests"][0]["request_hash"] == old["request_hash"]
                    )
                    if not row["stage1_request_matches_baseline"]:
                        row["error"] = {"type": "RequestMismatch", "message": "stage1 body changed"}
                    record(row)
            for index, item in enumerate(packs["challenge"].cases):
                for order_index, order in enumerate(("registered", "reversed")):
                    variants = (
                        ("baseline", "candidate")
                        if (index + order_index) % 2 == 0
                        else ("candidate", "baseline")
                    )
                    for variant in variants:
                        row = observe(
                            item,
                            config,
                            registry,
                            context,
                            variant=variant,
                            seed=42,
                            tool_order=order,
                        )
                        row.update(
                            entry=entry.name,
                            cohort="challenge",
                            trial=1,
                            pair_execution_order=list(variants),
                        )
                        record(row)
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    report["summaries"] = {
        f"{entry.name}/{cohort}/{variant}": summarize_rows(
            [
                row
                for row in report["rows"]
                if (row["entry"], row["cohort"], row["variant"]) == (entry.name, cohort, variant)
            ]
        )
        for entry, _, _ in prepared
        for cohort, variant in (
            ("frozen", "candidate"),
            ("challenge", "baseline"),
            ("challenge", "candidate"),
        )
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
