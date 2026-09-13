from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.models import EvaluationCase
from app.services.rag_evaluation import (
    DEFAULT_RETRIEVER_DESCRIPTOR,
)
from app.services.tool_execution import (
    DEFAULT_TOOL_REGISTRY,
)

from .contracts import (
    AGENT_APPROVAL_POLICY_VERSION,
    AGENT_CONTEXT_VERSION,
    AGENT_EXECUTION_TRACE_VERSION,
    AGENT_OBSERVATION_VERSION,
    AGENT_RECOVERY_POLICY_VERSION,
    AGENT_RUNTIME_VERSION,
    OPERATIONAL_MEMORY_REGISTRY_VERSION,
    AgentExecutionTrace,
    AgentPreparation,
)


def _empty_trace(
    evaluation_case: EvaluationCase,
    preparation: AgentPreparation,
    *,
    parse_error: str,
    expected_actions: list[str],
    actual_actions: list[str],
) -> AgentExecutionTrace:
    return AgentExecutionTrace(
        schema_version=AGENT_EXECUTION_TRACE_VERSION,
        context_version=AGENT_CONTEXT_VERSION,
        runtime_version=AGENT_RUNTIME_VERSION,
        observation_schema_version=AGENT_OBSERVATION_VERSION,
        recovery_policy_version=AGENT_RECOVERY_POLICY_VERSION,
        approval_policy_version=AGENT_APPROVAL_POLICY_VERSION,
        memory_registry_version=OPERATIONAL_MEMORY_REGISTRY_VERSION,
        tool_registry_version=DEFAULT_TOOL_REGISTRY.registry_version,
        corpus_version=preparation.corpus.corpus_version,
        retriever_version=DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version,
        external_case_id=evaluation_case.external_case_id,
        parse_valid=False,
        parse_error=parse_error,
        plan_valid=False,
        status="invalid_plan",
        successful=False,
        step_limit=int(preparation.agent_context["step_limit"]),
        execution_step_limit=int(preparation.agent_context["execution_step_limit"]),
        replan_limit=int(preparation.agent_context["replan_limit"]),
        step_count=0,
        expected_action_sequence=expected_actions,
        actual_action_sequence=actual_actions,
        sequence_match=False,
        successful_step_count=0,
        failed_step_count=0,
        step_success_rate=None,
        tool_call_count=0,
        retrieval_count=0,
        memory_read_count=0,
        memory_write_count=0,
        retried_tool_count=0,
        recovered_tool_count=0,
        policy_violation_count=1,
        final_response_present=False,
        memory_provenance_count=0,
        memory_action_count=0,
        observation_count=0,
        replan_count=0,
        successful_replan_count=0,
        recovery_step_count=0,
        successful_recovery_step_count=0,
        recovery_sequence_match=None,
        unrecovered_failure_count=0,
        approval_checkpoint_count=0,
        approved_checkpoint_count=0,
        denied_checkpoint_count=0,
        pending_checkpoint_count=0,
        approval_provenance_count=0,
        halt_reason="invalid_plan",
        total_duration_ms=0.0,
        replans=[],
        steps=[],
    )


def _policy_trace(
    evaluation_case: EvaluationCase,
    preparation: AgentPreparation,
    *,
    parse_error: str,
    expected_actions: list[str],
    actual_actions: list[str],
    status: str = "failed",
) -> AgentExecutionTrace:
    trace = _empty_trace(
        evaluation_case,
        preparation,
        parse_error=parse_error,
        expected_actions=expected_actions,
        actual_actions=actual_actions,
    )
    return replace(
        trace,
        parse_valid=True,
        status=status,
        halt_reason="policy_violation",
    )


def _limit_trace(
    evaluation_case: EvaluationCase,
    preparation: AgentPreparation,
    *,
    expected_actions: list[str],
    actual_actions: list[str],
    planned_steps: list[dict[str, Any]],
) -> AgentExecutionTrace:
    trace = _empty_trace(
        evaluation_case,
        preparation,
        parse_error=(
            f"agent step count {len(planned_steps)} exceeds limit "
            f"{preparation.agent_context['step_limit']}"
        ),
        expected_actions=expected_actions,
        actual_actions=actual_actions,
    )
    return replace(
        trace,
        parse_valid=True,
        status="limit_exceeded",
        step_count=len(planned_steps),
        halt_reason="step_limit_exceeded",
    )
