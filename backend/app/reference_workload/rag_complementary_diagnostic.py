"""Versioned term-preservation and complementary-evidence experiment; no default adoption."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

from app.reference_workload.manifest import default_repository_root, file_sha256, stable_hash
from app.reference_workload.rag_bilingual_diagnostic import (
    MODEL_DIGEST,
    load_inputs,
    source_inventory,
)
from app.reference_workload.rag_bilingual_diagnostic import (
    load_replay as load_previous,
)
from app.reference_workload.rag_grounding_diagnostic import evaluator_case
from app.reference_workload.runtime_matrix import (
    load_runtime_matrix,
    probe_runtime,
    resolve_runtime_entry,
)
from app.reference_workload.tool_two_stage_diagnostic import CapturedBaseline, configuration_for
from app.services.inference_adapters.cited_rag import ORDINARY_RAG_CATEGORIES
from app.services.rag_bilingual import bilingual_rankings
from app.services.rag_complementary import (
    MAX_SELECTION_CALLS,
    MODEL,
    SELECTION_PROMPT,
    TRANSLATION_PROMPT,
    candidate_pool,
    parse_guarded_translation,
    public_rankings,
    select_complementary,
    term_guard,
    translation_request,
)
from app.services.rag_complementary import (
    VERSION as CANDIDATE_VERSION,
)
from app.services.rag_evaluation import prepare_rag_execution
from app.services.rag_evidence_contract import parse_rag_evidence_expectation

VERSION = "rag-complementary-diagnostic-v1"
PREVIOUS = "artifacts/rag-bilingual/2026-09-11/live.json"
PREVIOUS_HASH = "ed0dde864fedd8417e054c34a084890062079cfcc798bb9ac26febd8b23941e8"
VARIANTS = ("baseline", "previous_bilingual", "guarded_bilingual", "pool_rrf", "complementary")


class NativeCalls:
    def __init__(self, config, base_url, journal, replay=None):
        self.config, self.base_url, self.journal = config, base_url, journal
        self.replay = replay
        self.records = []

    def call(self, body: dict) -> dict:
        index = len(self.records)
        record = {"index": index, "request_sha256": stable_hash(body), "body": copy.deepcopy(body)}
        if self.replay is not None:
            if index >= len(self.replay) or self.replay[index]["body"] != body:
                raise ValueError("replay request order or content mismatch")
            saved = self.replay[index]
            if saved["request_sha256"] != stable_hash(body):
                raise ValueError("replay request hash mismatch")
            record = copy.deepcopy(saved)
        else:
            adapter = CapturedBaseline()
            adapter.reset_capture()
            started = time.perf_counter()
            try:
                record["response"] = adapter._post_json(
                    self.config,
                    self.base_url,
                    "/api/chat",
                    body,
                    deadline=time.perf_counter() + 120,
                )
            except Exception as exc:
                record["error"] = {"type": type(exc).__name__, "message": str(exc)}
            record["latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        self.records.append(record)
        self.journal.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.journal.flush()
        if "error" in record:
            raise RuntimeError("recorded native request failed: " + record["error"]["message"])
        return record["response"]


def guarded_translations(previous: dict, call) -> dict:
    rows = {}
    for query, old in sorted(previous["translations"].items()):
        translated = old.get("translated_query") if old["status"] == "valid" else ""
        before = term_guard(query, translated)
        row = {
            "query": query,
            "original_translation": translated,
            "before_guard": before,
            "repair_attempted": not translated or not before["passed"],
        }
        if row["repair_attempted"]:
            try:
                translated = parse_guarded_translation(call(translation_request(query)), query)
                row["status"] = "accepted_after_one_retry"
            except Exception as exc:
                row.update(
                    status="blocked", error={"type": type(exc).__name__, "message": str(exc)}
                )
                translated = ""
        else:
            row["status"] = "accepted_from_previous"
        row["translated_query"] = translated
        row["after_guard"] = term_guard(query, translated)
        rows[query] = row
    return rows


def compare(pack, bundle, previous, translations, call, progress=None) -> dict:
    expected = {
        c.reference_context["rag"]["query"]
        for c in pack.approved_cases
        if c.category in ORDINARY_RAG_CATEGORIES
    }
    if set(translations) != expected or set(previous["translations"]) != expected:
        raise ValueError("translation coverage differs from approved queries")
    previous_rows = {r["external_case_id"]: r for r in previous["retrieval"]["rows"]}
    rows = []
    for case in pack.approved_cases:
        rag = (case.reference_context or {}).get("rag")
        if not isinstance(rag, dict):
            continue
        prior = previous_rows.get(case.external_case_id)
        if prior is None or prior["case_sha256"] != pack.case_hashes[case.external_case_id]:
            raise ValueError("previous result case identity mismatch")
        baseline = prepare_rag_execution(
            SimpleNamespace(retrieval_config_json={"top_k": 5, "min_score": 0.0}),
            evaluator_case(case),
            bundle.registry,
        )
        if baseline is None or baseline.retrieval_trace.status == "invalid_config":
            raise ValueError("invalid baseline preparation")
        trace = baseline.retrieval_trace
        applied = case.category in ORDINARY_RAG_CATEGORIES
        rankings = {v: trace.retrieved_chunks for v in VARIANTS if v != "previous_bilingual"}
        pool, stages, failure = [], [], None
        guard = translations[trace.query] if applied else None
        if applied and guard["status"] != "blocked":
            translated = guard["translated_query"]
            if not term_guard(trace.query, translated)["passed"]:
                raise ValueError("unguarded translation cannot enter ranking")
            rankings["guarded_bilingual"] = bilingual_rankings(
                corpus=bundle.corpus,
                query=trace.query,
                translated_query=translated,
            )["bilingual_rrf"]
            pool = candidate_pool(
                corpus=bundle.corpus,
                query=trace.query,
                translated_query=translated,
                baseline_chunks=trace.retrieved_chunks,
            )
            rankings["pool_rrf"] = pool[:5]
            try:
                rankings["complementary"], stages = select_complementary(
                    trace.query, translated, pool, call
                )
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
        elif applied:
            failure = {
                "type": "TranslationGuardBlocked",
                "message": "required literals were not preserved",
            }
        expectation = parse_rag_evidence_expectation(rag)
        variants = {}
        for variant, chunks in rankings.items():
            match = expectation.match(c.chunk_id for c in chunks)
            variants[variant] = {
                "chunks": public_rankings(chunks),
                "reachable": match.satisfied,
                "recall": round(match.coverage, 6),
            }
        variants["previous_bilingual"] = {
            k: prior["variants"]["bilingual_rrf"][k] for k in ("chunks", "reachable", "recall")
        }
        pool_match = expectation.match(c.chunk_id for c in pool)
        rows.append(
            {
                "external_case_id": case.external_case_id,
                "case_sha256": pack.case_hashes[case.external_case_id],
                "category": case.category,
                "criticality": case.criticality,
                "query": trace.query,
                "in_scope": applied,
                "variants": variants,
                "candidate_pool": public_rankings(pool),
                "pool_reachable": pool_match.satisfied if applied else None,
                "selection_stages": stages,
                "candidate_failure": failure,
                "fallback_preparation_identical": not applied,
            }
        )
        if progress:
            progress(rows[-1])
    summaries = {}
    for name in VARIANTS:
        ordinary = [r for r in rows if r["in_scope"]]
        critical = [r for r in ordinary if r["criticality"] == "critical"]
        regressions = [
            r["external_case_id"]
            for r in rows
            if r["variants"]["baseline"]["reachable"] and not r["variants"][name]["reachable"]
        ]
        gains = [
            r["external_case_id"]
            for r in rows
            if not r["variants"]["baseline"]["reachable"] and r["variants"][name]["reachable"]
        ]
        summaries[name] = {
            "reachable": sum(r["variants"][name]["reachable"] for r in rows),
            "ordinary_reachable": sum(r["variants"][name]["reachable"] for r in ordinary),
            "critical_ordinary_reachable": sum(r["variants"][name]["reachable"] for r in critical),
            "gains": gains,
            "regressions": regressions,
        }
    return {
        "case_count": len(rows),
        "ordinary_count": len(ordinary),
        "critical_ordinary_count": len(critical),
        "pool_reachable_count": sum(r["pool_reachable"] is True for r in rows),
        "candidate_failure_count": sum(r["candidate_failure"] is not None for r in rows),
        "variants": summaries,
        "rows": rows,
    }


def load_replay(path: Path, expected_hash: str):
    if file_sha256(path) != expected_hash:
        raise ValueError("replay file hash mismatch")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema_version") != VERSION or report.get("status") != "completed":
        raise ValueError("only completed complementary reports may be replayed")
    if report.get("content_sha256") != stable_hash(
        {k: v for k, v in report.items() if k != "content_sha256"}
    ):
        raise ValueError("replay content hash mismatch")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument(
        "--previous", type=Path, help="Pinned prior report in a separate artifact mount"
    )
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--replay-sha256")
    args = parser.parse_args()
    journal = args.output.with_suffix(".requests.jsonl")
    if args.output.exists() or journal.exists():
        parser.error("output or journal exists; select a new path")
    if bool(args.replay) != bool(args.replay_sha256):
        parser.error("replay requires a path and pinned SHA-256")
    url = urlparse(args.base_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"localhost", "127.0.0.1", "ollama"}
        or (url.username or url.password or url.query or url.fragment or url.path not in {"", "/"})
    ):
        parser.error("only a local Ollama root URL is allowed")
    root = args.repository_root.resolve()
    previous_path = args.previous if args.previous is not None else root / PREVIOUS
    inventory = source_inventory(root)
    pack, bundle = load_inputs(root)
    previous = load_previous(previous_path, PREVIOUS_HASH)
    if previous["corpus_sha256"] != bundle.corpus.corpus_hash:
        raise ValueError("previous corpus differs from approved corpus")
    replay = load_replay(args.replay, args.replay_sha256) if args.replay else None
    entry = next(
        e
        for e in load_runtime_matrix(root / "reference_workload/runtime_matrix.json").entries
        if e.name == "medium-candidate"
    )
    env = {entry.base_url_env: args.base_url.rstrip("/"), entry.model_env: MODEL}
    resolved = resolve_runtime_entry(entry, environment=env)
    runtime = (
        replay["runtime_before"]
        if replay
        else probe_runtime(resolved, environment=env).model_dump()
    )
    if runtime["digest"] != MODEL_DIGEST:
        raise ValueError("unexpected local model digest")
    report = {
        "schema_version": VERSION,
        "status": "running",
        "revision": "1.0.5",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "previous_file_sha256": PREVIOUS_HASH,
        "corpus_sha256": bundle.corpus.corpus_hash,
        "source_sha256": inventory,
        "runtime_before": runtime,
        "mode": "offline_replay" if replay else "live_guard_and_selection",
        "replay_source_sha256": args.replay_sha256,
        "protocol": {
            "candidate_version": CANDIDATE_VERSION,
            "translation_prompt": TRANSLATION_PROMPT,
            "selection_prompt": SELECTION_PROMPT,
            "pool_size": 50,
            "top_k": 5,
            "retry_limit": 1,
            "max_selection_calls_per_case": MAX_SELECTION_CALLS,
            "context_tokens": 16384,
            "request_byte_budget": 12000,
            "max_output_tokens": 256,
            "seed": 42,
            "temperature": 0,
            "concurrency": 1,
            "timeout_seconds": 120,
            "truncate": False,
            "labels_visible_to_candidate": False,
            "variants": list(VARIANTS),
            "failure_policy": "record failure, retain baseline, block advancement",
        },
        "boundary": {
            "default_changed": False,
            "database_writes": False,
            "task_answer_calls": 0,
            "human_review": False,
            "gate_promotion": False,
            "production_readiness": "not_production_ready",
            "population": "known development cases, not a holdout",
            "selection_is_not_semantic_approval": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    with journal.open("x", encoding="utf-8") as output:
        calls = NativeCalls(
            configuration_for(entry, resolved, {}),
            resolved.base_url,
            output,
            replay["requests"] if replay else None,
        )
        report["translations"] = guarded_translations(previous, calls.call)
        report["repair_request_count"] = len(calls.records)
        report["retrieval"] = compare(
            pack,
            bundle,
            previous,
            report["translations"],
            calls.call,
            progress=lambda r: print(
                json.dumps(
                    {
                        "case": r["external_case_id"],
                        "in_scope": r["in_scope"],
                        "failure": r["candidate_failure"],
                        "requests": len(calls.records),
                    }
                ),
                flush=True,
            ),
        )
        if replay and len(calls.records) != len(replay["requests"]):
            raise ValueError("replay has unused requests")
        report["requests"] = calls.records
    report["runtime_after"] = (
        runtime if replay else probe_runtime(resolved, environment=env).model_dump()
    )
    report["source_unchanged"] = (
        inventory == source_inventory(root) and file_sha256(previous_path) == PREVIOUS_HASH
    )
    report["runtime_unchanged"] = runtime == report["runtime_after"]
    report["request_journal_sha256"] = file_sha256(journal)
    report["model_calls_this_run"] = 0 if replay else len(report["requests"])
    report["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["status"] = (
        "completed" if report["source_unchanged"] and report["runtime_unchanged"] else "invalidated"
    )
    result = report["retrieval"]
    report["answer_diagnostic_eligible"] = (
        not result["candidate_failure_count"]
        and not result["variants"]["complementary"]["regressions"]
        and result["variants"]["complementary"]["critical_ordinary_reachable"] == 5
    )
    report["content_sha256"] = stable_hash(report)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(
        json.dumps(
            {
                "status": report["status"],
                "variants": result["variants"],
                "candidate_failures": result["candidate_failure_count"],
                "answer_diagnostic_eligible": report["answer_diagnostic_eligible"],
            }
        )
    )
    return 0 if report["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
