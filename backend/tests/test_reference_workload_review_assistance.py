from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.review_assistance import (
    REVIEW_ATTESTATION_STATEMENT,
    ReviewAssistanceError,
    build_review_assistance_report,
    finalize_assisted_review,
    write_review_assistance_artifacts,
)
from app.reference_workload.review_ui import write_review_assistance_html


def _artifacts(tmp_path: Path):
    bundle = build_reference_corpus()
    empty_review_path = tmp_path / "empty-reviews.jsonl"
    empty_review_path.write_text("", encoding="utf-8")
    case_pack = load_reference_case_pack(
        corpus_bundle=bundle,
        review_manifest_path=empty_review_path,
    )
    report = build_review_assistance_report(
        case_pack=case_pack,
        corpus_bundle=bundle,
    )
    report_path = tmp_path / "review_assistance.json"
    csv_path = tmp_path / "review_assistance.csv"
    attestation_path = tmp_path / "review_attestation.json"
    write_review_assistance_artifacts(
        report=report,
        json_path=report_path,
        csv_path=csv_path,
        attestation_path=attestation_path,
    )
    return bundle, case_pack, report, report_path, csv_path, attestation_path


def test_machine_assistance_covers_every_case_without_approving_it(tmp_path: Path) -> None:
    _, case_pack, report, report_path, csv_path, attestation_path = _artifacts(tmp_path)

    assert report["summary"]["case_count"] == 64
    assert sum(
        report["summary"][key]
        for key in (
            "eligible_for_bulk_review",
            "spot_check_required",
            "repair_required",
        )
    ) == 64
    assert report["automation_boundary"]["machine_review_only"] is True
    assert report["automation_boundary"]["human_approval_required"] is True
    assert case_pack.approved_case_count == 0
    assert report_path.exists()
    assert csv_path.exists()
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    assert attestation["reviewer"] == ""
    assert attestation["approve_automated_passes"] is False
    assert attestation["confirmed_case_ids"] == []


def test_standalone_review_html_embeds_current_report_without_human_decisions(
    tmp_path: Path,
) -> None:
    _, _, report, _, _, _ = _artifacts(tmp_path)
    html_path = tmp_path / "review_assistance.html"

    write_review_assistance_html(html_path, report=report)
    html = html_path.read_text(encoding="utf-8")

    assert '<html lang="ko">' in html
    assert report["report_sha256"] in html
    assert 'download = "review_attestation.json"' in html
    assert "approve_automated_passes: true" in html
    assert "human_attestation_recorded" not in html


def test_assisted_review_rejects_incomplete_human_attestation(tmp_path: Path) -> None:
    _, _, report, report_path, _, attestation_path = _artifacts(tmp_path)

    with pytest.raises(ReviewAssistanceError, match="human reviewer identity"):
        finalize_assisted_review(
            current_report=report,
            report_path=report_path,
            attestation_path=attestation_path,
            output_path=tmp_path / "reviews.jsonl",
        )


def test_assisted_review_rejects_a_tampered_report(tmp_path: Path) -> None:
    _, _, report, report_path, _, attestation_path = _artifacts(tmp_path)
    stored = json.loads(report_path.read_text(encoding="utf-8"))
    stored["items"][0]["title"] = "tampered"
    report_path.write_text(json.dumps(stored), encoding="utf-8")

    with pytest.raises(ReviewAssistanceError, match="report hash is invalid"):
        finalize_assisted_review(
            current_report=report,
            report_path=report_path,
            attestation_path=attestation_path,
            output_path=tmp_path / "reviews.jsonl",
        )


def test_real_batch_attestation_produces_hash_bound_approved_pack(tmp_path: Path) -> None:
    bundle, _, report, report_path, _, attestation_path = _artifacts(tmp_path)
    assert report["summary"]["repair_required"] == 0
    attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
    attestation.update(
        {
            "reviewer": "portfolio-owner",
            "attestation": REVIEW_ATTESTATION_STATEMENT,
            "approve_automated_passes": True,
            "confirmed_case_ids": report["summary"]["required_human_case_ids"],
            "notes": "Test-only human attestation fixture over the generated report.",
        }
    )
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")
    review_path = tmp_path / "reviews.jsonl"

    summary = finalize_assisted_review(
        current_report=report,
        report_path=report_path,
        attestation_path=attestation_path,
        output_path=review_path,
    )
    reviewed = load_reference_case_pack(
        corpus_bundle=bundle,
        review_manifest_path=review_path,
    )

    assert summary["status"] == "human_attestation_recorded"
    assert summary["approved_case_count"] == 64
    assert reviewed.approved_case_count == 64
    assert reviewed.approved_critical_case_count == 20
    assert reviewed.portfolio_ready is True
