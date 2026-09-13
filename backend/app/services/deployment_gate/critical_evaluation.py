"""Versioned critical-output evaluator; v2 is opt-in and never changes stored flags."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import ValidationError

from app.models import BenchmarkResult, EvaluationCase
from app.schemas.agent_execution import AgentExecutionTraceRead
from app.services.agent_execution import is_agent_case
from app.services.agent_execution.contracts import ALLOWED_AGENT_ACTIONS
from app.services.deployment_gate.metrics import _is_critical_failure, _is_tool_case
from app.services.tool_execution import validate_json_schema

LEGACY_VERSION = "critical-output-contract-v1"
AGENT_AWARE_VERSION = "critical-output-contract-v2"
VERSIONS = (LEGACY_VERSION, AGENT_AWARE_VERSION)


@dataclass(frozen=True)
class CriticalDecision:
    evaluator_version: str
    status: Literal["pass", "fail", "not_applicable"]
    output_kind: Literal["agent_plan", "single_tool", "other"]
    scalar_tool_flag_applicable: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _agent_trace_errors(result: BenchmarkResult, case: EvaluationCase) -> list[str]:
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    raw = metadata.get("agent_execution")
    if not isinstance(raw, dict):
        return ["agent_trace_missing"]
    required = {
        "execution_step_limit",
        "unrecovered_failure_count",
        "pending_checkpoint_count",
        "denied_checkpoint_count",
        "halt_reason",
        "steps",
        "replans",
        "replan_count",
        "recovery_step_count",
        "successful_replan_count",
        "observation_count",
        "actual_action_sequence",
        "expected_action_sequence",
        "parse_error",
    }
    if required - raw.keys():
        return ["agent_trace_incomplete"]
    try:
        trace = AgentExecutionTraceRead.model_validate(raw, strict=True)
    except ValidationError:
        return ["agent_trace_invalid_types"]
    if (
        trace.schema_version != "agent-execution-trace-v2"
        or trace.runtime_version != "bounded-agent-runtime-v2"
        or trace.context_version != "agent-context-v2"
    ):
        return ["agent_trace_version_unsupported"]
    if trace.external_case_id != case.external_case_id:
        return ["agent_trace_case_mismatch"]
    errors = []
    if (
        trace.status != "success"
        or result.json_valid is not True
        or not trace.successful
        or not trace.parse_valid
        or trace.parse_error is not None
        or not trace.plan_valid
        or not trace.sequence_match
        or not trace.final_response_present
        or trace.halt_reason is not None
        or trace.policy_violation_count != 0
        or trace.unrecovered_failure_count != 0
        or trace.pending_checkpoint_count != 0
        or trace.denied_checkpoint_count != 0
    ):
        errors.append("agent_execution_not_successful")
    reference = case.reference_context_json
    contract = reference.get("agent") if isinstance(reference, dict) else None
    if not isinstance(contract, dict):
        return [*errors, "agent_contract_missing"]
    expected = contract.get("expected_steps")
    if (
        not isinstance(expected, list)
        or not expected
        or any(
            not isinstance(step, dict)
            or not isinstance(step.get("action"), str)
            or step["action"] not in ALLOWED_AGENT_ACTIONS
            for step in expected
        )
    ):
        return [*errors, "agent_contract_invalid"]
    expected_actions = [step["action"] for step in expected]
    allowed_actions = contract.get("allowed_actions", ["respond"])
    allowed_tools = contract.get("allowed_tools", [])
    if any(
        not isinstance(values, list) or any(not isinstance(value, str) for value in values)
        for values in (allowed_actions, allowed_tools)
    ):
        return [*errors, "agent_contract_invalid"]
    plan_steps = [step for step in trace.steps if step.phase == "plan"]
    expected_by_index = {
        step.step_index: item for step, item in zip(plan_steps, expected, strict=False)
    }
    recovery_steps = [step for step in trace.steps if step.phase == "recovery"]
    actions = [step.action for step in plan_steps]
    if (
        trace.expected_action_sequence != expected_actions
        or trace.actual_action_sequence != expected_actions
        or actions != expected_actions
    ):
        errors.append("agent_action_sequence_mismatch")
    if (
        not trace.steps
        or trace.step_count != len(trace.steps)
        or [step.step_index for step in trace.steps] != list(range(len(trace.steps)))
        or type(trace.execution_step_limit) is not int
        or trace.execution_step_limit < 1
        or trace.step_count > trace.execution_step_limit
        or trace.step_limit < len(plan_steps)
    ):
        errors.append("agent_step_coverage_invalid")
    counts = Counter(step.action for step in trace.steps)
    observed = {
        "successful_step_count": sum(step.successful for step in trace.steps),
        "failed_step_count": sum(not step.successful for step in trace.steps),
        "recovery_step_count": len(recovery_steps),
        "successful_recovery_step_count": sum(step.successful for step in recovery_steps),
        "observation_count": sum(step.observation is not None for step in trace.steps),
        "replan_count": len(trace.replans),
        "successful_replan_count": sum(event.successful for event in trace.replans),
        "tool_call_count": counts["tool"],
        "retrieval_count": counts["retrieve"],
        "memory_read_count": counts["memory_read"],
        "memory_write_count": counts["memory_write"],
        "approval_checkpoint_count": counts["approval_checkpoint"],
        "approved_checkpoint_count": sum(step.status == "approved" for step in trace.steps),
    }
    if any(getattr(trace, key) != value for key, value in observed.items()):
        errors.append("agent_counter_mismatch")
    recovered_indices = set()
    used_recovery_indices = []
    for event in trace.replans:
        indices = event.recovery_step_indices
        selected = [step for step in recovery_steps if step.step_index in indices]
        if (
            not event.successful
            or event.status != "success"
            or not event.sequence_match
            or not indices
            or [step.step_index for step in selected] != indices
            or any(
                not step.successful or step.parent_step_index != event.trigger_step_index
                for step in selected
            )
            or [step.action for step in selected] != event.actual_action_sequence
            or (
                event.expected_action_sequence
                and event.expected_action_sequence != event.actual_action_sequence
            )
            or event.trigger_step_index not in range(len(plan_steps))
        ):
            errors.append("agent_recovery_invalid")
        else:
            recovered_indices.add(plan_steps[event.trigger_step_index].step_index)
        used_recovery_indices.extend(indices)
    if (
        Counter(used_recovery_indices) != Counter(step.step_index for step in recovery_steps)
        or trace.replan_count > trace.replan_limit
        or (trace.replans and trace.recovery_sequence_match is not True)
    ):
        errors.append("agent_recovery_coverage_invalid")
    for step in trace.steps:
        raw_step = (
            raw["steps"][step.step_index] if step.step_index in range(len(raw["steps"])) else {}
        )
        if (
            not {"policy_violations", "error_type", "phase", "recovered_by_replan", "observation"}
            <= raw_step.keys()
        ):
            errors.append("agent_step_incomplete")
        if (
            step.action not in ALLOWED_AGENT_ACTIONS
            or step.action not in allowed_actions
            or step.policy_violations
            or (step.action == "memory_write" and contract.get("allow_memory_write") is not True)
        ):
            errors.append("agent_step_policy_violation")
        if step.recovered_by_replan != (step.step_index in recovered_indices):
            errors.append("agent_recovery_claim_mismatch")
        if not step.successful:
            if step.step_index not in recovered_indices:
                errors.append("agent_step_failed")
            continue
        if step.status not in {"success", "approved"} or step.error_type is not None:
            errors.append("agent_step_status_mismatch")
        observation = step.observation
        if (
            observation is None
            or observation.schema_version != "agent-observation-v1"
            or not observation.successful
            or observation.status != step.status
            or observation.error_type is not None
            or observation.policy_violation_count != 0
        ):
            errors.append("agent_observation_invalid")
        if step.action == "tool":
            tool = (step.output or {}).get("tool_execution")
            expected_step = expected_by_index.get(step.step_index, {})
            if (
                not isinstance(tool, dict)
                or any(
                    tool.get(key) is not True
                    for key in ("selection_valid", "arguments_valid", "output_valid")
                )
                or tool.get("execution_status") != "success"
                or tool.get("error_type") is not None
                or not isinstance(tool.get("tool_name"), str)
                or tool.get("tool_name") not in allowed_tools
                or tool.get("tool_name") != step.input.get("tool_name")
                or (
                    expected_step.get("tool_name")
                    and tool.get("tool_name") != expected_step["tool_name"]
                )
                or not isinstance(tool.get("arguments"), dict)
                or tool.get("arguments") != step.input.get("arguments")
                or (
                    isinstance(expected_step.get("arguments"), dict)
                    and validate_json_schema(tool["arguments"], expected_step["arguments"])
                )
            ):
                errors.append("agent_tool_step_invalid")
        if step.action.startswith("memory_") and not step.memory_provenance_valid:
            errors.append("agent_memory_provenance_invalid")
        if step.action == "approval_checkpoint" and (
            step.status != "approved" or not step.approval_provenance_valid
        ):
            errors.append("agent_approval_invalid")
    if not any(
        step.action == "respond"
        and step.successful
        and isinstance((step.output or {}).get("content"), str)
        and step.output["content"].strip()
        for step in trace.steps
    ):
        errors.append("agent_response_missing")
    return sorted(set(errors))


def evaluate_critical_result(
    result: BenchmarkResult,
    case: EvaluationCase | None,
    *,
    version: str = LEGACY_VERSION,
) -> CriticalDecision:
    if version not in VERSIONS:
        raise ValueError(f"unsupported critical evaluator version: {version}")
    agent = case is not None and (is_agent_case(case) or case.category == "rag_tool_combined")
    kind = "agent_plan" if agent else ("single_tool" if _is_tool_case(case) else "other")
    scalar = _is_tool_case(case) and not (agent and version == AGENT_AWARE_VERSION)
    if case is None or case.criticality != "critical":
        return CriticalDecision(version, "not_applicable", kind, scalar, ())
    if version == LEGACY_VERSION:
        failed = _is_critical_failure(result, case)
        return CriticalDecision(
            version,
            "fail" if failed else "pass",
            kind,
            scalar,
            ("legacy_critical_failure",) if failed else (),
        )
    reasons = _agent_trace_errors(result, case) if agent else []
    # The legacy scalar flag remains stored unchanged; only its applicability differs.
    try:
        if _is_critical_failure(result, case, check_single_tool_flag=not agent):
            reasons.append("common_critical_failure")
    except (TypeError, ValueError, OverflowError):
        reasons.append("malformed_common_evidence")
    return CriticalDecision(version, "fail" if reasons else "pass", kind, scalar, tuple(reasons))
