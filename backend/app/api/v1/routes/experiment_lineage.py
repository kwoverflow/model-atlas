from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    ExperimentLineageEventRead,
    ExperimentLineageMaterializeResponse,
    ExperimentLineageReport,
)
from app.services.experiment_lineage import (
    build_experiment_lineage_report,
    list_experiment_lineage_events,
    materialize_experiment_lineage,
)

router = APIRouter()


@router.get("/events", response_model=list[ExperimentLineageEventRead])
def list_events(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    event_type: str | None = None,
    sync_missing: bool = True,
    db: Session = Depends(get_db),
) -> list[ExperimentLineageEventRead]:
    return list(
        list_experiment_lineage_events(
            db,
            limit=limit,
            offset=offset,
            deployment_configuration_id=deployment_configuration_id,
            evaluation_suite_id=evaluation_suite_id,
            acceptance_policy_id=acceptance_policy_id,
            prompt_version_id=prompt_version_id,
            event_type=event_type,
            sync_missing=sync_missing,
        )
    )


@router.get("/report", response_model=ExperimentLineageReport)
def get_report(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    event_type: str | None = None,
    db: Session = Depends(get_db),
) -> ExperimentLineageReport:
    return build_experiment_lineage_report(
        db,
        limit=limit,
        offset=offset,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
        prompt_version_id=prompt_version_id,
        event_type=event_type,
    )


@router.post("/materialize", response_model=ExperimentLineageMaterializeResponse)
def materialize_events(db: Session = Depends(get_db)) -> ExperimentLineageMaterializeResponse:
    return materialize_experiment_lineage(db)
