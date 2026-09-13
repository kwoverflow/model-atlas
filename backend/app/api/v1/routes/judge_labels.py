from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    JudgeLabelImportRequest,
    JudgeLabelImportSummaryRead,
    JudgeLabelReviewDecisionCreate,
    JudgeLabelReviewDecisionRead,
    JudgeLabelReviewResponse,
)
from app.services.judge_label_decisions import (
    assert_judge_reviewer,
    create_judge_label_review_decision,
    list_judge_label_review_decisions,
)
from app.services.judge_label_import import import_judge_label_content
from app.services.judge_label_review import review_judge_labels
from app.services.operator_identity import local_operator_identity

router = APIRouter()


def _operator_identity(request: Request):
    return (
        getattr(request.state, "operator_identity", None)
        or local_operator_identity()
    )


@router.get("/review", response_model=JudgeLabelReviewResponse)
def get_judge_label_review(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    benchmark_run_id: UUID | None = None,
    benchmark_result_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> JudgeLabelReviewResponse:
    return review_judge_labels(
        db,
        limit=limit,
        offset=offset,
        benchmark_run_id=benchmark_run_id,
        benchmark_result_id=benchmark_result_id,
    )


@router.post("/import", response_model=JudgeLabelImportSummaryRead)
def import_judge_label_file(
    payload: JudgeLabelImportRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> JudgeLabelImportSummaryRead:
    reviewer_identity = _operator_identity(request)
    if payload.apply_labels:
        assert_judge_reviewer(reviewer_identity)
    summary = import_judge_label_content(
        db,
        benchmark_run_id=payload.benchmark_run_id,
        filename=payload.filename,
        content=payload.content,
        apply_labels=payload.apply_labels,
        reviewer_identity=(reviewer_identity if payload.apply_labels else None),
    )
    return JudgeLabelImportSummaryRead(**summary.to_dict())


@router.post(
    "/review-decisions",
    response_model=JudgeLabelReviewDecisionRead,
    status_code=201,
)
def create_review_decision(
    payload: JudgeLabelReviewDecisionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> JudgeLabelReviewDecisionRead:
    return create_judge_label_review_decision(
        db,
        payload=payload,
        reviewer_identity=_operator_identity(request),
    )


@router.get(
    "/review-decisions",
    response_model=list[JudgeLabelReviewDecisionRead],
)
def get_review_decisions(
    benchmark_result_id: UUID | None = None,
    benchmark_run_id: UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[JudgeLabelReviewDecisionRead]:
    return list_judge_label_review_decisions(
        db,
        benchmark_result_id=benchmark_result_id,
        benchmark_run_id=benchmark_run_id,
        limit=limit,
    )
