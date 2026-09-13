from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.reference_workload.cases import (
    CasePackValidationError,
    load_reference_case_pack,
    write_review_worksheet,
)
from app.reference_workload.contracts import CaseReviewContract
from app.reference_workload.corpus import build_reference_corpus


def _draft_pack(bundle, tmp_path: Path):
    review_path = tmp_path / "empty-reviews.jsonl"
    review_path.write_text("", encoding="utf-8")
    return load_reference_case_pack(
        corpus_bundle=bundle,
        review_manifest_path=review_path,
    )


def test_repository_draft_pack_has_required_taxonomy_without_claiming_approval(
    tmp_path: Path,
) -> None:
    bundle = build_reference_corpus()
    pack = _draft_pack(bundle, tmp_path)

    assert len(pack.cases) == 64
    assert pack.draft_case_count == 64
    assert pack.approved_case_count == 0
    assert pack.approved_critical_case_count == 0
    assert pack.portfolio_ready is False
    assert sum(pack.critical_category_counts.values()) == 20
    assert pack.category_counts == {
        "rag_single_document": 12,
        "rag_multi_document": 10,
        "rag_version_or_scope": 6,
        "insufficient_evidence_refusal": 8,
        "tool_single_step": 10,
        "tool_failure_recovery": 6,
        "rag_tool_combined": 6,
        "agent_multi_step": 6,
    }
    assert all(len(case_hash) == 64 for case_hash in pack.case_hashes.values())


def test_inline_approval_without_human_metadata_is_rejected() -> None:
    with pytest.raises(ValueError, match="reviewed cases require reviewer"):
        CaseReviewContract(status="approved")


def test_review_manifest_is_bound_to_exact_case_hash(tmp_path: Path) -> None:
    bundle = build_reference_corpus()
    original = _draft_pack(bundle, tmp_path)
    first = original.cases[0]
    review_path = tmp_path / "reviews.jsonl"
    review_path.write_text(
        json.dumps(
            {
                "schema_version": "model-atlas-reference-review-v1",
                "external_case_id": first.external_case_id,
                "case_sha256": "0" * 64,
                "decision": "approved",
                "reviewer": "test-reviewer",
                "reviewed_at": "2026-08-04T00:00:00+00:00",
                "notes": "Test-only review metadata.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(CasePackValidationError, match="review hash mismatch"):
        load_reference_case_pack(
            corpus_bundle=bundle,
            review_manifest_path=review_path,
        )


def test_valid_review_does_not_make_an_incomplete_pack_ready(tmp_path: Path) -> None:
    bundle = build_reference_corpus()
    original = _draft_pack(bundle, tmp_path)
    first = original.cases[0]
    review_path = tmp_path / "reviews.jsonl"
    review_path.write_text(
        json.dumps(
            {
                "schema_version": "model-atlas-reference-review-v1",
                "external_case_id": first.external_case_id,
                "case_sha256": original.case_hashes[first.external_case_id],
                "decision": "approved",
                "reviewer": "test-reviewer",
                "reviewed_at": "2026-08-04T00:00:00+00:00",
                "notes": "Test-only review metadata.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    reviewed = load_reference_case_pack(
        corpus_bundle=bundle,
        review_manifest_path=review_path,
    )

    assert reviewed.approved_case_count == 1
    assert reviewed.draft_case_count == 63
    assert reviewed.portfolio_ready is False


def test_review_worksheet_leaves_human_evidence_fields_blank(tmp_path: Path) -> None:
    bundle = build_reference_corpus()
    pack = _draft_pack(bundle, tmp_path)
    output_path = tmp_path / "review.csv"

    write_review_worksheet(
        output_path,
        case_pack=pack,
        corpus_bundle=bundle,
    )

    with output_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 64
    assert all(row["case_sha256"] for row in rows)
    assert all(row["decision"] == "" for row in rows)
    assert all(row["reviewer"] == "" for row in rows)
    assert all(row["reviewed_at"] == "" for row in rows)
