from __future__ import annotations

from typing import Any


def _approval_decisions_from_trace(trace: dict[str, Any]) -> dict[str, dict[str, Any]]:
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return {}
    decisions: dict[str, dict[str, Any]] = {}
    for step in steps:
        if not isinstance(step, dict) or step.get("action") != "approval_checkpoint":
            continue
        output = step.get("output")
        if not isinstance(output, dict):
            continue
        checkpoint_id = str(output.get("checkpoint_id") or "").strip()
        decision = str(output.get("decision") or "").strip().lower()
        decided_by = str(output.get("decided_by") or "").strip()
        reason = str(output.get("reason") or "").strip()
        if not checkpoint_id or decision not in {"approved", "denied"}:
            continue
        if not decided_by or not reason:
            continue
        decisions[checkpoint_id] = {
            key: output[key]
            for key in (
                "decision",
                "decided_by",
                "reason",
                "decision_source",
                "policy_version",
                "decision_hash",
                "identity_verified",
                "approver_identity",
                "decided_at",
                "checkpoint_record_id",
            )
            if output.get(key) is not None
        }
    return decisions


def approval_decisions_from_agent_trace(
    trace: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return _approval_decisions_from_trace(trace)
