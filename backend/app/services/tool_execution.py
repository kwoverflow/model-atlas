from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from app.models import EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult
from app.services.tool_fault_scenarios import (
    TOOL_FAULT_REGISTRY_VERSION,
    TOOL_FAULT_TRACE_VERSION,
    ToolFaultScenario,
    validate_fault_case,
)

TOOL_EXECUTION_SCHEMA_VERSION = "tool-execution-trace-v1"
TOOL_REGISTRY_VERSION = "local-tool-registry-v1"
MAX_TOOL_CALLS_PER_CASE = 8
MAX_TOOL_ATTEMPTS = 3


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    tool_version: str
    display_name: str
    description: str
    argument_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capabilities: frozenset[str]
    side_effect_mode: str = "none"
    default_max_attempts: int = 1

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capabilities"] = sorted(self.capabilities)
        return payload


@dataclass(frozen=True)
class ToolExecutionContext:
    external_case_id: str
    step_index: int
    attempt_number: int
    prior_outputs: tuple[dict[str, Any], ...]


class ToolExecutionError(RuntimeError):
    def __init__(self, message: str, *, error_type: str, retryable: bool) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


ToolHandler = Callable[[dict[str, Any], ToolExecutionContext], dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    descriptor: ToolDescriptor
    handler: ToolHandler


@dataclass(frozen=True)
class ToolRegistry:
    tools: dict[str, RegisteredTool]
    registry_id: str = "model_atlas_local_tools"
    registry_version: str = TOOL_REGISTRY_VERSION

    def get(self, tool_id: str) -> RegisteredTool | None:
        return self.tools.get(tool_id)

    def descriptor(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "tool_count": len(self.tools),
            "tools": [self.tools[tool_id].descriptor.to_dict() for tool_id in sorted(self.tools)],
        }


@dataclass(frozen=True)
class ToolExecutionAttempt:
    attempt_number: int
    status: str
    retryable: bool
    duration_ms: float
    error_type: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class FaultExecutionAttempt(ToolExecutionAttempt):
    fault_injected: bool = False
    handler_invoked: bool = False


@dataclass(frozen=True)
class ToolExecutionStep:
    step_index: int
    call_id: str
    expected_tool_name: str | None
    tool_name: str
    arguments: dict[str, Any]
    selection_valid: bool
    arguments_valid: bool
    validation_errors: list[str]
    execution_status: str
    attempt_count: int
    retry_count: int
    recovered: bool
    output_valid: bool
    output_validation_errors: list[str]
    output: dict[str, Any] | None
    error_type: str | None
    error_message: str | None
    duration_ms: float
    attempts: list[ToolExecutionAttempt] = field(default_factory=list)


@dataclass(frozen=True)
class ToolExecutionTrace:
    schema_version: str
    registry_id: str
    registry_version: str
    external_case_id: str
    parse_valid: bool
    parse_error: str | None
    call_valid: bool
    status: str
    successful: bool
    sequence_match: bool
    expected_tool_sequence: list[str]
    actual_tool_sequence: list[str]
    selection_accuracy: float | None
    argument_validity_rate: float | None
    execution_success_rate: float | None
    retry_recovery_rate: float | None
    total_duration_ms: float
    steps: list[ToolExecutionStep] = field(default_factory=list)
    fault_scenario: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.fault_scenario is None:
            payload.pop("fault_scenario")
        return payload


def _query_schema(*, extra_properties: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
            "simulate_failure": {
                "type": "string",
                "enum": ["transient_once", "permanent"],
            },
            **(extra_properties or {}),
        },
        "additionalProperties": False,
    }


def _output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["tool", "status", "data"],
        "properties": {
            "tool": {"type": "string"},
            "status": {"type": "string"},
            "data": {"type": "object"},
        },
    }


def _document_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["document_id"],
        "properties": {
            "document_id": {"type": "string", "minLength": 1, "maxLength": 160},
            "simulate_failure": {
                "type": "string",
                "enum": ["transient_once", "permanent"],
            },
        },
        "additionalProperties": False,
    }


def _result(tool: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"tool": tool, "status": "ok", "data": data}


def _lookup_internal_document(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    return _result(
        "lookup_internal_document",
        {
            "document_id": arguments["document_id"],
            "title": "Deterministic local document fixture",
            "case_id": context.external_case_id,
        },
    )


def _lookup_policy(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    return _result(
        "lookup_policy",
        {
            "query": arguments["query"],
            "policy_id": "POL-LOCAL-001",
            "release_requires_gate": True,
            "case_id": context.external_case_id,
        },
    )


def _search_incidents(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    return _result(
        "search_incidents",
        {
            "query": arguments["query"],
            "incident_ids": ["INC-1042", "INC-1088"],
            "count": 2,
            "case_id": context.external_case_id,
        },
    )


def _create_ticket(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    digest = hashlib.sha256(
        f"{context.external_case_id}:{arguments['query']}".encode()
    ).hexdigest()[:8]
    return _result(
        "create_ticket",
        {
            "ticket_id": f"SIM-{digest.upper()}",
            "priority": arguments.get("priority", "normal"),
            "simulated": True,
        },
    )


def _lookup_customer(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    return _result(
        "lookup_customer",
        {
            "query": arguments["query"],
            "contract_status": "active",
            "support_tier": "standard",
            "case_id": context.external_case_id,
        },
    )


def _summarize_thread(
    arguments: dict[str, Any],
    context: ToolExecutionContext,
) -> dict[str, Any]:
    return _result(
        "summarize_thread",
        {
            "summary": str(arguments["query"])[:160],
            "source_step_count": len(context.prior_outputs),
            "case_id": context.external_case_id,
        },
    )


def build_default_tool_registry() -> ToolRegistry:
    common_output = _output_schema()
    specs = [
        (
            "lookup_internal_document",
            "Lookup Internal Document",
            "Returns a deterministic in-memory document fixture.",
            _document_schema(),
            _lookup_internal_document,
            frozenset({"read", "document", "legacy_compatible"}),
            "none",
            2,
        ),
        (
            "lookup_policy",
            "Lookup Policy",
            "Returns a deterministic local policy record.",
            _query_schema(),
            _lookup_policy,
            frozenset({"read", "policy"}),
            "none",
            2,
        ),
        (
            "search_incidents",
            "Search Incidents",
            "Searches an in-memory incident fixture.",
            _query_schema(),
            _search_incidents,
            frozenset({"read", "incident"}),
            "none",
            2,
        ),
        (
            "create_ticket",
            "Create Ticket",
            "Creates a deterministic simulated ticket without external side effects.",
            _query_schema(
                extra_properties={
                    "priority": {
                        "type": "string",
                        "enum": ["low", "normal", "high"],
                    }
                }
            ),
            _create_ticket,
            frozenset({"write", "ticket", "simulated"}),
            "simulated",
            1,
        ),
        (
            "lookup_customer",
            "Lookup Customer",
            "Returns a deterministic local customer fixture.",
            _query_schema(),
            _lookup_customer,
            frozenset({"read", "customer"}),
            "none",
            2,
        ),
        (
            "summarize_thread",
            "Summarize Thread",
            "Summarizes local text and can consume prior tool outputs.",
            _query_schema(),
            _summarize_thread,
            frozenset({"read", "summary", "multi_step"}),
            "none",
            1,
        ),
    ]
    tools: dict[str, RegisteredTool] = {}
    for (
        tool_id,
        display_name,
        description,
        argument_schema,
        handler,
        capabilities,
        side_effect_mode,
        default_max_attempts,
    ) in specs:
        tools[tool_id] = RegisteredTool(
            descriptor=ToolDescriptor(
                tool_id=tool_id,
                tool_version=f"{tool_id}-v1",
                display_name=display_name,
                description=description,
                argument_schema=argument_schema,
                output_schema=common_output,
                capabilities=capabilities,
                side_effect_mode=side_effect_mode,
                default_max_attempts=default_max_attempts,
            ),
            handler=handler,
        )
    return ToolRegistry(tools=tools)


DEFAULT_TOOL_REGISTRY = build_default_tool_registry()


def build_fault_tool_registry(registry: ToolRegistry | None = None) -> ToolRegistry:
    source = registry or DEFAULT_TOOL_REGISTRY
    tools: dict[str, RegisteredTool] = {}
    for name, tool in source.tools.items():
        schema = deepcopy(tool.descriptor.argument_schema)
        schema.get("properties", {}).pop("simulate_failure", None)
        schema["required"] = [
            key for key in schema.get("required", []) if key != "simulate_failure"
        ]
        tools[name] = replace(
            tool,
            descriptor=replace(
                tool.descriptor,
                argument_schema=schema,
                tool_version=f"{tool.descriptor.tool_id}-fault-fixture-v1",
            ),
        )
    return ToolRegistry(
        tools=tools,
        registry_id=source.registry_id,
        registry_version=TOOL_FAULT_REGISTRY_VERSION,
    )


def execute_tool_calls(
    evaluation_case: EvaluationCase,
    normalized_output: str,
    registry: ToolRegistry | None = None,
    *,
    execution_block_reason: str | None = None,
    fault_scenario: ToolFaultScenario | None = None,
) -> ToolExecutionTrace:
    resolved_registry = registry or DEFAULT_TOOL_REGISTRY
    if fault_scenario is not None:
        validate_fault_case(evaluation_case)
        resolved_registry = build_fault_tool_registry(resolved_registry)
    expected_steps = _expected_steps(evaluation_case.expected_tool_schema_json)
    calls, parse_error = _parse_tool_calls(normalized_output)
    if fault_scenario is not None and len(calls) != 1 and parse_error is None:
        parse_error = "environment fault scenarios require exactly one generated Tool call"
        calls = []
    if len(calls) > MAX_TOOL_CALLS_PER_CASE:
        parse_error = f"tool call count exceeds limit {MAX_TOOL_CALLS_PER_CASE}"
        calls = []
    if parse_error is not None:
        trace = _empty_trace(
            evaluation_case,
            resolved_registry,
            expected_steps,
            parse_error,
        )
        return _attach_fault_scenario(trace, fault_scenario)

    expected_sequence = [str(step["tool_name"]) for step in expected_steps]
    actual_sequence = [str(call["tool_name"]) for call in calls]
    sequence_match = not expected_sequence or actual_sequence == expected_sequence
    prior_outputs: list[dict[str, Any]] = []
    steps: list[ToolExecutionStep] = []
    for index, call in enumerate(calls):
        expected = expected_steps[index] if index < len(expected_steps) else None
        step = _execute_step(
            external_case_id=evaluation_case.external_case_id,
            step_index=index,
            call=call,
            expected=expected,
            prior_outputs=prior_outputs,
            registry=resolved_registry,
            execution_block_reason=execution_block_reason,
            fault_scenario=fault_scenario,
        )
        steps.append(step)
        if step.output is not None:
            prior_outputs.append(step.output)

    selection_valid = [step.selection_valid for step in steps]
    arguments_valid = [step.arguments_valid for step in steps]
    execution_success = [step.execution_status == "success" for step in steps]
    retried_steps = [step for step in steps if step.retry_count > 0]
    successful = bool(steps) and all(execution_success)
    call_valid = bool(steps) and sequence_match and all(selection_valid) and all(arguments_valid)
    if successful:
        status = "success"
    elif any(execution_success):
        status = "partial_failure"
    elif steps:
        status = "failed"
    else:
        status = "invalid_call"
    trace = ToolExecutionTrace(
        schema_version=TOOL_EXECUTION_SCHEMA_VERSION,
        registry_id=resolved_registry.registry_id,
        registry_version=resolved_registry.registry_version,
        external_case_id=evaluation_case.external_case_id,
        parse_valid=True,
        parse_error=None,
        call_valid=call_valid,
        status=status,
        successful=successful,
        sequence_match=sequence_match,
        expected_tool_sequence=expected_sequence,
        actual_tool_sequence=actual_sequence,
        selection_accuracy=_rate(selection_valid),
        argument_validity_rate=_rate(arguments_valid),
        execution_success_rate=_rate(execution_success),
        retry_recovery_rate=(
            _rate([step.recovered for step in retried_steps]) if retried_steps else None
        ),
        total_duration_ms=round(sum(step.duration_ms for step in steps), 3),
        steps=steps,
    )
    return _attach_fault_scenario(trace, fault_scenario)


def _attach_fault_scenario(
    trace: ToolExecutionTrace,
    scenario: ToolFaultScenario | None,
) -> ToolExecutionTrace:
    if scenario is None:
        return trace
    return replace(
        trace,
        schema_version=TOOL_FAULT_TRACE_VERSION,
        fault_scenario=scenario.audit_record(trace.to_dict()),
    )


def execute_registered_tool_call(
    *,
    external_case_id: str,
    step_index: int,
    tool_name: str,
    arguments: dict[str, Any],
    expected: dict[str, Any] | None = None,
    prior_outputs: list[dict[str, Any]] | None = None,
    call_id: str | None = None,
    registry: ToolRegistry | None = None,
) -> ToolExecutionStep:
    """Execute one validated registry call for a bounded composite workflow."""
    return _execute_step(
        external_case_id=external_case_id,
        step_index=step_index,
        call={
            "call_id": call_id or f"agent-call-{step_index + 1}",
            "tool_name": tool_name,
            "arguments": arguments,
        },
        expected=expected,
        prior_outputs=list(prior_outputs or []),
        registry=registry or DEFAULT_TOOL_REGISTRY,
    )


def attach_tool_execution(
    evaluation_case: EvaluationCase,
    result: AdapterCaseResult,
    registry: ToolRegistry | None = None,
    *,
    fault_scenario: ToolFaultScenario | None = None,
) -> AdapterCaseResult:
    if isinstance(result.metadata.get("agent_execution"), dict):
        return result
    if not _is_tool_case(evaluation_case):
        return result
    resolved_registry = registry or DEFAULT_TOOL_REGISTRY
    if fault_scenario is not None:
        resolved_registry = build_fault_tool_registry(resolved_registry)
    trace = execute_tool_calls(
        evaluation_case,
        result.normalized_output,
        resolved_registry,
        execution_block_reason=tool_argument_block_reason(result.metadata),
        fault_scenario=fault_scenario,
    )
    retry_count = sum(step.retry_count for step in trace.steps)
    trace_logs = [
        {
            "event_type": "tool_execution_step",
            "level": "info" if step.execution_status == "success" else "error",
            "message": (
                f"Tool step {step.step_index + 1} {step.tool_name}: {step.execution_status}."
            ),
            "payload_json": {
                "tool_name": step.tool_name,
                "expected_tool_name": step.expected_tool_name,
                "execution_status": step.execution_status,
                "attempt_count": step.attempt_count,
                "recovered": step.recovered,
                "error_type": step.error_type,
            },
        }
        for step in trace.steps
    ]
    trace_logs.append(
        {
            "event_type": "tool_execution_completed",
            "level": "info" if trace.successful else "error",
            "message": f"Tool execution finished with status {trace.status}.",
            "payload_json": {
                "schema_version": trace.schema_version,
                "registry_version": trace.registry_version,
                "status": trace.status,
                "call_count": len(trace.steps),
                "sequence_match": trace.sequence_match,
                "retry_count": retry_count,
            },
        }
    )
    return replace(
        result,
        exact_match=trace.call_valid and trace.successful,
        tool_call_valid=trace.call_valid,
        error_type=(
            result.error_type
            if result.error_type
            else (None if trace.successful else "tool_execution_failed")
        ),
        end_to_end_latency_ms=result.end_to_end_latency_ms + trace.total_duration_ms,
        retry_count=result.retry_count + retry_count,
        logs=[*result.logs, *trace_logs],
        metadata={
            **result.metadata,
            "tool_execution": trace.to_dict(),
            "tool_registry": resolved_registry.descriptor(),
        },
    )


def tool_argument_block_reason(metadata: dict[str, Any]) -> str | None:
    guard = metadata.get("tool_call_contract")
    if isinstance(guard, dict) and guard.get("execution_allowed") is False:
        errors = [*guard.get("schema_errors", []), *guard.get("boundary_errors", [])]
        return "Tool argument guard rejected the call: " + "; ".join(str(item) for item in errors)
    return None


def summarize_tool_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    steps = [step for trace in traces for step in trace.get("steps", []) if isinstance(step, dict)]
    retried_steps = [step for step in steps if int(step.get("retry_count") or 0) > 0]
    successful_steps = [step for step in steps if step.get("execution_status") == "success"]
    selection_values = [bool(step.get("selection_valid")) for step in steps]
    argument_values = [bool(step.get("arguments_valid")) for step in steps]
    summary = {
        "schema_version": "tool-execution-summary-v1",
        "tool_case_count": len(traces),
        "call_count": len(steps),
        "successful_call_count": len(successful_steps),
        "failed_call_count": len(steps) - len(successful_steps),
        "retried_call_count": len(retried_steps),
        "recovered_call_count": sum(1 for step in retried_steps if step.get("recovered")),
        "multi_step_case_count": sum(1 for trace in traces if len(trace.get("steps", [])) > 1),
        "invalid_call_case_count": sum(1 for trace in traces if not bool(trace.get("call_valid"))),
        "selection_accuracy": _rate(selection_values),
        "argument_validity_rate": _rate(argument_values),
        "execution_success_rate": (len(successful_steps) / len(steps) if steps else None),
        "sequence_success_rate": (
            sum(1 for trace in traces if trace.get("sequence_match")) / len(traces)
            if traces
            else None
        ),
        "retry_recovery_rate": (
            sum(1 for step in retried_steps if step.get("recovered")) / len(retried_steps)
            if retried_steps
            else None
        ),
    }
    fixtures = [
        trace["fault_scenario"] for trace in traces if isinstance(trace.get("fault_scenario"), dict)
    ]
    if fixtures:
        summary["fault_scenario_summary"] = {
            "schema_version": "tool-fault-scenario-summary-v1",
            "case_count": len(fixtures),
            "passed_count": sum(f["passed"] for f in fixtures),
            "not_exercised_count": sum(f["status"] == "not_exercised" for f in fixtures),
            "injected_failure_count": sum(f["injected_failure_count"] for f in fixtures),
            "handler_invocation_count": sum(f["handler_invocation_count"] for f in fixtures),
            "gate_evidence": False,
        }
    return summary


def validate_json_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type and not _matches_type(value, str(expected_type)):
        return [f"{path} must be {expected_type}"]
    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        errors.append(f"{path} must be one of {enum}")
    if isinstance(value, str):
        minimum_length = schema.get("minLength")
        maximum_length = schema.get("maxLength")
        if isinstance(minimum_length, int) and len(value) < minimum_length:
            errors.append(f"{path} is shorter than {minimum_length}")
        if isinstance(maximum_length, int) and len(value) > maximum_length:
            errors.append(f"{path} is longer than {maximum_length}")
    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    errors.append(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    errors.extend(validate_json_schema(value[key], child_schema, f"{path}.{key}"))
            if schema.get("additionalProperties") is False:
                unknown = sorted(str(key) for key in value if key not in properties)
                errors.extend(f"{path}.{key} is not allowed" for key in unknown)
    if isinstance(value, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                errors.extend(validate_json_schema(item, item_schema, f"{path}[{index}]"))
    return errors


def _execute_step(
    *,
    external_case_id: str,
    step_index: int,
    call: dict[str, Any],
    expected: dict[str, Any] | None,
    prior_outputs: list[dict[str, Any]],
    registry: ToolRegistry,
    execution_block_reason: str | None = None,
    fault_scenario: ToolFaultScenario | None = None,
) -> ToolExecutionStep:
    tool_name = str(call["tool_name"])
    call_id = str(call.get("call_id") or f"call-{step_index + 1}")
    arguments = call.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    registered = registry.get(tool_name)
    expected_name = str(expected["tool_name"]) if expected and expected.get("tool_name") else None
    selection_valid = registered is not None and (
        expected_name is None or tool_name == expected_name
    )
    validation_errors: list[str] = []
    if registered is None:
        validation_errors.append(f"tool {tool_name} is not registered")
    else:
        validation_errors.extend(
            validate_json_schema(arguments, registered.descriptor.argument_schema)
        )
    expected_arguments = expected.get("arguments") if expected else None
    if isinstance(expected_arguments, dict):
        validation_errors.extend(validate_json_schema(arguments, expected_arguments))
    if execution_block_reason:
        validation_errors.append(execution_block_reason)
    if fault_scenario is not None:
        if "simulate_failure" in arguments:
            validation_errors.append(
                "model-authored failure simulation is forbidden in fault fixtures"
            )
        if registered is not None and registered.descriptor.side_effect_mode not in (
            "none",
            "simulated",
        ):
            validation_errors.append(
                "environment faults are limited to local read/simulated fixtures"
            )
    arguments_valid = not validation_errors

    if not selection_valid or not arguments_valid or registered is None:
        error_type = "invalid_tool_selection" if not selection_valid else "invalid_arguments"
        return ToolExecutionStep(
            step_index=step_index,
            call_id=call_id,
            expected_tool_name=expected_name,
            tool_name=tool_name,
            arguments=arguments,
            selection_valid=selection_valid,
            arguments_valid=arguments_valid,
            validation_errors=validation_errors,
            execution_status="skipped",
            attempt_count=0,
            retry_count=0,
            recovered=False,
            output_valid=False,
            output_validation_errors=[],
            output=None,
            error_type=error_type,
            error_message="Tool execution was skipped because the call contract was invalid.",
            duration_ms=0.0,
            attempts=[],
        )

    max_attempts = (
        fault_scenario.max_attempts
        if fault_scenario is not None
        else _max_attempts(expected, registered.descriptor.default_max_attempts)
    )
    attempts: list[ToolExecutionAttempt] = []
    output: dict[str, Any] | None = None
    output_errors: list[str] = []
    error_type: str | None = None
    error_message: str | None = None
    for attempt_number in range(1, max_attempts + 1):
        started = time.perf_counter()
        attempt_type = FaultExecutionAttempt if fault_scenario is not None else ToolExecutionAttempt
        attempt_details = (
            {"fault_injected": False, "handler_invoked": False}
            if fault_scenario is not None
            else {}
        )
        try:
            if fault_scenario is not None:
                mode = fault_scenario.fault_at(attempt_number)
                attempt_details["fault_injected"] = mode is not None
                if mode is not None:
                    raise ToolExecutionError(
                        "The test environment injected a failure before the handler.",
                        error_type=(
                            "transient_tool_error"
                            if mode == "transient_once"
                            else "permanent_tool_error"
                        ),
                        retryable=mode == "transient_once",
                    )
            else:
                _raise_simulated_failure(arguments, attempt_number)
            context = ToolExecutionContext(
                external_case_id=external_case_id,
                step_index=step_index,
                attempt_number=attempt_number,
                prior_outputs=tuple(prior_outputs),
            )
            if fault_scenario is not None:
                attempt_details["handler_invoked"] = True
            candidate_output = registered.handler(arguments, context)
            output_errors = validate_json_schema(
                candidate_output,
                registered.descriptor.output_schema,
            )
            if output_errors:
                raise ToolExecutionError(
                    "Tool output did not match its descriptor.",
                    error_type="invalid_tool_output",
                    retryable=False,
                )
            output = candidate_output
            attempts.append(
                attempt_type(
                    attempt_number=attempt_number,
                    status="success",
                    retryable=False,
                    duration_ms=_elapsed_ms(started),
                    **attempt_details,
                )
            )
            break
        except ToolExecutionError as exc:
            error_type = exc.error_type
            error_message = str(exc)
            attempts.append(
                attempt_type(
                    attempt_number=attempt_number,
                    status="failed",
                    retryable=exc.retryable,
                    duration_ms=_elapsed_ms(started),
                    error_type=exc.error_type,
                    message=str(exc),
                    **attempt_details,
                )
            )
            if not exc.retryable:
                break
        except Exception as exc:  # pragma: no cover - defensive boundary for custom tools
            error_type = "tool_internal_error"
            error_message = str(exc)
            attempts.append(
                attempt_type(
                    attempt_number=attempt_number,
                    status="failed",
                    retryable=False,
                    duration_ms=_elapsed_ms(started),
                    error_type=error_type,
                    message=error_message,
                    **attempt_details,
                )
            )
            break

    success = output is not None and not output_errors
    return ToolExecutionStep(
        step_index=step_index,
        call_id=call_id,
        expected_tool_name=expected_name,
        tool_name=tool_name,
        arguments=arguments,
        selection_valid=True,
        arguments_valid=True,
        validation_errors=[],
        execution_status="success" if success else "failed",
        attempt_count=len(attempts),
        retry_count=max(0, len(attempts) - 1),
        recovered=success and len(attempts) > 1,
        output_valid=success,
        output_validation_errors=output_errors,
        output=output,
        error_type=None if success else error_type,
        error_message=None if success else error_message,
        duration_ms=round(sum(attempt.duration_ms for attempt in attempts), 3),
        attempts=attempts,
    )


def _expected_steps(schema: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(schema, dict):
        return []
    sequence = schema.get("expected_sequence")
    if isinstance(sequence, list):
        steps: list[dict[str, Any]] = []
        for item in sequence:
            if isinstance(item, str):
                steps.append({"tool_name": item})
            elif isinstance(item, dict) and item.get("tool_name"):
                steps.append(dict(item))
        return steps
    if schema.get("tool_name"):
        arguments = schema.get("arguments")
        required_arguments = schema.get("required_arguments")
        if not isinstance(arguments, dict) and isinstance(required_arguments, list):
            arguments = {
                "type": "object",
                "required": [str(item) for item in required_arguments],
                "properties": {str(item): {"type": "string"} for item in required_arguments},
            }
        return [
            {
                "tool_name": str(schema["tool_name"]),
                "arguments": arguments,
                "example_arguments": schema.get("example_arguments"),
                "max_attempts": schema.get("max_attempts"),
            }
        ]
    return []


def _parse_tool_calls(output: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        parsed = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return [], "output is not valid JSON"
    raw_calls: list[Any]
    if isinstance(parsed, dict) and isinstance(parsed.get("tool_calls"), list):
        raw_calls = parsed["tool_calls"]
    elif isinstance(parsed, dict) and parsed.get("tool_call") is not None:
        raw_calls = [parsed["tool_call"]]
    elif isinstance(parsed, dict) and (parsed.get("tool_name") or parsed.get("name")):
        raw_calls = [parsed]
    else:
        return [], "output does not contain a tool call"
    calls: list[dict[str, Any]] = []
    for index, raw_call in enumerate(raw_calls):
        call, error = _normalize_call(raw_call, index)
        if error:
            return [], error
        calls.append(call)
    return calls, None


def _normalize_call(raw_call: Any, index: int) -> tuple[dict[str, Any], str | None]:
    if not isinstance(raw_call, dict):
        return {}, f"tool call {index + 1} must be an object"
    function = raw_call.get("function")
    source = function if isinstance(function, dict) else raw_call
    tool_name = source.get("tool_name") or source.get("name")
    if not tool_name:
        return {}, f"tool call {index + 1} is missing tool_name"
    arguments = source.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return {}, f"tool call {index + 1} arguments are not valid JSON"
    if not isinstance(arguments, dict):
        return {}, f"tool call {index + 1} arguments must be an object"
    return {
        "call_id": raw_call.get("id") or raw_call.get("call_id") or f"call-{index + 1}",
        "tool_name": str(tool_name),
        "arguments": arguments,
    }, None


def _empty_trace(
    evaluation_case: EvaluationCase,
    registry: ToolRegistry,
    expected_steps: list[dict[str, Any]],
    parse_error: str,
) -> ToolExecutionTrace:
    return ToolExecutionTrace(
        schema_version=TOOL_EXECUTION_SCHEMA_VERSION,
        registry_id=registry.registry_id,
        registry_version=registry.registry_version,
        external_case_id=evaluation_case.external_case_id,
        parse_valid=False,
        parse_error=parse_error,
        call_valid=False,
        status="invalid_call",
        successful=False,
        sequence_match=False,
        expected_tool_sequence=[str(step["tool_name"]) for step in expected_steps],
        actual_tool_sequence=[],
        selection_accuracy=None,
        argument_validity_rate=None,
        execution_success_rate=None,
        retry_recovery_rate=None,
        total_duration_ms=0.0,
        steps=[],
    )


def _max_attempts(expected: dict[str, Any] | None, default: int) -> int:
    configured = expected.get("max_attempts") if expected else None
    value = configured if isinstance(configured, int) else default
    return max(1, min(MAX_TOOL_ATTEMPTS, value))


def _raise_simulated_failure(arguments: dict[str, Any], attempt_number: int) -> None:
    mode = arguments.get("simulate_failure")
    if mode == "transient_once" and attempt_number == 1:
        raise ToolExecutionError(
            "The deterministic fixture produced one transient failure.",
            error_type="transient_tool_error",
            retryable=True,
        )
    if mode == "permanent":
        raise ToolExecutionError(
            "The deterministic fixture produced a permanent failure.",
            error_type="permanent_tool_error",
            retryable=False,
        )


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _is_tool_case(evaluation_case: EvaluationCase) -> bool:
    return (
        evaluation_case.expected_tool_schema_json is not None
        or "tool" in (evaluation_case.category or "").lower()
    )


def _rate(values: list[bool]) -> float | None:
    return sum(1 for value in values if value) / len(values) if values else None


def _elapsed_ms(started: float) -> float:
    return round(max(0.0, (time.perf_counter() - started) * 1000), 3)
