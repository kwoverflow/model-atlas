"""Deterministic comparison against supplied structured constraints, not inferred intent."""

from __future__ import annotations

import hashlib
import json

from app.schemas.structured_requests import StructuredTicketInput

VERSION = "user-structured-ticket-contract-v1"


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def proposal_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def public_descriptor(registry) -> dict:
    tool = registry.get("create_ticket")
    return {
        "tool_name": "create_ticket",
        "description": tool.descriptor.description,
        "argument_schema": tool.descriptor.argument_schema,
    }


def requested_arguments(draft: StructuredTicketInput) -> dict:
    arguments = {"query": draft.query}
    if draft.priority.mode == "set":
        arguments["priority"] = draft.priority.value
    return arguments


def compare_structured_ticket(draft: StructuredTicketInput, proposal: str, registry) -> dict:
    from app.services.tool_call_contract import compile_bounded_tool_call

    guard = compile_bounded_tool_call(
        proposal, input_payload={"available_tools": [public_descriptor(registry)]}
    )
    reasons = []
    actual = None
    if draft.priority.mode == "unresolved":
        reasons.append("priority_unresolved")
    if not guard.execution_allowed:
        reasons.append("public_guard_rejected")
    else:
        actual = json.loads(guard.normalized_output)["arguments"]
        if actual.get("query") != draft.query:
            reasons.append("query_mismatch")
        if draft.priority.mode == "set" and actual.get("priority") != draft.priority.value:
            reasons.append("priority_mismatch")
        elif draft.priority.mode == "omit" and "priority" in actual:
            reasons.append("priority_must_be_absent")
    return {
        "version": VERSION,
        "allowed": not reasons,
        "reasons": reasons,
        "normalized_proposal": guard.normalized_output,
        "actual_arguments": actual,
        "requested_arguments": requested_arguments(draft),
        "public_guard": guard.audit_record(),
        "argument_repair": False,
        "model_inference": False,
        "scope": "explicit_ticket_tool_query_priority_only",
    }
