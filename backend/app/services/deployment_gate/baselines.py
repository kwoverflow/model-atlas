from __future__ import annotations

import datetime as dt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeploymentBaseline, GateEvaluation
from app.schemas import BaselinePromotionCreate
from app.services.deployment_gate.evidence import stable_hash
from app.services.experiment_lineage import (
    record_baseline_promoted,
    record_baseline_superseded,
)
from app.validators import DomainValidationError


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _baseline_hash(gate: GateEvaluation) -> str:
    snapshot = gate.evidence_snapshot_json or {}
    return stable_hash(
        {
            "gate_evaluation_id": str(gate.id),
            "decision_hash": gate.decision_hash,
            "deployment_configuration_id": str(gate.deployment_configuration_id),
            "evaluation_suite_id": str(gate.evaluation_suite_id),
            "acceptance_policy_id": str(gate.acceptance_policy_id),
            "configuration_hash": snapshot.get("configuration_hash"),
            "suite_hash": snapshot.get("suite_hash"),
            "policy_hash": snapshot.get("policy_hash"),
            "scorecard_metrics": (gate.scorecard_json or {}).get("metrics", {}),
            "verdict": gate.verdict,
        }
    )


def _active_baselines_for_scope(
    db: Session,
    *,
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
    acceptance_policy_id: UUID,
) -> list[DeploymentBaseline]:
    return list(
        db.scalars(
            select(DeploymentBaseline)
            .where(
                DeploymentBaseline.deployment_configuration_id == deployment_configuration_id,
                DeploymentBaseline.evaluation_suite_id == evaluation_suite_id,
                DeploymentBaseline.acceptance_policy_id == acceptance_policy_id,
                DeploymentBaseline.status == "active",
            )
            .order_by(DeploymentBaseline.promoted_at.desc())
        )
    )


def get_active_baseline_gate(
    db: Session,
    *,
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
    acceptance_policy_id: UUID,
) -> GateEvaluation | None:
    baseline = db.scalar(
        select(DeploymentBaseline)
        .where(
            DeploymentBaseline.deployment_configuration_id == deployment_configuration_id,
            DeploymentBaseline.evaluation_suite_id == evaluation_suite_id,
            DeploymentBaseline.acceptance_policy_id == acceptance_policy_id,
            DeploymentBaseline.status == "active",
        )
        .order_by(DeploymentBaseline.promoted_at.desc())
        .limit(1)
    )
    if baseline is None:
        return None
    return db.get(GateEvaluation, baseline.gate_evaluation_id)


def promote_gate_evaluation_as_baseline(
    db: Session,
    *,
    gate_evaluation_id: UUID,
    payload: BaselinePromotionCreate,
) -> DeploymentBaseline:
    gate = db.get(GateEvaluation, gate_evaluation_id)
    if gate is None:
        raise DomainValidationError("gate_evaluation was not found")
    if gate.status != "completed":
        raise DomainValidationError("only completed gate evaluations can be promoted")
    if gate.verdict != "APPROVED":
        raise DomainValidationError("only APPROVED gate evaluations can be promoted")

    now = _utcnow()
    previous_active = _active_baselines_for_scope(
        db,
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        acceptance_policy_id=gate.acceptance_policy_id,
    )
    baseline = DeploymentBaseline(
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        acceptance_policy_id=gate.acceptance_policy_id,
        gate_evaluation_id=gate.id,
        promoted_at=now,
        promoted_by=payload.promoted_by,
        promotion_reason=payload.promotion_reason,
        baseline_hash=_baseline_hash(gate),
        status="active",
        notes=payload.notes,
    )
    db.add(baseline)
    db.flush()
    record_baseline_promoted(db, baseline)

    for previous in previous_active:
        previous.status = "superseded"
        previous.superseded_at = now
        previous.superseded_by_baseline_id = baseline.id
        db.add(previous)
        record_baseline_superseded(db, previous)

    db.commit()
    db.refresh(baseline)
    return baseline


def get_deployment_baseline(db: Session, baseline_id: UUID) -> DeploymentBaseline:
    baseline = db.get(DeploymentBaseline, baseline_id)
    if baseline is None:
        raise DomainValidationError("deployment_baseline was not found")
    return baseline


def list_deployment_baselines(
    db: Session,
    *,
    limit: int,
    offset: int,
    active_only: bool = False,
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
) -> list[DeploymentBaseline]:
    query = select(DeploymentBaseline)
    if active_only:
        query = query.where(DeploymentBaseline.status == "active")
    if deployment_configuration_id is not None:
        query = query.where(
            DeploymentBaseline.deployment_configuration_id == deployment_configuration_id
        )
    if evaluation_suite_id is not None:
        query = query.where(DeploymentBaseline.evaluation_suite_id == evaluation_suite_id)
    if acceptance_policy_id is not None:
        query = query.where(DeploymentBaseline.acceptance_policy_id == acceptance_policy_id)
    return list(
        db.scalars(
            query.order_by(DeploymentBaseline.promoted_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )
