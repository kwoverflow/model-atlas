"""One pre-registered comparison; saved evidence only, no default or DB changes."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.metadata
import json
import platform
import time
from pathlib import Path

from app.reference_workload.manifest import file_sha256, stable_hash
from app.reference_workload.rag_bilingual_diagnostic import (
    load_inputs,
    source_inventory,
)
from app.reference_workload.rag_complementary_diagnostic import (
    load_replay as load_previous,
)
from app.services.rag_evidence_contract import parse_rag_evidence_expectation

from experiments.retrieval_research.ranker import (
    LAMBDA,
    MODEL_ID,
    MODEL_REVISION,
    OnnxRanker,
    RedundancyIndex,
    select_mmr,
    select_top,
    validate_scores,
)

VERSION = "paper-reranking-comparison-v1"
PREVIOUS_HASH = "7f7536daba6baf4c20ba2a0d30a1856f2b4d854a7a3f614ecb9f84a69c5be15a"
CANDIDATES = ("cross_encoder", "cross_encoder_mmr")


def checked_report(path, expected_hash):
    if file_sha256(path) != expected_hash:
        raise ValueError("research replay file hash mismatch")
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("schema_version") != VERSION or report.get("status") != "completed":
        raise ValueError("only completed research reports can be replayed")
    if stable_hash({k: v for k, v in report.items() if k != "content_sha256"}) != report.get(
        "content_sha256"
    ):
        raise ValueError("research replay content hash mismatch")
    return report


def public_inputs(previous, pack, corpus):
    cases = {
        c.external_case_id: c
        for c in pack.approved_cases
        if isinstance((c.reference_context or {}).get("rag"), dict)
    }
    rows = previous["retrieval"]["rows"]
    if len(rows) != 48 or len({r["external_case_id"] for r in rows}) != 48:
        raise ValueError("previous RAG coverage mismatch")
    if set(cases) != {r["external_case_id"] for r in rows}:
        raise ValueError("case population differs")
    source = {c.chunk_id: c for c in corpus.chunks}
    inputs, unique = {}, {}
    for row in rows:
        key = row["external_case_id"]
        case = cases[key]
        if row["case_sha256"] != pack.case_hashes[key]:
            raise ValueError("case hash mismatch")
        if row["query"] != case.reference_context["rag"]["query"]:
            raise ValueError("query identity mismatch")
        if not row["in_scope"]:
            continue
        translation = previous["translations"][row["query"]]
        if not translation["after_guard"]["passed"] or translation["status"] == "blocked":
            raise ValueError("guarded translation required")
        chunks = []
        for chunk in row["candidate_pool"]:
            actual = source[chunk["chunk_id"]]
            public = {k: chunk[k] for k in ("chunk_id", "document_id", "title", "text")}
            if any(getattr(actual, k) != v for k, v in public.items()):
                raise ValueError("candidate source does not match approved corpus")
            chunks.append(public)
            unique[public["chunk_id"]] = public
        validate_scores(chunks, [0.0] * len(chunks))
        inputs[key] = {"query": translation["translated_query"], "chunks": chunks}
    if len(inputs) != 22 or sum(len(v["chunks"]) for v in inputs.values()) > 1100:
        raise ValueError("ordinary candidate budget differs")
    return cases, inputs, list(unique.values())


def selection_result(chunks, indices, expectation):
    ids = [chunks[i]["chunk_id"] for i in indices]
    match = expectation.match(ids)
    return {"selected_ids": ids, "reachable": match.satisfied, "recall": match.coverage}


def summarize(rows):
    ordinary = [r for r in rows if r["in_scope"]]
    critical = [r for r in ordinary if r["criticality"] == "critical"]
    result = {}
    for name in ("baseline", "guarded_rrf", *CANDIDATES):
        result[name] = {
            "all_reachable": sum(r["variants"][name]["reachable"] for r in rows),
            "ordinary_reachable": sum(r["variants"][name]["reachable"] for r in ordinary),
            "critical_reachable": sum(r["variants"][name]["reachable"] for r in critical),
            "regressions": {},
            "gains": {},
        }
        for baseline in ("baseline", "guarded_rrf"):
            result[name]["regressions"][baseline] = [
                r["external_case_id"]
                for r in rows
                if r["variants"][baseline]["reachable"] and not r["variants"][name]["reachable"]
            ]
            result[name]["gains"][baseline] = [
                r["external_case_id"]
                for r in rows
                if not r["variants"][baseline]["reachable"] and r["variants"][name]["reachable"]
            ]
    return result


def decision(summary, failures, average_seconds):
    result = {}
    for name in CANDIDATES:
        metrics = summary[name]
        no_regressions = not any(metrics["regressions"].values())
        result[name] = {
            "promising_development_candidate": not failures
            and no_regressions
            and metrics["ordinary_reachable"] >= 12
            and metrics["critical_reachable"] >= 3
            and average_seconds < 10,
            "answer_diagnostic_eligible": not failures
            and no_regressions
            and metrics["critical_reachable"] == 5,
            "default_adoption": False,
        }
    return result


def inventory(root):
    result = source_inventory(root)
    for path in sorted((root / "experiments/retrieval_research").iterdir()):
        if path.is_file() and path.suffix in {".py", ".md", ".txt"}:
            result[path.relative_to(root).as_posix()] = file_sha256(path)
    return result


def model_inventory(path):
    return {
        name: file_sha256(path / name)
        for name in ("onnx/model.onnx", "tokenizer.json", "config.json", "README.md")
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--replay-sha256")
    args = parser.parse_args()
    journal = args.output.with_suffix(".scores.jsonl")
    if args.output.exists() or journal.exists():
        parser.error("select unused output and journal paths")
    if bool(args.replay) != bool(args.replay_sha256) or (not args.replay and not args.model_dir):
        parser.error("supply a local model directory or a pinned replay")
    root = args.repository_root.resolve()
    sources = inventory(root)
    previous = load_previous(args.previous, PREVIOUS_HASH)
    pack, bundle = load_inputs(root)
    if previous["corpus_sha256"] != bundle.corpus.corpus_hash:
        raise ValueError("corpus hash mismatch")
    cases, inputs, corpus = public_inputs(previous, pack, bundle.corpus)
    replay = checked_report(args.replay, args.replay_sha256) if args.replay else None
    if replay and (
        replay["previous_sha256"] != PREVIOUS_HASH or set(replay["score_records"]) != set(inputs)
    ):
        raise ValueError("replay inputs differ")
    files = replay["model_files"] if replay else model_inventory(args.model_dir)
    loading = time.perf_counter()
    ranker = None if replay else OnnxRanker(args.model_dir)
    redundancy = RedundancyIndex(corpus)
    setup_seconds = time.perf_counter() - loading
    report = {
        "schema_version": VERSION,
        "status": "running",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "mode": "replay" if replay else "live_cpu_scoring",
        "previous_sha256": PREVIOUS_HASH,
        "replay_sha256": args.replay_sha256,
        "source_sha256": sources,
        "corpus_sha256": bundle.corpus.corpus_hash,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "model_files": files,
        "runtime": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()},
        },
        "protocol": {
            "lambda": LAMBDA,
            "top_k": 5,
            "max_pairs": 1100,
            "sequence_length": 512,
            "window_overlap": 64,
            "max_windows": 8,
            "batch_size": 8,
            "threads": 4,
            "scoring_budget_seconds": 900,
        },
        "boundary": {
            "known_development_cases": True,
            "human_review": False,
            "new_translation_calls": 0,
            "answer_calls": 0,
            "training": False,
            "default_changed": False,
            "database_writes": False,
            "gate_promotion": False,
            "production_readiness": "not_production_ready",
        },
        "model_and_index_setup_seconds": setup_seconds,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
    records, rows = {}, []
    started = time.perf_counter()
    with journal.open("x", encoding="utf-8") as output:
        for prior in previous["retrieval"]["rows"]:
            key = prior["external_case_id"]
            variants = {}
            for old, new in (("baseline", "baseline"), ("pool_rrf", "guarded_rrf")):
                saved = prior["variants"][old]
                variants[new] = {
                    "selected_ids": [c["chunk_id"] for c in saved["chunks"]],
                    "reachable": saved["reachable"],
                    "recall": saved["recall"],
                }
            failure = None
            if prior["in_scope"]:
                payload = inputs[key]
                record = {"input_sha256": stable_hash(payload)}
                case_started = time.perf_counter()
                try:
                    if replay:
                        record = replay["score_records"][key]
                        if record["input_sha256"] != stable_hash(payload):
                            raise ValueError("score replay binding mismatch")
                        if "error" in record:
                            raise ValueError(record["error"])
                    else:
                        if time.perf_counter() - started > 900:
                            raise TimeoutError("pre-registered scoring budget exhausted")
                        record.update(
                            ranker.score(
                                **{
                                    "query": payload["query"],
                                    "chunks": payload["chunks"],
                                }
                            )
                        )
                        record["elapsed_seconds"] = time.perf_counter() - case_started
                    chunks, scores = payload["chunks"], record["scores"]
                    validate_scores(chunks, scores)
                    if len(record["window_scores"]) != len(chunks) or any(
                        not 1 <= n <= 8 or len(values) != n or max(values) != score
                        for n, values, score in zip(
                            record["window_counts"],
                            record["window_scores"],
                            scores,
                            strict=True,
                        )
                    ):
                        raise ValueError("invalid saved window scores")
                    expectation = parse_rag_evidence_expectation(
                        cases[key].reference_context["rag"]
                    )
                    variants["cross_encoder"] = selection_result(
                        chunks, select_top(chunks, scores), expectation
                    )
                    variants["cross_encoder_mmr"] = selection_result(
                        chunks,
                        select_mmr(chunks, scores, redundancy.similarities(chunks)),
                        expectation,
                    )
                except Exception as exc:
                    failure = f"{type(exc).__name__}: {exc}"
                    if replay:
                        raise ValueError(
                            "replay failed; do not treat corruption as fallback"
                        ) from exc
                    record["error"] = failure
                    record.setdefault("elapsed_seconds", time.perf_counter() - case_started)
                records[key] = record
                output.write(json.dumps({"case_id": key, **record}, ensure_ascii=False) + "\n")
                output.flush()
                print(json.dumps({"case": key, "scored": failure is None}), flush=True)
            for name in CANDIDATES:
                variants.setdefault(name, dict(variants["baseline"]))
            rows.append(
                {
                    "external_case_id": key,
                    "case_sha256": prior["case_sha256"],
                    "criticality": prior["criticality"],
                    "in_scope": prior["in_scope"],
                    "failure": failure,
                    "variants": variants,
                }
            )
    report["score_records"] = records
    report["rows"] = rows
    report["summary"] = summarize(rows)
    report["failure_count"] = sum(r["failure"] is not None for r in rows)
    report["captured_scoring_seconds"] = sum(r["elapsed_seconds"] for r in records.values())
    report["average_captured_case_seconds"] = report["captured_scoring_seconds"] / 22
    report["model_pairs_this_run"] = (
        0 if replay else sum(len(r.get("scores", [])) for r in records.values())
    )
    report["decision"] = decision(
        report["summary"],
        report["failure_count"],
        report["average_captured_case_seconds"],
    )
    unchanged = sources == inventory(root) and file_sha256(args.previous) == PREVIOUS_HASH
    if not replay:
        unchanged = unchanged and files == model_inventory(args.model_dir)
    report["source_and_model_unchanged"] = unchanged
    report["status"] = "completed" if unchanged else "invalidated"
    if not unchanged:
        report["decision"] = decision(report["summary"], 1, float("inf"))
    report["journal_sha256"] = file_sha256(journal)
    report["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["content_sha256"] = stable_hash(report)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "summary": report["summary"],
                "decision": report["decision"],
            }
        )
    )
    return 0 if unchanged else 2


if __name__ == "__main__":
    raise SystemExit(main())
