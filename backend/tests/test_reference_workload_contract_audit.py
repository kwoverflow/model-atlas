from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.contract_audit import (
    RetrievalContractAuditError,
    build_retrieval_contract_audit,
    write_retrieval_contract_audit,
)
from app.reference_workload.corpus import build_reference_corpus

P0_AGENT_CASE_IDS = [
    "KO-AGENT-001",
    "KO-RAG-TOOL-001",
    "KO-RAG-TOOL-002",
    "KO-RAG-TOOL-003",
]


def _inputs():
    corpus_bundle = build_reference_corpus()
    case_pack = load_reference_case_pack(corpus_bundle=corpus_bundle)
    return corpus_bundle, case_pack


def test_retrieval_contract_audit_exposes_unreachable_p0_cases() -> None:
    corpus_bundle, case_pack = _inputs()

    report = build_retrieval_contract_audit(
        case_pack=case_pack,
        corpus_bundle=corpus_bundle,
        case_ids=P0_AGENT_CASE_IDS,
    )

    assert report["summary"] == {
        "reachable_case_count": 0,
        "blocked_case_count": 4,
        "critical_blocked_case_count": 4,
        "status": "blocked",
    }
    assert report["evidence_boundary"] == {
        "mutates_case_contracts": False,
        "mutates_historical_results": False,
        "authoritative_portfolio_evidence": False,
        "production_readiness": "not_production_ready",
    }
    expected_ranks = {
        "KO-RAG-TOOL-001": 8,
        "KO-RAG-TOOL-002": 40,
        "KO-RAG-TOOL-003": 14,
        "KO-AGENT-001": 15,
    }
    for row in report["cases"]:
        assert row["top_k"] == 5
        assert row["retrieval_recall"] == 0.0
        assert row["contract_reachable"] is False
        assert list(row["expected_chunk_ranks"].values()) == [
            expected_ranks[row["external_case_id"]]
        ]


def test_retrieval_contract_audit_is_stable_and_writable(tmp_path: Path) -> None:
    corpus_bundle, case_pack = _inputs()
    first = build_retrieval_contract_audit(
        case_pack=case_pack,
        corpus_bundle=corpus_bundle,
        case_ids=P0_AGENT_CASE_IDS,
    )
    second = build_retrieval_contract_audit(
        case_pack=case_pack,
        corpus_bundle=corpus_bundle,
        case_ids=P0_AGENT_CASE_IDS,
    )
    output = tmp_path / "retrieval-contract-audit.json"

    write_retrieval_contract_audit(output, first)

    assert first["report_sha256"] == second["report_sha256"]
    assert json.loads(output.read_text(encoding="utf-8")) == first


@pytest.mark.parametrize(
    "case_ids, message",
    [
        (["UNKNOWN-001"], "were not found"),
        (["KO-AGENT-001", "KO-AGENT-001"], "must not contain duplicates"),
    ],
)
def test_retrieval_contract_audit_rejects_invalid_case_ids(
    case_ids: list[str],
    message: str,
) -> None:
    corpus_bundle, case_pack = _inputs()

    with pytest.raises(RetrievalContractAuditError, match=message):
        build_retrieval_contract_audit(
            case_pack=case_pack,
            corpus_bundle=corpus_bundle,
            case_ids=case_ids,
        )
