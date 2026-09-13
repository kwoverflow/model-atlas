from __future__ import annotations

from typing import Any

from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS,
    DEFAULT_RETRIEVER_DESCRIPTOR,
)
from app.services.tool_execution import (
    DEFAULT_TOOL_REGISTRY,
)

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
    MAX_AGENT_APPROVAL_CHECKPOINTS,
    MAX_AGENT_LIVE_REPLAN_CALLS,
    MAX_AGENT_MEMORY_READS,
    MAX_AGENT_MEMORY_WRITES,
    MAX_AGENT_RECOVERY_BRANCHES,
    MAX_AGENT_RECOVERY_STEPS,
    MAX_AGENT_REPLANS,
    MAX_AGENT_RETRIEVALS,
    MAX_AGENT_STEPS,
    MAX_AGENT_TOOL_CALLS,
)


def agent_runtime_descriptor() -> dict[str, Any]:
    return {
        "runtime_id": "model_atlas_bounded_agent",
        "runtime_version": AGENT_RUNTIME_VERSION,
        "trace_schema_version": AGENT_EXECUTION_TRACE_VERSION,
        "context_schema_version": AGENT_CONTEXT_VERSION,
        "observation_schema_version": AGENT_OBSERVATION_VERSION,
        "recovery_policy_version": AGENT_RECOVERY_POLICY_VERSION,
        "approval_policy_version": AGENT_APPROVAL_POLICY_VERSION,
        "allowed_actions": sorted(ALLOWED_AGENT_ACTIONS),
        "limits": {
            "max_steps": MAX_AGENT_STEPS,
            "max_execution_steps": MAX_AGENT_STEPS + MAX_AGENT_RECOVERY_STEPS,
            "max_replans": MAX_AGENT_REPLANS,
            "max_live_replan_model_calls": MAX_AGENT_LIVE_REPLAN_CALLS,
            "max_recovery_steps": MAX_AGENT_RECOVERY_STEPS,
            "max_recovery_branches": MAX_AGENT_RECOVERY_BRANCHES,
            "max_approval_checkpoints": MAX_AGENT_APPROVAL_CHECKPOINTS,
            "max_tool_calls": MAX_AGENT_TOOL_CALLS,
            "max_retrievals": MAX_AGENT_RETRIEVALS,
            "max_memory_reads": MAX_AGENT_MEMORY_READS,
            "max_memory_writes": MAX_AGENT_MEMORY_WRITES,
        },
        "tool_registry_version": DEFAULT_TOOL_REGISTRY.registry_version,
        "memory_registry_version": DEFAULT_OPERATIONAL_MEMORY_REGISTRY.registry_version,
        "corpus_version": DEFAULT_RAG_CORPUS.corpus_version,
        "retriever_version": DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version,
        "memory_write_mode": "task_local_simulated",
        "approval_decision_mode": "external_request_only",
        "live_replan_callback_version": AGENT_LIVE_REPLAN_VERSION,
    }
