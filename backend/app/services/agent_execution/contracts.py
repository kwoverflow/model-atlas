from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from app.services.rag_evaluation import (
    RagCorpus,
)

AGENT_EXECUTION_TRACE_VERSION = "agent-execution-trace-v2"


AGENT_EXECUTION_SUMMARY_VERSION = "agent-execution-summary-v2"


AGENT_CONTEXT_VERSION = "agent-context-v2"


AGENT_RUNTIME_VERSION = "bounded-agent-runtime-v2"


AGENT_OBSERVATION_VERSION = "agent-observation-v1"


AGENT_RECOVERY_POLICY_VERSION = "bounded-recovery-policy-v1"


AGENT_APPROVAL_POLICY_VERSION = "human-checkpoint-policy-v1"


AGENT_LIVE_REPLAN_VERSION = "agent-live-replan-callback-v1"


OPERATIONAL_MEMORY_REGISTRY_VERSION = "operational-memory-registry-v1"


SUPPORTED_AGENT_TRACE_VERSIONS = frozenset(
    {"agent-execution-trace-v1", AGENT_EXECUTION_TRACE_VERSION}
)


MAX_AGENT_STEPS = 6


MAX_AGENT_REPLANS = 1


MAX_AGENT_LIVE_REPLAN_CALLS = 1


MAX_AGENT_RECOVERY_STEPS = 2


MAX_AGENT_RECOVERY_BRANCHES = 3


MAX_AGENT_APPROVAL_CHECKPOINTS = 2


MAX_AGENT_TOOL_CALLS = 3


MAX_AGENT_RETRIEVALS = 2


MAX_AGENT_MEMORY_READS = 2


MAX_AGENT_MEMORY_WRITES = 1


ALLOWED_AGENT_ACTIONS = frozenset(
    {
        "approval_checkpoint",
        "memory_read",
        "retrieve",
        "tool",
        "memory_write",
        "respond",
    }
)


@dataclass(frozen=True)
class OperationalMemoryRecord:
    memory_id: str
    memory_version: str
    title: str
    content: str
    tags: tuple[str, ...]
    data_classification: str = "internal_fixture"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()

    def descriptor(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "memory_version": self.memory_version,
            "title": self.title,
            "tags": list(self.tags),
            "data_classification": self.data_classification,
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class OperationalMemoryRegistry:
    records: dict[str, OperationalMemoryRecord]
    registry_id: str = "model_atlas_operational_memory"
    registry_version: str = OPERATIONAL_MEMORY_REGISTRY_VERSION

    def get(self, memory_id: str) -> OperationalMemoryRecord | None:
        return self.records.get(memory_id)

    def descriptor(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "record_count": len(self.records),
            "records": [self.records[memory_id].descriptor() for memory_id in sorted(self.records)],
        }


@dataclass(frozen=True)
class AgentPreparation:
    contract: dict[str, Any]
    agent_context: dict[str, Any]
    approval_decisions: dict[str, dict[str, Any]]
    adapter_input_payload: dict[str, Any]
    adapter_reference_context: dict[str, Any]
    corpus: RagCorpus


@dataclass(frozen=True)
class AgentLiveReplanRequest:
    schema_version: str
    external_case_id: str
    trigger_step_index: int
    trigger_error_type: str
    observation: dict[str, Any] | None
    expected_recovery_steps: list[dict[str, Any]]
    prior_outputs: list[dict[str, Any]]
    recovery_step_limit: int


@dataclass(frozen=True)
class AgentLiveReplanResponse:
    steps: list[dict[str, Any]]
    provider_id: str
    provider_version: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    model_call_latency_ms: float
    estimated_cost_usd: float

    def provenance(self, *, callback_duration_ms: float) -> dict[str, Any]:
        response_payload = {
            "steps": self.steps,
            "provider_id": self.provider_id,
            "provider_version": self.provider_version,
            "model_name": self.model_name,
            "prompt_tokens": max(0, self.prompt_tokens),
            "completion_tokens": max(0, self.completion_tokens),
            "model_call_latency_ms": max(0.0, self.model_call_latency_ms),
            "estimated_cost_usd": max(0.0, self.estimated_cost_usd),
        }
        semantic_response_payload = {
            key: value for key, value in response_payload.items() if key != "model_call_latency_ms"
        }
        return {
            "schema_version": AGENT_LIVE_REPLAN_VERSION,
            **response_payload,
            "callback_duration_ms": round(max(0.0, callback_duration_ms), 3),
            "response_hash": hashlib.sha256(
                json.dumps(
                    semantic_response_payload,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        }


class AgentLiveReplanCallback(Protocol):
    def __call__(
        self,
        request: AgentLiveReplanRequest,
    ) -> AgentLiveReplanResponse | None: ...


@dataclass(frozen=True)
class AgentExecutionTrace:
    schema_version: str
    context_version: str
    runtime_version: str
    observation_schema_version: str
    recovery_policy_version: str
    approval_policy_version: str
    memory_registry_version: str
    tool_registry_version: str
    corpus_version: str
    retriever_version: str
    external_case_id: str
    parse_valid: bool
    parse_error: str | None
    plan_valid: bool
    status: str
    successful: bool
    step_limit: int
    execution_step_limit: int
    replan_limit: int
    step_count: int
    expected_action_sequence: list[str]
    actual_action_sequence: list[str]
    sequence_match: bool
    successful_step_count: int
    failed_step_count: int
    step_success_rate: float | None
    tool_call_count: int
    retrieval_count: int
    memory_read_count: int
    memory_write_count: int
    retried_tool_count: int
    recovered_tool_count: int
    policy_violation_count: int
    final_response_present: bool
    memory_provenance_count: int
    memory_action_count: int
    observation_count: int
    replan_count: int
    successful_replan_count: int
    recovery_step_count: int
    successful_recovery_step_count: int
    recovery_sequence_match: bool | None
    unrecovered_failure_count: int
    approval_checkpoint_count: int
    approved_checkpoint_count: int
    denied_checkpoint_count: int
    pending_checkpoint_count: int
    approval_provenance_count: int
    halt_reason: str | None
    total_duration_ms: float
    live_replan_count: int = 0
    live_replan_model_call_count: int = 0
    live_replan_prompt_tokens: int = 0
    live_replan_completion_tokens: int = 0
    live_replan_latency_ms: float = 0.0
    live_replan_estimated_cost_usd: float = 0.0
    replans: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _build_default_memory_registry() -> OperationalMemoryRegistry:
    records = [
        OperationalMemoryRecord(
            memory_id="memory-release-guardrails",
            memory_version="release-guardrails-v1",
            title="Release guardrails",
            content=(
                "Production release requires an approved deployment gate, verified evidence, "
                "and an authorized release decision."
            ),
            tags=("release", "governance"),
        ),
        OperationalMemoryRecord(
            memory_id="memory-incident-response",
            memory_version="incident-response-v1",
            title="Incident response preference",
            content=(
                "Severity one runtime incidents require immediate paging, an incident commander, "
                "and a rollback readiness check."
            ),
            tags=("incident", "runtime"),
        ),
        OperationalMemoryRecord(
            memory_id="memory-customer-c008",
            memory_version="customer-c008-v1",
            title="Customer C-008 operating note",
            content=(
                "Customer C-008 changes require account-owner approval and a policy review before "
                "production release."
            ),
            tags=("customer", "approval"),
        ),
        OperationalMemoryRecord(
            memory_id="memory-rollback-owner",
            memory_version="rollback-owner-v1",
            title="Rollback ownership",
            content="The platform team owns rollback and targets recovery within 30 minutes.",
            tags=("rollback", "operations"),
        ),
    ]
    return OperationalMemoryRegistry(records={record.memory_id: record for record in records})


DEFAULT_OPERATIONAL_MEMORY_REGISTRY = _build_default_memory_registry()
