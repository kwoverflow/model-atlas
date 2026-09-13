"""Versioned development/fresh comparison for explicit optional-argument preservation."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root
from app.reference_workload.runtime_matrix import (
    RuntimeMatrixEntry,
    probe_runtime,
    resolve_runtime_entry,
)
from app.reference_workload.tool_argument_equivalence import validate_default_policy
from app.reference_workload.tool_default_semantics_diagnostic import (
    attach_comparison,
    load_previous,
    summary,
)
from app.reference_workload.tool_fault_baseline import _sha256, measure_generation
from app.reference_workload.tool_fault_cases import load_baseline_pack, prepare_baseline_cases
from app.reference_workload.tool_two_stage_diagnostic import (
    CapturedBaseline,
    CapturedCandidate,
    RequestCapture,
    configuration_for,
)
from app.services.inference_adapters.nullable_presence_tool import NullablePresenceToolAdapter
from app.services.inference_adapters.presence_aware_tool import PresenceAwareToolAdapter
from app.services.tool_execution import build_fault_tool_registry

PREVIOUS_PATH = "artifacts/reference-workload/tool-default-semantics-diagnostic-v1.json"
PREVIOUS_SHA256 = "ed5c3b2304d89e6241f7e713480798b78f068565a690498271933d8c911abd50"
FRESH_PATH = "reference_workload/diagnostics/tool-presence-fresh-v1.json"
VARIANTS = ("baseline", "candidate_v1", "candidate_v2")
SOURCES = (
    "services/inference_adapters/presence_aware_tool.py",
    "services/inference_adapters/nullable_presence_tool.py",
    "reference_workload/tool_presence_diagnostic.py",
)


class CapturedPresence(PresenceAwareToolAdapter, CapturedCandidate):
    """MRO rewrites the request before RequestCapture records the actual HTTP body."""


class CapturedNullable(RequestCapture, NullablePresenceToolAdapter):
    pass


def observe_presence(item, config, registry, context, *, variant, seed, order):
    adapters = {
        "baseline": CapturedBaseline,
        "candidate_v1": CapturedCandidate,
        "candidate_v2": CapturedPresence,
        "candidate_v3": CapturedNullable,
    }
    if variant not in adapters or order not in {"registered", "reversed"}:
        raise ValueError("invalid variant or catalog order")
    public, evaluator = prepare_baseline_cases(item, registry, context)
    if order == "reversed":
        public.input_payload_json["available_tools"].reverse()
    adapter = adapters[variant]()
    adapter.reset_capture()
    row = {"id": item.id, "variant": variant, "seed": seed, "tool_order": order}
    try:
        result = adapter.run_case(configuration=config, evaluation_case=public, seed=seed)
        row.update(
            raw_output=result.raw_output,
            normalized_output=result.normalized_output,
            metadata=result.metadata,
        )
        row.update(measure_generation(item, public, evaluator, result, registry, context))
        generation = result.metadata.get("tool_argument_generation", {})
        row["stage1_selected_tool"] = generation.get(
            "selected_tool", result.metadata["tool_call_contract"]["tool_name"]
        )
        if generation.get("status") == "failed":
            row["error"] = generation["error"]
    except Exception as exc:
        row["error"] = {"type": type(exc).__name__, "message": str(exc)}
    row["requests"] = adapter.requests
    usages = [record.get("response", {}).get("usage") for record in adapter.requests]
    row["http_usage_complete"] = bool(usages) and all(
        isinstance(usage, dict)
        and all(
            type(usage.get(k)) is int and usage[k] >= 0
            for k in ("prompt_tokens", "completion_tokens")
        )
        for usage in usages
    )
    row["measured_tokens"] = (
        {key: sum(usage[key] for usage in usages) for key in ("prompt_tokens", "completion_tokens")}
        if row["http_usage_complete"]
        else None
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--cohort", choices=("development", "fresh"), required=True)
    parser.add_argument("--candidate", choices=("v2", "v3"), default="v2")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    variant_names = ("baseline", "candidate_v1", f"candidate_{args.candidate}")
    journal = args.output.with_suffix(".observations.jsonl")
    if args.output.exists() or journal.exists():
        parser.error("output or journal already exists; choose a new evidence path")
    root = args.repository_root
    load_previous(root)
    previous_path = root / PREVIOUS_PATH
    if _sha256(previous_path) != PREVIOUS_SHA256:
        raise ValueError("previous semantics evidence changed")
    previous = json.loads(previous_path.read_text("utf-8"))
    if _sha256(previous_path.with_suffix(".observations.jsonl")) != previous["journal_sha256"]:
        raise ValueError("previous semantics journal changed")
    for name, expected in previous["source_sha256"].items():
        if _sha256(root / "backend/app" / name) != expected:
            raise ValueError(f"frozen implementation changed: {name}")
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
    case_path = previous["case_pack_path"] if args.cohort == "development" else FRESH_PATH
    pack = load_baseline_pack(root / case_path, registry, context)
    cases = (
        tuple(c for c in pack.cases if c.expected_tool == "create_ticket")
        if args.cohort == "development"
        else pack.cases
    )
    if args.cohort == "fresh":
        prior_requests = {c["request"] for c in previous["case_pack"]["cases"]}
        if any(c.request in prior_requests for c in cases):
            raise ValueError("fresh requests overlap development cases")
    entry = RuntimeMatrixEntry.model_validate(previous["matrix_entry"])
    environment = {
        "REFERENCE_RUNTIME_BASE_URL": args.base_url,
        "REFERENCE_MODEL_MEDIUM": "qwen2.5:1.5b",
    }
    resolved = resolve_runtime_entry(entry, environment=environment)
    runtime = probe_runtime(resolved, environment=environment).model_dump()
    if runtime != previous["runtime"]:
        raise ValueError("runtime identity changed")
    config = configuration_for(entry, resolved, context)
    report = {
        "schema_version": "tool-optional-presence-diagnostic-v1",
        "status": "running",
        "cohort": args.cohort,
        "candidate_version": args.candidate,
        "human_reviewed": False,
        "gate_evidence": False,
        "database_writes_performed": False,
        "production_readiness": "not_production_ready",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "previous_path": PREVIOUS_PATH,
        "previous_sha256": PREVIOUS_SHA256,
        "case_pack_path": case_path,
        "case_pack_sha256": _sha256(root / case_path),
        "cases": [c.model_dump(mode="json") for c in cases],
        "policy": validate_default_policy(registry),
        "document_context": context,
        "runtime": runtime,
        "matrix_entry": entry.model_dump(),
        "runtime_config": config.runtime_config_json,
        "generation_config": config.generation_config_json,
        "source_sha256": {
            **previous["source_sha256"],
            **{name: _sha256(root / "backend/app" / name) for name in SOURCES},
        },
        "protocol": {
            "variants": list(variant_names),
            "concurrency": 1,
            "expected_observations": len(cases) * 2 * entry.trials * len(variant_names),
            "seeds": [41 + trial for trial in range(1, entry.trials + 1)],
            "orders": ["registered", "reversed"],
            "variant_order": "rotate three variants across case/order/trial conditions",
            "changed": (
                "v2 optional-field prompt/checklist"
                if args.candidate == "v2"
                else "v3 explicit nullable optional-field response protocol and prompt"
            ),
            "unchanged": (
                "stage1, models, argument schema, required-only stage2, guards, "
                "exact/default scoring"
            ),
            "labels_available_to_adapter": False,
            "argument_repair": False,
            "sample_limit": (
                "locally authored; development requests are known; "
                "fresh requests are not independently reviewed"
            ),
        },
        "rows": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with journal.open("x", encoding="utf-8") as log:
        for index, item in enumerate(cases):
            for order_index, order in enumerate(("registered", "reversed")):
                for trial in range(1, entry.trials + 1):
                    offset = (index * 4 + order_index * 2 + trial - 1) % len(variant_names)
                    variants = variant_names[offset:] + variant_names[:offset]
                    for variant in variants:
                        row = observe_presence(
                            item,
                            config,
                            registry,
                            context,
                            variant=variant,
                            seed=41 + trial,
                            order=order,
                        )
                        row.update(trial=trial, execution_order=list(variants))
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
                            log.write(json.dumps(row, ensure_ascii=False) + "\n")
                            log.flush()
                        print(
                            json.dumps(
                                {
                                    "cohort": args.cohort,
                                    "id": item.id,
                                    "trial": trial,
                                    "order": order,
                                    "variant": variant,
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
        v: summary([r for r in report["rows"] if r["variant"] == v]) for v in variant_names
    }
    errors = sum("error" in row for row in report["rows"])
    report["status"] = "complete_with_errors" if errors else "complete"
    report["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["journal_sha256"] = _sha256(journal)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": report["status"], "sha256": _sha256(args.output)}), flush=True)
    return int(errors > 0)


if __name__ == "__main__":
    raise SystemExit(main())
