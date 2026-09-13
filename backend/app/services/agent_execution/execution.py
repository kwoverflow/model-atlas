from __future__ import annotations

import time
from typing import Any

from app.models import EvaluationCase
from app.services.rag_evaluation import (
    DEFAULT_RETRIEVER_DESCRIPTOR,
)
from app.services.tool_execution import (
    DEFAULT_TOOL_REGISTRY,
)

from .checkpoints import _record_approved_checkpoint
from .contracts import (
    AGENT_APPROVAL_POLICY_VERSION,
    AGENT_CONTEXT_VERSION,
    AGENT_EXECUTION_TRACE_VERSION,
    AGENT_LIVE_REPLAN_VERSION,
    AGENT_OBSERVATION_VERSION,
    AGENT_RECOVERY_POLICY_VERSION,
    AGENT_RUNTIME_VERSION,
    ALLOWED_AGENT_ACTIONS,
    DEFAULT_OPERATIONAL_MEMORY_REGISTRY,
    MAX_AGENT_LIVE_REPLAN_CALLS,
    AgentExecutionTrace,
    AgentLiveReplanCallback,
    AgentLiveReplanRequest,
    AgentPreparation,
    OperationalMemoryRegistry,
)
from .planning import (
    _expected_recovery_steps,
    _expected_steps,
    _parse_plan,
)
from .recovery import (
    _has_ambiguous_recovery_plans,
    _select_recovery_plan,
)
from .steps import (
    _decorate_executed_step,
    _execute_agent_step,
)
from .traces import (
    _empty_trace,
    _limit_trace,
    _policy_trace,
)
from .utils import _rate


def execute_agent_plan(
    evaluation_case: EvaluationCase,
    normalized_output: str,
    preparation: AgentPreparation,
    memory_registry: OperationalMemoryRegistry | None = None,
    *,
    live_replan_callback: AgentLiveReplanCallback | None = None,
) -> AgentExecutionTrace:
    registry = memory_registry or DEFAULT_OPERATIONAL_MEMORY_REGISTRY
    planned_steps, recovery_plans, parse_error = _parse_plan(normalized_output)
    contract = preparation.contract
    context = preparation.agent_context
    expected_steps = _expected_steps(contract)
    expected_actions = [str(step.get("action")) for step in expected_steps]
    actual_actions = [str(step.get("action") or "") for step in planned_steps]
    sequence_match = actual_actions == expected_actions if expected_actions else True
    step_limit = int(context["step_limit"])
    if parse_error is not None:
        return _empty_trace(
            evaluation_case,
            preparation,
            parse_error=parse_error,
            expected_actions=expected_actions,
            actual_actions=actual_actions,
        )
    if len(planned_steps) > step_limit:
        return _limit_trace(
            evaluation_case,
            preparation,
            expected_actions=expected_actions,
            actual_actions=actual_actions,
            planned_steps=planned_steps,
        )
    replan_limit = int(context["replan_limit"])
    recovery_step_limit = int(context["recovery_step_limit"])
    if recovery_plans and replan_limit == 0:
        return _policy_trace(
            evaluation_case,
            preparation,
            parse_error="recovery plans are not allowed for this task",
            expected_actions=expected_actions,
            actual_actions=actual_actions,
        )
    if len(recovery_plans) > int(context["recovery_branch_limit"]):
        return _policy_trace(
            evaluation_case,
            preparation,
            parse_error=(
                f"recovery branch count {len(recovery_plans)} exceeds limit "
                f"{context['recovery_branch_limit']}"
            ),
            expected_actions=expected_actions,
            actual_actions=actual_actions,
            status="limit_exceeded",
        )
    if _has_ambiguous_recovery_plans(recovery_plans):
        return _policy_trace(
            evaluation_case,
            preparation,
            parse_error="recovery plans contain overlapping triggers",
            expected_actions=expected_actions,
            actual_actions=actual_actions,
        )
    oversized_recovery = next(
        (branch for branch in recovery_plans if len(branch.get("steps", [])) > recovery_step_limit),
        None,
    )
    if oversized_recovery is not None:
        return _policy_trace(
            evaluation_case,
            preparation,
            parse_error=(f"recovery step count exceeds limit {recovery_step_limit}"),
            expected_actions=expected_actions,
            actual_actions=actual_actions,
            status="limit_exceeded",
        )

    action_counts = {action: 0 for action in ALLOWED_AGENT_ACTIONS}
    prior_outputs: list[dict[str, Any]] = []
    executed_steps: list[dict[str, Any]] = []
    approved_checkpoint_ids: set[str] = set()
    replan_events: list[dict[str, Any]] = []
    live_replan_call_count = 0
    halt_reason: str | None = None
    for index, planned_step in enumerate(planned_steps):
        action = str(planned_step.get("action") or "")
        expected = expected_steps[index] if index < len(expected_steps) else None
        action_counts[action] = action_counts.get(action, 0) + 1
        step = _execute_agent_step(
            evaluation_case=evaluation_case,
            step_index=len(executed_steps),
            planned_step=planned_step,
            expected=expected,
            preparation=preparation,
            memory_registry=registry,
            action_count=action_counts[action],
            prior_outputs=prior_outputs,
            approved_checkpoint_ids=approved_checkpoint_ids,
        )
        _decorate_executed_step(step, phase="plan", parent_step_index=None)
        executed_steps.append(step)
        output = step.get("output")
        if step.get("successful") and isinstance(output, dict):
            prior_outputs.append(output)
        _record_approved_checkpoint(step, approved_checkpoint_ids)
        if step.get("status") in {"pending", "denied"}:
            halt_reason = (
                "approval_pending" if step.get("status") == "pending" else "approval_denied"
            )
            break
        if step.get("policy_violations"):
            halt_reason = "policy_violation"
            break
        if step.get("successful"):
            continue

        recovery_plan = _select_recovery_plan(
            recovery_plans,
            trigger_step_index=index,
            error_type=str(step.get("error_type") or ""),
        )
        expected_recovery = _expected_recovery_steps(contract, index)
        recovery_source = "predeclared_plan"
        live_model_call: dict[str, Any] | None = None
        if (
            recovery_plan is None
            and live_replan_callback is not None
            and bool(context.get("allow_live_replanning"))
            and live_replan_call_count < MAX_AGENT_LIVE_REPLAN_CALLS
            and len(replan_events) < replan_limit
        ):
            callback_started = time.perf_counter()
            live_replan_call_count += 1
            try:
                live_response = live_replan_callback(
                    AgentLiveReplanRequest(
                        schema_version=AGENT_LIVE_REPLAN_VERSION,
                        external_case_id=evaluation_case.external_case_id,
                        trigger_step_index=index,
                        trigger_error_type=str(step.get("error_type") or ""),
                        observation=(
                            step.get("observation")
                            if isinstance(step.get("observation"), dict)
                            else None
                        ),
                        expected_recovery_steps=expected_recovery,
                        prior_outputs=list(prior_outputs),
                        recovery_step_limit=recovery_step_limit,
                    )
                )
            except Exception as exc:
                callback_duration_ms = (time.perf_counter() - callback_started) * 1000
                replan_events.append(
                    {
                        "replan_index": len(replan_events) + 1,
                        "trigger_step_index": index,
                        "trigger_error_type": step.get("error_type"),
                        "observation": step.get("observation"),
                        "strategy": "live_callback",
                        "source": "live_callback",
                        "expected_action_sequence": [
                            str(item.get("action")) for item in expected_recovery
                        ],
                        "actual_action_sequence": [],
                        "sequence_match": False,
                        "recovery_step_indices": [],
                        "status": "callback_error",
                        "successful": False,
                        "policy_version": AGENT_RECOVERY_POLICY_VERSION,
                        "model_call": {
                            "schema_version": AGENT_LIVE_REPLAN_VERSION,
                            "callback_duration_ms": round(callback_duration_ms, 3),
                            "error_type": type(exc).__name__,
                        },
                    }
                )
                halt_reason = "live_replan_callback_error"
                break
            callback_duration_ms = (time.perf_counter() - callback_started) * 1000
            if live_response is not None:
                live_model_call = live_response.provenance(
                    callback_duration_ms=callback_duration_ms
                )
                recovery_plan = {
                    "steps": live_response.steps,
                    "strategy": "live_callback_recovery",
                }
                recovery_source = "live_callback"
            else:
                replan_events.append(
                    {
                        "replan_index": len(replan_events) + 1,
                        "trigger_step_index": index,
                        "trigger_error_type": step.get("error_type"),
                        "observation": step.get("observation"),
                        "strategy": "live_callback",
                        "source": "live_callback",
                        "expected_action_sequence": [
                            str(item.get("action")) for item in expected_recovery
                        ],
                        "actual_action_sequence": [],
                        "sequence_match": False,
                        "recovery_step_indices": [],
                        "status": "no_recovery",
                        "successful": False,
                        "policy_version": AGENT_RECOVERY_POLICY_VERSION,
                        "model_call": {
                            "schema_version": AGENT_LIVE_REPLAN_VERSION,
                            "callback_duration_ms": round(callback_duration_ms, 3),
                        },
                    }
                )
                halt_reason = "live_replan_no_recovery"
                break
        if recovery_plan is None or len(replan_events) >= replan_limit:
            continue
        recovery_steps = recovery_plan.get("steps", [])
        if not isinstance(recovery_steps, list):
            recovery_steps = []
        if len(recovery_steps) > recovery_step_limit:
            replan_events.append(
                {
                    "replan_index": len(replan_events) + 1,
                    "trigger_step_index": index,
                    "trigger_error_type": step.get("error_type"),
                    "observation": step.get("observation"),
                    "strategy": str(recovery_plan.get("strategy") or "recovery"),
                    "source": recovery_source,
                    "expected_action_sequence": [
                        str(item.get("action")) for item in expected_recovery
                    ],
                    "actual_action_sequence": [
                        str(item.get("action") or "")
                        for item in recovery_steps
                        if isinstance(item, dict)
                    ],
                    "sequence_match": False,
                    "recovery_step_indices": [],
                    "status": "limit_exceeded",
                    "successful": False,
                    "policy_version": AGENT_RECOVERY_POLICY_VERSION,
                    "model_call": live_model_call,
                }
            )
            halt_reason = "recovery_step_limit_exceeded"
            break
        expected_recovery_actions = [str(item.get("action")) for item in expected_recovery]
        actual_recovery_actions = [
            str(item.get("action") or "") for item in recovery_steps if isinstance(item, dict)
        ]
        recovery_sequence_match = (
            actual_recovery_actions == expected_recovery_actions
            if expected_recovery_actions
            else True
        )
        replan_event: dict[str, Any] = {
            "replan_index": len(replan_events) + 1,
            "trigger_step_index": index,
            "trigger_error_type": step.get("error_type"),
            "observation": step.get("observation"),
            "strategy": str(recovery_plan.get("strategy") or "replace_with_recovery_steps"),
            "expected_action_sequence": expected_recovery_actions,
            "actual_action_sequence": actual_recovery_actions,
            "sequence_match": recovery_sequence_match,
            "recovery_step_indices": [],
            "status": "running",
            "successful": False,
            "policy_version": AGENT_RECOVERY_POLICY_VERSION,
            "source": recovery_source,
            "model_call": live_model_call,
        }
        replan_events.append(replan_event)
        recovery_successful = bool(recovery_steps) and recovery_sequence_match
        if not recovery_sequence_match:
            replan_event["status"] = "policy_violation"
            halt_reason = "recovery_sequence_violation"
            break
        for recovery_index, recovery_step in enumerate(recovery_steps):
            if not isinstance(recovery_step, dict):
                recovery_successful = False
                replan_event["status"] = "invalid_recovery_step"
                break
            if len(executed_steps) >= int(context["execution_step_limit"]):
                recovery_successful = False
                replan_event["status"] = "limit_exceeded"
                halt_reason = "execution_step_limit_exceeded"
                break
            recovery_action = str(recovery_step.get("action") or "")
            expected_recovery_step = (
                expected_recovery[recovery_index]
                if recovery_index < len(expected_recovery)
                else None
            )
            action_counts[recovery_action] = action_counts.get(recovery_action, 0) + 1
            executed_recovery = _execute_agent_step(
                evaluation_case=evaluation_case,
                step_index=len(executed_steps),
                planned_step=recovery_step,
                expected=expected_recovery_step,
                preparation=preparation,
                memory_registry=registry,
                action_count=action_counts[recovery_action],
                prior_outputs=prior_outputs,
                approved_checkpoint_ids=approved_checkpoint_ids,
            )
            _decorate_executed_step(
                executed_recovery,
                phase="recovery",
                parent_step_index=index,
            )
            executed_steps.append(executed_recovery)
            replan_event["recovery_step_indices"].append(executed_recovery["step_index"])
            recovery_output = executed_recovery.get("output")
            if executed_recovery.get("successful") and isinstance(recovery_output, dict):
                prior_outputs.append(recovery_output)
            _record_approved_checkpoint(
                executed_recovery,
                approved_checkpoint_ids,
            )
            if not executed_recovery.get("successful"):
                recovery_successful = False
                if replan_event["status"] == "running":
                    replan_event["status"] = "failed"
                break
        if recovery_successful:
            step["recovered_by_replan"] = True
            replan_event["status"] = "success"
            replan_event["successful"] = True
        else:
            if replan_event["status"] == "running":
                replan_event["status"] = "failed"
            halt_reason = halt_reason or "recovery_failed"
            break

    successful_steps = [step for step in executed_steps if step.get("successful")]
    failed_steps = [step for step in executed_steps if not step.get("successful")]
    unrecovered_failed_steps = [
        step for step in failed_steps if not step.get("recovered_by_replan")
    ]
    policy_violations = sum(len(step.get("policy_violations", [])) for step in executed_steps)
    if not sequence_match:
        policy_violations += 1
    if any(event.get("sequence_match") is False for event in replan_events):
        policy_violations += 1
    final_response_present = any(
        step.get("action") == "respond" and step.get("successful") for step in executed_steps
    )
    memory_steps = [
        step for step in executed_steps if step.get("action") in {"memory_read", "memory_write"}
    ]
    memory_provenance_count = sum(1 for step in memory_steps if step.get("memory_provenance_valid"))
    retried_tool_steps = [step for step in executed_steps if int(step.get("retry_count") or 0) > 0]
    approval_steps = [
        step for step in executed_steps if step.get("action") == "approval_checkpoint"
    ]
    recovery_steps = [step for step in executed_steps if step.get("phase") == "recovery"]
    recovery_sequence_match = (
        all(bool(event.get("sequence_match")) for event in replan_events) if replan_events else None
    )
    plan_valid = (
        sequence_match and policy_violations == 0 and (recovery_sequence_match is not False)
    )
    successful = (
        bool(executed_steps)
        and plan_valid
        and not unrecovered_failed_steps
        and final_response_present
        and halt_reason is None
    )
    if halt_reason == "approval_pending":
        status = "pending_approval"
    elif halt_reason == "approval_denied":
        status = "approval_denied"
    elif successful:
        status = "success"
    elif successful_steps:
        status = "partial_failure"
    else:
        status = "failed"
    live_replan_events = [
        event for event in replan_events if event.get("source") == "live_callback"
    ]
    live_model_calls = [
        event["model_call"]
        for event in live_replan_events
        if isinstance(event.get("model_call"), dict)
    ]
    return AgentExecutionTrace(
        schema_version=AGENT_EXECUTION_TRACE_VERSION,
        context_version=AGENT_CONTEXT_VERSION,
        runtime_version=AGENT_RUNTIME_VERSION,
        observation_schema_version=AGENT_OBSERVATION_VERSION,
        recovery_policy_version=AGENT_RECOVERY_POLICY_VERSION,
        approval_policy_version=AGENT_APPROVAL_POLICY_VERSION,
        memory_registry_version=registry.registry_version,
        tool_registry_version=DEFAULT_TOOL_REGISTRY.registry_version,
        corpus_version=preparation.corpus.corpus_version,
        retriever_version=DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version,
        external_case_id=evaluation_case.external_case_id,
        parse_valid=True,
        parse_error=None,
        plan_valid=plan_valid,
        status=status,
        successful=successful,
        step_limit=step_limit,
        execution_step_limit=int(context["execution_step_limit"]),
        replan_limit=replan_limit,
        step_count=len(executed_steps),
        expected_action_sequence=expected_actions,
        actual_action_sequence=actual_actions,
        sequence_match=sequence_match,
        successful_step_count=len(successful_steps),
        failed_step_count=len(failed_steps),
        step_success_rate=_rate(len(successful_steps), len(executed_steps)),
        tool_call_count=action_counts.get("tool", 0),
        retrieval_count=action_counts.get("retrieve", 0),
        memory_read_count=action_counts.get("memory_read", 0),
        memory_write_count=action_counts.get("memory_write", 0),
        retried_tool_count=len(retried_tool_steps),
        recovered_tool_count=sum(1 for step in retried_tool_steps if step.get("recovered")),
        policy_violation_count=policy_violations,
        final_response_present=final_response_present,
        memory_provenance_count=memory_provenance_count,
        memory_action_count=len(memory_steps),
        observation_count=sum(
            1 for step in executed_steps if isinstance(step.get("observation"), dict)
        ),
        replan_count=len(replan_events),
        successful_replan_count=sum(1 for event in replan_events if event.get("successful")),
        recovery_step_count=len(recovery_steps),
        successful_recovery_step_count=sum(1 for step in recovery_steps if step.get("successful")),
        recovery_sequence_match=recovery_sequence_match,
        unrecovered_failure_count=len(unrecovered_failed_steps),
        approval_checkpoint_count=len(approval_steps),
        approved_checkpoint_count=sum(
            1 for step in approval_steps if step.get("status") == "approved"
        ),
        denied_checkpoint_count=sum(1 for step in approval_steps if step.get("status") == "denied"),
        pending_checkpoint_count=sum(
            1 for step in approval_steps if step.get("status") == "pending"
        ),
        approval_provenance_count=sum(
            1 for step in approval_steps if step.get("approval_provenance_valid")
        ),
        halt_reason=halt_reason,
        total_duration_ms=round(
            sum(float(step.get("duration_ms") or 0) for step in executed_steps)
            + sum(
                max(
                    float(call.get("model_call_latency_ms") or 0),
                    float(call.get("callback_duration_ms") or 0),
                )
                for call in live_model_calls
            ),
            3,
        ),
        live_replan_count=len(live_replan_events),
        live_replan_model_call_count=len(live_model_calls),
        live_replan_prompt_tokens=sum(
            int(call.get("prompt_tokens") or 0) for call in live_model_calls
        ),
        live_replan_completion_tokens=sum(
            int(call.get("completion_tokens") or 0) for call in live_model_calls
        ),
        live_replan_latency_ms=round(
            sum(float(call.get("model_call_latency_ms") or 0) for call in live_model_calls),
            3,
        ),
        live_replan_estimated_cost_usd=round(
            sum(float(call.get("estimated_cost_usd") or 0) for call in live_model_calls),
            8,
        ),
        replans=replan_events,
        steps=executed_steps,
    )
