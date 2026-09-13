from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeploymentConfiguration, EvaluationSuite, GateEvaluation
from app.services.deployment_gate.evidence import (
    collect_evidence,
    evidence_revision_hash,
)

GATE_STALENESS_VERSION = "gate-evidence-staleness-v1"


@dataclass(frozen=True)
class GateStalenessReconciliation:
    scanned_count: int
    stale_count: int
    scopes_checked: int
    reconciled_at: dt.datetime

    def to_json(self) -> dict[str, int | str]:
        return {
            "schema_version": GATE_STALENESS_VERSION,
            "scanned_count": self.scanned_count,
            "stale_count": self.stale_count,
            "scopes_checked": self.scopes_checked,
            "reconciled_at": self.reconciled_at.isoformat(),
        }


def current_scope_evidence_revision_hash(
    db: Session,
    *,
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
) -> str:
    configuration = db.get(DeploymentConfiguration, deployment_configuration_id)
    suite = db.get(EvaluationSuite, evaluation_suite_id)
    if configuration is None or suite is None:
        return ""
    bundle = collect_evidence(
        db,
        deployment_configuration=configuration,
        evaluation_suite=suite,
    )
    return evidence_revision_hash(bundle)


def mark_scope_gates_stale(
    db: Session,
    *,
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
    current_revision_hash: str | None = None,
    reason: str,
    now: dt.datetime | None = None,
    exclude_gate_evaluation_id: UUID | None = None,
) -> list[GateEvaluation]:
    reconciled_at = now or _utcnow()
    resolved_hash = current_revision_hash or current_scope_evidence_revision_hash(
        db,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
    )
    query = (
        select(GateEvaluation)
        .where(
            GateEvaluation.deployment_configuration_id
            == deployment_configuration_id
        )
        .where(GateEvaluation.evaluation_suite_id == evaluation_suite_id)
        .where(GateEvaluation.status == "completed")
        .with_for_update()
    )
    if exclude_gate_evaluation_id is not None:
        query = query.where(GateEvaluation.id != exclude_gate_evaluation_id)
    stale: list[GateEvaluation] = []
    for gate in db.scalars(query).all():
        frozen_hash = gate.evidence_revision_hash or str(
            (gate.evidence_snapshot_json or {}).get("evidence_revision_hash") or ""
        )
        if frozen_hash == resolved_hash:
            continue
        gate.status = "stale"
        gate.stale_at = reconciled_at
        gate.stale_reason = reason
        stale.append(gate)
    if stale:
        from app.services.release_decisions import record_stale_release_actions

        for gate in stale:
            record_stale_release_actions(
                db,
                gate=gate,
                reason=reason,
                occurred_at=reconciled_at,
            )
    return stale


def supersede_stale_gates(
    db: Session,
    *,
    replacement_gate: GateEvaluation,
) -> int:
    stale_gates = list(
        db.scalars(
            select(GateEvaluation)
            .where(
                GateEvaluation.deployment_configuration_id
                == replacement_gate.deployment_configuration_id
            )
            .where(
                GateEvaluation.evaluation_suite_id
                == replacement_gate.evaluation_suite_id
            )
            .where(GateEvaluation.status == "stale")
            .where(GateEvaluation.superseded_by_gate_evaluation_id.is_(None))
            .with_for_update()
        ).all()
    )
    for gate in stale_gates:
        gate.superseded_by_gate_evaluation_id = replacement_gate.id
    return len(stale_gates)


def reconcile_all_gate_staleness(db: Session) -> GateStalenessReconciliation:
    now = _utcnow()
    gates = list(
        db.scalars(
            select(GateEvaluation)
            .where(GateEvaluation.status == "completed")
            .order_by(GateEvaluation.created_at)
        ).all()
    )
    scopes = {
        (gate.deployment_configuration_id, gate.evaluation_suite_id)
        for gate in gates
    }
    stale_count = 0
    for configuration_id, suite_id in scopes:
        stale_count += len(
            mark_scope_gates_stale(
                db,
                deployment_configuration_id=configuration_id,
                evaluation_suite_id=suite_id,
                reason=(
                    "Evidence revisions changed after this Gate evaluation. "
                    "A new Gate evaluation is required."
                ),
                now=now,
            )
        )
    return GateStalenessReconciliation(
        scanned_count=len(gates),
        stale_count=stale_count,
        scopes_checked=len(scopes),
        reconciled_at=now,
    )


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)
