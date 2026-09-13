from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import (
    AgentExecutionJobRead,
    ModelArtifactAttestationRead,
    ModelValidationCampaignCreate,
    ModelValidationReportRead,
    ObservedRuntimeConfigurationCreate,
    ObservedRuntimeConfigurationRead,
)
from app.services.agent_jobs import enqueue_model_validation_job
from app.services.model_artifact_attestation import (
    create_observed_runtime_configuration,
    list_model_artifact_attestations,
)
from app.services.model_validation import (
    build_model_validation_report,
    render_model_validation_markdown,
)
from app.services.operator_identity import local_operator_identity

router = APIRouter()
settings = get_settings()


def _operator_identity(request: Request):
    return (
        getattr(request.state, "operator_identity", None)
        or local_operator_identity()
    )


@router.post(
    "/campaigns",
    response_model=AgentExecutionJobRead,
    status_code=202,
)
def create_model_validation_campaign(
    payload: ModelValidationCampaignCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    return enqueue_model_validation_job(
        db,
        payload=payload,
        signer_identity=_operator_identity(request),
    )


@router.post(
    "/observed-runtime-configurations",
    response_model=ObservedRuntimeConfigurationRead,
    status_code=201,
)
def create_attested_observed_runtime_configuration(
    payload: ObservedRuntimeConfigurationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ObservedRuntimeConfigurationRead:
    return create_observed_runtime_configuration(
        db,
        payload=payload,
        signer_identity=_operator_identity(request),
        allowed_hosts=settings.model_attestation_allowed_hosts,
        timeout_seconds=settings.model_attestation_http_timeout_seconds,
    )


@router.get(
    "/artifact-attestations",
    response_model=list[ModelArtifactAttestationRead],
)
def get_model_artifact_attestations(
    model_artifact_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ModelArtifactAttestationRead]:
    return list_model_artifact_attestations(
        db,
        model_artifact_id=model_artifact_id,
        limit=limit,
    )


@router.get("/report", response_model=ModelValidationReportRead)
def get_model_validation_report(
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
    focus_benchmark_run_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> ModelValidationReportRead:
    return build_model_validation_report(
        db,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        focus_benchmark_run_id=focus_benchmark_run_id,
    )


@router.get("/report.md", response_class=PlainTextResponse)
def get_model_validation_report_markdown(
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
    focus_benchmark_run_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> str:
    report = build_model_validation_report(
        db,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        focus_benchmark_run_id=focus_benchmark_run_id,
    )
    return render_model_validation_markdown(report)
