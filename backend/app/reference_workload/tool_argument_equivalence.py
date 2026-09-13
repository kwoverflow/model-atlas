"""Evaluator-only comparison of exact arguments and a pinned local default contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.reference_workload.manifest import stable_hash
from app.reference_workload.tool_fault_cases import prepare_baseline_cases
from app.services import tool_execution
from app.services.tool_call_contract import compile_bounded_tool_call

POLICY_VERSION = "local-tool-default-equivalence-v1"
HANDLER_SOURCE_SHA256 = "e3f6e0a1cb986c2a3530a5cf3a0a92b188278e7cd508034c2d23544cb8cb2887"
TICKET_VERSION = "create_ticket-fault-fixture-v1"


def validate_default_policy(registry) -> dict:
    """Refuse to carry a default assumption into changed or external Tool implementations."""
    ticket = registry.get("create_ticket")
    if ticket is None or ticket.descriptor.tool_version != TICKET_VERSION:
        raise ValueError("default equivalence requires the pinned local ticket fixture")
    if ticket.handler is not tool_execution._create_ticket:
        raise ValueError("default equivalence does not cover a replacement ticket handler")
    source_hash = hashlib.sha256(Path(tool_execution.__file__).read_bytes()).hexdigest()
    if source_hash != HANDLER_SOURCE_SHA256:
        raise ValueError("local default handler implementation changed; review the policy")
    schema = ticket.descriptor.argument_schema
    if "priority" in schema.get("required", []) or schema.get("properties", {}).get("priority") != {
        "type": "string",
        "enum": ["low", "normal", "high"],
    }:
        raise ValueError("optional priority schema changed; review the policy")
    return {
        "version": POLICY_VERSION,
        "scope": "local_registered_optional_defaults_only",
        "defaults": {"create_ticket": {"priority": "normal"}},
        "tool_version": TICKET_VERSION,
        "handler_source_sha256": source_hash,
        "comparison_only": True,
        "applied_to_execution": False,
    }


def compare_argument_contract(output: str | None, item, registry, context) -> dict:
    policy = validate_default_policy(registry)
    public, _ = prepare_baseline_cases(item, registry, context)
    expected = compile_bounded_tool_call(
        json.dumps({"tool_name": item.expected_tool, "arguments": item.expected_arguments}),
        input_payload=public.input_payload_json,
        document_context=context,
    )
    if not expected.execution_allowed:
        raise ValueError("invalid evaluator expected argument contract")
    actual = compile_bounded_tool_call(
        output if output is not None else "",
        input_payload=public.input_payload_json,
        document_context=context,
    )
    selected = actual.tool_name == item.expected_tool
    exact = selected and actual.arguments_hash == expected.arguments_hash
    equivalent = False
    actual_defaulted = []
    expected_defaulted = []
    effective_actual_hash = effective_expected_hash = None
    if actual.execution_allowed and selected:
        actual_arguments = json.loads(actual.normalized_output)["arguments"]
        expected_arguments = dict(item.expected_arguments)
        defaults = policy["defaults"].get(item.expected_tool, {})
        actual_defaulted = sorted(set(defaults) - set(actual_arguments))
        expected_defaulted = sorted(set(defaults) - set(expected_arguments))
        # Evaluation projections only. The captured call and executed arguments are never changed.
        effective_actual_hash = stable_hash({**defaults, **actual_arguments})
        effective_expected_hash = stable_hash({**defaults, **expected_arguments})
        equivalent = effective_actual_hash == effective_expected_hash
    reason = (
        "generation_missing"
        if output is None
        else "guard_rejected"
        if not actual.execution_allowed
        else "wrong_tool"
        if not selected
        else "exact_match"
        if exact
        else "declared_default_only"
        if equivalent
        else "argument_values_differ"
    )
    return {
        "policy_version": POLICY_VERSION,
        "semantic_scope": policy["scope"],
        "comparison_only": True,
        "applied_to_execution": False,
        "selection_correct": selected,
        "exact_call": exact,
        "default_equivalent_call": equivalent,
        "default_only_difference": equivalent and not exact,
        "execution_eligible": actual.execution_allowed,
        "reason": reason,
        "actual_arguments_hash": actual.arguments_hash,
        "expected_arguments_hash": expected.arguments_hash,
        "comparison_actual_hash": effective_actual_hash,
        "comparison_expected_hash": effective_expected_hash,
        "comparison_defaulted_actual_keys": actual_defaulted,
        "comparison_defaulted_expected_keys": expected_defaulted,
        "guard": actual.audit_record(),
    }
