from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.models import EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult

from .contracts import (
    AGENT_EXECUTION_SUMMARY_VERSION,
    DEFAULT_OPERATIONAL_MEMORY_REGISTRY,
    SUPPORTED_AGENT_TRACE_VERSIONS,
    AgentLiveReplanCallback,
    AgentPreparation,
    OperationalMemoryRegistry,
)
from .execution import execute_agent_plan
from .planning import compile_bounded_agent_plan
from .utils import _rate


def attach_agent_execution(
    evaluation_case: EvaluationCase,
    result: AdapterCaseResult,
    preparation: AgentPreparation | None,
    memory_registry: OperationalMemoryRegistry | None = None,
    *,
    live_replan_callback: AgentLiveReplanCallback | None = None,
) -> AdapterCaseResult:
    if preparation is None:
        return result
    registry = memory_registry or DEFAULT_OPERATIONAL_MEMORY_REGISTRY
    compiled_output, compilation = compile_bounded_agent_plan(
        evaluation_case,
        result.normalized_output,
        preparation,
    )
    trace = execute_agent_plan(
        evaluation_case,
        compiled_output,
        preparation,
        registry,
        live_replan_callback=live_replan_callback,
    )
    retry_count = sum(int(step.get("retry_count") or 0) for step in trace.steps)
    logs = (
        [
            {
                "event_type": "agent_plan_compiled",
                "level": "info",
                "message": "Agent plan was compiled into the bounded public contract.",
                "payload_json": compilation,
            }
        ]
        if compilation["applied"]
        else []
    )
    logs.extend(
        {
            "event_type": "agent_execution_step",
            "level": "info" if step.get("successful") else "error",
            "message": (
                f"Agent step {int(step.get('step_index') or 0) + 1} "
                f"{step.get('action')}: {step.get('status')}."
            ),
            "payload_json": {
                "action": step.get("action"),
                "status": step.get("status"),
                "error_type": step.get("error_type"),
                "policy_violations": step.get("policy_violations", []),
                "recovered": step.get("recovered", False),
            },
        }
        for step in trace.steps
    )
    logs.extend(
        {
            "event_type": "agent_replan_completed",
            "level": "info" if event.get("successful") else "error",
            "message": (
                f"Agent replan {event.get('replan_index')} finished with "
                f"status {event.get('status')}."
            ),
            "payload_json": {
                "trigger_step_index": event.get("trigger_step_index"),
                "trigger_error_type": event.get("trigger_error_type"),
                "status": event.get("status"),
                "sequence_match": event.get("sequence_match"),
                "recovery_step_indices": event.get("recovery_step_indices", []),
                "source": event.get("source"),
                "model_call": event.get("model_call"),
            },
        }
        for event in trace.replans
    )
    logs.append(
        {
            "event_type": "agent_execution_completed",
            "level": "info" if trace.successful else "error",
            "message": f"Agent execution finished with status {trace.status}.",
            "payload_json": {
                "schema_version": trace.schema_version,
                "status": trace.status,
                "step_count": trace.step_count,
                "policy_violation_count": trace.policy_violation_count,
                "replan_count": trace.replan_count,
                "live_replan_model_call_count": trace.live_replan_model_call_count,
                "approval_checkpoint_count": trace.approval_checkpoint_count,
                "halt_reason": trace.halt_reason,
            },
        }
    )
    return replace(
        result,
        normalized_output=compiled_output,
        exact_match=trace.successful,
        json_valid=trace.parse_valid,
        error_type=(
            result.error_type
            if result.error_type
            else (None if trace.successful else "agent_execution_failed")
        ),
        end_to_end_latency_ms=result.end_to_end_latency_ms + trace.total_duration_ms,
        retry_count=result.retry_count + retry_count,
        logs=[*result.logs, *logs],
        metadata={
            **result.metadata,
            "agent_plan_compilation": compilation,
            "agent_execution": trace.to_dict(),
            "operational_memory_registry": registry.descriptor(),
        },
    )


def summarize_agent_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        trace for trace in traces if trace.get("schema_version") in SUPPORTED_AGENT_TRACE_VERSIONS
    ]
    if not valid:
        return _empty_summary()
    case_count = len(valid)
    total_steps = sum(int(trace.get("step_count") or 0) for trace in valid)
    successful_steps = sum(int(trace.get("successful_step_count") or 0) for trace in valid)
    memory_actions = sum(int(trace.get("memory_action_count") or 0) for trace in valid)
    memory_provenance = sum(int(trace.get("memory_provenance_count") or 0) for trace in valid)
    retried_tools = sum(int(trace.get("retried_tool_count") or 0) for trace in valid)
    recovered_tools = sum(int(trace.get("recovered_tool_count") or 0) for trace in valid)
    replan_count = sum(int(trace.get("replan_count") or 0) for trace in valid)
    successful_replans = sum(int(trace.get("successful_replan_count") or 0) for trace in valid)
    live_replans = sum(int(trace.get("live_replan_count") or 0) for trace in valid)
    live_model_calls = sum(int(trace.get("live_replan_model_call_count") or 0) for trace in valid)
    recovery_steps = sum(int(trace.get("recovery_step_count") or 0) for trace in valid)
    successful_recovery_steps = sum(
        int(trace.get("successful_recovery_step_count") or 0) for trace in valid
    )
    approval_checkpoints = sum(int(trace.get("approval_checkpoint_count") or 0) for trace in valid)
    approved_checkpoints = sum(int(trace.get("approved_checkpoint_count") or 0) for trace in valid)
    denied_checkpoints = sum(int(trace.get("denied_checkpoint_count") or 0) for trace in valid)
    pending_checkpoints = sum(int(trace.get("pending_checkpoint_count") or 0) for trace in valid)
    approval_provenance = sum(int(trace.get("approval_provenance_count") or 0) for trace in valid)
    observations = sum(int(trace.get("observation_count") or 0) for trace in valid)
    unrecovered_failure_cases = sum(
        1 for trace in valid if int(trace.get("unrecovered_failure_count") or 0) > 0
    )
    violation_cases = sum(1 for trace in valid if int(trace.get("policy_violation_count") or 0) > 0)
    return {
        "schema_version": AGENT_EXECUTION_SUMMARY_VERSION,
        "agent_case_count": case_count,
        "successful_case_count": sum(1 for trace in valid if trace.get("successful")),
        "failed_case_count": sum(1 for trace in valid if not trace.get("successful")),
        "total_step_count": total_steps,
        "successful_step_count": successful_steps,
        "failed_step_count": total_steps - successful_steps,
        "task_success_rate": _rate(
            sum(1 for trace in valid if trace.get("successful")), case_count
        ),
        "plan_validity_rate": _rate(
            sum(1 for trace in valid if trace.get("plan_valid")), case_count
        ),
        "step_success_rate": _rate(successful_steps, total_steps),
        "action_sequence_accuracy": _rate(
            sum(1 for trace in valid if trace.get("sequence_match")), case_count
        ),
        "policy_violation_rate": _rate(violation_cases, case_count),
        "final_response_rate": _rate(
            sum(1 for trace in valid if trace.get("final_response_present")),
            case_count,
        ),
        "memory_provenance_rate": (
            _rate(memory_provenance, memory_actions) if memory_actions else None
        ),
        "retried_tool_count": retried_tools,
        "recovered_tool_count": recovered_tools,
        "tool_retry_recovery_rate": (
            _rate(recovered_tools, retried_tools) if retried_tools else None
        ),
        "replan_case_count": sum(1 for trace in valid if int(trace.get("replan_count") or 0) > 0),
        "replan_count": replan_count,
        "successful_replan_count": successful_replans,
        "replan_success_rate": (_rate(successful_replans, replan_count) if replan_count else None),
        "live_replan_count": live_replans,
        "live_replan_model_call_count": live_model_calls,
        "live_replan_prompt_tokens": sum(
            int(trace.get("live_replan_prompt_tokens") or 0) for trace in valid
        ),
        "live_replan_completion_tokens": sum(
            int(trace.get("live_replan_completion_tokens") or 0) for trace in valid
        ),
        "live_replan_latency_ms": round(
            sum(float(trace.get("live_replan_latency_ms") or 0) for trace in valid),
            3,
        ),
        "live_replan_estimated_cost_usd": round(
            sum(float(trace.get("live_replan_estimated_cost_usd") or 0) for trace in valid),
            8,
        ),
        "recovery_step_count": recovery_steps,
        "successful_recovery_step_count": successful_recovery_steps,
        "recovery_step_success_rate": (
            _rate(successful_recovery_steps, recovery_steps) if recovery_steps else None
        ),
        "approval_checkpoint_count": approval_checkpoints,
        "approved_checkpoint_count": approved_checkpoints,
        "denied_checkpoint_count": denied_checkpoints,
        "pending_checkpoint_count": pending_checkpoints,
        "approval_compliance_rate": (
            _rate(approved_checkpoints, approval_checkpoints) if approval_checkpoints else None
        ),
        "approval_provenance_rate": (
            _rate(approval_provenance, approval_checkpoints) if approval_checkpoints else None
        ),
        "pending_approval_rate": (
            _rate(pending_checkpoints, approval_checkpoints) if approval_checkpoints else None
        ),
        "observation_coverage_rate": (_rate(observations, total_steps) if total_steps else None),
        "unrecovered_failure_rate": _rate(
            unrecovered_failure_cases,
            case_count,
        ),
        "halted_case_count": sum(1 for trace in valid if trace.get("halt_reason")),
        "average_steps_per_case": round(total_steps / case_count, 3),
        "memory_registry_versions": sorted(
            {
                str(trace["memory_registry_version"])
                for trace in valid
                if trace.get("memory_registry_version")
            }
        ),
        "tool_registry_versions": sorted(
            {
                str(trace["tool_registry_version"])
                for trace in valid
                if trace.get("tool_registry_version")
            }
        ),
        "corpus_versions": sorted(
            {str(trace["corpus_version"]) for trace in valid if trace.get("corpus_version")}
        ),
        "retriever_versions": sorted(
            {str(trace["retriever_version"]) for trace in valid if trace.get("retriever_version")}
        ),
        "observation_versions": sorted(
            {
                str(trace["observation_schema_version"])
                for trace in valid
                if trace.get("observation_schema_version")
            }
        ),
        "recovery_policy_versions": sorted(
            {
                str(trace["recovery_policy_version"])
                for trace in valid
                if trace.get("recovery_policy_version")
            }
        ),
        "approval_policy_versions": sorted(
            {
                str(trace["approval_policy_version"])
                for trace in valid
                if trace.get("approval_policy_version")
            }
        ),
        "trace_versions": sorted(
            {str(trace["schema_version"]) for trace in valid if trace.get("schema_version")}
        ),
    }


def _empty_summary() -> dict[str, Any]:
    return {
        "schema_version": AGENT_EXECUTION_SUMMARY_VERSION,
        "agent_case_count": 0,
        "successful_case_count": 0,
        "failed_case_count": 0,
        "total_step_count": 0,
        "successful_step_count": 0,
        "failed_step_count": 0,
        "task_success_rate": None,
        "plan_validity_rate": None,
        "step_success_rate": None,
        "action_sequence_accuracy": None,
        "policy_violation_rate": None,
        "final_response_rate": None,
        "memory_provenance_rate": None,
        "retried_tool_count": 0,
        "recovered_tool_count": 0,
        "tool_retry_recovery_rate": None,
        "replan_case_count": 0,
        "replan_count": 0,
        "successful_replan_count": 0,
        "replan_success_rate": None,
        "live_replan_count": 0,
        "live_replan_model_call_count": 0,
        "live_replan_prompt_tokens": 0,
        "live_replan_completion_tokens": 0,
        "live_replan_latency_ms": 0.0,
        "live_replan_estimated_cost_usd": 0.0,
        "recovery_step_count": 0,
        "successful_recovery_step_count": 0,
        "recovery_step_success_rate": None,
        "approval_checkpoint_count": 0,
        "approved_checkpoint_count": 0,
        "denied_checkpoint_count": 0,
        "pending_checkpoint_count": 0,
        "approval_compliance_rate": None,
        "approval_provenance_rate": None,
        "pending_approval_rate": None,
        "observation_coverage_rate": None,
        "unrecovered_failure_rate": None,
        "halted_case_count": 0,
        "average_steps_per_case": None,
        "memory_registry_versions": [],
        "tool_registry_versions": [],
        "corpus_versions": [],
        "retriever_versions": [],
        "observation_versions": [],
        "recovery_policy_versions": [],
        "approval_policy_versions": [],
        "trace_versions": [],
    }
