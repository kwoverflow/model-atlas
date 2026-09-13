from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    EvaluationCase,
    EvaluationSuite,
    MetricDefinition,
    WorkloadProfile,
)
from app.reference_workload.bootstrap import (
    ReferenceWorkloadApprovalRequired,
    bootstrap_reference_workload,
)
from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus


def _empty_review_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "empty-reviews.jsonl"
    path.write_text("", encoding="utf-8")
    return path


def _approved_review_manifest(tmp_path: Path) -> Path:
    bundle = build_reference_corpus()
    draft_pack = load_reference_case_pack(
        corpus_bundle=bundle,
        review_manifest_path=_empty_review_manifest(tmp_path),
    )
    path = tmp_path / "test-approved-reviews.jsonl"
    rows = [
        {
            "schema_version": "model-atlas-reference-review-v1",
            "external_case_id": case.external_case_id,
            "case_sha256": draft_pack.case_hashes[case.external_case_id],
            "decision": "approved",
            "reviewer": "test-human-review-fixture",
            "reviewed_at": "2026-08-04T00:00:00+00:00",
            "notes": "Synthetic test-only approval used to verify idempotent persistence.",
        }
        for case in draft_pack.cases
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _count(db: Session, model: type[object]) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def test_unapproved_pack_stops_before_database_writes(
    db_session: Session,
    tmp_path: Path,
) -> None:
    bundle = build_reference_corpus()
    draft_pack = load_reference_case_pack(
        corpus_bundle=bundle,
        review_manifest_path=_empty_review_manifest(tmp_path),
    )

    with pytest.raises(ReferenceWorkloadApprovalRequired):
        bootstrap_reference_workload(
            db_session,
            corpus_bundle=bundle,
            case_pack=draft_pack,
        )

    assert _count(db_session, WorkloadProfile) == 0
    assert _count(db_session, EvaluationSuite) == 0
    assert _count(db_session, EvaluationCase) == 0
    assert _count(db_session, AcceptancePolicy) == 0


def test_approved_test_pack_bootstrap_is_idempotent(
    db_session: Session,
    tmp_path: Path,
) -> None:
    bundle = build_reference_corpus()
    review_path = _approved_review_manifest(tmp_path)
    approved_pack = load_reference_case_pack(
        corpus_bundle=bundle,
        review_manifest_path=review_path,
    )
    assert approved_pack.portfolio_ready is True

    first = bootstrap_reference_workload(
        db_session,
        corpus_bundle=bundle,
        case_pack=approved_pack,
    )
    second = bootstrap_reference_workload(
        db_session,
        corpus_bundle=bundle,
        case_pack=approved_pack,
    )

    assert first["created"] == {"workload": True, "suite": True, "policy": True}
    assert second["created"] == {"workload": False, "suite": False, "policy": False}
    assert first["evaluation_suite_id"] == second["evaluation_suite_id"]
    assert first["suite_hash"] == second["suite_hash"]
    assert first["production_readiness"] == "not_production_ready"
    assert _count(db_session, WorkloadProfile) == 1
    assert _count(db_session, EvaluationSuite) == 1
    assert _count(db_session, EvaluationCase) == 64
    assert _count(db_session, MetricDefinition) == 11
    assert _count(db_session, AcceptancePolicy) == 1
    assert _count(db_session, AcceptancePolicyRule) == 11
