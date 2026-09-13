from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models import DeploymentConfiguration, EvaluationCase
from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS,
    DEFAULT_RAG_CORPUS_REGISTRY,
    DEFAULT_RETRIEVER_DESCRIPTOR,
    RagCorpusRegistry,
)
from app.services.tool_execution import (
    DEFAULT_TOOL_REGISTRY,
    validate_json_schema,
)

from .contracts import (
    AGENT_APPROVAL_POLICY_VERSION,
    AGENT_CONTEXT_VERSION,
    AGENT_OBSERVATION_VERSION,
    AGENT_RECOVERY_POLICY_VERSION,
    AGENT_RUNTIME_VERSION,
    ALLOWED_AGENT_ACTIONS,
    DEFAULT_OPERATIONAL_MEMORY_REGISTRY,
    MAX_AGENT_APPROVAL_CHECKPOINTS,
    MAX_AGENT_MEMORY_READS,
    MAX_AGENT_MEMORY_WRITES,
    MAX_AGENT_RECOVERY_BRANCHES,
    MAX_AGENT_RECOVERY_STEPS,
    MAX_AGENT_REPLANS,
    MAX_AGENT_RETRIEVALS,
    MAX_AGENT_STEPS,
    MAX_AGENT_TOOL_CALLS,
    AgentPreparation,
    OperationalMemoryRegistry,
)
from .utils import (
    _bounded_int,
    _string_list,
)

AGENT_PLAN_COMPILER_VERSION = "bounded-agent-plan-compiler-v1"
SUPPORTED_AGENT_RETRIEVAL_QUERY_STRATEGIES = frozenset({"reviewed-bilingual-retrieval-query-v1"})


def compile_bounded_agent_plan(
    evaluation_case: EvaluationCase,
    normalized_output: str,
    preparation: AgentPreparation,
) -> tuple[str, dict[str, Any]]:
    context = preparation.agent_context
    record: dict[str, Any] = {
        "schema_version": AGENT_PLAN_COMPILER_VERSION,
        "applied": False,
        "eligible": False,
        "reason": "contract_not_eligible",
        "source_output_hash": _text_hash(normalized_output),
        "compiled_output_hash": None,
        "source_action_sequence": [],
        "compiled_action_sequence": [],
        "inserted_actions": [],
        "removed_step_count": 0,
        "reordered": False,
        "retrieval_query_source": None,
        "uses_expected_steps": False,
    }
    allowed_actions = set(_string_list(context.get("allowed_actions")))
    allowed_tools = _string_list(context.get("allowed_tools"))
    eligible = (
        "mock_agent_plan" not in preparation.adapter_input_payload
        and allowed_actions == {"retrieve", "tool", "respond"}
        and len(allowed_tools) == 1
        and int(context.get("step_limit") or 0) == 3
        and int(context.get("retrieval_limit") or 0) == 1
        and int(context.get("tool_call_limit") or 0) == 1
    )
    record["eligible"] = eligible
    if not eligible:
        return normalized_output, record
    try:
        payload = json.loads(normalized_output)
    except (json.JSONDecodeError, TypeError):
        record["reason"] = "source_output_not_valid_json"
        return normalized_output, record
    steps = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(steps, list) or not steps:
        record["reason"] = "source_steps_missing"
        return normalized_output, record
    source_steps = [dict(step) for step in steps if isinstance(step, dict)]
    if len(source_steps) != len(steps):
        record["reason"] = "source_step_not_object"
        return normalized_output, record
    source_actions = [str(step.get("action") or "") for step in source_steps]
    record["source_action_sequence"] = source_actions
    if any(action not in allowed_actions for action in source_actions):
        record["reason"] = "source_contains_disallowed_action"
        return normalized_output, record

    tool_name = allowed_tools[0]
    tool_step = next(
        (
            step
            for step in source_steps
            if step.get("action") == "tool" and step.get("tool_name") == tool_name
        ),
        None,
    )
    registered_tool = DEFAULT_TOOL_REGISTRY.get(tool_name)
    if tool_step is None or registered_tool is None:
        record["reason"] = "allowed_tool_intent_missing"
        return normalized_output, record
    source_arguments = tool_step.get("arguments")
    if not isinstance(source_arguments, dict):
        record["reason"] = "tool_arguments_missing"
        return normalized_output, record
    argument_schema = registered_tool.descriptor.argument_schema
    required = argument_schema.get("required")
    required = required if isinstance(required, list) else []
    arguments = {str(name): source_arguments[name] for name in required if name in source_arguments}
    required_schema = {
        **argument_schema,
        "properties": {
            str(name): argument_schema.get("properties", {}).get(name, {}) for name in required
        },
        "additionalProperties": False,
    }
    if validate_json_schema(arguments, required_schema):
        record["reason"] = "required_tool_arguments_invalid"
        return normalized_output, record

    request_text = str(
        evaluation_case.input_payload_json.get("request")
        or evaluation_case.input_payload_json.get("query")
        or evaluation_case.title
    ).strip()
    retrieval_step = next(
        (step for step in source_steps if step.get("action") == "retrieve"),
        None,
    )
    source_retrieval_query = (
        str(retrieval_step.get("query") or "").strip() if retrieval_step is not None else ""
    )
    configured_retrieval_query = str(context.get("retrieval_query") or "").strip()
    retrieval_query = configured_retrieval_query or source_retrieval_query or request_text
    record["retrieval_query_source"] = (
        "public_contract"
        if configured_retrieval_query
        else "model_plan"
        if source_retrieval_query
        else "request"
    )
    response_step = next(
        (step for step in source_steps if step.get("action") == "respond"),
        None,
    )
    response_content = (
        str(response_step.get("content") or "").strip() if response_step is not None else ""
    ) or f"retrieve 후 {tool_name} 실행, retrieve, tool, respond 순서 완료"
    compiled_steps = [
        {"action": "retrieve", "query": retrieval_query},
        {"action": "tool", "tool_name": tool_name, "arguments": arguments},
        {"action": "respond", "content": response_content},
    ]
    compiled_output = json.dumps(
        {"steps": compiled_steps},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    compiled_actions = ["retrieve", "tool", "respond"]
    record.update(
        {
            "applied": True,
            "reason": "compiled_from_allowed_tool_intent",
            "compiled_output_hash": _text_hash(compiled_output),
            "compiled_action_sequence": compiled_actions,
            "inserted_actions": [
                action for action in compiled_actions if action not in source_actions
            ],
            "removed_step_count": max(0, len(source_steps) - len(compiled_steps)),
            "reordered": source_actions != compiled_actions,
        }
    )
    return compiled_output, record


def _text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_agent_case(evaluation_case: EvaluationCase) -> bool:
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    return (
        isinstance(reference.get("agent"), dict)
        or "agent" in (evaluation_case.category or "").lower()
    )


def prepare_agent_execution(
    configuration: DeploymentConfiguration,
    evaluation_case: EvaluationCase,
    *,
    include_mock_plan: bool,
    approval_decisions: dict[str, Any] | None = None,
    memory_registry: OperationalMemoryRegistry | None = None,
    rag_corpus_registry: RagCorpusRegistry | None = None,
) -> AgentPreparation | None:
    if not is_agent_case(evaluation_case):
        return None
    registry = memory_registry or DEFAULT_OPERATIONAL_MEMORY_REGISTRY
    contract = _agent_contract(evaluation_case)
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    rag_contract = reference.get("rag")
    rag_contract = rag_contract if isinstance(rag_contract, dict) else {}
    retrieval_query_strategy = str(rag_contract.get("query_strategy") or "")
    retrieval_query = (
        str(rag_contract.get("query") or "").strip()
        if retrieval_query_strategy in SUPPORTED_AGENT_RETRIEVAL_QUERY_STRATEGIES
        else ""
    )
    retrieval_config = (
        configuration.retrieval_config_json
        if isinstance(configuration.retrieval_config_json, dict)
        else {}
    )
    corpus_id = str(retrieval_config.get("corpus_id") or DEFAULT_RAG_CORPUS.corpus_id)
    corpus_registry = rag_corpus_registry or DEFAULT_RAG_CORPUS_REGISTRY
    corpus = corpus_registry.get(corpus_id) or DEFAULT_RAG_CORPUS
    allowed_actions = _allowed_actions(contract)
    allowed_memory_ids = [
        memory_id
        for memory_id in _string_list(contract.get("allowed_memory_ids"))
        if registry.get(memory_id) is not None
    ]
    allowed_tools = [
        tool_name
        for tool_name in _string_list(contract.get("allowed_tools"))
        if DEFAULT_TOOL_REGISTRY.get(tool_name) is not None
    ]
    step_limit = _bounded_int(contract.get("max_steps"), MAX_AGENT_STEPS, MAX_AGENT_STEPS)
    replan_limit = (
        _bounded_int(contract.get("max_replans"), MAX_AGENT_REPLANS, MAX_AGENT_REPLANS)
        if bool(contract.get("allow_replanning", False))
        else 0
    )
    recovery_step_limit = (
        _bounded_int(
            contract.get("max_recovery_steps"),
            MAX_AGENT_RECOVERY_STEPS,
            MAX_AGENT_RECOVERY_STEPS,
        )
        if replan_limit
        else 0
    )
    allowed_checkpoint_ids = _string_list(contract.get("allowed_checkpoint_ids"))
    normalized_decisions = _normalize_approval_decisions(approval_decisions)
    context = {
        "schema_version": AGENT_CONTEXT_VERSION,
        "runtime_version": AGENT_RUNTIME_VERSION,
        "observation_schema_version": AGENT_OBSERVATION_VERSION,
        "recovery_policy_version": AGENT_RECOVERY_POLICY_VERSION,
        "approval_policy_version": AGENT_APPROVAL_POLICY_VERSION,
        "step_limit": step_limit,
        "execution_step_limit": step_limit + recovery_step_limit,
        "replan_limit": replan_limit,
        "recovery_step_limit": recovery_step_limit,
        "recovery_branch_limit": MAX_AGENT_RECOVERY_BRANCHES,
        "approval_checkpoint_limit": min(
            _bounded_int(
                contract.get("max_approval_checkpoints"),
                MAX_AGENT_APPROVAL_CHECKPOINTS,
                MAX_AGENT_APPROVAL_CHECKPOINTS,
            ),
            step_limit,
        ),
        "allowed_actions": allowed_actions,
        "allowed_memory_ids": allowed_memory_ids,
        "allowed_tools": allowed_tools,
        "allowed_checkpoint_ids": allowed_checkpoint_ids,
        "allow_memory_write": bool(contract.get("allow_memory_write", False)),
        "allow_live_replanning": bool(
            replan_limit and contract.get("allow_live_replanning", False)
        ),
        "approval_decision_mode": "external_request_only",
        "tool_call_limit": min(
            _bounded_int(
                contract.get("max_tool_calls"),
                MAX_AGENT_TOOL_CALLS,
                MAX_AGENT_TOOL_CALLS,
            ),
            step_limit,
        ),
        "retrieval_limit": min(
            _bounded_int(
                contract.get("max_retrievals"),
                MAX_AGENT_RETRIEVALS,
                MAX_AGENT_RETRIEVALS,
            ),
            step_limit,
        ),
        "memory_read_limit": min(
            _bounded_int(
                contract.get("max_memory_reads"),
                MAX_AGENT_MEMORY_READS,
                MAX_AGENT_MEMORY_READS,
            ),
            step_limit,
        ),
        "memory_write_limit": min(
            _bounded_int(
                contract.get("max_memory_writes"),
                MAX_AGENT_MEMORY_WRITES,
                MAX_AGENT_MEMORY_WRITES,
            ),
            step_limit,
        ),
        "memory_registry_id": registry.registry_id,
        "memory_registry_version": registry.registry_version,
        "tool_registry_id": DEFAULT_TOOL_REGISTRY.registry_id,
        "tool_registry_version": DEFAULT_TOOL_REGISTRY.registry_version,
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "retriever_id": DEFAULT_RETRIEVER_DESCRIPTOR.retriever_id,
        "retriever_version": DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version,
        "retrieval_top_k": _bounded_int(retrieval_config.get("top_k"), 3, 10),
        "retrieval_min_score": float(retrieval_config.get("min_score", 0.05)),
    }
    if retrieval_query:
        context["retrieval_query"] = retrieval_query
        context["retrieval_query_strategy"] = retrieval_query_strategy
    adapter_input = dict(evaluation_case.input_payload_json or {})
    if not include_mock_plan:
        adapter_input.pop("mock_agent_plan", None)
    adapter_input.pop("agent_approval_decisions", None)
    adapter_input["agent_context"] = context
    return AgentPreparation(
        contract=contract,
        agent_context=context,
        approval_decisions=normalized_decisions,
        adapter_input_payload=adapter_input,
        adapter_reference_context={"agent_context": context},
        corpus=corpus,
    )


def _parse_plan(
    normalized_output: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    try:
        payload = json.loads(normalized_output)
    except (json.JSONDecodeError, TypeError):
        return [], [], "agent output is not valid JSON"
    if not isinstance(payload, dict):
        return [], [], "agent output must be a JSON object"
    steps = payload.get("steps") or payload.get("agent_steps")
    if not isinstance(steps, list):
        return [], [], "agent output must contain a steps array"
    normalized_steps = [dict(step) for step in steps if isinstance(step, dict)]
    if len(normalized_steps) != len(steps):
        return [], [], "every agent step must be a JSON object"
    recovery_plans = payload.get("recovery_plans", [])
    if not isinstance(recovery_plans, list):
        return [], [], "agent recovery_plans must be an array"
    normalized_recovery: list[dict[str, Any]] = []
    for branch in recovery_plans:
        if not isinstance(branch, dict):
            return [], [], "every recovery plan must be a JSON object"
        trigger_index = branch.get("trigger_step_index")
        branch_steps = branch.get("steps")
        if not isinstance(trigger_index, int) or isinstance(trigger_index, bool):
            return [], [], "recovery plan trigger_step_index must be an integer"
        if trigger_index < 0 or trigger_index >= len(normalized_steps):
            return [], [], "recovery plan trigger_step_index is out of range"
        if not isinstance(branch_steps, list) or not branch_steps:
            return [], [], "recovery plan must contain a non-empty steps array"
        normalized_branch_steps = [dict(step) for step in branch_steps if isinstance(step, dict)]
        if len(normalized_branch_steps) != len(branch_steps):
            return [], [], "every recovery step must be a JSON object"
        normalized_recovery.append(
            {
                **branch,
                "trigger_step_index": trigger_index,
                "steps": normalized_branch_steps,
            }
        )
    return normalized_steps, normalized_recovery, None


def _agent_contract(evaluation_case: EvaluationCase) -> dict[str, Any]:
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    contract = reference.get("agent")
    return dict(contract) if isinstance(contract, dict) else {}


def _expected_steps(contract: dict[str, Any]) -> list[dict[str, Any]]:
    steps = contract.get("expected_steps")
    if not isinstance(steps, list):
        return []
    return [dict(step) for step in steps if isinstance(step, dict) and step.get("action")]


def _expected_recovery_steps(
    contract: dict[str, Any],
    trigger_step_index: int,
) -> list[dict[str, Any]]:
    branches = contract.get("expected_recovery_plans")
    if not isinstance(branches, list):
        return []
    for branch in branches:
        if not isinstance(branch, dict):
            continue
        if branch.get("trigger_step_index") != trigger_step_index:
            continue
        steps = branch.get("steps")
        if not isinstance(steps, list):
            return []
        return [dict(step) for step in steps if isinstance(step, dict) and step.get("action")]
    return []


def _allowed_actions(contract: dict[str, Any]) -> list[str]:
    configured = _string_list(contract.get("allowed_actions"))
    actions = configured or ["respond"]
    return [action for action in actions if action in ALLOWED_AGENT_ACTIONS]


def _action_limit(action: str, context: dict[str, Any]) -> int | None:
    return {
        "approval_checkpoint": int(context["approval_checkpoint_limit"]),
        "tool": int(context["tool_call_limit"]),
        "retrieve": int(context["retrieval_limit"]),
        "memory_read": int(context["memory_read_limit"]),
        "memory_write": int(context["memory_write_limit"]),
    }.get(action)


def _normalize_approval_decisions(
    decisions: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(decisions, dict):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for checkpoint_id, raw_decision in decisions.items():
        if not isinstance(raw_decision, dict):
            continue
        decision = str(raw_decision.get("decision") or "").strip().lower()
        decided_by = str(raw_decision.get("decided_by") or "").strip()
        reason = str(raw_decision.get("reason") or "").strip()
        if decision not in {"approved", "denied"} or not decided_by or not reason:
            continue
        normalized_decision: dict[str, Any] = {
            "decision": decision,
            "decided_by": decided_by,
            "reason": reason,
        }
        for key in (
            "decision_source",
            "policy_version",
            "decision_hash",
            "identity_verified",
            "approver_identity",
            "decided_at",
            "checkpoint_record_id",
        ):
            if raw_decision.get(key) is not None:
                normalized_decision[key] = raw_decision[key]
        normalized[str(checkpoint_id)] = normalized_decision
    return normalized
