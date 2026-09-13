from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import (
    EvidenceTrustRootActionCreate,
    EvidenceTrustRootActionRead,
    EvidenceTrustRootCreate,
    EvidenceTrustRootCreateRead,
    EvidenceTrustRootRead,
    EvidenceTrustSourceCreate,
    EvidenceTrustSourceCreateRead,
    EvidenceTrustSourceRead,
    EvidenceTrustSourceScheduleRead,
    EvidenceTrustSourceScheduleUpsert,
    EvidenceTrustSourceSyncCreate,
    EvidenceTrustSourceSyncCreateRead,
    EvidenceTrustSourceSyncRead,
    TransparencyProofCreate,
    TransparencyProofCreateRead,
    TransparencyProofRead,
    TrustRegistryOverviewRead,
)
from app.services.operator_identity import local_operator_identity
from app.services.trust_registry import (
    build_trust_registry_overview,
    create_evidence_trust_root,
    create_transparency_proof,
    list_evidence_trust_roots,
    list_evidence_trust_source_syncs,
    list_evidence_trust_sources,
    list_transparency_proofs,
    record_evidence_trust_root_action,
)
from app.services.trust_source_scheduler import (
    list_evidence_trust_source_schedules,
    request_evidence_trust_source_schedule_run,
    upsert_evidence_trust_source_schedule,
)
from app.services.trust_source_sync import (
    create_evidence_trust_source,
    fetch_remote_jwks,
    sync_evidence_trust_source,
)

router = APIRouter()
settings = get_settings()


def _operator_identity(request: Request):
    return getattr(request.state, "operator_identity", None) or local_operator_identity()


@router.get("/overview", response_model=TrustRegistryOverviewRead)
def get_trust_registry_overview(
    db: Session = Depends(get_db),
) -> TrustRegistryOverviewRead:
    return build_trust_registry_overview(db)


@router.get("/roots", response_model=list[EvidenceTrustRootRead])
def get_evidence_trust_roots(
    purpose: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[EvidenceTrustRootRead]:
    return list_evidence_trust_roots(db, purpose=purpose, limit=limit)


@router.post(
    "/roots",
    response_model=EvidenceTrustRootCreateRead,
    status_code=201,
)
def register_evidence_trust_root(
    payload: EvidenceTrustRootCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EvidenceTrustRootCreateRead:
    return create_evidence_trust_root(
        db,
        payload=payload,
        signer_identity=_operator_identity(request),
    )


@router.get("/sources", response_model=list[EvidenceTrustSourceRead])
def get_evidence_trust_sources(
    purpose: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[EvidenceTrustSourceRead]:
    return list_evidence_trust_sources(db, purpose=purpose, limit=limit)


@router.post(
    "/sources",
    response_model=EvidenceTrustSourceCreateRead,
    status_code=201,
)
def register_evidence_trust_source(
    payload: EvidenceTrustSourceCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EvidenceTrustSourceCreateRead:
    return create_evidence_trust_source(
        db,
        payload=payload,
        signer_identity=_operator_identity(request),
        allowed_hosts=settings.trust_source_allowed_hosts,
        allow_insecure_http=settings.trust_source_allow_insecure_http,
    )


@router.get(
    "/source-schedules",
    response_model=list[EvidenceTrustSourceScheduleRead],
)
def get_evidence_trust_source_schedules(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[EvidenceTrustSourceScheduleRead]:
    return list_evidence_trust_source_schedules(db, limit=limit)


@router.put(
    "/sources/{trust_source_id}/schedule",
    response_model=EvidenceTrustSourceScheduleRead,
)
def configure_evidence_trust_source_schedule(
    trust_source_id: UUID,
    payload: EvidenceTrustSourceScheduleUpsert,
    request: Request,
    db: Session = Depends(get_db),
) -> EvidenceTrustSourceScheduleRead:
    return upsert_evidence_trust_source_schedule(
        db,
        trust_source_id=trust_source_id,
        payload=payload,
        signer_identity=_operator_identity(request),
    )


@router.post(
    "/sources/{trust_source_id}/schedule/run",
    response_model=EvidenceTrustSourceScheduleRead,
)
def run_evidence_trust_source_schedule(
    trust_source_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
) -> EvidenceTrustSourceScheduleRead:
    return request_evidence_trust_source_schedule_run(
        db,
        trust_source_id=trust_source_id,
        signer_identity=_operator_identity(request),
    )


@router.post(
    "/sources/{trust_source_id}/sync",
    response_model=EvidenceTrustSourceSyncCreateRead,
    status_code=201,
)
def synchronize_evidence_trust_source(
    trust_source_id: UUID,
    payload: EvidenceTrustSourceSyncCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EvidenceTrustSourceSyncCreateRead:
    return sync_evidence_trust_source(
        db,
        trust_source_id=trust_source_id,
        payload=payload,
        signer_identity=_operator_identity(request),
        allowed_hosts=settings.trust_source_allowed_hosts,
        allow_insecure_http=settings.trust_source_allow_insecure_http,
        timeout_seconds=settings.trust_source_http_timeout_seconds,
        max_bytes=settings.trust_source_max_jwks_bytes,
        fetcher=fetch_remote_jwks,
    )


@router.get(
    "/source-syncs",
    response_model=list[EvidenceTrustSourceSyncRead],
)
def get_evidence_trust_source_syncs(
    trust_source_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[EvidenceTrustSourceSyncRead]:
    return list_evidence_trust_source_syncs(
        db,
        trust_source_id=trust_source_id,
        limit=limit,
    )


@router.post(
    "/roots/{trust_root_id}/actions",
    response_model=EvidenceTrustRootActionRead,
    status_code=201,
)
def update_evidence_trust_root_lifecycle(
    trust_root_id: UUID,
    payload: EvidenceTrustRootActionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> EvidenceTrustRootActionRead:
    return record_evidence_trust_root_action(
        db,
        trust_root_id=trust_root_id,
        payload=payload,
        signer_identity=_operator_identity(request),
    )


@router.get(
    "/transparency-proofs",
    response_model=list[TransparencyProofRead],
)
def get_transparency_proofs(
    supply_chain_attestation_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[TransparencyProofRead]:
    return list_transparency_proofs(
        db,
        supply_chain_attestation_id=supply_chain_attestation_id,
        limit=limit,
    )


@router.post(
    "/transparency-proofs",
    response_model=TransparencyProofCreateRead,
    status_code=201,
)
def register_transparency_proof(
    payload: TransparencyProofCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> TransparencyProofCreateRead:
    return create_transparency_proof(
        db,
        payload=payload,
        signer_identity=_operator_identity(request),
        max_age_seconds=settings.signed_evidence_max_age_seconds,
    )
