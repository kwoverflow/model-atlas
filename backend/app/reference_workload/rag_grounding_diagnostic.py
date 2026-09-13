"""Isolated retrieval and paired-citation ablation; no application database writes."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root, stable_hash
from app.reference_workload.runtime_matrix import (
    load_runtime_matrix,
    probe_runtime,
    resolve_runtime_entry,
)
from app.reference_workload.tool_two_stage_diagnostic import (
    CapturedBaseline,
    RequestCapture,
    configuration_for,
)
from app.services.inference_adapters.cited_rag import ORDINARY_RAG_CATEGORIES, CitedRagAdapter
from app.services.rag_bm25 import RETRIEVER_VERSION, rank_bm25
from app.services.rag_evaluation import (
    RagPreparation,
    evaluate_rag_output,
    prepare_rag_execution,
)
from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    parse_rag_evidence_expectation,
)

VARIANTS = ("baseline", "bm25", "paired", "bm25_paired")
REVISION = "reference_workload/revisions/1.0.4"


class CapturedCitedRag(RequestCapture, CitedRagAdapter):
    pass


def evaluator_case(case):
    return SimpleNamespace(
        external_case_id=case.external_case_id,
        category=case.category,
        title=case.title,
        input_payload_json=copy.deepcopy(case.input_payload),
        reference_context_json=copy.deepcopy(case.reference_context),
        expected_output_json=copy.deepcopy(case.expected_output),
        expected_tool_schema_json=copy.deepcopy(case.expected_tool_schema),
    )


def prepare_candidate(baseline: RagPreparation, *, corpus, category: str) -> RagPreparation:
    if category not in ORDINARY_RAG_CATEGORIES:
        return baseline
    trace = baseline.retrieval_trace
    if trace.status == "invalid_config":
        raise ValueError("cannot run candidate against an invalid baseline configuration")
    if trace.min_score != 0:
        raise ValueError("BM25 diagnostic requires min_score=0; score scales are different")
    started = time.perf_counter()
    chunks = rank_bm25(corpus=corpus, query=trace.query, top_k=trace.top_k)
    elapsed = (time.perf_counter() - started) * 1000
    # Labels are evaluated only after the label-blind ranker has returned its ranking.
    expectation = parse_rag_evidence_expectation(
        {
            "relevant_chunk_ids": trace.expected_relevant_chunk_ids,
            "evidence_contract_version": trace.evidence_contract_version,
            **(
                {"acceptable_evidence_groups": trace.acceptable_evidence_groups}
                if trace.evidence_contract_version == ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
                else {}
            ),
        }
    )
    ids = {chunk.chunk_id for chunk in chunks}
    match = expectation.match(ids)
    candidate_trace = replace(
        trace,
        retriever_id="sqlite_bm25_ko_bigram",
        retriever_version=RETRIEVER_VERSION,
        retrieved_chunks=chunks,
        retrieval_latency_ms=round(elapsed, 3),
        relevant_retrieved_chunk_ids=[i for i in trace.expected_relevant_chunk_ids if i in ids],
        matched_acceptable_chunk_ids=[i for i in expectation.acceptable_chunk_ids if i in ids],
        retrieval_recall=round(match.coverage, 6),
        retrieval_contract_satisfied=match.satisfied,
        satisfied_evidence_group_index=match.group_index,
        status="success" if chunks else "empty",
        errors=[],
        evidence_selection={},
        selected_relevant_chunk_ids=[],
        selected_acceptable_chunk_ids=[],
        evidence_selection_recall=0.0,
        evidence_selection_contract_satisfied=False,
        satisfied_selection_group_index=None,
    )
    context = {
        "query": trace.query,
        "corpus_id": trace.corpus_id,
        "corpus_version": trace.corpus_version,
        "retriever_id": candidate_trace.retriever_id,
        "retriever_version": RETRIEVER_VERSION,
        "score_semantics": "positive_bm25_not_probability",
        "retrieved_chunks": [asdict(chunk) for chunk in chunks],
    }
    return RagPreparation(
        retrieval_trace=candidate_trace,
        adapter_input_payload={"query": trace.query, "rag_context": context},
        adapter_reference_context={"rag_context": context},
    )


def public_case(case, preparation):
    return SimpleNamespace(
        external_case_id=case.external_case_id,
        category=case.category,
        title=case.title,
        input_payload_json=copy.deepcopy(preparation.adapter_input_payload),
        reference_context_json=copy.deepcopy(preparation.adapter_reference_context),
        # An empty shape marker enables the existing adapter's JSON mode without labels.
        expected_output_json={},
        expected_tool_schema_json=None,
    )


def compare_retrieval(case_pack, bundle, config):
    rows, preparations = [], {}
    for case in case_pack.approved_cases:
        if not isinstance((case.reference_context or {}).get("rag"), dict):
            continue
        baseline = prepare_rag_execution(config, evaluator_case(case), bundle.registry)
        if baseline is None or baseline.retrieval_trace.status == "invalid_config":
            raise ValueError(f"invalid RAG preparation for {case.external_case_id}")
        candidate = prepare_candidate(baseline, corpus=bundle.corpus, category=case.category)
        preparations[case.external_case_id] = (baseline, candidate)
        old, new = baseline.retrieval_trace, candidate.retrieval_trace
        row = {
            "external_case_id": case.external_case_id,
            "category": case.category,
            "criticality": case.criticality,
            "case_sha256": case_pack.case_hashes[case.external_case_id],
            "candidate_applied": case.category in ORDINARY_RAG_CATEGORIES,
            "baseline": old.to_dict(),
            "candidate": new.to_dict(),
            "pass_to_fail": old.retrieval_contract_satisfied
            and not new.retrieval_contract_satisfied,
            "fail_to_pass": not old.retrieval_contract_satisfied
            and new.retrieval_contract_satisfied,
            "fallback_context_identical": baseline == candidate if baseline is candidate else None,
        }
        rows.append(row)
    return {
        "case_count": len(rows),
        "applied_count": sum(r["candidate_applied"] for r in rows),
        "baseline_reachable": sum(r["baseline"]["retrieval_contract_satisfied"] for r in rows),
        "candidate_reachable": sum(r["candidate"]["retrieval_contract_satisfied"] for r in rows),
        "pass_to_fail": sum(r["pass_to_fail"] for r in rows),
        "fail_to_pass": sum(r["fail_to_pass"] for r in rows),
        "rows": rows,
    }, preparations


def observe(case, config, preparation, *, variant, seed):
    if variant not in VARIANTS:
        raise ValueError("unknown diagnostic variant")
    adapter = CapturedCitedRag() if variant in {"paired", "bm25_paired"} else CapturedBaseline()
    adapter.reset_capture()
    row = {"external_case_id": case.external_case_id, "variant": variant, "seed": seed}
    try:
        result = adapter.run_case(
            configuration=config, evaluation_case=public_case(case, preparation), seed=seed
        )
        trace = evaluate_rag_output(
            normalized_output=result.normalized_output,
            retrieval=preparation.retrieval_trace,
            expected_output=case.expected_output,
            answer_contract=preparation.answer_contract,
        )
        pair_contract = result.metadata.get("paired_quote_contract")
        row.update(
            raw_output=result.raw_output,
            normalized_output=result.normalized_output,
            metadata=result.metadata,
            evaluation=trace.to_dict(),
            passed=trace.successful and result.error_type is None,
            paired_quote_valid=pair_contract["valid"] if pair_contract else None,
            error_type=result.error_type,
        )
    except Exception as exc:
        row.update(passed=False, error={"type": type(exc).__name__, "message": str(exc)})
    row["requests"] = adapter.requests
    row["request_contract_valid"] = bool(adapter.requests) and all(
        request["body"].get("response_format", {}).get("type") == "json_schema"
        for request in adapter.requests
    )
    return row


def summarize_observations(rows):
    return {
        variant: {
            "count": len(selected := [row for row in rows if row["variant"] == variant]),
            "passed": sum(row["passed"] for row in selected),
            "retrieval_satisfied": sum(
                row.get("evaluation", {})
                .get("retrieval", {})
                .get("retrieval_contract_satisfied", False)
                for row in selected
            ),
            "citation_satisfied": sum(
                row.get("evaluation", {}).get("citation_contract_satisfied", False)
                for row in selected
            ),
            "required_facts_satisfied": sum(
                row.get("evaluation", {}).get("required_fact_contract_satisfied", False)
                for row in selected
            ),
            "paired_quote_valid": sum(row.get("paired_quote_valid") is True for row in selected),
            "errors": sum(bool(row.get("error") or row.get("error_type")) for row in selected),
        }
        for variant in VARIANTS
    }


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_inventory(root):
    paths = list((root / "backend/app").rglob("*.py"))
    paths += list((root / REVISION).glob("*.json*"))
    paths += [root / "reference_workload/runtime_matrix.json"]
    return {path.relative_to(root).as_posix(): file_sha256(path) for path in sorted(paths)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--live", action="store_true", help="Run bounded serial local model calls")
    parser.add_argument("--variant", action="append", choices=VARIANTS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    variants = tuple(args.variant or ("baseline", "paired"))
    if len(set(variants)) != len(variants):
        parser.error("variants must not contain duplicates")
    journal = args.output.with_suffix(".observations.jsonl")
    if args.output.exists() or journal.exists():
        parser.error("output or journal exists; choose a new evidence path")
    root = args.repository_root.resolve()
    inventory = source_inventory(root)
    bundle = build_reference_corpus(root / REVISION / "manifest.json", repository_root=root)
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=root / REVISION / "cases.jsonl",
        review_manifest_path=root / REVISION / "review_manifest.jsonl",
    )
    matrix = load_runtime_matrix(root / "reference_workload/runtime_matrix.json")
    entry = next(e for e in matrix.entries if e.name == "medium-candidate")
    environment = {entry.base_url_env: args.base_url, entry.model_env: "qwen2.5:1.5b"}
    resolved = resolve_runtime_entry(entry, environment=environment)
    config = configuration_for(entry, resolved, {})
    config.generation_config_json = {"temperature": 0, "max_tokens": 768}
    config.retrieval_config_json = {"top_k": 5, "min_score": 0.0}
    retrieval, preparations = compare_retrieval(pack, bundle, config)
    live_cases = [
        case
        for case in pack.approved_cases
        if case.category in ORDINARY_RAG_CATEGORIES and case.criticality == "critical"
    ]
    if len(live_cases) != 5:
        raise ValueError("protocol requires exactly five ordinary critical RAG cases")
    report = {
        "schema_version": "rag-grounding-diagnostic-v2",
        "status": "running",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "gate_evidence": False,
        "human_reviewed": False,
        "application_database_writes": 0,
        "production_readiness": "not_production_ready",
        "source_sha256": inventory,
        "sqlite_version": sqlite3.sqlite_version,
        "corpus": bundle.corpus.summary(),
        "retrieval_comparison": retrieval,
        "runtime": probe_runtime(resolved, environment=environment).model_dump()
        if args.live
        else None,
        "protocol": {
            "live": args.live,
            "variants": list(variants),
            "seed": 42,
            "trials": 1,
            "expected_observations": len(live_cases) * len(variants) if args.live else 0,
            "generation": config.generation_config_json,
            "matrix_entry": entry.model_dump(),
            "matrix_context_length_declared": entry.context_length,
            "effective_context_length_verified": False,
            "variant_order": "rotate by case index",
            "concurrency": 1,
            "labels_available_to_ranker_or_adapter": False,
            "ordinary_rag_only": True,
            "candidate_promoted": False,
        },
        "label_source_review_material": [
            {
                "case": case.model_dump(mode="json"),
                "expected_sources": [
                    chunk.to_dict()
                    for chunk in bundle.corpus.chunks
                    if chunk.chunk_id
                    in parse_rag_evidence_expectation(
                        case.reference_context["rag"]
                    ).acceptable_chunk_ids
                ],
            }
            for case in live_cases
        ],
        "limitations": [
            "Known development cases, not a held-out or human-reviewed evaluation.",
            "BM25 scores are not comparable to overlap scores; minimum score is zero.",
            "Paired quotes prove exact source provenance, not free-form answer entailment.",
            "Old citation scores measure approved chunk-ID membership, not semantic truth.",
            "One model/configuration and seed; no production or quality generalization.",
            "768-token contemporaneous controls are not comparable to old 384-token canaries.",
            "Scope/refusal fallback is unchanged; no fresh live measurements in those categories.",
        ],
        "rows": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, indent=2)
    with journal.open("x", encoding="utf-8") as log:
        if args.live:
            for index, case in enumerate(live_cases):
                offset = index % len(variants)
                order = variants[offset:] + variants[:offset]
                for variant in order:
                    baseline, candidate = preparations[case.external_case_id]
                    row = observe(
                        case,
                        config,
                        candidate if variant in {"bm25", "bm25_paired"} else baseline,
                        variant=variant,
                        seed=42,
                    )
                    row["execution_order"] = list(order)
                    report["rows"].append(row)
                    log.write(json.dumps(row, ensure_ascii=False) + "\n")
                    log.flush()
                    print(
                        json.dumps(
                            {
                                key: row.get(key)
                                for key in (
                                    "external_case_id",
                                    "variant",
                                    "passed",
                                    "paired_quote_valid",
                                    "error",
                                )
                            }
                        ),
                        flush=True,
                    )
    report["source_unchanged_during_run"] = inventory == source_inventory(root)
    report["runtime_after"] = (
        probe_runtime(resolved, environment=environment).model_dump() if args.live else None
    )
    report["runtime_unchanged"] = report["runtime_after"] == report["runtime"]
    report["status"] = (
        "complete"
        if (
            report["source_unchanged_during_run"]
            and report["runtime_unchanged"]
            and len(report["rows"]) == report["protocol"]["expected_observations"]
            and all(row["request_contract_valid"] for row in report["rows"])
        )
        else "invalidated"
    )
    report["summary"] = summarize_observations(report["rows"])
    report["journal_sha256"] = file_sha256(journal)
    report["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["content_sha256"] = stable_hash(report)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"status": report["status"], "summary": report["summary"]}), flush=True)
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
