from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict
from typing import Any

from app.models import EvaluationCase
from app.services.rag_evaluation import (
    retrieve,
)
from app.services.tool_execution import (
    execute_registered_tool_call,
)

from .checkpoints import _execute_approval_checkpoint, _step_result
from .contracts import AGENT_OBSERVATION_VERSION, AgentPreparation, OperationalMemoryRegistry
from .planning import _action_limit
from .semantics import _semantic_projection
from .utils import _string_list


def _execute_agent_step(
    *,
    evaluation_case: EvaluationCase,
    step_index: int,
    planned_step: dict[str, Any],
    expected: dict[str, Any] | None,
    preparation: AgentPreparation,
    memory_registry: OperationalMemoryRegistry,
    action_count: int,
    prior_outputs: list[dict[str, Any]],
    approved_checkpoint_ids: set[str],
) -> dict[str, Any]:
    started = time.perf_counter()
    action = str(planned_step.get("action") or "")
    expected_action = str(expected.get("action")) if expected else None
    violations: list[str] = []
    if action not in preparation.agent_context["allowed_actions"]:
        violations.append(f"action {action or '<missing>'} is not allowed")
    if expected_action is not None and action != expected_action:
        violations.append(f"expected action {expected_action}, received {action}")
    action_limit = _action_limit(action, preparation.agent_context)
    if action_limit is not None and action_count > action_limit:
        violations.append(f"action {action} exceeds limit {action_limit}")
    planned_checkpoint = str(planned_step.get("requires_approval") or "").strip()
    expected_checkpoint = str(expected.get("requires_approval") or "").strip() if expected else ""
    if expected_checkpoint and planned_checkpoint != expected_checkpoint:
        violations.append(f"action {action} must declare checkpoint {expected_checkpoint}")
    required_checkpoint = expected_checkpoint or planned_checkpoint
    if required_checkpoint and required_checkpoint not in approved_checkpoint_ids:
        violations.append(
            f"checkpoint {required_checkpoint} must be approved before action {action}"
        )
    if violations:
        return _step_result(
            step_index=step_index,
            action=action,
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

    if action == "approval_checkpoint":
        return _execute_approval_checkpoint(
            step_index,
            planned_step,
            expected,
            expected_action,
            preparation,
            started,
        )
    if action == "memory_read":
        return _execute_memory_read(
            step_index,
            planned_step,
            expected_action,
            preparation,
            memory_registry,
            started,
        )
    if action == "memory_write":
        return _execute_memory_write(
            evaluation_case,
            step_index,
            planned_step,
            expected_action,
            preparation,
            memory_registry,
            started,
        )
    if action == "retrieve":
        return _execute_retrieval(
            step_index,
            planned_step,
            expected,
            expected_action,
            preparation,
            started,
        )
    if action == "tool":
        return _execute_tool_action(
            evaluation_case,
            step_index,
            planned_step,
            expected,
            expected_action,
            preparation,
            prior_outputs,
            started,
        )
    if action == "respond":
        return _execute_response(
            step_index,
            planned_step,
            expected,
            expected_action,
            started,
        )
    return _step_result(
        step_index=step_index,
        action=action,
        expected_action=expected_action,
        planned_step=planned_step,
        started=started,
        successful=False,
        status="failed",
        output=None,
        error_type="unsupported_agent_action",
        error_message=f"Action {action or '<missing>'} is not supported.",
    )


def _execute_memory_read(
    step_index: int,
    planned_step: dict[str, Any],
    expected_action: str | None,
    preparation: AgentPreparation,
    registry: OperationalMemoryRegistry,
    started: float,
) -> dict[str, Any]:
    memory_id = str(planned_step.get("memory_id") or "")
    record = registry.get(memory_id)
    allowed = memory_id in preparation.agent_context["allowed_memory_ids"]
    successful = record is not None and allowed
    output = (
        {
            "memory_id": record.memory_id,
            "memory_version": record.memory_version,
            "content": record.content,
            "content_hash": record.content_hash,
            "registry_version": registry.registry_version,
        }
        if successful and record is not None
        else None
    )
    return _step_result(
        step_index=step_index,
        action="memory_read",
        expected_action=expected_action,
        planned_step=planned_step,
        started=started,
        successful=successful,
        status="success" if successful else "failed",
        output=output,
        error_type=None if successful else "memory_access_denied",
        error_message=(
            None
            if successful
            else f"Memory {memory_id or '<missing>'} is unavailable or not allowed."
        ),
        memory_provenance_valid=successful,
    )


def _execute_memory_write(
    evaluation_case: EvaluationCase,
    step_index: int,
    planned_step: dict[str, Any],
    expected_action: str | None,
    preparation: AgentPreparation,
    registry: OperationalMemoryRegistry,
    started: float,
) -> dict[str, Any]:
    key = str(planned_step.get("key") or "").strip()
    value = str(planned_step.get("value") or "").strip()
    allowed = bool(preparation.agent_context["allow_memory_write"])
    successful = allowed and bool(key) and bool(value)
    memory_id = (
        "task-memory-"
        + hashlib.sha256(f"{evaluation_case.external_case_id}:{key}:{value}".encode()).hexdigest()[
            :12
        ]
        if successful
        else None
    )
    output = (
        {
            "memory_id": memory_id,
            "key": key,
            "value": value,
            "scope": "task_local_simulated",
            "registry_version": registry.registry_version,
            "persisted": False,
        }
        if successful
        else None
    )
    return _step_result(
        step_index=step_index,
        action="memory_write",
        expected_action=expected_action,
        planned_step=planned_step,
        started=started,
        successful=successful,
        status="success" if successful else "failed",
        output=output,
        error_type=None if successful else "memory_write_denied",
        error_message=(
            None if successful else "Memory write is disabled or the task-local key/value is empty."
        ),
        memory_provenance_valid=successful,
    )


def _execute_retrieval(
    step_index: int,
    planned_step: dict[str, Any],
    expected: dict[str, Any] | None,
    expected_action: str | None,
    preparation: AgentPreparation,
    started: float,
) -> dict[str, Any]:
    query = str(planned_step.get("query") or "").strip()
    relevant_chunk_ids = _string_list(expected.get("relevant_chunk_ids") if expected else None)
    trace = retrieve(
        corpus=preparation.corpus,
        query=query,
        relevant_chunk_ids=relevant_chunk_ids,
        top_k=int(preparation.agent_context["retrieval_top_k"]),
        min_score=float(preparation.agent_context["retrieval_min_score"]),
    )
    successful = (
        bool(query)
        and trace.status == "success"
        and (not relevant_chunk_ids or trace.retrieval_recall == 1.0)
    )
    return _step_result(
        step_index=step_index,
        action="retrieve",
        expected_action=expected_action,
        planned_step=planned_step,
        started=started,
        successful=successful,
        status="success" if successful else "failed",
        output={"retrieval": trace.to_dict()},
        error_type=None if successful else "agent_retrieval_failed",
        error_message=(
            None if successful else "Retrieval was empty or missed a required relevant chunk."
        ),
    )


def _execute_tool_action(
    evaluation_case: EvaluationCase,
    step_index: int,
    planned_step: dict[str, Any],
    expected: dict[str, Any] | None,
    expected_action: str | None,
    preparation: AgentPreparation,
    prior_outputs: list[dict[str, Any]],
    started: float,
) -> dict[str, Any]:
    tool_name = str(planned_step.get("tool_name") or "")
    arguments = planned_step.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    if tool_name not in preparation.agent_context["allowed_tools"]:
        return _step_result(
            step_index=step_index,
            action="tool",
            expected_action=expected_action,
            planned_step=planned_step,
            started=started,
            successful=False,
            status="failed",
            output=None,
            error_type="tool_access_denied",
            error_message=f"Tool {tool_name or '<missing>'} is not allowed for this task.",
            policy_violations=["tool allowlist violation"],
        )
    tool_step = execute_registered_tool_call(
        external_case_id=evaluation_case.external_case_id,
        step_index=step_index,
        tool_name=tool_name,
        arguments=arguments,
        expected=expected,
        prior_outputs=prior_outputs,
        call_id=str(planned_step.get("call_id") or f"agent-call-{step_index + 1}"),
    )
    payload = _step_result(
        step_index=step_index,
        action="tool",
        expected_action=expected_action,
        planned_step=planned_step,
        started=started,
        successful=tool_step.execution_status == "success",
        status=tool_step.execution_status,
        output={"tool_execution": asdict(tool_step)},
        error_type=tool_step.error_type,
        error_message=tool_step.error_message,
        recovered=tool_step.recovered,
        retry_count=tool_step.retry_count,
    )
    payload["duration_ms"] = tool_step.duration_ms
    return payload


def _execute_response(
    step_index: int,
    planned_step: dict[str, Any],
    expected: dict[str, Any] | None,
    expected_action: str | None,
    started: float,
) -> dict[str, Any]:
    content = str(planned_step.get("content") or "").strip()
    required_terms = _string_list(expected.get("required_terms") if expected else None)
    missing_terms = [term for term in required_terms if term.lower() not in content.lower()]
    successful = bool(content) and not missing_terms
    return _step_result(
        step_index=step_index,
        action="respond",
        expected_action=expected_action,
        planned_step=planned_step,
        started=started,
        successful=successful,
        status="success" if successful else "failed",
        output={
            "content": content,
            "citations": _string_list(planned_step.get("citations")),
        },
        error_type=None if successful else "invalid_final_response",
        error_message=(
            None
            if successful
            else (
                "Final response is empty."
                if not content
                else f"Final response is missing required terms: {missing_terms}."
            )
        ),
    )


def _decorate_executed_step(
    step: dict[str, Any],
    *,
    phase: str,
    parent_step_index: int | None,
) -> None:
    step["phase"] = phase
    step["parent_step_index"] = parent_step_index
    output = step.get("output")
    output_digest = (
        hashlib.sha256(
            json.dumps(
                _semantic_projection(output),
                default=str,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if output is not None
        else None
    )
    step["observation"] = {
        "schema_version": AGENT_OBSERVATION_VERSION,
        "status": step.get("status"),
        "successful": bool(step.get("successful")),
        "error_type": step.get("error_type"),
        "policy_violation_count": len(step.get("policy_violations", [])),
        "output_digest": output_digest,
    }
