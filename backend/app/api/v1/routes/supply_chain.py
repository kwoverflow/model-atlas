from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas import (
    ModelSupplyChainAttestationCreate,
    ModelSupplyChainAttestationCreateRead,
    ModelSupplyChainAttestationRead,
    ProductionEvidenceReceiptCreate,
    ProductionEvidenceReceiptCreateRead,
    ProductionEvidenceReceiptRead,
    SupplyChainOverviewRead,
    SupplyChainRevocationCreate,
    SupplyChainRevocationRead,
)
from app.services.operator_identity import local_operator_identity
from app.services.supply_chain import (
    build_supply_chain_overview,
    create_model_supply_chain_attestation,
    create_production_evidence_receipt,
    list_model_supply_chain_attestations,
    list_production_evidence_receipts,
    revoke_model_supply_chain_attestation,
)

router = APIRouter()
settings = get_settings()


def _operator_identity(request: Request):
    return getattr(request.state, "operator_identity", None) or local_operator_identity()


@router.get("/overview", response_model=SupplyChainOverviewRead)
def get_supply_chain_overview(
    db: Session = Depends(get_db),
) -> SupplyChainOverviewRead:
    return build_supply_chain_overview(db, settings=settings)


@router.get(
    "/model-attestations",
    response_model=list[ModelSupplyChainAttestationRead],
)
def get_model_supply_chain_attestations(
    model_artifact_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ModelSupplyChainAttestationRead]:
    return list_model_supply_chain_attestations(
        db,
        model_artifact_id=model_artifact_id,
        limit=limit,
    )


@router.post(
    "/model-attestations",
    response_model=ModelSupplyChainAttestationCreateRead,
    status_code=201,
)
def create_signed_model_supply_chain_attestation(
    payload: ModelSupplyChainAttestationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ModelSupplyChainAttestationCreateRead:
    return create_model_supply_chain_attestation(
        db,
        payload=payload,
        signer_identity=_operator_identity(request),
        settings=settings,
    )


@router.post(
    "/model-attestations/{attestation_id}/revocations",
    response_model=SupplyChainRevocationRead,
    status_code=201,
)
def revoke_signed_model_supply_chain_attestation(
    attestation_id: UUID,
    payload: SupplyChainRevocationCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> SupplyChainRevocationRead:
    return revoke_model_supply_chain_attestation(
        db,
        attestation_id=attestation_id,
        payload=payload,
        signer_identity=_operator_identity(request),
    )


@router.get(
    "/production-receipts",
    response_model=list[ProductionEvidenceReceiptRead],
)
def get_production_evidence_receipts(
    benchmark_run_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[ProductionEvidenceReceiptRead]:
    return list_production_evidence_receipts(
        db,
        benchmark_run_id=benchmark_run_id,
        limit=limit,
    )


@router.post(
    "/production-receipts",
    response_model=ProductionEvidenceReceiptCreateRead,
    status_code=201,
)
def create_signed_production_evidence_receipt(
    payload: ProductionEvidenceReceiptCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> ProductionEvidenceReceiptCreateRead:
    return create_production_evidence_receipt(
        db,
        payload=payload,
        signer_identity=_operator_identity(request),
        settings=settings,
    )
