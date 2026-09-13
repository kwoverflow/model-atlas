import json
from pathlib import Path

from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root, file_sha256
from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    parse_rag_evidence_expectation,
)

EXPECTED_ALTERNATIVES = {
    "KO-RAG-SCOPE-002": "ko-b70165b4b3f47cf87a34ff25",
    "KO-RAG-SCOPE-003": "ko-9c59bd29a1b754b80c476d62",
    "KO-REFUSE-002": "ko-8b7f33d47228772f0cbba790",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_checked_in_1_0_3_revision_is_reviewed_finalized_and_isolated() -> None:
    root = default_repository_root()
    revision = root / "reference_workload" / "revisions" / "1.0.3"
    report = _load_json(revision / "revision_report.json")
    audit = _load_json(revision / "retrieval_contract_audit.json")
    finalization = _load_json(revision / "finalization_report.json")

    assert report["source_workload_version"] == "1.0.2"
    assert report["summary"]["changed_case_count"] == 3
    assert report["summary"]["pending_review_count"] == 3
    assert report["summary"]["portfolio_ready"] is False
    assert report["evidence_boundary"]["canonical_case_pack_mutated"] is False
    assert report["evidence_boundary"]["changed_cases_approved"] is False
    assert (revision / "review_attestation.json").is_file()
    assert finalization["revision_id"] == "1.0.3"
    assert finalization["revision_report_sha256"] == report["report_sha256"]
    assert set(finalization["approved_case_ids"]) == set(EXPECTED_ALTERNATIVES)
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
    assert file_sha256(root / "reference_workload" / "revisions" / "1.0.2" / "cases.jsonl") == (
        report["artifact_identity"]["source_cases_sha256"]
    )
    assert audit["summary"]["status"] == "pass"
    assert audit["summary"]["blocked_case_count"] == 0

    bundle = build_reference_corpus(revision / "manifest.json", repository_root=root)
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=revision / "cases.jsonl",
        review_manifest_path=revision / "review_manifest.jsonl",
    )
    reviewed_cases = {
        case.external_case_id: case
        for case in pack.cases
        if case.external_case_id in EXPECTED_ALTERNATIVES
    }
    assert set(reviewed_cases) == set(EXPECTED_ALTERNATIVES)
    assert all(case.review.status == "approved" for case in reviewed_cases.values())

    for case_id, alternative_id in EXPECTED_ALTERNATIVES.items():
        rag = (reviewed_cases[case_id].reference_context or {})["rag"]
        expectation = parse_rag_evidence_expectation(rag)
        assert expectation.contract_version == ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
        assert len(expectation.acceptable_groups) == 2
        assert expectation.match([alternative_id]).satisfied is True
        assert expectation.match([alternative_id]).group_index == 1
