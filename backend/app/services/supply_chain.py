from __future__ import annotations

import datetime as dt
import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    EvidenceTrustRoot,
    InferenceMetric,
    ModelArtifactAttestation,
    ModelSupplyChainAttestation,
    ModelSupplyChainAttestationAction,
    ProductionEvidenceReceipt,
    SupplyChainTransparencyProof,
)
from app.schemas import (
    ModelSupplyChainAttestationCreate,
    ModelSupplyChainAttestationCreateRead,
    ModelSupplyChainAttestationRead,
    ProductionEvidenceReceiptCreate,
    ProductionEvidenceReceiptCreateRead,
    ProductionEvidenceReceiptRead,
    SupplyChainOverviewRead,
    SupplyChainRevocationCreate,
)
from app.services.agent_jobs import MAINTENANCE_ROLES
from app.services.deployment_gate.evidence import stable_hash
from app.services.operator_identity import SignerIdentity
from app.services.signed_evidence import verify_signed_statement
from app.services.trust_registry import (
    production_receipt_is_eligible,
    supply_chain_is_production_eligible,
    supply_chain_transparency_status,
    trust_root_status,
    verify_registered_signed_statement,
)
from app.validators import DomainValidationError

SUPPLY_CHAIN_SCHEMA_VERSION = "model-supply-chain-attestation-v1"
SUPPLY_CHAIN_RESPONSE_VERSION = "model-supply-chain-response-v2"
SUPPLY_CHAIN_OVERVIEW_VERSION = "model-supply-chain-overview-v2"
PRODUCTION_CAPTURE_SCHEMA_VERSION = "model-atlas-production-capture-v1"
PRODUCTION_CAPTURE_RESPONSE_VERSION = "production-evidence-receipt-response-v2"
IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
SUPPLY_CHAIN_PREDICATE_TYPE = (
    "https://model-atlas.dev/attestations/model-supply-chain/v1"
)
MAX_SBOM_BYTES = 1_048_576


def create_model_supply_chain_attestation(
    db: Session,
    *,
    payload: ModelSupplyChainAttestationCreate,
    signer_identity: SignerIdentity,
    settings: Settings,
    now: dt.datetime | None = None,
) -> ModelSupplyChainAttestationCreateRead:
    _assert_supply_chain_operator(signer_identity)
    runtime_attestation = db.get(
        ModelArtifactAttestation,
        payload.model_artifact_attestation_id,
    )
    if runtime_attestation is None:
        raise DomainValidationError("model artifact runtime attestation was not found")
    if (
        runtime_attestation.status != "verified"
        or not runtime_attestation.identity_verified
    ):
        raise DomainValidationError("runtime attestation is not active and verified")
    registered = verify_registered_signed_statement(
        db,
        payload.signed_statement_jws,
        purpose="model_publisher",
        max_age_seconds=settings.signed_evidence_max_age_seconds,
        now=now,
    )
    if registered is not None:
        verified = registered.statement
        publisher_trust_root = registered.trust_root
    else:
        verified = verify_signed_statement(
            payload.signed_statement_jws,
            jwks_path=settings.model_publisher_jwks_path,
            allowed_issuers=settings.model_publisher_allowed_issuers,
            allowed_algorithms=settings.model_publisher_allowed_algorithms,
            max_age_seconds=settings.signed_evidence_max_age_seconds,
            now=now,
        )
        publisher_trust_root = None
    sbom = _validated_cyclonedx_sbom(payload.sbom_json)
    subject_digest, predicate = _validated_supply_chain_statement(
        verified.claims,
        runtime_attestation=runtime_attestation,
        sbom=sbom,
    )
    sbom_digest = stable_hash(sbom)
    attestation_hash = stable_hash(
        {
            "schema_version": SUPPLY_CHAIN_SCHEMA_VERSION,
            "runtime_attestation_id": str(runtime_attestation.id),
            "statement": verified.claims,
            "statement_header": verified.header,
            "statement_jws_hash": stable_hash(payload.signed_statement_jws.strip()),
            "key_fingerprint": verified.key_fingerprint,
            "sbom_digest": sbom_digest,
        }
    )
    existing = db.scalar(
        select(ModelSupplyChainAttestation).where(
            ModelSupplyChainAttestation.statement_id == verified.statement_id
        )
    )
    if existing is not None:
        if existing.attestation_hash != attestation_hash:
            raise DomainValidationError(
                "signed supply-chain statement id was already used with different content"
            )
        return ModelSupplyChainAttestationCreateRead(
            schema_version=SUPPLY_CHAIN_RESPONSE_VERSION,
            created=False,
            attestation=model_supply_chain_attestation_read(db, existing),
        )
    verified_at = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    attestation = ModelSupplyChainAttestation(
        model_artifact_attestation_id=runtime_attestation.id,
        publisher_trust_root_id=(
            publisher_trust_root.id if publisher_trust_root is not None else None
        ),
        publisher_trust_tier=(
            publisher_trust_root.trust_tier
            if publisher_trust_root is not None
            else "development"
        ),
        schema_version=SUPPLY_CHAIN_SCHEMA_VERSION,
        statement_id=verified.statement_id,
        statement_type=IN_TOTO_STATEMENT_TYPE,
        predicate_type=SUPPLY_CHAIN_PREDICATE_TYPE,
        publisher=verified.issuer,
        publisher_key_id=verified.key_id,
        signature_algorithm=verified.algorithm,
        key_fingerprint=verified.key_fingerprint,
        subject_digest=subject_digest,
        sbom_format="CycloneDX",
        sbom_version=str(sbom["specVersion"]),
        sbom_digest=sbom_digest,
        sbom_json=sbom,
        statement_json=verified.claims,
        statement_jws=payload.signed_statement_jws.strip(),
        signature_verified=True,
        verified_at=verified_at,
        verified_by_identity_json=signer_identity.to_json(),
        identity_verified=True,
        attestation_hash=attestation_hash,
        notes=_optional_text(payload.notes),
    )
    db.add(attestation)
    db.commit()
    db.refresh(attestation)
    return ModelSupplyChainAttestationCreateRead(
        schema_version=SUPPLY_CHAIN_RESPONSE_VERSION,
        created=True,
        attestation=model_supply_chain_attestation_read(db, attestation),
    )


def list_model_supply_chain_attestations(
    db: Session,
    *,
    model_artifact_id: UUID | None = None,
    limit: int = 100,
) -> list[ModelSupplyChainAttestationRead]:
    query = select(ModelSupplyChainAttestation)
    if model_artifact_id is not None:
        query = query.join(ModelArtifactAttestation).where(
            ModelArtifactAttestation.model_artifact_id == model_artifact_id
        )
    records = list(
        db.scalars(
            query.order_by(ModelSupplyChainAttestation.verified_at.desc()).limit(limit)
        ).all()
    )
    return [model_supply_chain_attestation_read(db, record) for record in records]


def model_supply_chain_attestation_read(
    db: Session,
    attestation: ModelSupplyChainAttestation,
) -> ModelSupplyChainAttestationRead:
    actions = list(
        db.scalars(
            select(ModelSupplyChainAttestationAction)
            .where(
                ModelSupplyChainAttestationAction.supply_chain_attestation_id
                == attestation.id
            )
            .order_by(ModelSupplyChainAttestationAction.occurred_at)
        ).all()
    )
    base = {
        column.name: getattr(attestation, column.name)
        for column in ModelSupplyChainAttestation.__table__.columns
        if column.name != "statement_jws"
    }
    publisher_trust_root = (
        db.get(EvidenceTrustRoot, attestation.publisher_trust_root_id)
        if attestation.publisher_trust_root_id
        else None
    )
    return ModelSupplyChainAttestationRead.model_validate(
        {
            **base,
            "status": "revoked" if actions else "verified",
            "revocation_count": len(actions),
            "latest_revocation_at": actions[-1].occurred_at if actions else None,
            "publisher_trust_status": (
                trust_root_status(db, publisher_trust_root)
                if publisher_trust_root is not None
                else "unmanaged"
            ),
            "transparency_status": supply_chain_transparency_status(db, attestation),
            "production_eligible": supply_chain_is_production_eligible(db, attestation),
        }
    )


def revoke_model_supply_chain_attestation(
    db: Session,
    *,
    attestation_id: UUID,
    payload: SupplyChainRevocationCreate,
    signer_identity: SignerIdentity,
    now: dt.datetime | None = None,
) -> ModelSupplyChainAttestationAction:
    _assert_supply_chain_operator(signer_identity)
    attestation = db.get(ModelSupplyChainAttestation, attestation_id)
    if attestation is None:
        raise DomainValidationError("model supply-chain attestation was not found")
    if model_supply_chain_attestation_read(db, attestation).status == "revoked":
        raise DomainValidationError("model supply-chain attestation is already revoked")
    verifier_subject = str(
        (attestation.verified_by_identity_json or {}).get("subject_id") or ""
    )
    if verifier_subject and verifier_subject == signer_identity.subject_id:
        raise DomainValidationError(
            "supply-chain revocation requires separation from the attestation verifier"
        )
    occurred_at = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    reason = payload.reason.strip()
    action_hash = stable_hash(
        {
            "schema_version": SUPPLY_CHAIN_SCHEMA_VERSION,
            "supply_chain_attestation_id": str(attestation.id),
            "action_type": "revoked",
            "reason": reason,
            "ticket_reference": _optional_text(payload.ticket_reference),
            "actor": signer_identity.to_json(),
            "occurred_at": occurred_at.isoformat(),
        }
    )
    action = ModelSupplyChainAttestationAction(
        supply_chain_attestation_id=attestation.id,
        action_type="revoked",
        reason=reason,
        ticket_reference=_optional_text(payload.ticket_reference),
        actor_identity_json=signer_identity.to_json(),
        identity_verified=True,
        occurred_at=occurred_at,
        action_hash=action_hash,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def create_production_evidence_receipt(
    db: Session,
    *,
    payload: ProductionEvidenceReceiptCreate,
    signer_identity: SignerIdentity,
    settings: Settings,
    now: dt.datetime | None = None,
) -> ProductionEvidenceReceiptCreateRead:
    _assert_supply_chain_operator(signer_identity)
    registered = verify_registered_signed_statement(
        db,
        payload.signed_statement_jws,
        purpose="production_collector",
        max_age_seconds=settings.signed_evidence_max_age_seconds,
        now=now,
    )
    if registered is not None:
        verified = registered.statement
        collector_trust_root = registered.trust_root
    else:
        verified = verify_signed_statement(
            payload.signed_statement_jws,
            jwks_path=settings.production_evidence_jwks_path,
            allowed_issuers=settings.production_evidence_allowed_issuers,
            allowed_algorithms=settings.production_evidence_allowed_algorithms,
            max_age_seconds=settings.signed_evidence_max_age_seconds,
            now=now,
        )
        collector_trust_root = None
    claims = verified.claims
    if claims.get("schema_version") != PRODUCTION_CAPTURE_SCHEMA_VERSION:
        raise DomainValidationError("production evidence schema_version is not supported")
    run_id = _uuid_claim(claims, "benchmark_run_id")
    runtime_attestation_id = _uuid_claim(claims, "model_artifact_attestation_id")
    supply_chain_attestation_id = _uuid_claim(
        claims,
        "supply_chain_attestation_id",
    )
    run = db.get(BenchmarkRun, run_id)
    runtime_attestation = db.get(ModelArtifactAttestation, runtime_attestation_id)
    supply_chain_attestation = db.get(
        ModelSupplyChainAttestation,
        supply_chain_attestation_id,
    )
    if run is None:
        raise DomainValidationError("production evidence benchmark run was not found")
    if runtime_attestation is None or supply_chain_attestation is None:
        raise DomainValidationError("production evidence attestation chain was not found")
    if supply_chain_attestation.model_artifact_attestation_id != runtime_attestation.id:
        raise DomainValidationError("production evidence attestation chain does not match")
    if model_supply_chain_attestation_read(db, supply_chain_attestation).status != "verified":
        raise DomainValidationError("production evidence supply-chain attestation is revoked")
    if run.status != "completed" or run.data_source != "production_captured":
        raise DomainValidationError(
            "production evidence requires a completed production_captured benchmark run"
        )
    if run.model_artifact_id != runtime_attestation.model_artifact_id:
        raise DomainValidationError("production evidence model artifact does not match the run")
    expected_configuration_id = str(run.deployment_configuration_id or "")
    if str(claims.get("deployment_configuration_id") or "") != expected_configuration_id:
        raise DomainValidationError("production evidence deployment configuration does not match")
    subject_digest = _normalized_digest(claims.get("subject_digest"))
    if subject_digest != runtime_attestation.digest_value:
        raise DomainValidationError("production evidence artifact digest does not match")
    if claims.get("artifact_attestation_hash") != runtime_attestation.attestation_hash:
        raise DomainValidationError("production evidence runtime attestation hash does not match")
    if claims.get("supply_chain_attestation_hash") != supply_chain_attestation.attestation_hash:
        raise DomainValidationError("production evidence supply-chain hash does not match")
    result_count = int(
        db.scalar(
            select(func.count(BenchmarkResult.id)).where(
                BenchmarkResult.benchmark_run_id == run.id
            )
        )
        or 0
    )
    metric_count = int(
        db.scalar(
            select(func.count(InferenceMetric.id)).where(
                InferenceMetric.benchmark_run_id == run.id
            )
        )
        or 0
    )
    untrusted_result_count = int(
        db.scalar(
            select(func.count(BenchmarkResult.id))
            .where(BenchmarkResult.benchmark_run_id == run.id)
            .where(BenchmarkResult.data_source != "production_captured")
        )
        or 0
    )
    if untrusted_result_count:
        raise DomainValidationError(
            "production evidence run contains results without production provenance"
        )
    if _integer_claim(claims, "result_count") != result_count:
        raise DomainValidationError("production evidence result_count does not match")
    if _integer_claim(claims, "metric_count") != metric_count:
        raise DomainValidationError("production evidence metric_count does not match")
    capture_started_at = _datetime_claim(claims, "capture_started_at")
    capture_ended_at = _datetime_claim(claims, "capture_ended_at")
    if capture_ended_at < capture_started_at:
        raise DomainValidationError("production evidence capture window is invalid")
    observed_at = now or dt.datetime.now(dt.UTC)
    if capture_ended_at > observed_at + dt.timedelta(minutes=5):
        raise DomainValidationError("production evidence capture window ends in the future")
    source_environment = claims.get("source_environment")
    if not isinstance(source_environment, dict) or not str(
        source_environment.get("name") or ""
    ).strip():
        raise DomainValidationError("production evidence source_environment is invalid")
    receipt_hash = stable_hash(
        {
            "schema_version": PRODUCTION_CAPTURE_SCHEMA_VERSION,
            "statement": claims,
            "statement_header": verified.header,
            "statement_jws_hash": stable_hash(payload.signed_statement_jws.strip()),
            "key_fingerprint": verified.key_fingerprint,
        }
    )
    existing = db.scalar(
        select(ProductionEvidenceReceipt).where(
            ProductionEvidenceReceipt.capture_id == verified.statement_id
        )
    )
    if existing is not None:
        if existing.receipt_hash != receipt_hash:
            raise DomainValidationError(
                "production evidence capture id was already used with different content"
            )
        return ProductionEvidenceReceiptCreateRead(
            schema_version=PRODUCTION_CAPTURE_RESPONSE_VERSION,
            created=False,
            receipt=production_evidence_receipt_read(db, existing),
        )
    verified_at = observed_at.replace(microsecond=0)
    receipt = ProductionEvidenceReceipt(
        benchmark_run_id=run.id,
        model_artifact_attestation_id=runtime_attestation.id,
        supply_chain_attestation_id=supply_chain_attestation.id,
        collector_trust_root_id=(
            collector_trust_root.id if collector_trust_root is not None else None
        ),
        collector_trust_tier=(
            collector_trust_root.trust_tier
            if collector_trust_root is not None
            else "development"
        ),
        schema_version=PRODUCTION_CAPTURE_SCHEMA_VERSION,
        capture_id=verified.statement_id,
        issuer=verified.issuer,
        key_id=verified.key_id,
        signature_algorithm=verified.algorithm,
        key_fingerprint=verified.key_fingerprint,
        subject_digest=subject_digest,
        source_environment_json=dict(source_environment),
        capture_started_at=capture_started_at,
        capture_ended_at=capture_ended_at,
        result_count=result_count,
        metric_count=metric_count,
        statement_json=claims,
        statement_jws=payload.signed_statement_jws.strip(),
        signature_verified=True,
        verified_at=verified_at,
        verified_by_identity_json=signer_identity.to_json(),
        identity_verified=True,
        receipt_hash=receipt_hash,
        notes=_optional_text(payload.notes),
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return ProductionEvidenceReceiptCreateRead(
        schema_version=PRODUCTION_CAPTURE_RESPONSE_VERSION,
        created=True,
        receipt=production_evidence_receipt_read(db, receipt),
    )


def list_production_evidence_receipts(
    db: Session,
    *,
    benchmark_run_id: UUID | None = None,
    limit: int = 100,
) -> list[ProductionEvidenceReceiptRead]:
    query = select(ProductionEvidenceReceipt)
    if benchmark_run_id is not None:
        query = query.where(
            ProductionEvidenceReceipt.benchmark_run_id == benchmark_run_id
        )
    records = list(
        db.scalars(
            query.order_by(ProductionEvidenceReceipt.verified_at.desc()).limit(limit)
        ).all()
    )
    return [production_evidence_receipt_read(db, record) for record in records]


def production_evidence_receipt_read(
    db: Session,
    receipt: ProductionEvidenceReceipt,
) -> ProductionEvidenceReceiptRead:
    collector_trust_root = (
        db.get(EvidenceTrustRoot, receipt.collector_trust_root_id)
        if receipt.collector_trust_root_id
        else None
    )
    supply_chain_attestation = db.get(
        ModelSupplyChainAttestation,
        receipt.supply_chain_attestation_id,
    )
    base = {
        column.name: getattr(receipt, column.name)
        for column in ProductionEvidenceReceipt.__table__.columns
        if column.name != "statement_jws"
    }
    supply_chain_eligible = bool(
        supply_chain_attestation is not None
        and supply_chain_is_production_eligible(db, supply_chain_attestation)
    )
    return ProductionEvidenceReceiptRead.model_validate(
        {
            **base,
            "collector_trust_status": (
                trust_root_status(db, collector_trust_root)
                if collector_trust_root is not None
                else "unmanaged"
            ),
            "supply_chain_production_eligible": supply_chain_eligible,
            "production_eligible": production_receipt_is_eligible(db, receipt),
        }
    )


def verified_production_run_ids(
    db: Session,
    run_ids: set[UUID],
) -> set[UUID]:
    if not run_ids:
        return set()
    receipts = list(
        db.scalars(
            select(ProductionEvidenceReceipt)
            .where(ProductionEvidenceReceipt.benchmark_run_id.in_(run_ids))
            .where(ProductionEvidenceReceipt.signature_verified.is_(True))
            .where(ProductionEvidenceReceipt.identity_verified.is_(True))
        ).all()
    )
    if not receipts:
        return set()
    supply_chain_ids = {receipt.supply_chain_attestation_id for receipt in receipts}
    revoked_ids = set(
        db.scalars(
            select(ModelSupplyChainAttestationAction.supply_chain_attestation_id)
            .where(
                ModelSupplyChainAttestationAction.supply_chain_attestation_id.in_(
                    supply_chain_ids
                )
            )
            .where(ModelSupplyChainAttestationAction.action_type == "revoked")
        ).all()
    )
    return {
        receipt.benchmark_run_id
        for receipt in receipts
        if receipt.supply_chain_attestation_id not in revoked_ids
        and production_receipt_is_eligible(db, receipt)
    }


def supply_chain_status_for_model_artifact(
    db: Session,
    *,
    model_artifact_id: UUID,
) -> tuple[str, UUID | None]:
    records = list_model_supply_chain_attestations(
        db,
        model_artifact_id=model_artifact_id,
        limit=500,
    )
    active = next((record for record in records if record.status == "verified"), None)
    if active is not None:
        return "verified", active.id
    if records:
        return "revoked", records[0].id
    return "missing", None


def supply_chain_assurance_for_model_artifact(
    db: Session,
    *,
    model_artifact_id: UUID,
) -> tuple[str, UUID | None, str, str, bool]:
    records = list_model_supply_chain_attestations(
        db,
        model_artifact_id=model_artifact_id,
        limit=500,
    )
    active = next((record for record in records if record.status == "verified"), None)
    selected = active or (records[0] if records else None)
    if selected is None:
        return "missing", None, "unmanaged", "missing", False
    return (
        selected.status,
        selected.id,
        selected.publisher_trust_tier,
        selected.transparency_status,
        selected.production_eligible,
    )


def build_supply_chain_overview(
    db: Session,
    *,
    settings: Settings,
) -> SupplyChainOverviewRead:
    records = list_model_supply_chain_attestations(db, limit=500)
    trust_roots = list(db.scalars(select(EvidenceTrustRoot)).all())
    active_publisher_root = any(
        root.purpose == "model_publisher" and trust_root_status(db, root) == "active"
        for root in trust_roots
    )
    active_collector_root = any(
        root.purpose == "production_collector"
        and trust_root_status(db, root) == "active"
        for root in trust_roots
    )
    receipt_count = int(
        db.scalar(select(func.count(ProductionEvidenceReceipt.id))) or 0
    )
    production_run_ids = set(
        db.scalars(
            select(BenchmarkRun.id).where(
                BenchmarkRun.data_source == "production_captured"
            )
        ).all()
    )
    verified_run_ids = verified_production_run_ids(db, production_run_ids)
    return SupplyChainOverviewRead(
        schema_version=SUPPLY_CHAIN_OVERVIEW_VERSION,
        publisher_trust_configured=bool(
            active_publisher_root
            or (
                settings.model_publisher_jwks_path
                and settings.model_publisher_allowed_issuers
                and settings.model_publisher_allowed_algorithms
            )
        ),
        production_evidence_trust_configured=bool(
            active_collector_root
            or (
                settings.production_evidence_jwks_path
                and settings.production_evidence_allowed_issuers
                and settings.production_evidence_allowed_algorithms
            )
        ),
        verified_attestation_count=sum(
            record.status == "verified" for record in records
        ),
        revoked_attestation_count=sum(record.status == "revoked" for record in records),
        production_receipt_count=receipt_count,
        managed_attestation_count=sum(
            record.publisher_trust_root_id is not None for record in records
        ),
        production_eligible_attestation_count=sum(
            record.production_eligible for record in records
        ),
        transparency_proof_count=int(
            db.scalar(select(func.count(SupplyChainTransparencyProof.id))) or 0
        ),
        production_eligible_receipt_count=sum(
            record.production_eligible
            for record in list_production_evidence_receipts(db, limit=500)
        ),
        unverified_production_run_count=len(production_run_ids - verified_run_ids),
    )


def _validated_supply_chain_statement(
    claims: dict[str, Any],
    *,
    runtime_attestation: ModelArtifactAttestation,
    sbom: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if claims.get("_type") != IN_TOTO_STATEMENT_TYPE:
        raise DomainValidationError("supply-chain statement _type is not supported")
    if claims.get("predicateType") != SUPPLY_CHAIN_PREDICATE_TYPE:
        raise DomainValidationError("supply-chain predicateType is not supported")
    subjects = claims.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1:
        raise DomainValidationError("supply-chain statement requires exactly one subject")
    subject = subjects[0]
    digest_map = subject.get("digest") if isinstance(subject, dict) else None
    if not isinstance(digest_map, dict):
        raise DomainValidationError("supply-chain subject digest is missing")
    subject_digest = _normalized_digest(digest_map.get("sha256"))
    if subject_digest != runtime_attestation.digest_value:
        raise DomainValidationError("supply-chain subject digest does not match the artifact")
    predicate = claims.get("predicate")
    if not isinstance(predicate, dict):
        raise DomainValidationError("supply-chain predicate is missing")
    if predicate.get("artifact_attestation_hash") != runtime_attestation.attestation_hash:
        raise DomainValidationError("supply-chain runtime attestation hash does not match")
    if predicate.get("runtime_manifest_hash") != runtime_attestation.manifest_hash:
        raise DomainValidationError("supply-chain runtime manifest hash does not match")
    sbom_reference = predicate.get("sbom")
    if not isinstance(sbom_reference, dict):
        raise DomainValidationError("supply-chain SBOM reference is missing")
    digest_reference = sbom_reference.get("digest")
    if (
        sbom_reference.get("format") != "CycloneDX"
        or sbom_reference.get("spec_version") != sbom.get("specVersion")
        or not isinstance(digest_reference, dict)
        or digest_reference.get("sha256") != stable_hash(sbom)
    ):
        raise DomainValidationError("supply-chain SBOM reference does not match the SBOM")
    return subject_digest, predicate


def _validated_cyclonedx_sbom(value: dict[str, Any]) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("CycloneDX SBOM must be JSON serializable") from exc
    if len(encoded) > MAX_SBOM_BYTES:
        raise DomainValidationError("CycloneDX SBOM is too large")
    if value.get("bomFormat") != "CycloneDX":
        raise DomainValidationError("SBOM format must be CycloneDX")
    spec_version = str(value.get("specVersion") or "").strip()
    if spec_version not in {"1.4", "1.5", "1.6"}:
        raise DomainValidationError("CycloneDX SBOM specVersion is not supported")
    components = value.get("components")
    if not isinstance(components, list) or not components:
        raise DomainValidationError("CycloneDX SBOM must contain components")
    for component in components:
        if (
            not isinstance(component, dict)
            or not str(component.get("name") or "").strip()
            or not str(component.get("type") or "").strip()
        ):
            raise DomainValidationError("CycloneDX SBOM contains an invalid component")
    return dict(value)


def _normalized_digest(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized[7:]
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise DomainValidationError("signed evidence subject digest is not SHA-256")
    return f"sha256:{normalized}"


def _uuid_claim(claims: dict[str, Any], name: str) -> UUID:
    try:
        return UUID(str(claims.get(name) or ""))
    except ValueError as exc:
        raise DomainValidationError(f"production evidence {name} is invalid") from exc


def _integer_claim(claims: dict[str, Any], name: str) -> int:
    value = claims.get(name)
    if isinstance(value, bool):
        raise DomainValidationError(f"production evidence {name} is invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(f"production evidence {name} is invalid") from exc
    if parsed < 0:
        raise DomainValidationError(f"production evidence {name} is invalid")
    return parsed


def _datetime_claim(claims: dict[str, Any], name: str) -> dt.datetime:
    value = str(claims.get(name) or "").strip()
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainValidationError(f"production evidence {name} is invalid") from exc
    if parsed.tzinfo is None:
        raise DomainValidationError(f"production evidence {name} requires a timezone")
    return parsed.astimezone(dt.UTC)


def _assert_supply_chain_operator(identity: SignerIdentity) -> None:
    role = (identity.role or "").strip().lower()
    if not identity.identity_verified or role not in MAINTENANCE_ROLES:
        raise DomainValidationError(
            "supply-chain evidence requires a verified maintenance operator"
        )


def _optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None
