from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.reference_workload.case_revision import (
    CasePackRevisionError,
    create_case_pack_revision,
)
from app.reference_workload.case_revision_review import (
    CASE_REVISION_ATTESTATION_STATEMENT,
    CASE_REVISION_ATTESTATION_VERSION,
    finalize_case_pack_revision,
    write_case_revision_review_html,
)
from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root, file_sha256


def _revision_sandbox(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_root = default_repository_root()
    root = tmp_path / "repository"
    shutil.copytree(source_root / "docs", root / "docs")
    shutil.copy2(source_root / "EVALUATOR_GUIDE_KO.md", root)
    reference = root / "reference_workload"
    reference.mkdir(parents=True)
    for name in ("manifest.json", "cases.jsonl", "review_manifest.jsonl"):
        shutil.copy2(source_root / "reference_workload" / name, reference / name)
    output = reference / "revisions" / "1.0.1"
    output.mkdir(parents=True)
    spec = output / "revision_spec.json"
    shutil.copy2(
        source_root / "reference_workload" / "revisions" / "1.0.1" / "revision_spec.json",
        spec,
    )
    return root, spec, output


def _copy_revision_spec(root: Path, version: str) -> tuple[Path, Path]:
    output = root / "reference_workload" / "revisions" / version
    output.mkdir(parents=True, exist_ok=True)
    spec = output / "revision_spec.json"
    shutil.copy2(
        default_repository_root()
        / "reference_workload"
        / "revisions"
        / version
        / "revision_spec.json",
        spec,
    )
    return spec, output


def test_case_pack_revision_is_isolated_reviewable_and_reachable(
    tmp_path: Path,
) -> None:
    root, spec, output = _revision_sandbox(tmp_path)
    canonical_paths = [
        root / "reference_workload" / name
        for name in ("manifest.json", "cases.jsonl", "review_manifest.jsonl")
    ]
    original_hashes = [file_sha256(path) for path in canonical_paths]

    report = create_case_pack_revision(
        repository_root=root,
        spec_path=spec,
        output_directory=output,
    )

    assert [file_sha256(path) for path in canonical_paths] == original_hashes
    assert report["summary"] == {
        "case_count": 64,
        "changed_case_count": 4,
        "retained_approval_count": 60,
        "pending_review_count": 4,
        "approved_case_count": 60,
        "approved_critical_case_count": 16,
        "portfolio_ready": False,
        "retrieval_contract_status": "pass",
    }
    assert report["evidence_boundary"] == {
        "canonical_case_pack_mutated": False,
        "historical_results_mutated": False,
        "changed_cases_approved": False,
        "bootstrap_allowed": False,
        "authoritative_portfolio_evidence": False,
        "production_readiness": "not_production_ready",
    }
    assert all(
        change["revised_contract"]["contract_reachable"] is True
        and change["revised_contract"]["retrieval_recall"] == 1.0
        and max(
            rank
            for rank in change["revised_contract"]["expected_chunk_ranks"].values()
            if rank is not None
        )
        <= 5
        for change in report["changes"]
    )
    assert len((output / "review_manifest.jsonl").read_text(encoding="utf-8").splitlines()) == 60

    bundle = build_reference_corpus(output / "manifest.json", repository_root=root)
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=output / "cases.jsonl",
        review_manifest_path=output / "review_manifest.jsonl",
    )
    changed_ids = {change["external_case_id"] for change in report["changes"]}
    assert {
        case.external_case_id for case in pack.cases if case.review.status == "draft"
    } == changed_ids
    assert (
        json.loads((output / "manifest.json").read_text(encoding="utf-8"))["workload_version"]
        == "1.0.1"
    )

    rerun = create_case_pack_revision(
        repository_root=root,
        spec_path=spec,
        output_directory=output,
    )
    assert rerun["report_sha256"] == report["report_sha256"]

    next_spec, next_output = _copy_revision_spec(root, "1.0.2")
    with pytest.raises(CasePackRevisionError, match="finalization report is invalid"):
        create_case_pack_revision(
            repository_root=root,
            spec_path=next_spec,
            output_directory=next_output,
        )


def test_case_pack_revision_focused_review_and_finalization(tmp_path: Path) -> None:
    root, spec, output = _revision_sandbox(tmp_path)
    report = create_case_pack_revision(
        repository_root=root,
        spec_path=spec,
        output_directory=output,
    )
    review_html = output / "revision_review.html"
    write_case_revision_review_html(output / "revision_report.json", review_html)

    rendered = review_html.read_text(encoding="utf-8")
    assert report["report_sha256"] in rendered
    assert all(change["external_case_id"] in rendered for change in report["changes"])
    attestation = {
        "schema_version": CASE_REVISION_ATTESTATION_VERSION,
        "revision_id": "1.0.1",
        "revision_report_sha256": report["report_sha256"],
        "statement": CASE_REVISION_ATTESTATION_STATEMENT,
        "reviewer": "Rok N",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "decisions": [
            {
                "external_case_id": change["external_case_id"],
                "revised_case_sha256": change["revised_case_sha256"],
                "decision": "approved",
                "notes": "The revised evidence directly supports the stated request.",
            }
            for change in report["changes"]
        ],
    }
    attestation_path = output / "attestation.json"
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")

    finalization = finalize_case_pack_revision(
        repository_root=root,
        output_directory=output,
        attestation_path=attestation_path,
    )

    assert finalization["case_pack"]["approved_case_count"] == 64
    assert finalization["case_pack"]["approved_critical_case_count"] == 20
    assert finalization["case_pack"]["portfolio_ready"] is True
    assert len(finalization["approved_case_ids"]) == 4
    assert finalization["rejected_case_ids"] == []
    assert len((output / "review_manifest.jsonl").read_text().splitlines()) == 64
    with pytest.raises(CasePackRevisionError, match="finalized revision cannot be regenerated"):
        create_case_pack_revision(
            repository_root=root,
            spec_path=spec,
            output_directory=output,
        )

    finalized_source_paths = [
        output / name
        for name in (
            "manifest.json",
            "cases.jsonl",
            "review_manifest.jsonl",
            "revision_report.json",
            "finalization_report.json",
        )
    ]
    finalized_source_hashes = [file_sha256(path) for path in finalized_source_paths]
    next_spec, next_output = _copy_revision_spec(root, "1.0.2")
    next_report = create_case_pack_revision(
        repository_root=root,
        spec_path=next_spec,
        output_directory=next_output,
    )

    assert [file_sha256(path) for path in finalized_source_paths] == finalized_source_hashes
    assert next_report["source_provenance"] == {
        "kind": "finalized_revision",
        "directory": "reference_workload/revisions/1.0.1",
        "revision_report_sha256": report["report_sha256"],
        "finalization_report_sha256": finalization["report_sha256"],
    }
    assert next_report["summary"] == {
        "case_count": 64,
        "changed_case_count": 1,
        "retained_approval_count": 63,
        "pending_review_count": 1,
        "approved_case_count": 63,
        "approved_critical_case_count": 19,
        "portfolio_ready": False,
        "retrieval_contract_status": "pass",
    }
    next_change = next_report["changes"][0]
    assert next_change["external_case_id"] == "KO-RAG-SCOPE-001"
    assert next_change["request"] == (
        "로컬 Gate APPROVED를 production-ready라고 표시해도 되나요?"
    )
    assert next_change["old_contract"]["expected_chunk_ranks"] == {
        "ko-081cc59533de7d8df33dd074": 15
    }
    assert next_change["revised_contract"]["expected_chunk_ranks"] == {
        "ko-2bbdb970a082e17107cea0e9": 1
    }
    assert next_change["revised_contract"]["retrieval_recall"] == 1.0

    next_attestation = {
        "schema_version": CASE_REVISION_ATTESTATION_VERSION,
        "revision_id": "1.0.2",
        "revision_report_sha256": next_report["report_sha256"],
        "statement": CASE_REVISION_ATTESTATION_STATEMENT,
        "reviewer": "Rok N",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "decisions": [
            {
                "external_case_id": next_change["external_case_id"],
                "revised_case_sha256": next_change["revised_case_sha256"],
                "decision": "approved",
                "notes": "The revised evidence directly supports the scope distinction.",
            }
        ],
    }
    next_attestation_path = next_output / "attestation.json"
    next_attestation_path.write_text(json.dumps(next_attestation), encoding="utf-8")
    next_finalization = finalize_case_pack_revision(
        repository_root=root,
        output_directory=next_output,
        attestation_path=next_attestation_path,
    )
    assert next_finalization["case_pack"]["approved_case_count"] == 64
    assert next_finalization["case_pack"]["approved_critical_case_count"] == 20
    assert next_finalization["case_pack"]["portfolio_ready"] is True
