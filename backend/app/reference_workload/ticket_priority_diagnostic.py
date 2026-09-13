"""Paired unchanged v3 proposals with/without a separate request-only priority veto."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root
from app.reference_workload.runtime_matrix import (
    RuntimeMatrixEntry,
    probe_runtime,
    resolve_runtime_entry,
)
from app.reference_workload.tool_argument_equivalence import compare_argument_contract
from app.reference_workload.tool_default_semantics_diagnostic import load_previous
from app.reference_workload.tool_fault_baseline import MODES, _sha256
from app.reference_workload.tool_fault_cases import prepare_baseline_cases
from app.reference_workload.tool_presence_diagnostic import CapturedNullable
from app.reference_workload.tool_two_stage_diagnostic import RequestCapture, configuration_for
from app.services.ticket_priority_verification import TicketPriorityVerifier
from app.services.tool_call_contract import compile_bounded_tool_call
from app.services.tool_execution import build_fault_tool_registry, execute_tool_calls
from app.services.tool_fault_scenarios import ToolFaultScenario

PREVIOUS_PATH = "artifacts/reference-workload/tool-presence-fresh-v3.json"
PREVIOUS_SHA256 = "c7d745ad01978de0ce70d8f88b20e5a383e599bfa0367a04fef291943214241a"
CASE_PATH = "reference_workload/diagnostics/ticket-priority-intent-v1.json"
SOURCES = (
    "services/ticket_priority_verification.py",
    "reference_workload/ticket_priority_diagnostic.py",
)


class IntentCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^TCI-[0-9]{3}$")
    cohort: Literal["development", "fresh"]
    stratum: str = Field(min_length=1)
    request: str = Field(min_length=1)
    expected_tool: str
    expected_action: Literal["execute", "clarify"]
    expected_arguments: dict[str, str] | None
    expected_intent: Literal["set", "omit", "unspecified", "clarify", "out_of_scope"]

    @model_validator(mode="after")
    def consistent_expectation(self):
        if (self.expected_action == "clarify") != (self.expected_arguments is None):
            raise ValueError("clarification cases must not invent expected arguments")
        if (self.expected_action == "clarify") != (self.expected_intent == "clarify"):
            raise ValueError("clarification intent and outcome must agree")
        if (self.expected_tool != "create_ticket") != (self.expected_intent == "out_of_scope"):
            raise ValueError("priority labels only cover tickets")
        if self.expected_action == "execute" and self.expected_tool == "create_ticket":
            if (self.expected_intent == "set") != ("priority" in self.expected_arguments):
                raise ValueError("only assigned priority may be present")
        return self


class IntentPack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["ticket-priority-intent-cases-v1"]
    authority: Literal["local_authored_diagnostic"]
    human_reviewed: Literal[False]
    gate_evidence: Literal[False]
    corpus_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[IntentCase, ...] = Field(min_length=1, max_length=60)

    @model_validator(mode="after")
    def unique_cases(self):
        if len({c.id for c in self.cases}) != len(self.cases) or len(
            {c.request for c in self.cases}
        ) != len(self.cases):
            raise ValueError("duplicate case IDs or requests")
        return self


def load_cases(root, registry, context):
    pack = IntentPack.model_validate_json((root / CASE_PATH).read_text("utf-8"))
    if pack.corpus_hash != context["corpus_hash"]:
        raise ValueError("intent corpus changed")
    for item in pack.cases:
        if registry.get(item.expected_tool) is None:
            raise ValueError("unknown expected tool")
        if item.expected_action == "execute":
            public, _ = prepare_baseline_cases(item, registry, context)
            expected = compile_bounded_tool_call(
                json.dumps({"tool_name": item.expected_tool, "arguments": item.expected_arguments}),
                input_payload=public.input_payload_json,
                document_context=context,
            )
            if not expected.execution_allowed or any(
                v not in item.request for v in item.expected_arguments.values()
            ):
                raise ValueError(f"invalid expected contract for {item.id}")
    return pack


class CapturedVerifier(RequestCapture, TicketPriorityVerifier):
    pass


def measured_usage(requests):
    usages = [r.get("response", {}).get("usage") for r in requests]
    if any(
        not isinstance(u, dict)
        or any(
            type(u.get(k)) is not int or u[k] < 0 for k in ("prompt_tokens", "completion_tokens")
        )
        for u in usages
    ):
        return None
    return {k: sum(u[k] for u in usages) for k in ("prompt_tokens", "completion_tokens")}


def observe_intent(item, config, registry, context, *, seed, order):
    if order not in {"registered", "reversed"}:
        raise ValueError("invalid tool order")
    public, _ = prepare_baseline_cases(item, registry, context)
    if order == "reversed":
        public.input_payload_json["available_tools"].reverse()
    generator, verifier = CapturedNullable(), CapturedVerifier()
    generator.reset_capture()
    verifier.reset_capture()
    started = time.perf_counter()
    deadline = started + generator._case_timeout_seconds(config)
    row = {"id": item.id, "seed": seed, "tool_order": order, "stratum": item.stratum}
    try:
        result = generator.run_case(configuration=config, evaluation_case=public, seed=seed)
        proposal = result.normalized_output
        guard = compile_bounded_tool_call(
            proposal, input_payload=public.input_payload_json, document_context=context
        )
        if guard.audit_record() != result.metadata["tool_call_contract"]:
            raise ValueError("proposal guard metadata mismatch")
        # Bind the local fixture to the proposed Tool, never to the evaluator's expected selection.
        execution_case = copy.copy(public)
        execution_case.expected_tool_schema_json = {"tool_name": guard.tool_name or "__invalid__"}
        check = verifier.verify(
            configuration=config,
            input_payload=public.input_payload_json,
            proposal=proposal,
            seed=seed,
            deadline=deadline,
        )
        row.update(
            proposal=proposal,
            raw_output=result.raw_output,
            metadata=result.metadata,
            public_guard=guard.audit_record(),
            verification=check,
            proposal_latency_ms=result.end_to_end_latency_ms,
        )
        row["comparison"] = (
            compare_argument_contract(proposal, item, registry, context)
            if item.expected_action == "execute"
            else None
        )
        row["traces"] = {}
        for variant, allowed in (
            ("v3", guard.execution_allowed),
            ("v3_verified", guard.execution_allowed and check["execution_allowed"]),
        ):
            reason = None if allowed else check["reason"] or "public_guard_rejected"
            row["traces"][variant] = {
                mode: execute_tool_calls(
                    execution_case,
                    proposal,
                    registry,
                    execution_block_reason=reason,
                    fault_scenario=ToolFaultScenario(mode),
                ).to_dict()
                for mode in MODES
            }
    except Exception as exc:
        row["error"] = {"type": type(exc).__name__, "message": str(exc)}
    row.update(
        proposal_requests=generator.requests,
        verification_requests=verifier.requests,
        proposal_tokens=measured_usage(generator.requests),
        verification_tokens=measured_usage(verifier.requests),
        total_latency_ms=(time.perf_counter() - started) * 1000,
    )
    return row


def summarize(rows, cases):
    lookup = {c.id: c for c in cases}
    result = {
        "observations": len(rows),
        "actionable": sum(lookup[r["id"]].expected_action == "execute" for r in rows),
        "clarification_required": sum(lookup[r["id"]].expected_action == "clarify" for r in rows),
        "errors": sum("error" in r for r in rows),
        "verification_failures": sum(
            r.get("verification", {}).get("status") == "failed" for r in rows
        ),
    }
    for variant in ("v3", "v3_verified"):
        counts = {
            k: 0
            for k in (
                "accepted",
                "exact_completed",
                "equivalent_completed",
                "unsafe_accepted",
                "clarification_blocked",
                "correct_proposal_blocked",
                "wrong_proposal_blocked",
                "intent_classification_correct",
            )
        }
        for row in rows:
            if "error" in row:
                continue
            item = lookup[row["id"]]
            comparison = row["comparison"] or {}
            base_allowed = row["public_guard"]["execution_allowed"]
            allowed = base_allowed and (variant == "v3" or row["verification"]["execution_allowed"])
            exact = comparison.get("exact_call", False)
            equivalent = comparison.get("default_equivalent_call", False)
            counts["accepted"] += allowed
            counts["exact_completed"] += allowed and exact
            counts["equivalent_completed"] += allowed and equivalent
            counts["unsafe_accepted"] += allowed and not equivalent
            counts["clarification_blocked"] += item.expected_action == "clarify" and not allowed
            counts["correct_proposal_blocked"] += base_allowed and exact and not allowed
            counts["wrong_proposal_blocked"] += base_allowed and not equivalent and not allowed
            intent = row["verification"]["intent"]
            if variant == "v3_verified":
                predicted = intent["action"] if intent else row["verification"]["status"]
                counts["intent_classification_correct"] += predicted == item.expected_intent and (
                    predicted != "set" or intent["value"] == item.expected_arguments["priority"]
                )
        result[variant] = counts
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--cohort", choices=("development", "fresh"), required=True)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    journal = args.output.with_suffix(".observations.jsonl")
    if args.output.exists() or journal.exists():
        parser.error("output or journal exists; choose a new evidence path")
    root = args.repository_root
    load_previous(root)
    previous_path = root / PREVIOUS_PATH
    if _sha256(previous_path) != PREVIOUS_SHA256:
        raise ValueError("previous v3 evidence changed")
    previous = json.loads(previous_path.read_text("utf-8"))
    if _sha256(previous_path.with_suffix(".observations.jsonl")) != previous["journal_sha256"]:
        raise ValueError("previous v3 journal changed")
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
        "document_ids": sorted({c.document_id for c in corpus.chunks}),
    }
    registry = build_fault_tool_registry()
    pack = load_cases(root, registry, context)
    cases = tuple(c for c in pack.cases if c.cohort == args.cohort)
    if not cases:
        raise ValueError("empty cohort")
    if any(
        c.request == p["request"] for c in cases if c.cohort == "fresh" for p in previous["cases"]
    ):
        raise ValueError("fresh request overlaps previous evidence")
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
        "schema_version": "ticket-priority-verification-diagnostic-v1",
        "status": "running",
        "cohort": args.cohort,
        "human_reviewed": False,
        "gate_evidence": False,
        "database_writes_performed": False,
        "production_readiness": "not_production_ready",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "previous_path": PREVIOUS_PATH,
        "previous_sha256": PREVIOUS_SHA256,
        "case_pack_path": CASE_PATH,
        "case_pack_sha256": _sha256(root / CASE_PATH),
        "cases": [c.model_dump() for c in cases],
        "document_context": context,
        "runtime": runtime,
        "matrix_entry": entry.model_dump(),
        "generation_config": config.generation_config_json,
        "source_sha256": {
            **previous["source_sha256"],
            **{name: _sha256(root / "backend/app" / name) for name in SOURCES},
        },
        "protocol": {
            "design": "one_v3_proposal_two_execution_policies",
            "classifier_input": "original_request_and_public_selected_schema_only",
            "repair": False,
            "expected_observations": len(cases) * 4,
            "seeds": [42, 43],
            "orders": ["registered", "reversed"],
            "shared_case_timeout_seconds": 120,
            "concurrency": 1,
            "sample_limit": "locally authored, repeated and not independently reviewed",
        },
        "rows": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as out:
        json.dump(report, out, ensure_ascii=False, indent=2)
    with journal.open("x", encoding="utf-8") as log:
        for item in cases:
            for order in ("registered", "reversed"):
                for seed in (42, 43):
                    row = observe_intent(item, config, registry, context, seed=seed, order=order)
                    report["rows"].append(row)
                    log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    log.flush()
                    print(
                        json.dumps(
                            {
                                "id": item.id,
                                "seed": seed,
                                "order": order,
                                "verification": row.get("verification", {}).get("reason"),
                                "error": row.get("error"),
                            }
                        ),
                        flush=True,
                    )
            args.output.write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    report.update(
        status="complete_with_errors" if any("error" in r for r in report["rows"]) else "complete",
        completed_at=dt.datetime.now(dt.UTC).isoformat(),
        journal_sha256=_sha256(journal),
        summary=summarize(report["rows"], cases),
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"sha256": _sha256(args.output), "summary": report["summary"]}), flush=True)
    return int(report["status"] != "complete")


if __name__ == "__main__":
    raise SystemExit(main())
