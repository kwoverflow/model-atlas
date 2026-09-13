from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GateEvaluation, ReleaseDecision, ReleaseDecisionAction
from app.schemas import (
    ReleaseDecisionActionCreate,
    ReleaseDecisionCreate,
    ReleaseDecisionRead,
    ReleaseSnapshotDiffItem,
    ReleaseSnapshotDiffRead,
)
from app.services.deployment_gate.evidence import stable_hash
from app.services.experiment_lineage import record_release_decision_signed
from app.services.operator_identity import SignerIdentity, build_signer_identity
from app.services.release_approval_policy import assert_release_decision_allowed
from app.services.release_readiness import build_release_readiness_snapshot
from app.validators import DomainValidationError

APPROVABLE_READINESS_STATUSES = {"READY", "READY_TO_PROMOTE"}
DECISION_HASH_VERSION = "release-decision-v1"
IGNORED_SNAPSHOT_DIFF_PATHS = {"generated_at"}
MAX_SNAPSHOT_DIFF_ITEMS = 200
RELEASE_OPERATION_VERSION = "release-decision-operations-v1"
RELEASE_REVIEW_ROLES = frozenset(
    {
        "release manager",
        "ml ops lead",
        "model governance",
        "admin",
        "qa lead",
        "sre lead",
    }
)
RELEASE_REVOKE_ROLES = frozenset(
    {"release manager", "ml ops lead", "model governance", "admin"}
)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _normalized_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _decision_hash(
    *,
    payload: ReleaseDecisionCreate,
    snapshot_hash: str,
    signature_hash: str,
    signer_identity: SignerIdentity,
    approval_policy_json: dict[str, object],
    readiness_status: str,
    gate: GateEvaluation,
    decided_at: dt.datetime,
) -> str:
    return stable_hash(
        {
            "version": DECISION_HASH_VERSION,
            "gate_evaluation_id": str(gate.id),
            "deployment_configuration_id": str(gate.deployment_configuration_id),
            "evaluation_suite_id": str(gate.evaluation_suite_id),
            "acceptance_policy_id": str(gate.acceptance_policy_id),
            "gate_decision_hash": gate.decision_hash,
            "release_readiness_status": readiness_status,
            "snapshot_hash": snapshot_hash,
            "signature_hash": signature_hash,
            "signer_identity": signer_identity.to_json(),
            "approval_policy": approval_policy_json,
            "decision": payload.decision,
            "decided_at": decided_at.isoformat(),
            "decision_reason": payload.decision_reason.strip(),
            "notes": _normalized_text(payload.notes),
            "replaces_release_decision_id": (
                str(payload.replaces_release_decision_id)
                if payload.replaces_release_decision_id
                else None
            ),
        }
    )


def _signature_statement(payload: ReleaseDecisionCreate) -> str:
    default_statement = (
        "I reviewed the frozen readiness snapshot and accept responsibility for "
        "this release decision."
    )
    return (
        _normalized_text(payload.signature_statement)
        or default_statement
    )


def _signature_hash(
    *,
    payload: ReleaseDecisionCreate,
    signer_identity: SignerIdentity,
    snapshot_hash: str,
    readiness_status: str,
    gate: GateEvaluation,
    decided_at: dt.datetime,
    signature_statement: str,
) -> str:
    return stable_hash(
        {
            "version": "release-signature-v1",
            "gate_evaluation_id": str(gate.id),
            "gate_decision_hash": gate.decision_hash,
            "snapshot_hash": snapshot_hash,
            "release_readiness_status": readiness_status,
            "decision": payload.decision,
            "decided_at": decided_at.isoformat(),
            "signer_identity": signer_identity.to_json(),
            "signature_statement": signature_statement,
            "decision_reason": payload.decision_reason.strip(),
            "notes": _normalized_text(payload.notes),
            "replaces_release_decision_id": (
                str(payload.replaces_release_decision_id)
                if payload.replaces_release_decision_id
                else None
            ),
        }
    )


def create_release_decision(
    db: Session,
    payload: ReleaseDecisionCreate,
    *,
    operator_headers: Mapping[str, str] | None = None,
    trusted_operator_identity: SignerIdentity | None = None,
) -> ReleaseDecision:
    gate = db.get(GateEvaluation, payload.gate_evaluation_id)
    if gate is None:
        raise DomainValidationError("gate_evaluation was not found")
    replaced_decision = _validated_replaced_decision(
        db,
        replacement_id=payload.replaces_release_decision_id,
        replacement_gate=gate,
    )

    snapshot = build_release_readiness_snapshot(
        db,
        gate_evaluation_id=payload.gate_evaluation_id,
    )
    if (
        payload.decision == "APPROVE_RELEASE"
        and snapshot.status not in APPROVABLE_READINESS_STATUSES
    ):
        raise DomainValidationError(
            "APPROVE_RELEASE requires readiness status READY or READY_TO_PROMOTE"
        )

    decided_at = _utcnow()
    snapshot_json = snapshot.model_dump(mode="json")
    snapshot_hash = stable_hash(snapshot_json)
    signer_identity = build_signer_identity(
        payload,
        headers=operator_headers,
        trusted_operator_identity=trusted_operator_identity,
    )
    approval_policy = assert_release_decision_allowed(
        decision=payload.decision,
        signer_identity=signer_identity,
    )
    approval_policy_json = approval_policy.to_json()
    signature_statement = _signature_statement(payload)
    signature_hash = _signature_hash(
        payload=payload,
        signer_identity=signer_identity,
        snapshot_hash=snapshot_hash,
        readiness_status=snapshot.status,
        gate=gate,
        decided_at=decided_at,
        signature_statement=signature_statement,
    )
    release_decision = ReleaseDecision(
        gate_evaluation_id=gate.id,
        deployment_configuration_id=snapshot.deployment_configuration_id,
        evaluation_suite_id=snapshot.evaluation_suite_id,
        acceptance_policy_id=snapshot.acceptance_policy_id,
        decision=payload.decision,
        release_readiness_status=snapshot.status,
        decided_at=decided_at,
        decided_by=signer_identity.display_name,
        signer_identity_json=signer_identity.to_json(),
        identity_verified=signer_identity.identity_verified,
        signature_hash=signature_hash,
        signature_statement=signature_statement,
        approval_policy_json=approval_policy_json,
        decision_reason=payload.decision_reason.strip(),
        notes=_normalized_text(payload.notes),
        snapshot_hash=snapshot_hash,
        snapshot_json=snapshot_json,
        decision_hash=_decision_hash(
            payload=payload,
            snapshot_hash=snapshot_hash,
            signature_hash=signature_hash,
            signer_identity=signer_identity,
            approval_policy_json=approval_policy_json,
            readiness_status=snapshot.status,
            gate=gate,
            decided_at=decided_at,
        ),
        replaces_release_decision_id=(
            replaced_decision.id if replaced_decision is not None else None
        ),
    )
    db.add(release_decision)
    db.flush()
    if replaced_decision is not None:
        _add_release_action(
            db,
            release_decision=replaced_decision,
            action_type="replaced",
            dedupe_key=f"replacement:{replaced_decision.id}:{release_decision.id}",
            actor_identity=signer_identity,
            reason=payload.decision_reason.strip(),
            source_gate_evaluation_id=gate.id,
            replacement_release_decision_id=release_decision.id,
            metadata_json={
                "schema_version": RELEASE_OPERATION_VERSION,
                "replacement_decision": payload.decision,
                "replacement_gate_evaluation_id": str(gate.id),
            },
            occurred_at=decided_at,
        )
    record_release_decision_signed(db, release_decision)
    db.commit()
    db.refresh(release_decision)
    return release_decision


def get_release_decision(db: Session, release_decision_id: UUID) -> ReleaseDecision:
    release_decision = db.get(ReleaseDecision, release_decision_id)
    if release_decision is None:
        raise DomainValidationError("release_decision was not found")
    return release_decision


def release_decision_read(
    db: Session,
    release_decision: ReleaseDecision,
) -> ReleaseDecisionRead:
    actions = list_release_decision_actions(
        db,
        release_decision_id=release_decision.id,
    )
    action_types = {action.action_type for action in actions}
    latest_review_request_at = max(
        (
            action.occurred_at
            for action in actions
            if action.action_type == "review_requested"
        ),
        default=None,
    )
    latest_acknowledged_at = max(
        (
            action.occurred_at
            for action in actions
            if action.action_type == "acknowledged"
        ),
        default=None,
    )
    unresolved_review_request = latest_review_request_at is not None and (
        latest_acknowledged_at is None
        or latest_acknowledged_at < latest_review_request_at
    )
    gate = db.get(GateEvaluation, release_decision.gate_evaluation_id)
    stale_warning = (gate is not None and gate.status == "stale") or (
        "stale_detected" in action_types
    )
    if "replaced" in action_types:
        operational_status = "replaced"
    elif "revoked" in action_types:
        operational_status = "revoked"
    elif (
        release_decision.decision == "APPROVE_RELEASE" and stale_warning
    ) or unresolved_review_request:
        operational_status = "needs_review"
    elif release_decision.decision == "APPROVE_RELEASE":
        operational_status = "active"
    else:
        operational_status = "recorded"
    base = ReleaseDecisionRead.model_validate(release_decision)
    return base.model_copy(
        update={
            "operational_status": operational_status,
            "stale_warning": stale_warning,
            "action_count": len(actions),
            "latest_action_at": (
                actions[-1].occurred_at if actions else None
            ),
        }
    )


def list_release_decision_actions(
    db: Session,
    *,
    release_decision_id: UUID,
) -> list[ReleaseDecisionAction]:
    return list(
        db.scalars(
            select(ReleaseDecisionAction)
            .where(
                ReleaseDecisionAction.release_decision_id
                == release_decision_id
            )
            .order_by(
                ReleaseDecisionAction.occurred_at,
                ReleaseDecisionAction.created_at,
            )
        ).all()
    )


def create_release_decision_action(
    db: Session,
    *,
    release_decision_id: UUID,
    payload: ReleaseDecisionActionCreate,
    signer_identity: SignerIdentity,
) -> ReleaseDecisionAction:
    release_decision = get_release_decision(db, release_decision_id)
    _assert_release_operation_allowed(
        action_type=payload.action_type,
        signer_identity=signer_identity,
    )
    current = release_decision_read(db, release_decision)
    if current.operational_status == "replaced":
        raise DomainValidationError(
            "replaced release decisions cannot receive new operations"
        )
    if payload.action_type == "revoked":
        if release_decision.decision != "APPROVE_RELEASE":
            raise DomainValidationError(
                "only approved release decisions can be revoked"
            )
        if current.operational_status == "revoked":
            raise DomainValidationError("release decision is already revoked")
    if (
        payload.action_type == "acknowledged"
        and current.operational_status != "needs_review"
    ):
        raise DomainValidationError(
            "release decision does not currently require review"
        )
    occurred_at = _utcnow()
    action = _add_release_action(
        db,
        release_decision=release_decision,
        action_type=payload.action_type,
        dedupe_key=(
            f"manual:{release_decision.id}:{payload.action_type}:{uuid.uuid4()}"
        ),
        actor_identity=signer_identity,
        reason=payload.reason.strip(),
        source_gate_evaluation_id=release_decision.gate_evaluation_id,
        metadata_json={
            "schema_version": RELEASE_OPERATION_VERSION,
            "operational_status_before": current.operational_status,
        },
        occurred_at=occurred_at,
    )
    db.commit()
    db.refresh(action)
    return action


def record_stale_release_actions(
    db: Session,
    *,
    gate: GateEvaluation,
    reason: str,
    occurred_at: dt.datetime,
) -> int:
    release_decisions = list(
        db.scalars(
            select(ReleaseDecision)
            .where(ReleaseDecision.gate_evaluation_id == gate.id)
            .where(ReleaseDecision.decision == "APPROVE_RELEASE")
        ).all()
    )
    created_count = 0
    for release_decision in release_decisions:
        dedupe_key = f"stale:{release_decision.id}:{gate.id}"
        existing = db.scalar(
            select(ReleaseDecisionAction).where(
                ReleaseDecisionAction.dedupe_key == dedupe_key
            )
        )
        if existing is not None:
            continue
        _add_release_action(
            db,
            release_decision=release_decision,
            action_type="stale_detected",
            dedupe_key=dedupe_key,
            actor_identity=SignerIdentity(
                subject_id="gate-staleness-reconciler",
                display_name="Gate Staleness Reconciler",
                role="System Worker",
                identity_provider="model-atlas",
                auth_source="gate_evidence_reconciliation",
                identity_verified=True,
                ticket_reference=None,
            ),
            reason=reason,
            source_gate_evaluation_id=gate.id,
            metadata_json={
                "schema_version": RELEASE_OPERATION_VERSION,
                "gate_status": gate.status,
                "evidence_revision_hash": gate.evidence_revision_hash,
            },
            occurred_at=occurred_at,
        )
        created_count += 1
    if created_count:
        db.flush()
    return created_count


def build_release_decision_snapshot_diff(
    db: Session,
    release_decision_id: UUID,
) -> ReleaseSnapshotDiffRead:
    release_decision = get_release_decision(db, release_decision_id)
    current_snapshot = build_release_readiness_snapshot(
        db,
        gate_evaluation_id=release_decision.gate_evaluation_id,
    )
    current_snapshot_json = current_snapshot.model_dump(mode="json")
    current_snapshot_hash = stable_hash(current_snapshot_json)
    diffs: list[ReleaseSnapshotDiffItem] = []
    _collect_snapshot_diffs(
        release_decision.snapshot_json or {},
        current_snapshot_json,
        path="",
        diffs=diffs,
    )
    truncated = len(diffs) > MAX_SNAPSHOT_DIFF_ITEMS
    visible_diffs = diffs[:MAX_SNAPSHOT_DIFF_ITEMS]
    return ReleaseSnapshotDiffRead(
        release_decision_id=release_decision.id,
        gate_evaluation_id=release_decision.gate_evaluation_id,
        frozen_snapshot_hash=release_decision.snapshot_hash,
        current_snapshot_hash=current_snapshot_hash,
        changed=bool(diffs),
        diff_count=len(diffs),
        truncated=truncated,
        ignored_paths=sorted(IGNORED_SNAPSHOT_DIFF_PATHS),
        diffs=visible_diffs,
    )


def list_release_decisions(
    db: Session,
    *,
    limit: int,
    offset: int,
    gate_evaluation_id: UUID | None = None,
) -> list[ReleaseDecision]:
    query = select(ReleaseDecision)
    if gate_evaluation_id is not None:
        query = query.where(ReleaseDecision.gate_evaluation_id == gate_evaluation_id)
    return list(
        db.scalars(
            query.order_by(ReleaseDecision.decided_at.desc(), ReleaseDecision.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    )


def _validated_replaced_decision(
    db: Session,
    *,
    replacement_id: UUID | None,
    replacement_gate: GateEvaluation,
) -> ReleaseDecision | None:
    if replacement_id is None:
        return None
    replaced = get_release_decision(db, replacement_id)
    if replaced.gate_evaluation_id == replacement_gate.id:
        raise DomainValidationError(
            "replacement release decision requires a different Gate evaluation"
        )
    if (
        replaced.deployment_configuration_id
        != replacement_gate.deployment_configuration_id
        or replaced.evaluation_suite_id != replacement_gate.evaluation_suite_id
        or replaced.acceptance_policy_id != replacement_gate.acceptance_policy_id
    ):
        raise DomainValidationError(
            "replacement release decision must use the same release scope"
        )
    if release_decision_read(db, replaced).operational_status == "replaced":
        raise DomainValidationError("release decision was already replaced")
    return replaced


def _assert_release_operation_allowed(
    *,
    action_type: str,
    signer_identity: SignerIdentity,
) -> None:
    role = (signer_identity.role or "").strip().lower()
    allowed_roles = (
        RELEASE_REVOKE_ROLES
        if action_type == "revoked"
        else RELEASE_REVIEW_ROLES
    )
    if not signer_identity.identity_verified or role not in allowed_roles:
        raise DomainValidationError(
            "release decision operation requires a verified authorized operator"
        )


def _add_release_action(
    db: Session,
    *,
    release_decision: ReleaseDecision,
    action_type: str,
    dedupe_key: str,
    actor_identity: SignerIdentity,
    reason: str,
    source_gate_evaluation_id: UUID | None,
    metadata_json: dict[str, object],
    occurred_at: dt.datetime,
    replacement_release_decision_id: UUID | None = None,
) -> ReleaseDecisionAction:
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise DomainValidationError("release decision operation reason is required")
    action = ReleaseDecisionAction(
        release_decision_id=release_decision.id,
        action_type=action_type,
        dedupe_key=dedupe_key,
        actor_identity_json=actor_identity.to_json(),
        reason=normalized_reason,
        source_gate_evaluation_id=source_gate_evaluation_id,
        replacement_release_decision_id=replacement_release_decision_id,
        metadata_json=metadata_json,
        occurred_at=occurred_at,
    )
    db.add(action)
    return action


def _collect_snapshot_diffs(
    frozen_value: object,
    current_value: object,
    *,
    path: str,
    diffs: list[ReleaseSnapshotDiffItem],
) -> None:
    if path in IGNORED_SNAPSHOT_DIFF_PATHS:
        return
    if isinstance(frozen_value, dict) and isinstance(current_value, dict):
        for key in sorted(set(frozen_value) | set(current_value)):
            child_path = f"{path}.{key}" if path else str(key)
            frozen_present = key in frozen_value
            current_present = key in current_value
            if not frozen_present:
                diffs.append(
                    ReleaseSnapshotDiffItem(
                        path=child_path,
                        status="added",
                        frozen_present=False,
                        current_present=True,
                        current_value=current_value[key],
                    )
                )
            elif not current_present:
                diffs.append(
                    ReleaseSnapshotDiffItem(
                        path=child_path,
                        status="removed",
                        frozen_present=True,
                        current_present=False,
                        frozen_value=frozen_value[key],
                    )
                )
            else:
                _collect_snapshot_diffs(
                    frozen_value[key],
                    current_value[key],
                    path=child_path,
                    diffs=diffs,
                )
        return

    if isinstance(frozen_value, list) and isinstance(current_value, list):
        shared_count = min(len(frozen_value), len(current_value))
        for index in range(shared_count):
            _collect_snapshot_diffs(
                frozen_value[index],
                current_value[index],
                path=f"{path}[{index}]",
                diffs=diffs,
            )
        for index in range(shared_count, len(current_value)):
            diffs.append(
                ReleaseSnapshotDiffItem(
                    path=f"{path}[{index}]",
                    status="added",
                    frozen_present=False,
                    current_present=True,
                    current_value=current_value[index],
                )
            )
        for index in range(shared_count, len(frozen_value)):
            diffs.append(
                ReleaseSnapshotDiffItem(
                    path=f"{path}[{index}]",
                    status="removed",
                    frozen_present=True,
                    current_present=False,
                    frozen_value=frozen_value[index],
                )
            )
        return

    if frozen_value != current_value:
        diffs.append(
            ReleaseSnapshotDiffItem(
                path=path or "$",
                status="changed",
                frozen_present=True,
                current_present=True,
                frozen_value=frozen_value,
                current_value=current_value,
            )
        )


def render_release_decision_markdown(release_decision: ReleaseDecision) -> str:
    snapshot = release_decision.snapshot_json or {}
    gate = snapshot.get("gate") or {}
    baseline = snapshot.get("baseline") or {}
    judge = snapshot.get("judge_calibration") or {}
    prompt = snapshot.get("prompt_regression") or {}
    evidence_trust = snapshot.get("evidence_trust") or {}
    readiness_reasons = snapshot.get("readiness_reasons") or []
    review_reasons = snapshot.get("review_reasons") or []
    next_actions = snapshot.get("next_actions") or []

    lines = [
        "# Model Atlas Release Decision Record",
        "",
        f"- Decision: {release_decision.decision}",
        f"- Release readiness status: {release_decision.release_readiness_status}",
        f"- Evidence trust: {evidence_trust.get('trust_status') or 'unknown'}",
        f"- Production readiness: {snapshot.get('production_readiness') or 'unknown'}",
        f"- Decided at: {release_decision.decided_at.isoformat()}",
        f"- Decided by: {release_decision.decided_by}",
        f"- Identity verified: {release_decision.identity_verified}",
        f"- Gate evaluation: {release_decision.gate_evaluation_id}",
        f"- Decision hash: {release_decision.decision_hash}",
        f"- Snapshot hash: {release_decision.snapshot_hash}",
        f"- Signature hash: {release_decision.signature_hash or 'none'}",
        "",
        "## Signer Identity",
        "",
        *[
            f"- {key}: {value}"
            for key, value in (release_decision.signer_identity_json or {}).items()
        ],
        "",
        "## Signature Statement",
        "",
        release_decision.signature_statement or "none",
        "",
        "## Approval Policy",
        "",
        *[
            f"- {key}: {value}"
            for key, value in (release_decision.approval_policy_json or {}).items()
        ],
        "",
        "## Reason",
        "",
        release_decision.decision_reason,
        "",
        "## Notes",
        "",
        release_decision.notes or "none",
        "",
        "## Frozen Snapshot Summary",
        "",
        f"- Release summary: {snapshot.get('release_summary') or 'n/a'}",
        f"- Gate verdict: {gate.get('verdict') or 'n/a'}",
        f"- Gate decision hash: {gate.get('decision_hash') or 'n/a'}",
        f"- Active baseline: {baseline.get('active_baseline_id') or 'none'}",
        f"- Gate is active baseline: {baseline.get('gate_is_active_baseline')}",
        f"- Judge rows needing review: {judge.get('needs_review_count', 'n/a')}",
        f"- Prompt regression risk rows: {prompt.get('risk_row_count', 'n/a')}",
        (
            "- Applied judge label coverage: "
            f"{evidence_trust.get('applied_judge_label_rate', 'n/a')}"
        ),
        (
            "- Critical review coverage: "
            f"{evidence_trust.get('critical_review_coverage_rate', 'n/a')}"
        ),
        f"- Production-captured results: {evidence_trust.get('production_captured_count', 0)}",
        "",
        "## Readiness Reasons",
        "",
        *([f"- {reason}" for reason in readiness_reasons] or ["- none"]),
        "",
        "## Review Reasons",
        "",
        *([f"- {reason}" for reason in review_reasons] or ["- none"]),
        "",
        "## Next Actions",
        "",
        *([f"- {action}" for action in next_actions] or ["- none"]),
    ]
    return "\n".join(lines) + "\n"
