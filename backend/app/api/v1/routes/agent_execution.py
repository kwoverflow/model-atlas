from __future__ import annotations

import gzip
import io
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import (
    AgentApprovalCheckpointRead,
    AgentCheckpointDecisionCreate,
    AgentCheckpointResumeCreate,
    AgentCheckpointResumeJobCreate,
    AgentCheckpointResumeRead,
    AgentCheckpointRevocationCreate,
    AgentEvidenceImportCreate,
    AgentEvidenceImportRead,
    AgentExecutionJobRead,
    AgentJobOverviewRead,
    AgentJobRequeueCreate,
    AgentReconciliationJobCreate,
    AgentReplayRead,
    AgentRuntimeDescriptorRead,
    AgentTrafficEvidenceBatchCreate,
    AgentTrafficSourceStatusRead,
    OperationalMemoryRegistryRead,
)
from app.services.agent_control_plane import (
    decide_agent_approval_checkpoint,
    get_agent_approval_checkpoint,
    list_agent_approval_checkpoints,
    resume_agent_approval_checkpoint,
    revoke_agent_approval_checkpoint,
)
from app.services.agent_evidence_import import import_production_agent_evidence
from app.services.agent_execution import (
    DEFAULT_OPERATIONAL_MEMORY_REGISTRY,
    agent_runtime_descriptor,
    replay_agent_result,
)
from app.services.agent_jobs import (
    enqueue_checkpoint_reconciliation_job,
    enqueue_checkpoint_resume_job,
    get_agent_job,
    get_agent_job_overview,
    list_agent_jobs,
    requeue_agent_job,
)
from app.services.agent_traffic_ingestion import (
    AGENT_TRAFFIC_SIGNATURE_V1,
    list_traffic_source_status,
    queue_signed_traffic_batch,
)
from app.services.operator_identity import local_operator_identity
from app.validators import DomainValidationError

router = APIRouter()
settings = get_settings()


def _operator_identity(request: Request):
    return getattr(request.state, "operator_identity", None) or local_operator_identity()


@router.get("/runtime", response_model=AgentRuntimeDescriptorRead)
def get_agent_runtime() -> AgentRuntimeDescriptorRead:
    return AgentRuntimeDescriptorRead.model_validate(agent_runtime_descriptor())


@router.get("/memory-registry", response_model=OperationalMemoryRegistryRead)
def get_memory_registry() -> OperationalMemoryRegistryRead:
    return OperationalMemoryRegistryRead.model_validate(
        DEFAULT_OPERATIONAL_MEMORY_REGISTRY.descriptor()
    )


@router.post(
    "/evidence/import",
    response_model=AgentEvidenceImportRead,
    status_code=201,
)
def import_agent_evidence(
    payload: AgentEvidenceImportCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentEvidenceImportRead:
    return AgentEvidenceImportRead.model_validate(
        import_production_agent_evidence(
            db,
            payload=payload,
            signer_identity=_operator_identity(request),
        )
    )


@router.post(
    "/evidence/traffic-batches",
    response_model=AgentExecutionJobRead,
    status_code=202,
)
async def queue_traffic_evidence_batch(
    request: Request,
    signature: str = Header(alias="X-Model-Atlas-Traffic-Signature"),
    signature_version: str = Header(
        default=AGENT_TRAFFIC_SIGNATURE_V1,
        alias="X-Model-Atlas-Traffic-Signature-Version",
    ),
    key_id: str | None = Header(
        default=None,
        alias="X-Model-Atlas-Traffic-Key-Id",
    ),
    nonce: str | None = Header(
        default=None,
        alias="X-Model-Atlas-Traffic-Nonce",
    ),
    sent_at: str | None = Header(
        default=None,
        alias="X-Model-Atlas-Traffic-Sent-At",
    ),
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    raw_body = await request.body()
    content_encoding = request.headers.get("content-encoding", "identity").lower()
    if content_encoding == "gzip":
        if len(raw_body) > settings.agent_traffic_max_compressed_bytes:
            raise DomainValidationError("compressed traffic batch exceeds size limit")
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(raw_body)) as compressed:
                decoded_body = compressed.read(
                    settings.agent_traffic_max_decompressed_bytes + 1
                )
        except (OSError, EOFError) as exc:
            raise DomainValidationError("traffic batch gzip body is invalid") from exc
    elif content_encoding in {"", "identity"}:
        decoded_body = raw_body
    else:
        raise DomainValidationError("traffic content encoding is not supported")
    if len(decoded_body) > settings.agent_traffic_max_decompressed_bytes:
        raise DomainValidationError("traffic batch exceeds decompressed size limit")
    try:
        payload = AgentTrafficEvidenceBatchCreate.model_validate_json(decoded_body)
    except ValidationError as exc:
        raise DomainValidationError("traffic batch body is invalid") from exc
    return queue_signed_traffic_batch(
        db,
        payload=payload,
        supplied_signature=signature,
        hmac_keys=settings.agent_traffic_hmac_keys,
        signature_version=signature_version,
        key_id=key_id,
        nonce=nonce,
        sent_at=sent_at,
        allow_legacy_signatures=settings.agent_traffic_allow_legacy_signatures,
        max_clock_skew_seconds=settings.agent_traffic_max_clock_skew_seconds,
    )


@router.get(
    "/evidence/traffic-sources",
    response_model=list[AgentTrafficSourceStatusRead],
)
def get_traffic_source_status(
    db: Session = Depends(get_db),
) -> list[AgentTrafficSourceStatusRead]:
    return [
        AgentTrafficSourceStatusRead.model_validate(row)
        for row in list_traffic_source_status(
            db,
            hmac_keys=settings.agent_traffic_hmac_keys,
            stale_after_seconds=settings.agent_traffic_source_stale_seconds,
        )
    ]


@router.get("/checkpoints", response_model=list[AgentApprovalCheckpointRead])
def list_approval_checkpoints(
    benchmark_run_id: UUID | None = None,
    benchmark_result_id: UUID | None = None,
    status: str | None = Query(
        default=None,
        pattern="^(pending|approved|denied|revoked|expired|resumed)$",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AgentApprovalCheckpointRead]:
    return list_agent_approval_checkpoints(
        db,
        benchmark_run_id=benchmark_run_id,
        benchmark_result_id=benchmark_result_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/checkpoints/{checkpoint_record_id}",
    response_model=AgentApprovalCheckpointRead,
)
def get_approval_checkpoint(
    checkpoint_record_id: UUID,
    db: Session = Depends(get_db),
) -> AgentApprovalCheckpointRead:
    return get_agent_approval_checkpoint(db, checkpoint_record_id)


@router.post(
    "/checkpoints/{checkpoint_record_id}/decision",
    response_model=AgentApprovalCheckpointRead,
)
def decide_approval_checkpoint(
    checkpoint_record_id: UUID,
    payload: AgentCheckpointDecisionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentApprovalCheckpointRead:
    return decide_agent_approval_checkpoint(
        db,
        checkpoint_record_id=checkpoint_record_id,
        payload=payload,
        signer_identity=_operator_identity(request),
    )


@router.post(
    "/checkpoints/{checkpoint_record_id}/revoke",
    response_model=AgentApprovalCheckpointRead,
)
def revoke_approval_checkpoint(
    checkpoint_record_id: UUID,
    payload: AgentCheckpointRevocationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentApprovalCheckpointRead:
    return revoke_agent_approval_checkpoint(
        db,
        checkpoint_record_id=checkpoint_record_id,
        payload=payload,
        signer_identity=_operator_identity(request),
    )


@router.post(
    "/checkpoints/{checkpoint_record_id}/resume",
    response_model=AgentCheckpointResumeRead,
)
def resume_approval_checkpoint(
    checkpoint_record_id: UUID,
    payload: AgentCheckpointResumeCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentCheckpointResumeRead:
    outcome = resume_agent_approval_checkpoint(
        db,
        checkpoint_record_id=checkpoint_record_id,
        expected_version=payload.expected_version,
        signer_identity=_operator_identity(request),
    )
    return AgentCheckpointResumeRead(
        checkpoint=outcome.checkpoint,
        benchmark_run_id=outcome.benchmark_run_id,
        benchmark_result_id=outcome.benchmark_result_id,
        parent_benchmark_run_id=outcome.parent_benchmark_run_id,
        parent_benchmark_result_id=outcome.parent_benchmark_result_id,
        result_revision=outcome.result_revision,
        trace=outcome.trace,
        summary=outcome.summary,
    )


@router.post(
    "/checkpoints/{checkpoint_record_id}/resume-jobs",
    response_model=AgentExecutionJobRead,
    status_code=202,
)
def queue_approval_checkpoint_resume(
    checkpoint_record_id: UUID,
    payload: AgentCheckpointResumeJobCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    return enqueue_checkpoint_resume_job(
        db,
        checkpoint_record_id=checkpoint_record_id,
        expected_version=payload.expected_version,
        signer_identity=_operator_identity(request),
    )


@router.post(
    "/jobs/reconciliation",
    response_model=AgentExecutionJobRead,
    status_code=202,
)
def queue_agent_reconciliation(
    payload: AgentReconciliationJobCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    schedule_key = payload.schedule_key or f"manual-{uuid4()}"
    return enqueue_checkpoint_reconciliation_job(
        db,
        schedule_key=schedule_key,
        signer_identity=_operator_identity(request),
    )


@router.get("/jobs", response_model=list[AgentExecutionJobRead])
def list_execution_jobs(
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AgentExecutionJobRead]:
    return list_agent_jobs(
        db,
        status=status,
        job_type=job_type,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/overview", response_model=AgentJobOverviewRead)
def get_execution_job_overview(
    db: Session = Depends(get_db),
) -> AgentJobOverviewRead:
    return AgentJobOverviewRead.model_validate(
        get_agent_job_overview(
            db,
            worker_offline_seconds=settings.agent_worker_offline_seconds,
        )
    )


@router.get("/jobs/{job_id}", response_model=AgentExecutionJobRead)
def get_execution_job(
    job_id: UUID,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    return get_agent_job(db, job_id)


@router.post(
    "/jobs/{job_id}/requeue",
    response_model=AgentExecutionJobRead,
)
def requeue_execution_job(
    job_id: UUID,
    payload: AgentJobRequeueCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> AgentExecutionJobRead:
    return requeue_agent_job(
        db,
        job_id=job_id,
        reason=payload.reason,
        signer_identity=_operator_identity(request),
        max_attempts=payload.max_attempts,
    )


@router.post("/replay/{benchmark_result_id}", response_model=AgentReplayRead)
def replay_agent_execution(
    benchmark_result_id: UUID,
    db: Session = Depends(get_db),
) -> AgentReplayRead:
    return AgentReplayRead.model_validate(
        replay_agent_result(db, benchmark_result_id=benchmark_result_id)
    )
