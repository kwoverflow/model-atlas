from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EvidenceTrustRoot,
    EvidenceTrustRootAction,
    EvidenceTrustSource,
    EvidenceTrustSourceSync,
    ModelSupplyChainAttestation,
    ModelSupplyChainAttestationAction,
    ProductionEvidenceReceipt,
    SupplyChainTransparencyProof,
)
from app.schemas import (
    EvidenceTrustRootActionCreate,
    EvidenceTrustRootCreate,
    EvidenceTrustRootCreateRead,
    EvidenceTrustRootRead,
    EvidenceTrustSourceRead,
    EvidenceTrustSourceSyncRead,
    TransparencyProofCreate,
    TransparencyProofCreateRead,
    TransparencyProofRead,
    TrustRegistryOverviewRead,
)
from app.services.deployment_gate.evidence import stable_hash
from app.services.operator_identity import SignerIdentity
from app.services.signed_evidence import (
    VerifiedSignedStatement,
    inspect_signed_statement,
    verify_signed_statement_with_jwk,
)
from app.validators import DomainValidationError

TRUST_ROOT_SCHEMA_VERSION = "model-atlas-evidence-trust-root-v1"
TRUST_ROOT_RESPONSE_VERSION = "model-atlas-evidence-trust-root-response-v1"
TRUST_REGISTRY_OVERVIEW_VERSION = "model-atlas-trust-registry-overview-v3"
TRANSPARENCY_ENTRY_VERSION = "model-atlas-transparency-entry-v1"
TRANSPARENCY_CHECKPOINT_VERSION = "model-atlas-transparency-checkpoint-v1"
TRANSPARENCY_PROOF_VERSION = "model-atlas-transparency-proof-v1"
TRANSPARENCY_PROOF_RESPONSE_VERSION = "model-atlas-transparency-proof-response-v1"
PRODUCTION_TRUST_TIERS = frozenset({"internal_ca", "external"})
TRUST_GOVERNANCE_ROLES = frozenset({"admin", "model governance", "ml ops lead"})
EVIDENCE_OPERATOR_ROLES = TRUST_GOVERNANCE_ROLES | frozenset({"sre lead"})
PRIVATE_JWK_FIELDS = frozenset({"d", "p", "q", "dp", "dq", "qi", "oth", "k"})


@dataclass(frozen=True)
class RegisteredStatementVerification:
    statement: VerifiedSignedStatement
    trust_root: EvidenceTrustRoot


def create_evidence_trust_root(
    db: Session,
    *,
    payload: EvidenceTrustRootCreate,
    signer_identity: SignerIdentity,
    now: dt.datetime | None = None,
) -> EvidenceTrustRootCreateRead:
    assert_governance_operator(signer_identity)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    valid_from = _utc(payload.valid_from or observed_at).replace(microsecond=0)
    valid_until = (
        _utc(payload.valid_until).replace(microsecond=0)
        if payload.valid_until is not None
        else None
    )
    if valid_until is not None and valid_until <= valid_from:
        raise DomainValidationError("trust root valid_until must be after valid_from")
    jwk = validated_public_jwk(
        payload.public_key_jwk_json,
        key_id=payload.key_id.strip(),
        algorithm=payload.algorithm,
    )
    _validate_source_policy(payload)
    existing = db.scalar(
        select(EvidenceTrustRoot)
        .where(EvidenceTrustRoot.purpose == payload.purpose)
        .where(EvidenceTrustRoot.issuer == payload.issuer.strip())
        .where(EvidenceTrustRoot.key_id == payload.key_id.strip())
    )
    if existing is not None and payload.valid_from is None:
        valid_from = _utc(existing.valid_from)
    superseded = None
    if payload.supersedes_trust_root_id is not None and existing is None:
        superseded = db.get(EvidenceTrustRoot, payload.supersedes_trust_root_id)
        if superseded is None:
            raise DomainValidationError("superseded trust root was not found")
        if superseded.purpose != payload.purpose or superseded.issuer != payload.issuer.strip():
            raise DomainValidationError("rotated trust root must keep the same purpose and issuer")
        if superseded.key_id == payload.key_id.strip():
            raise DomainValidationError("rotated trust root requires a new key id")
        if trust_root_status(db, superseded, now=observed_at) != "active":
            raise DomainValidationError("only an active trust root can be rotated")
    registration_hash = stable_hash(
        {
            "schema_version": TRUST_ROOT_SCHEMA_VERSION,
            "name": payload.name.strip(),
            "purpose": payload.purpose,
            "issuer": payload.issuer.strip(),
            "key_id": payload.key_id.strip(),
            "algorithm": payload.algorithm,
            "public_key_jwk": jwk,
            "trust_tier": payload.trust_tier,
            "source_type": payload.source_type,
            "source_uri": _optional_text(payload.source_uri),
            "valid_from": valid_from.isoformat(),
            "valid_until": valid_until.isoformat() if valid_until else None,
            "supersedes_trust_root_id": (
                str(payload.supersedes_trust_root_id)
                if payload.supersedes_trust_root_id
                else None
            ),
        }
    )
    if existing is not None:
        if existing.registration_hash != registration_hash:
            raise DomainValidationError(
                "trust root purpose, issuer, and key id were already registered differently"
            )
        reconcile_existing_evidence(db, existing)
        db.commit()
        return EvidenceTrustRootCreateRead(
            schema_version=TRUST_ROOT_RESPONSE_VERSION,
            created=False,
            trust_root=evidence_trust_root_read(db, existing, now=observed_at),
        )
    trust_root = EvidenceTrustRoot(
        name=payload.name.strip(),
        purpose=payload.purpose,
        issuer=payload.issuer.strip(),
        key_id=payload.key_id.strip(),
        algorithm=payload.algorithm,
        key_fingerprint=stable_hash(jwk),
        public_key_jwk_json=jwk,
        trust_tier=payload.trust_tier,
        source_type=payload.source_type,
        source_uri=_optional_text(payload.source_uri),
        valid_from=valid_from,
        valid_until=valid_until,
        supersedes_trust_root_id=payload.supersedes_trust_root_id,
        registered_at=observed_at,
        registered_by_identity_json=signer_identity.to_json(),
        identity_verified=True,
        registration_hash=registration_hash,
        notes=_optional_text(payload.notes),
    )
    db.add(trust_root)
    db.flush()
    if superseded is not None:
        db.add(
            _trust_root_action(
                superseded,
                action_type="rotated",
                reason=f"Superseded by trust root {trust_root.id}",
                ticket_reference=signer_identity.ticket_reference,
                signer_identity=signer_identity,
                occurred_at=observed_at,
            )
        )
    reconcile_existing_evidence(db, trust_root)
    db.commit()
    db.refresh(trust_root)
    return EvidenceTrustRootCreateRead(
        schema_version=TRUST_ROOT_RESPONSE_VERSION,
        created=True,
        trust_root=evidence_trust_root_read(db, trust_root, now=observed_at),
    )


def list_evidence_trust_roots(
    db: Session,
    *,
    purpose: str | None = None,
    limit: int = 100,
    now: dt.datetime | None = None,
) -> list[EvidenceTrustRootRead]:
    query = select(EvidenceTrustRoot)
    if purpose is not None:
        query = query.where(EvidenceTrustRoot.purpose == purpose)
    records = list(
        db.scalars(
            query.order_by(EvidenceTrustRoot.registered_at.desc()).limit(limit)
        ).all()
    )
    return [evidence_trust_root_read(db, record, now=now) for record in records]


def list_evidence_trust_sources(
    db: Session,
    *,
    purpose: str | None = None,
    limit: int = 100,
    now: dt.datetime | None = None,
) -> list[EvidenceTrustSourceRead]:
    query = select(EvidenceTrustSource)
    if purpose is not None:
        query = query.where(EvidenceTrustSource.purpose == purpose)
    records = list(
        db.scalars(
            query.order_by(EvidenceTrustSource.registered_at.desc()).limit(limit)
        ).all()
    )
    return [evidence_trust_source_read(db, record, now=now) for record in records]


def list_evidence_trust_source_syncs(
    db: Session,
    *,
    trust_source_id: UUID | None = None,
    limit: int = 100,
) -> list[EvidenceTrustSourceSyncRead]:
    query = select(EvidenceTrustSourceSync)
    if trust_source_id is not None:
        query = query.where(EvidenceTrustSourceSync.trust_source_id == trust_source_id)
    records = list(
        db.scalars(
            query.order_by(
                EvidenceTrustSourceSync.completed_at.desc(),
                EvidenceTrustSourceSync.created_at.desc(),
            ).limit(limit)
        ).all()
    )
    return [EvidenceTrustSourceSyncRead.model_validate(record) for record in records]


def evidence_trust_source_read(
    db: Session,
    trust_source: EvidenceTrustSource,
    *,
    now: dt.datetime | None = None,
) -> EvidenceTrustSourceRead:
    observed_at = _utc(now or dt.datetime.now(dt.UTC))
    latest_attempt = _latest_source_sync(db, trust_source.id)
    latest_apply = _latest_successful_source_apply(db, trust_source.id)
    status = trust_source_status(
        db,
        trust_source,
        now=observed_at,
        latest_attempt=latest_attempt,
        latest_apply=latest_apply,
    )
    next_sync_due_at = (
        _utc(latest_apply.completed_at)
        + dt.timedelta(seconds=trust_source.freshness_seconds)
        if latest_apply is not None
        else None
    )
    base = {
        column.name: getattr(trust_source, column.name)
        for column in EvidenceTrustSource.__table__.columns
    }
    return EvidenceTrustSourceRead.model_validate(
        {
            **base,
            "status": status,
            "production_eligible": bool(
                trust_source.trust_tier in PRODUCTION_TRUST_TIERS
                and status in {"healthy", "degraded"}
            ),
            "latest_attempt_at": (
                latest_attempt.completed_at if latest_attempt is not None else None
            ),
            "latest_attempt_status": (
                latest_attempt.status if latest_attempt is not None else None
            ),
            "last_successful_apply_at": (
                latest_apply.completed_at if latest_apply is not None else None
            ),
            "next_sync_due_at": next_sync_due_at,
            "current_key_count": latest_apply.key_count if latest_apply is not None else 0,
        }
    )


def trust_source_status(
    db: Session,
    trust_source: EvidenceTrustSource,
    *,
    now: dt.datetime | None = None,
    latest_attempt: EvidenceTrustSourceSync | None = None,
    latest_apply: EvidenceTrustSourceSync | None = None,
) -> str:
    if not trust_source.enabled:
        return "disabled"
    observed_at = _utc(now or dt.datetime.now(dt.UTC))
    latest = latest_attempt or _latest_source_sync(db, trust_source.id)
    applied = latest_apply or _latest_successful_source_apply(db, trust_source.id)
    if applied is None:
        return "failed" if latest is not None and latest.status == "failed" else "unsynced"
    expires_at = _utc(applied.completed_at) + dt.timedelta(
        seconds=trust_source.freshness_seconds
    )
    if observed_at >= expires_at:
        return "stale"
    if (
        latest is not None
        and latest.status == "failed"
        and latest.id != applied.id
    ):
        return "degraded"
    return "healthy"


def trust_source_key_is_current(
    db: Session,
    trust_root: EvidenceTrustRoot,
    *,
    now: dt.datetime | None = None,
) -> bool:
    if trust_root.trust_source_id is None:
        return True
    trust_source = db.get(EvidenceTrustSource, trust_root.trust_source_id)
    if trust_source is None:
        return False
    latest_apply = _latest_successful_source_apply(db, trust_source.id)
    status = trust_source_status(
        db,
        trust_source,
        now=now,
        latest_apply=latest_apply,
    )
    if latest_apply is None or status not in {"healthy", "degraded"}:
        return False
    return any(
        str(item.get("fingerprint") or "") == trust_root.key_fingerprint
        for item in latest_apply.observed_keys_json
        if isinstance(item, dict)
    )


def _latest_source_sync(
    db: Session,
    trust_source_id: UUID,
) -> EvidenceTrustSourceSync | None:
    return db.scalar(
        select(EvidenceTrustSourceSync)
        .where(EvidenceTrustSourceSync.trust_source_id == trust_source_id)
        .order_by(
            EvidenceTrustSourceSync.completed_at.desc(),
            EvidenceTrustSourceSync.created_at.desc(),
        )
        .limit(1)
    )


def _latest_successful_source_apply(
    db: Session,
    trust_source_id: UUID,
) -> EvidenceTrustSourceSync | None:
    return db.scalar(
        select(EvidenceTrustSourceSync)
        .where(EvidenceTrustSourceSync.trust_source_id == trust_source_id)
        .where(EvidenceTrustSourceSync.mode == "apply")
        .where(EvidenceTrustSourceSync.status == "succeeded")
        .order_by(
            EvidenceTrustSourceSync.completed_at.desc(),
            EvidenceTrustSourceSync.created_at.desc(),
        )
        .limit(1)
    )


def evidence_trust_root_read(
    db: Session,
    trust_root: EvidenceTrustRoot,
    *,
    now: dt.datetime | None = None,
) -> EvidenceTrustRootRead:
    actions = _trust_root_actions(db, trust_root.id)
    status = trust_root_status(db, trust_root, actions=actions, now=now)
    base = {
        column.name: getattr(trust_root, column.name)
        for column in EvidenceTrustRoot.__table__.columns
    }
    latest = actions[-1] if actions else None
    trust_source = (
        db.get(EvidenceTrustSource, trust_root.trust_source_id)
        if trust_root.trust_source_id
        else None
    )
    source_status = (
        trust_source_status(db, trust_source, now=now)
        if trust_source is not None
        else None
    )
    source_key_current = (
        trust_source_key_is_current(db, trust_root, now=now)
        if trust_source is not None
        else None
    )
    return EvidenceTrustRootRead.model_validate(
        {
            **base,
            "status": status,
            "production_eligible": trust_root_is_production_eligible(
                db,
                trust_root,
                now=now,
            ),
            "action_count": len(actions),
            "latest_action_type": latest.action_type if latest else None,
            "latest_action_at": latest.occurred_at if latest else None,
            "trust_source_status": source_status,
            "source_key_current": source_key_current,
        }
    )


def record_evidence_trust_root_action(
    db: Session,
    *,
    trust_root_id: UUID,
    payload: EvidenceTrustRootActionCreate,
    signer_identity: SignerIdentity,
    now: dt.datetime | None = None,
) -> EvidenceTrustRootAction:
    assert_governance_operator(signer_identity)
    trust_root = db.get(EvidenceTrustRoot, trust_root_id)
    if trust_root is None:
        raise DomainValidationError("evidence trust root was not found")
    status = trust_root_status(db, trust_root, now=now)
    if payload.action_type == "retired" and status != "active":
        raise DomainValidationError("only an active trust root can be retired")
    if payload.action_type == "revoked" and status == "revoked":
        raise DomainValidationError("evidence trust root is already revoked")
    registrar_subject = str(
        (trust_root.registered_by_identity_json or {}).get("subject_id") or ""
    )
    if payload.action_type == "revoked" and registrar_subject == signer_identity.subject_id:
        raise DomainValidationError(
            "trust root revocation requires separation from the trust root registrar"
        )
    occurred_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    action = _trust_root_action(
        trust_root,
        action_type=payload.action_type,
        reason=payload.reason.strip(),
        ticket_reference=_optional_text(payload.ticket_reference),
        signer_identity=signer_identity,
        occurred_at=occurred_at,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def trust_root_status(
    db: Session,
    trust_root: EvidenceTrustRoot,
    *,
    actions: list[EvidenceTrustRootAction] | None = None,
    now: dt.datetime | None = None,
) -> str:
    root_actions = actions if actions is not None else _trust_root_actions(db, trust_root.id)
    action_types = {action.action_type for action in root_actions}
    if "revoked" in action_types:
        return "revoked"
    if action_types & {"retired", "rotated"}:
        return "retired"
    observed_at = _utc(now or dt.datetime.now(dt.UTC))
    if observed_at < _utc(trust_root.valid_from):
        return "scheduled"
    if trust_root.valid_until is not None and observed_at >= _utc(trust_root.valid_until):
        return "expired"
    return "active"


def trust_root_is_production_eligible(
    db: Session,
    trust_root: EvidenceTrustRoot | None,
    *,
    now: dt.datetime | None = None,
) -> bool:
    if (
        trust_root is None
        or trust_root.trust_tier not in PRODUCTION_TRUST_TIERS
        or trust_root_status(db, trust_root, now=now) != "active"
    ):
        return False
    if trust_root.trust_source_id is None:
        return True
    return trust_source_key_is_current(db, trust_root, now=now)


def verify_registered_signed_statement(
    db: Session,
    compact_jws: str,
    *,
    purpose: str,
    max_age_seconds: int,
    now: dt.datetime | None = None,
) -> RegisteredStatementVerification | None:
    identity = inspect_signed_statement(compact_jws)
    issuer_key_roots = list(
        db.scalars(
            select(EvidenceTrustRoot)
            .where(EvidenceTrustRoot.issuer == identity.issuer)
            .where(EvidenceTrustRoot.key_id == identity.key_id)
        ).all()
    )
    if not issuer_key_roots:
        return None
    matching = [root for root in issuer_key_roots if root.purpose == purpose]
    if len(matching) != 1:
        raise DomainValidationError("signed evidence key is not trusted for this purpose")
    trust_root = matching[0]
    if trust_root.algorithm != identity.algorithm:
        raise DomainValidationError("registered trust root algorithm does not match the JWS")
    if trust_root_status(db, trust_root, now=now) != "active":
        raise DomainValidationError("registered evidence trust root is not active")
    statement = verify_signed_statement_with_jwk(
        compact_jws,
        jwk=dict(trust_root.public_key_jwk_json),
        allowed_issuers=[trust_root.issuer],
        allowed_algorithms=[trust_root.algorithm],
        max_age_seconds=max_age_seconds,
        now=now,
    )
    if statement.key_fingerprint != trust_root.key_fingerprint:
        raise DomainValidationError("registered evidence key fingerprint does not match")
    return RegisteredStatementVerification(statement=statement, trust_root=trust_root)


def create_transparency_proof(
    db: Session,
    *,
    payload: TransparencyProofCreate,
    signer_identity: SignerIdentity,
    max_age_seconds: int,
    now: dt.datetime | None = None,
) -> TransparencyProofCreateRead:
    _assert_evidence_operator(signer_identity)
    observed_at = _utc(now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    attestation = db.get(
        ModelSupplyChainAttestation,
        payload.supply_chain_attestation_id,
    )
    if attestation is None:
        raise DomainValidationError("supply-chain attestation was not found")
    if _attestation_is_revoked(db, attestation.id):
        raise DomainValidationError("transparency proof cannot attach to a revoked attestation")
    registered = verify_registered_signed_statement(
        db,
        payload.signed_checkpoint_jws,
        purpose="transparency_log",
        max_age_seconds=max_age_seconds,
        now=observed_at,
    )
    if registered is None:
        raise DomainValidationError("transparency proof requires a managed log trust root")
    claims = registered.statement.claims
    if claims.get("schema_version") != TRANSPARENCY_CHECKPOINT_VERSION:
        raise DomainValidationError("transparency checkpoint schema_version is not supported")
    log_id = str(claims.get("log_id") or "").strip()
    if not log_id or len(log_id) > 240:
        raise DomainValidationError("transparency checkpoint log_id is invalid")
    tree_size = _positive_integer_claim(claims, "tree_size")
    if payload.log_index >= tree_size:
        raise DomainValidationError("transparency proof log_index is outside the tree")
    integrated_at = _datetime_claim(claims, "integrated_at")
    if integrated_at > observed_at + dt.timedelta(minutes=5):
        raise DomainValidationError("transparency checkpoint integrated_at is in the future")
    entry = _validated_transparency_entry(payload.entry_json, attestation=attestation)
    leaf_hash = transparency_leaf_hash(entry)
    if _hash_claim(claims, "leaf_hash") != leaf_hash:
        raise DomainValidationError("transparency checkpoint leaf hash does not match")
    root_hash = _hash_claim(claims, "root_hash")
    inclusion_path = [_normalized_hash(value) for value in payload.inclusion_path]
    calculated_root = calculate_transparency_root(
        leaf_hash,
        log_index=payload.log_index,
        tree_size=tree_size,
        inclusion_path=inclusion_path,
    )
    if calculated_root != root_hash:
        raise DomainValidationError("transparency inclusion proof does not match the checkpoint")
    proof_hash = stable_hash(
        {
            "schema_version": TRANSPARENCY_PROOF_VERSION,
            "supply_chain_attestation_id": str(attestation.id),
            "log_trust_root_id": str(registered.trust_root.id),
            "checkpoint": claims,
            "checkpoint_header": registered.statement.header,
            "checkpoint_jws_hash": stable_hash(payload.signed_checkpoint_jws.strip()),
            "entry": entry,
            "log_index": payload.log_index,
            "inclusion_path": inclusion_path,
        }
    )
    existing = db.scalar(
        select(SupplyChainTransparencyProof).where(
            SupplyChainTransparencyProof.proof_id == registered.statement.statement_id
        )
    )
    if existing is not None:
        if existing.proof_hash != proof_hash:
            raise DomainValidationError(
                "transparency proof id was already used with different content"
            )
        return TransparencyProofCreateRead(
            schema_version=TRANSPARENCY_PROOF_RESPONSE_VERSION,
            created=False,
            proof=transparency_proof_read(db, existing, now=observed_at),
        )
    proof = SupplyChainTransparencyProof(
        supply_chain_attestation_id=attestation.id,
        log_trust_root_id=registered.trust_root.id,
        schema_version=TRANSPARENCY_PROOF_VERSION,
        proof_id=registered.statement.statement_id,
        log_id=log_id,
        log_index=payload.log_index,
        tree_size=tree_size,
        integrated_at=integrated_at,
        leaf_hash=leaf_hash,
        root_hash=root_hash,
        entry_json=entry,
        inclusion_path_json=inclusion_path,
        checkpoint_json=claims,
        checkpoint_jws=payload.signed_checkpoint_jws.strip(),
        signature_algorithm=registered.statement.algorithm,
        key_id=registered.statement.key_id,
        key_fingerprint=registered.statement.key_fingerprint,
        signature_verified=True,
        verified_at=observed_at,
        verified_by_identity_json=signer_identity.to_json(),
        identity_verified=True,
        proof_hash=proof_hash,
        notes=_optional_text(payload.notes),
    )
    db.add(proof)
    db.commit()
    db.refresh(proof)
    return TransparencyProofCreateRead(
        schema_version=TRANSPARENCY_PROOF_RESPONSE_VERSION,
        created=True,
        proof=transparency_proof_read(db, proof, now=observed_at),
    )


def list_transparency_proofs(
    db: Session,
    *,
    supply_chain_attestation_id: UUID | None = None,
    limit: int = 100,
    now: dt.datetime | None = None,
) -> list[TransparencyProofRead]:
    query = select(SupplyChainTransparencyProof)
    if supply_chain_attestation_id is not None:
        query = query.where(
            SupplyChainTransparencyProof.supply_chain_attestation_id
            == supply_chain_attestation_id
        )
    records = list(
        db.scalars(
            query.order_by(SupplyChainTransparencyProof.integrated_at.desc()).limit(limit)
        ).all()
    )
    return [transparency_proof_read(db, record, now=now) for record in records]


def transparency_proof_read(
    db: Session,
    proof: SupplyChainTransparencyProof,
    *,
    now: dt.datetime | None = None,
) -> TransparencyProofRead:
    root = db.get(EvidenceTrustRoot, proof.log_trust_root_id)
    if root is None:
        raise DomainValidationError("transparency proof log trust root was not found")
    root_status = trust_root_status(db, root, now=now)
    base = {
        column.name: getattr(proof, column.name)
        for column in SupplyChainTransparencyProof.__table__.columns
        if column.name != "checkpoint_jws"
    }
    return TransparencyProofRead.model_validate(
        {
            **base,
            "trust_root_status": root_status,
            "production_eligible": bool(
                proof.signature_verified
                and proof.identity_verified
                and trust_root_is_production_eligible(db, root, now=now)
            ),
        }
    )


def supply_chain_transparency_status(
    db: Session,
    attestation: ModelSupplyChainAttestation,
    *,
    now: dt.datetime | None = None,
) -> str:
    proofs = list(
        db.scalars(
            select(SupplyChainTransparencyProof).where(
                SupplyChainTransparencyProof.supply_chain_attestation_id
                == attestation.id
            )
        ).all()
    )
    if not proofs:
        return "missing"
    if any(transparency_proof_read(db, proof, now=now).production_eligible for proof in proofs):
        return "verified"
    if any(
        proof.signature_verified
        and proof.identity_verified
        and (
            (root := db.get(EvidenceTrustRoot, proof.log_trust_root_id)) is not None
            and root.trust_tier == "development"
            and trust_root_status(db, root, now=now) == "active"
        )
        for proof in proofs
    ):
        return "development"
    return "invalidated"


def supply_chain_is_production_eligible(
    db: Session,
    attestation: ModelSupplyChainAttestation,
    *,
    now: dt.datetime | None = None,
) -> bool:
    if _attestation_is_revoked(db, attestation.id):
        return False
    publisher_root = (
        db.get(EvidenceTrustRoot, attestation.publisher_trust_root_id)
        if attestation.publisher_trust_root_id
        else None
    )
    return bool(
        trust_root_is_production_eligible(db, publisher_root, now=now)
        and supply_chain_transparency_status(db, attestation, now=now) == "verified"
    )


def production_receipt_is_eligible(
    db: Session,
    receipt: ProductionEvidenceReceipt,
    *,
    now: dt.datetime | None = None,
) -> bool:
    collector_root = (
        db.get(EvidenceTrustRoot, receipt.collector_trust_root_id)
        if receipt.collector_trust_root_id
        else None
    )
    attestation = db.get(
        ModelSupplyChainAttestation,
        receipt.supply_chain_attestation_id,
    )
    return bool(
        receipt.signature_verified
        and receipt.identity_verified
        and trust_root_is_production_eligible(db, collector_root, now=now)
        and attestation is not None
        and supply_chain_is_production_eligible(db, attestation, now=now)
    )


def build_trust_registry_overview(
    db: Session,
    *,
    now: dt.datetime | None = None,
) -> TrustRegistryOverviewRead:
    from app.services.trust_source_scheduler import trust_source_schedule_overview

    trust_sources = list(db.scalars(select(EvidenceTrustSource)).all())
    source_reads = [
        evidence_trust_source_read(db, source, now=now) for source in trust_sources
    ]
    roots = list(db.scalars(select(EvidenceTrustRoot)).all())
    root_reads = [evidence_trust_root_read(db, root, now=now) for root in roots]
    proofs = list(db.scalars(select(SupplyChainTransparencyProof)).all())
    proof_reads = [transparency_proof_read(db, proof, now=now) for proof in proofs]
    attestations = list(db.scalars(select(ModelSupplyChainAttestation)).all())
    schedule_overview = trust_source_schedule_overview(db, now=now)
    production_tier_attestation_pending_count = 0
    for attestation in attestations:
        publisher_root = (
            db.get(EvidenceTrustRoot, attestation.publisher_trust_root_id)
            if attestation.publisher_trust_root_id
            else None
        )
        if (
            trust_root_is_production_eligible(db, publisher_root, now=now)
            and not supply_chain_is_production_eligible(db, attestation, now=now)
        ):
            production_tier_attestation_pending_count += 1
    return TrustRegistryOverviewRead(
        schema_version=TRUST_REGISTRY_OVERVIEW_VERSION,
        trust_source_count=len(trust_sources),
        healthy_source_count=sum(source.status == "healthy" for source in source_reads),
        degraded_source_count=sum(
            source.status == "degraded" for source in source_reads
        ),
        stale_source_count=sum(source.status == "stale" for source in source_reads),
        failed_source_count=sum(source.status == "failed" for source in source_reads),
        unsynced_source_count=sum(
            source.status == "unsynced" for source in source_reads
        ),
        automatic_schedule_count=schedule_overview["schedule_count"],
        automatic_schedule_enabled_count=schedule_overview["enabled_count"],
        automatic_schedule_due_count=schedule_overview["due_count"],
        automatic_schedule_retrying_count=schedule_overview["retrying_count"],
        automatic_schedule_failed_count=schedule_overview["failed_count"],
        active_root_count=sum(root.status == "active" for root in root_reads),
        production_eligible_root_count=sum(root.production_eligible for root in root_reads),
        retired_root_count=sum(root.status == "retired" for root in root_reads),
        revoked_root_count=sum(root.status == "revoked" for root in root_reads),
        expired_root_count=sum(root.status == "expired" for root in root_reads),
        scheduled_root_count=sum(root.status == "scheduled" for root in root_reads),
        transparency_proof_count=len(proofs),
        production_eligible_proof_count=sum(proof.production_eligible for proof in proof_reads),
        managed_attestation_count=sum(
            attestation.publisher_trust_root_id is not None for attestation in attestations
        ),
        production_eligible_attestation_count=sum(
            supply_chain_is_production_eligible(db, attestation, now=now)
            for attestation in attestations
        ),
        production_tier_attestation_pending_count=(
            production_tier_attestation_pending_count
        ),
    )


def transparency_leaf_hash(entry: dict[str, Any]) -> str:
    encoded = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b"\x00" + encoded).hexdigest()


def calculate_transparency_root(
    leaf_hash: str,
    *,
    log_index: int,
    tree_size: int,
    inclusion_path: list[str],
) -> str:
    if tree_size <= 0 or log_index < 0 or log_index >= tree_size:
        raise DomainValidationError("transparency proof tree position is invalid")
    current = bytes.fromhex(_normalized_hash(leaf_hash))
    node_index = log_index
    last_node = tree_size - 1
    for sibling_value in inclusion_path:
        sibling = bytes.fromhex(_normalized_hash(sibling_value))
        if node_index == last_node or node_index & 1:
            current = _hash_tree_node(sibling, current)
            while node_index and not node_index & 1:
                node_index >>= 1
                last_node >>= 1
        else:
            current = _hash_tree_node(current, sibling)
        node_index >>= 1
        last_node >>= 1
    if last_node != 0:
        raise DomainValidationError("transparency inclusion path is incomplete")
    return current.hex()


def _hash_tree_node(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def validated_public_jwk(
    value: dict[str, Any],
    *,
    key_id: str,
    algorithm: str,
) -> dict[str, Any]:
    jwk = dict(value)
    if PRIVATE_JWK_FIELDS & set(jwk):
        raise DomainValidationError("trust registry accepts public JWK material only")
    if str(jwk.get("kid") or "").strip() != key_id:
        raise DomainValidationError("trust root JWK kid does not match key_id")
    if str(jwk.get("alg") or "").strip() != algorithm:
        raise DomainValidationError("trust root JWK alg does not match algorithm")
    if str(jwk.get("use") or "sig") != "sig":
        raise DomainValidationError("trust root JWK must be a signing key")
    if str(jwk.get("kty") or "").strip().lower() == "oct":
        raise DomainValidationError("symmetric keys cannot be registered as trust roots")
    try:
        jwt.PyJWK.from_dict(jwk, algorithm=algorithm)
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise DomainValidationError("trust root public JWK is invalid") from exc
    return jwk


def _validate_source_policy(payload: EvidenceTrustRootCreate) -> None:
    source_uri = _optional_text(payload.source_uri)
    if payload.trust_tier == "development":
        if payload.source_type != "development":
            raise DomainValidationError("development trust tier requires development source_type")
        return
    if not source_uri:
        raise DomainValidationError("production trust tiers require a source_uri")
    if payload.trust_tier == "internal_ca" and payload.source_type != "internal_ca":
        raise DomainValidationError("internal_ca trust tier requires internal_ca source_type")
    if payload.trust_tier == "external" and payload.source_type not in {
        "external_registry",
        "transparency_log",
    }:
        raise DomainValidationError(
            "external trust tier requires an external registry or transparency log source"
        )
    if payload.purpose == "transparency_log" and payload.source_type not in {
        "development",
        "internal_ca",
        "transparency_log",
    }:
        raise DomainValidationError("transparency log keys require a log-compatible source")


def _trust_root_action(
    trust_root: EvidenceTrustRoot,
    *,
    action_type: str,
    reason: str,
    ticket_reference: str | None,
    signer_identity: SignerIdentity,
    occurred_at: dt.datetime,
) -> EvidenceTrustRootAction:
    action_hash = stable_hash(
        {
            "schema_version": TRUST_ROOT_SCHEMA_VERSION,
            "trust_root_id": str(trust_root.id),
            "registration_hash": trust_root.registration_hash,
            "action_type": action_type,
            "reason": reason,
            "ticket_reference": ticket_reference,
            "actor": signer_identity.to_json(),
            "occurred_at": occurred_at.isoformat(),
        }
    )
    return EvidenceTrustRootAction(
        trust_root_id=trust_root.id,
        action_type=action_type,
        reason=reason,
        ticket_reference=ticket_reference,
        actor_identity_json=signer_identity.to_json(),
        identity_verified=True,
        occurred_at=occurred_at,
        action_hash=action_hash,
    )


def _trust_root_actions(
    db: Session,
    trust_root_id: UUID,
) -> list[EvidenceTrustRootAction]:
    return list(
        db.scalars(
            select(EvidenceTrustRootAction)
            .where(EvidenceTrustRootAction.trust_root_id == trust_root_id)
            .order_by(EvidenceTrustRootAction.occurred_at, EvidenceTrustRootAction.created_at)
        ).all()
    )


def reconcile_existing_evidence(db: Session, trust_root: EvidenceTrustRoot) -> None:
    if trust_root.purpose == "model_publisher":
        records = list(
            db.scalars(
                select(ModelSupplyChainAttestation)
                .where(ModelSupplyChainAttestation.publisher == trust_root.issuer)
                .where(ModelSupplyChainAttestation.publisher_key_id == trust_root.key_id)
                .where(ModelSupplyChainAttestation.key_fingerprint == trust_root.key_fingerprint)
                .where(ModelSupplyChainAttestation.publisher_trust_root_id.is_(None))
            ).all()
        )
        for record in records:
            record.publisher_trust_root_id = trust_root.id
            record.publisher_trust_tier = trust_root.trust_tier
    if trust_root.purpose == "production_collector":
        receipts = list(
            db.scalars(
                select(ProductionEvidenceReceipt)
                .where(ProductionEvidenceReceipt.issuer == trust_root.issuer)
                .where(ProductionEvidenceReceipt.key_id == trust_root.key_id)
                .where(ProductionEvidenceReceipt.key_fingerprint == trust_root.key_fingerprint)
                .where(ProductionEvidenceReceipt.collector_trust_root_id.is_(None))
            ).all()
        )
        for receipt in receipts:
            receipt.collector_trust_root_id = trust_root.id
            receipt.collector_trust_tier = trust_root.trust_tier


def _validated_transparency_entry(
    value: dict[str, Any],
    *,
    attestation: ModelSupplyChainAttestation,
) -> dict[str, Any]:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("transparency entry must be JSON serializable") from exc
    if len(encoded) > 262_144:
        raise DomainValidationError("transparency entry is too large")
    if value.get("schema_version") != TRANSPARENCY_ENTRY_VERSION:
        raise DomainValidationError("transparency entry schema_version is not supported")
    expected = {
        "supply_chain_attestation_id": str(attestation.id),
        "attestation_hash": attestation.attestation_hash,
        "statement_id": attestation.statement_id,
        "subject_digest": attestation.subject_digest,
    }
    for field, expected_value in expected.items():
        if str(value.get(field) or "") != expected_value:
            raise DomainValidationError(f"transparency entry {field} does not match")
    return dict(value)


def _attestation_is_revoked(db: Session, attestation_id: UUID) -> bool:
    return db.scalar(
        select(ModelSupplyChainAttestationAction.id)
        .where(
            ModelSupplyChainAttestationAction.supply_chain_attestation_id
            == attestation_id
        )
        .where(ModelSupplyChainAttestationAction.action_type == "revoked")
        .limit(1)
    ) is not None


def _positive_integer_claim(claims: dict[str, Any], name: str) -> int:
    value = claims.get(name)
    if isinstance(value, bool):
        raise DomainValidationError(f"transparency checkpoint {name} is invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError(f"transparency checkpoint {name} is invalid") from exc
    if parsed <= 0:
        raise DomainValidationError(f"transparency checkpoint {name} is invalid")
    return parsed


def _datetime_claim(claims: dict[str, Any], name: str) -> dt.datetime:
    value = str(claims.get(name) or "").strip()
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DomainValidationError(f"transparency checkpoint {name} is invalid") from exc
    if parsed.tzinfo is None:
        raise DomainValidationError(f"transparency checkpoint {name} requires a timezone")
    return parsed.astimezone(dt.UTC)


def _hash_claim(claims: dict[str, Any], name: str) -> str:
    return _normalized_hash(claims.get(name))


def _normalized_hash(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized[7:]
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise DomainValidationError("transparency proof contains an invalid SHA-256 hash")
    return normalized


def assert_governance_operator(identity: SignerIdentity) -> None:
    role = (identity.role or "").strip().lower()
    if not identity.identity_verified or role not in TRUST_GOVERNANCE_ROLES:
        raise DomainValidationError(
            "trust registry changes require a verified governance operator"
        )


def _assert_evidence_operator(identity: SignerIdentity) -> None:
    role = (identity.role or "").strip().lower()
    if not identity.identity_verified or role not in EVIDENCE_OPERATOR_ROLES:
        raise DomainValidationError(
            "transparency evidence requires a verified governance or SRE operator"
        )


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        raise DomainValidationError("trust registry timestamps require a timezone")
    return value.astimezone(dt.UTC)


def _optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None
