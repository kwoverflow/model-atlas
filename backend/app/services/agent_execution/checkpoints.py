from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from .contracts import AGENT_APPROVAL_POLICY_VERSION, AgentPreparation


def _step_result(
    *,
    step_index: int,
    action: str,
    expected_action: str | None,
    planned_step: dict[str, Any],
    started: float,
    successful: bool,
    status: str,
    output: dict[str, Any] | None,
    error_type: str | None,
    error_message: str | None,
    policy_violations: list[str] | None = None,
    recovered: bool = False,
    retry_count: int = 0,
    memory_provenance_valid: bool = False,
    approval_provenance_valid: bool = False,
) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "action": action,
        "expected_action": expected_action,
        "status": status,
        "successful": successful,
        "input": dict(planned_step),
        "output": output,
        "error_type": error_type,
        "error_message": error_message,
        "policy_violations": list(policy_violations or []),
        "recovered": recovered,
        "retry_count": retry_count,
        "memory_provenance_valid": memory_provenance_valid,
        "approval_provenance_valid": approval_provenance_valid,
        "recovered_by_replan": False,
        "duration_ms": round(max(0.0, (time.perf_counter() - started) * 1000), 3),
    }


def _execute_approval_checkpoint(
    step_index: int,
    planned_step: dict[str, Any],
    expected: dict[str, Any] | None,
    expected_action: str | None,
    preparation: AgentPreparation,
    started: float,
) -> dict[str, Any]:
    checkpoint_id = str(planned_step.get("checkpoint_id") or "").strip()
    allowed_ids = preparation.agent_context["allowed_checkpoint_ids"]
    expected_checkpoint_id = str(expected.get("checkpoint_id") or "").strip() if expected else ""
    violations: list[str] = []
    if not checkpoint_id:
        violations.append("approval checkpoint_id is required")
    if allowed_ids and checkpoint_id not in allowed_ids:
        violations.append(f"checkpoint {checkpoint_id} is not allowed")
    if expected_checkpoint_id and checkpoint_id != expected_checkpoint_id:
        violations.append(f"expected checkpoint {expected_checkpoint_id}, received {checkpoint_id}")
    if violations:
        return _step_result(
            step_index=step_index,
            action="approval_checkpoint",
            expected_action=expected_action,
            planned_step=planned_step,
            started=started,
            successful=False,
            status="policy_violation",
            output=None,
            error_type="agent_policy_violation",
            error_message="; ".join(violations),
            policy_violations=violations,
        )

    decision = preparation.approval_decisions.get(
        checkpoint_id,
        preparation.approval_decisions.get("*"),
    )
    if decision is None:
        return _step_result(
            step_index=step_index,
            action="approval_checkpoint",
            expected_action=expected_action,
            planned_step=planned_step,
            started=started,
            successful=False,
            status="pending",
            output={
                "checkpoint_id": checkpoint_id,
                "decision": "pending",
                "decision_source": "external_request_only",
                "decision_hash": None,
            },
            error_type="approval_pending",
            error_message=f"Checkpoint {checkpoint_id} requires a human decision.",
        )

    decision_payload: dict[str, Any] = {
        "checkpoint_id": checkpoint_id,
        "decision": decision["decision"],
        "decided_by": decision["decided_by"],
        "reason": decision["reason"],
        "decision_source": decision.get("decision_source", "benchmark_execution_request"),
        "policy_version": decision.get("policy_version", AGENT_APPROVAL_POLICY_VERSION),
    }
    for key in (
        "identity_verified",
        "approver_identity",
        "decided_at",
        "checkpoint_record_id",
    ):
        if decision.get(key) is not None:
            decision_payload[key] = decision[key]
    supplied_hash = str(decision.get("decision_hash") or "").strip().lower()
    decision_hash = (
        supplied_hash
        if len(supplied_hash) == 64
        and all(character in "0123456789abcdef" for character in supplied_hash)
        else hashlib.sha256(
            json.dumps(
                decision_payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    )
    approved = decision["decision"] == "approved"
    return _step_result(
        step_index=step_index,
        action="approval_checkpoint",
        expected_action=expected_action,
        planned_step=planned_step,
        started=started,
        successful=approved,
        status="approved" if approved else "denied",
        output={**decision_payload, "decision_hash": decision_hash},
        error_type=None if approved else "approval_denied",
        error_message=(
            None if approved else f"Checkpoint {checkpoint_id} was denied by the human approver."
        ),
        approval_provenance_valid=bool(decision_hash and decision.get("identity_verified", True)),
    )


def _record_approved_checkpoint(
    step: dict[str, Any],
    approved_checkpoint_ids: set[str],
) -> None:
    if step.get("action") != "approval_checkpoint" or step.get("status") != "approved":
        return
    output = step.get("output")
    if isinstance(output, dict) and output.get("checkpoint_id"):
        approved_checkpoint_ids.add(str(output["checkpoint_id"]))
