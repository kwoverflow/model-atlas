import json
from pathlib import Path

from app.reference_workload.case_revision_review import (
    CASE_REVISION_ATTESTATION_VERSION,
)
from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root, file_sha256
from app.services.rag_answer_contract import compile_bounded_rag_answer
from app.services.rag_evaluation import evaluate_rag_output, retrieve
from app.services.rag_evidence_contract import parse_rag_evidence_expectation
from app.services.rag_evidence_selection import EvidenceCandidate, select_evidence
from app.services.rag_semantic_contract import (
    ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
    parse_rag_semantic_expectation,
)

EXPECTED_CASE_IDS = {"KO-RAG-SCOPE-002", "KO-RAG-SCOPE-003"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_checked_in_1_0_4_revision_is_reviewed_finalized_and_reachable() -> None:
    root = default_repository_root()
    revision = root / "reference_workload" / "revisions" / "1.0.4"
    source = root / "reference_workload" / "revisions" / "1.0.3"
    report = _load_json(revision / "revision_report.json")
    audit = _load_json(revision / "retrieval_contract_audit.json")
    finalization = _load_json(revision / "finalization_report.json")
    review_html = (revision / "revision_review.html").read_text(encoding="utf-8")

    assert report["schema_version"] == "model-atlas-reference-case-pack-revision-report-v3"
    assert report["source_workload_version"] == "1.0.3"
    assert report["summary"]["changed_case_count"] == 2
    assert report["summary"]["retained_approval_count"] == 62
    assert report["summary"]["pending_review_count"] == 2
    assert report["summary"]["portfolio_ready"] is False
    assert report["evidence_boundary"]["changed_cases_approved"] is False
    assert (revision / "review_attestation.json").is_file()
    assert finalization["revision_id"] == "1.0.4"
    assert finalization["revision_report_sha256"] == report["report_sha256"]
    assert set(finalization["approved_case_ids"]) == EXPECTED_CASE_IDS
    assert finalization["rejected_case_ids"] == []
    assert finalization["case_pack"]["approved_case_count"] == 64
    assert finalization["case_pack"]["approved_critical_case_count"] == 20
    assert finalization["case_pack"]["portfolio_ready"] is True
    assert finalization["evidence_boundary"]["canonical_case_pack_mutated"] is False
    assert finalization["evidence_boundary"]["historical_results_mutated"] is False
    assert finalization["evidence_boundary"]["bootstrap_allowed"] is True
    assert finalization["evidence_boundary"]["authoritative_portfolio_evidence"] is False
    assert finalization["evidence_boundary"]["production_readiness"] == (
        "not_production_ready"
    )
    assert file_sha256(revision / "review_manifest.jsonl") == finalization[
        "review_manifest_sha256"
    ]
    assert file_sha256(source / "cases.jsonl") == report["artifact_identity"][
        "source_cases_sha256"
    ]
    assert audit["summary"]["status"] == "pass"
    assert audit["summary"]["blocked_case_count"] == 0
    assert review_html.count('<section class="case"') == 2
    assert review_html.count("허용 의미 그룹 2") == 2
    assert CASE_REVISION_ATTESTATION_VERSION in review_html
    assert "허용 근거 그룹과 의미 계약을 직접 검토했습니다." in review_html
    assert '<button id="download" type="button">검토 증명 다운로드</button>' in review_html

    bundle = build_reference_corpus(revision / "manifest.json", repository_root=root)
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=revision / "cases.jsonl",
        review_manifest_path=revision / "review_manifest.jsonl",
    )
    reviewed_cases = {
        case.external_case_id: case
        for case in pack.cases
        if case.external_case_id in EXPECTED_CASE_IDS
    }
    assert set(reviewed_cases) == EXPECTED_CASE_IDS
    assert all(case.review.status == "approved" for case in reviewed_cases.values())

    for case in reviewed_cases.values():
        rag = (case.reference_context or {})["rag"]
        evidence = parse_rag_evidence_expectation(rag)
        semantic = parse_rag_semantic_expectation(case.expected_output or {})
        assert semantic.contract_version == ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION
        assert len(semantic.acceptable_required_fact_groups) == 2

        retrieval = retrieve(
            corpus=bundle.corpus,
            query=rag["query"],
            relevant_chunk_ids=list(evidence.primary_chunk_ids),
            acceptable_evidence_groups=[list(group) for group in evidence.acceptable_groups],
            evidence_contract_version=evidence.contract_version,
            top_k=rag["top_k"],
            min_score=0.0,
        )
        selection = select_evidence(
            query=rag["query"],
            category=case.category,
            max_selected=1,
            candidates=[
                EvidenceCandidate(
                    rank=chunk.rank,
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    text=chunk.text,
                    retrieval_score=chunk.score,
                )
                for chunk in retrieval.retrieved_chunks
            ],
        )
        selected = selection.selections[0]
        answer_contract = compile_bounded_rag_answer(
            category=case.category,
            query=rag["query"],
            claims=[selected.claim],
        )
        assert answer_contract is not None
        trace = evaluate_rag_output(
            json.dumps(
                {
                    "answer": answer_contract.answer,
                    "citations": [selected.chunk_id],
                    "claims": [selected.claim],
                }
            ),
            retrieval,
            expected_output=case.expected_output,
            answer_contract=answer_contract.to_dict(),
        )

        assert trace.answer_contract_satisfied is True
        assert trace.satisfied_citation_group_index == 1
        assert trace.satisfied_required_fact_group_index == 1
        assert trace.semantic_contract_satisfied is True
        assert trace.successful is True
