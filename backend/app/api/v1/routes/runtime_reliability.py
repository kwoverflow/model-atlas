from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import RuntimeReliabilityComparisonRead
from app.services.runtime_reliability import compare_runtime_reliability_runs

router = APIRouter()


@router.get("/compare", response_model=RuntimeReliabilityComparisonRead)
def compare_runtime_reliability(
    left_run_id: UUID,
    right_run_id: UUID,
    db: Session = Depends(get_db),
) -> RuntimeReliabilityComparisonRead:
    return RuntimeReliabilityComparisonRead.model_validate(
        compare_runtime_reliability_runs(
            db,
            left_run_id=left_run_id,
            right_run_id=right_run_id,
        )
    )
