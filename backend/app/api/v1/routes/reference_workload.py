from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.reference_workload.cases import CasePackValidationError
from app.reference_workload.manifest import ManifestValidationError
from app.reference_workload.reporting import (
    build_reference_workload_report,
    render_reference_workload_markdown,
)
from app.reference_workload.runtime_matrix import RuntimeMatrixError
from app.schemas import (
    ReferenceCaseListRead,
    ReferenceConfigurationListRead,
    ReferenceFailureListRead,
    ReferenceMetricComparisonRead,
    ReferenceOutputReviewPlanRead,
    ReferenceWorkloadOverviewRead,
    ReferenceWorkloadReportRead,
)
from app.services.reference_output_review import build_reference_output_review_plan
from app.services.reference_workload_read_model import (
    build_reference_workload_comparison,
    build_reference_workload_overview,
    list_reference_workload_cases,
    list_reference_workload_configurations,
    list_reference_workload_failures,
)
from app.validators import DomainValidationError

router = APIRouter()


def _read[ReadModel](call: Callable[[], ReadModel]) -> ReadModel:
    try:
        return call()
    except (
        ManifestValidationError,
        CasePackValidationError,
        RuntimeMatrixError,
        DomainValidationError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/overview", response_model=ReferenceWorkloadOverviewRead)
def overview(db: Session = Depends(get_db)) -> ReferenceWorkloadOverviewRead:
    return _read(lambda: build_reference_workload_overview(db))


@router.get("/cases", response_model=ReferenceCaseListRead)
def cases(db: Session = Depends(get_db)) -> ReferenceCaseListRead:
    return _read(lambda: list_reference_workload_cases(db))


@router.get("/configurations", response_model=ReferenceConfigurationListRead)
def configurations(db: Session = Depends(get_db)) -> ReferenceConfigurationListRead:
    return _read(lambda: list_reference_workload_configurations(db))


@router.get("/comparison", response_model=ReferenceMetricComparisonRead)
def comparison(db: Session = Depends(get_db)) -> ReferenceMetricComparisonRead:
    return _read(lambda: build_reference_workload_comparison(db))


@router.get("/failures", response_model=ReferenceFailureListRead)
def failures(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> ReferenceFailureListRead:
    return _read(lambda: list_reference_workload_failures(db, limit=limit, offset=offset))


@router.get("/output-review-plan", response_model=ReferenceOutputReviewPlanRead)
def output_review_plan(
    target_count: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ReferenceOutputReviewPlanRead:
    return _read(
        lambda: build_reference_output_review_plan(db, target_count=target_count)
    )


@router.get("/report", response_model=ReferenceWorkloadReportRead)
def report(db: Session = Depends(get_db)) -> ReferenceWorkloadReportRead:
    return _read(lambda: build_reference_workload_report(db))


@router.get("/report.md", response_class=Response)
def report_markdown(db: Session = Depends(get_db)) -> Response:
    report_object = _read(lambda: build_reference_workload_report(db))
    return Response(
        content=render_reference_workload_markdown(report_object),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": (
                'attachment; filename="model-atlas-reference-workload-report.md"'
            )
        },
    )
