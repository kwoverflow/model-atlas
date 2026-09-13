from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.reference_workload.cases import ReferenceCasePack
from app.reference_workload.contracts import REFERENCE_WORKLOAD_SLUG
from app.reference_workload.corpus import ReferenceCorpusBundle
from app.reference_workload.manifest import canonical_json, stable_hash
from app.services.rag_evaluation import retrieve
from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    parse_rag_evidence_expectation,
)

RETRIEVAL_CONTRACT_AUDIT_VERSION = "model-atlas-reference-retrieval-contract-audit-v2"


class RetrievalContractAuditError(RuntimeError):
    pass


def build_retrieval_contract_audit(
    *,
    case_pack: ReferenceCasePack,
    corpus_bundle: ReferenceCorpusBundle,
    case_ids: list[str] | None = None,
) -> dict[str, Any]:
    requested_case_ids = case_ids or []
    if len(requested_case_ids) != len(set(requested_case_ids)):
        raise RetrievalContractAuditError("retrieval audit case IDs must not contain duplicates")
    requested_ids = set(requested_case_ids)
    known_ids = {case.external_case_id for case in case_pack.cases}
    missing_ids = sorted(requested_ids - known_ids)
    if missing_ids:
        raise RetrievalContractAuditError(
            "retrieval audit case IDs were not found: " + ", ".join(missing_ids)
        )
    rows: list[dict[str, Any]] = []
    for case in case_pack.cases:
        if requested_ids and case.external_case_id not in requested_ids:
            continue
        reference = case.reference_context or {}
        rag = reference.get("rag") if isinstance(reference.get("rag"), dict) else None
        if rag is None:
            continue
        query = str(rag.get("query") or "").strip()
        expectation = parse_rag_evidence_expectation(rag)
        expected_ids = list(expectation.primary_chunk_ids)
        acceptable_groups = [list(group) for group in expectation.acceptable_groups]
        top_k = int(rag.get("top_k") or 5)
        min_score = float(rag.get("minimum_score") or 0.0)
        contract_trace = retrieve(
            corpus=corpus_bundle.corpus,
            query=query,
            relevant_chunk_ids=expected_ids,
            acceptable_evidence_groups=(
                acceptable_groups
                if expectation.contract_version == ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
                else None
            ),
            evidence_contract_version=expectation.contract_version,
            top_k=top_k,
            min_score=min_score,
        )
        ranking_trace = retrieve(
            corpus=corpus_bundle.corpus,
            query=query,
            relevant_chunk_ids=expected_ids,
            acceptable_evidence_groups=(
                acceptable_groups
                if expectation.contract_version == ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
                else None
            ),
            evidence_contract_version=expectation.contract_version,
            top_k=len(corpus_bundle.corpus.chunks),
            min_score=0.0,
        )
        ranks = {
            chunk_id: next(
                (
                    chunk.rank
                    for chunk in ranking_trace.retrieved_chunks
                    if chunk.chunk_id == chunk_id
                ),
                None,
            )
            for chunk_id in expectation.acceptable_chunk_ids
        }
        rows.append(
            {
                "external_case_id": case.external_case_id,
                "case_sha256": case_pack.case_hashes[case.external_case_id],
                "title": case.title,
                "category": case.category,
                "criticality": case.criticality,
                "query": query,
                "top_k": top_k,
                "minimum_score": min_score,
                "expected_chunk_ids": expected_ids,
                "evidence_contract_version": expectation.contract_version,
                "acceptable_evidence_groups": acceptable_groups,
                "acceptable_chunk_ids": list(expectation.acceptable_chunk_ids),
                "expected_chunk_ranks": ranks,
                "retrieved_chunk_ids": [
                    chunk.chunk_id for chunk in contract_trace.retrieved_chunks
                ],
                "retrieval_recall": contract_trace.retrieval_recall,
                "contract_reachable": contract_trace.retrieval_contract_satisfied,
                "satisfied_evidence_group_index": (
                    contract_trace.satisfied_evidence_group_index
                ),
                "matched_acceptable_chunk_ids": (
                    contract_trace.matched_acceptable_chunk_ids
                ),
                "retriever_id": contract_trace.retriever_id,
                "retriever_version": contract_trace.retriever_version,
            }
        )
    blocked = [row for row in rows if not row["contract_reachable"]]
    critical_blocked = [row for row in blocked if row["criticality"] == "critical"]
    report: dict[str, Any] = {
        "schema_version": RETRIEVAL_CONTRACT_AUDIT_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "workload_slug": REFERENCE_WORKLOAD_SLUG,
        "corpus_sha256": corpus_bundle.corpus.corpus_hash,
        "scope": {
            "requested_case_ids": sorted(requested_ids),
            "rag_case_count": len(rows),
        },
        "summary": {
            "reachable_case_count": len(rows) - len(blocked),
            "blocked_case_count": len(blocked),
            "critical_blocked_case_count": len(critical_blocked),
            "status": "blocked" if blocked else "pass",
        },
        "cases": rows,
        "evidence_boundary": {
            "mutates_case_contracts": False,
            "mutates_historical_results": False,
            "authoritative_portfolio_evidence": False,
            "production_readiness": "not_production_ready",
        },
    }
    report["report_sha256"] = stable_hash(
        {key: value for key, value in report.items() if key != "generated_at"}
    )
    return report


def write_retrieval_contract_audit(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(f"{canonical_json(report)}\n", encoding="utf-8")
    temporary.replace(path)
