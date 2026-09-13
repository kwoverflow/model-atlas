from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import PromptRegressionReport
from app.services.prompt_regressions import build_prompt_regression_report

router = APIRouter()


@router.get("/report", response_model=PromptRegressionReport)
def get_prompt_regression_report(
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> PromptRegressionReport:
    return build_prompt_regression_report(
        db,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
    )
