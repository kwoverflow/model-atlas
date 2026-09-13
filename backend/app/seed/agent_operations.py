from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    MetricDefinition,
    WorkloadProfile,
)
from app.seed.demo import (
    AGENT_DEPLOYMENT_NAME,
    AGENT_POLICY_NAME,
    AGENT_SUITE_NAME,
    DEPLOYMENT_NAMES,
    WORKLOAD_SLUG,
    seed_demo_data,
)
from app.services.agent_execution import (
    AGENT_RUNTIME_VERSION,
    DEFAULT_OPERATIONAL_MEMORY_REGISTRY,
)
from app.services.deployment_gate.evidence import (
    deployment_configuration_hash,
    stable_hash,
)
from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS,
    DEFAULT_RETRIEVER_DESCRIPTOR,
)

AGENT_SUITE_VERSION = "v1-bounded-agent"
AGENT_POLICY_VERSION = "v1-bounded-agent"
AGENT_DATA_SOURCE = "local_authored"


def _query_arguments(*, include_failure: bool = False) -> dict[str, Any]:
    properties: dict[str, Any] = {"query": {"type": "string"}}
    required = ["query"]
    if include_failure:
        properties["simulate_failure"] = {
            "type": "string",
            "enum": ["transient_once"],
        }
        required.append("simulate_failure")
    return {
        "type": "object",
        "required": required,
        "properties": properties,
        "additionalProperties": False,
    }


def _case(
    *,
    external_case_id: str,
    title: str,
    request: str,
    steps: list[dict[str, Any]],
    expected_steps: list[dict[str, Any]],
    allowed_memory_ids: list[str] | None = None,
    allowed_tools: list[str] | None = None,
    allow_memory_write: bool = False,
    criticality: str = "standard",
) -> dict[str, Any]:
    actions = list(dict.fromkeys(str(step["action"]) for step in expected_steps))
    return {
        "external_case_id": external_case_id,
        "category": "bounded_agent_task",
        "title": title,
        "input_payload_json": {
            "request": request,
            "mock_agent_plan": {"steps": steps},
        },
        "expected_output_json": None,
        "reference_context_json": {
            "agent": {
                "max_steps": len(expected_steps),
                "allowed_actions": actions,
                "allowed_memory_ids": allowed_memory_ids or [],
                "allowed_tools": allowed_tools or [],
                "allow_memory_write": allow_memory_write,
                "max_tool_calls": max(
                    1,
                    sum(1 for step in expected_steps if step["action"] == "tool"),
                ),
                "max_retrievals": max(
                    1,
                    sum(1 for step in expected_steps if step["action"] == "retrieve"),
                ),
                "max_memory_reads": max(
                    1,
                    sum(1 for step in expected_steps if step["action"] == "memory_read"),
                ),
                "max_memory_writes": 1,
                "expected_steps": expected_steps,
            }
        },
        "expected_tool_schema_json": None,
        "tags_json": ["agent", "bounded", *actions, criticality],
        "criticality": criticality,
        "weight": 1.5 if criticality == "critical" else 1.0,
        "is_active": True,
        "data_source": AGENT_DATA_SOURCE,
    }


def _case_payloads() -> list[dict[str, Any]]:
    query_schema = _query_arguments()
    return [
        _case(
            external_case_id="agent-ops-001",
            title="Verify production release guardrails",
            request="Verify whether a production release can proceed.",
            steps=[
                {"action": "memory_read", "memory_id": "memory-release-guardrails"},
                {
                    "action": "retrieve",
                    "query": "approved deployment gate verified evidence release",
                },
                {
                    "action": "tool",
                    "tool_name": "lookup_policy",
                    "arguments": {"query": "production release approval"},
                },
                {
                    "action": "respond",
                    "content": (
                        "Release requires an approved deployment gate and verified evidence."
                    ),
                    "citations": ["ops-release-001"],
                },
            ],
            expected_steps=[
                {"action": "memory_read"},
                {"action": "retrieve", "relevant_chunk_ids": ["ops-release-001"]},
                {
                    "action": "tool",
                    "tool_name": "lookup_policy",
                    "arguments": query_schema,
                },
                {
                    "action": "respond",
                    "required_terms": ["approved deployment gate", "verified evidence"],
                },
            ],
            allowed_memory_ids=["memory-release-guardrails"],
            allowed_tools=["lookup_policy"],
            criticality="critical",
        ),
        _case(
            external_case_id="agent-ops-002",
            title="Coordinate a severity one incident",
            request="Check the severity one response and current incidents.",
            steps=[
                {"action": "memory_read", "memory_id": "memory-incident-response"},
                {
                    "action": "tool",
                    "tool_name": "search_incidents",
                    "arguments": {"query": "severity one runtime"},
                },
                {
                    "action": "respond",
                    "content": "Page immediately and assign an incident commander.",
                },
            ],
            expected_steps=[
                {"action": "memory_read"},
                {
                    "action": "tool",
                    "tool_name": "search_incidents",
                    "arguments": query_schema,
                },
                {
                    "action": "respond",
                    "required_terms": ["incident commander"],
                },
            ],
            allowed_memory_ids=["memory-incident-response"],
            allowed_tools=["search_incidents"],
            criticality="critical",
        ),
        _case(
            external_case_id="agent-ops-003",
            title="Review customer C-008 release request",
            request="Check customer C-008 and its release policy.",
            steps=[
                {"action": "memory_read", "memory_id": "memory-customer-c008"},
                {
                    "action": "tool",
                    "tool_name": "lookup_customer",
                    "arguments": {"query": "Customer C-008"},
                },
                {
                    "action": "tool",
                    "tool_name": "lookup_policy",
                    "arguments": {"query": "C-008 release policy"},
                },
                {
                    "action": "respond",
                    "content": "Obtain account-owner approval and complete policy review.",
                },
            ],
            expected_steps=[
                {"action": "memory_read"},
                {
                    "action": "tool",
                    "tool_name": "lookup_customer",
                    "arguments": query_schema,
                },
                {
                    "action": "tool",
                    "tool_name": "lookup_policy",
                    "arguments": query_schema,
                },
                {
                    "action": "respond",
                    "required_terms": ["account-owner approval", "policy review"],
                },
            ],
            allowed_memory_ids=["memory-customer-c008"],
            allowed_tools=["lookup_customer", "lookup_policy"],
        ),
        _case(
            external_case_id="agent-ops-004",
            title="Confirm rollback ownership and target",
            request="Confirm rollback owner and recovery target.",
            steps=[
                {"action": "memory_read", "memory_id": "memory-rollback-owner"},
                {
                    "action": "retrieve",
                    "query": "rollback owner platform team recovery 30 minutes",
                },
                {
                    "action": "respond",
                    "content": "The platform team owns rollback with a 30 minute target.",
                    "citations": ["ops-rollback-001"],
                },
            ],
            expected_steps=[
                {"action": "memory_read"},
                {"action": "retrieve", "relevant_chunk_ids": ["ops-rollback-001"]},
                {
                    "action": "respond",
                    "required_terms": ["platform team", "30 minute"],
                },
            ],
            allowed_memory_ids=["memory-rollback-owner"],
            criticality="critical",
        ),
        _case(
            external_case_id="agent-ops-005",
            title="Recover an incident search",
            request="Search timeout incidents and recover one transient failure.",
            steps=[
                {
                    "action": "tool",
                    "tool_name": "search_incidents",
                    "arguments": {
                        "query": "runtime timeout",
                        "simulate_failure": "transient_once",
                    },
                },
                {
                    "action": "respond",
                    "content": "The incident search recovered after retry.",
                },
            ],
            expected_steps=[
                {
                    "action": "tool",
                    "tool_name": "search_incidents",
                    "arguments": _query_arguments(include_failure=True),
                    "max_attempts": 2,
                },
                {"action": "respond", "required_terms": ["recovered"]},
            ],
            allowed_tools=["search_incidents"],
            criticality="critical",
        ),
        _case(
            external_case_id="agent-ops-006",
            title="Record a task-local review note",
            request="Record the review outcome only for this task.",
            steps=[
                {
                    "action": "memory_write",
                    "key": "review_outcome",
                    "value": "needs_release_manager_review",
                },
                {
                    "action": "respond",
                    "content": "The review outcome was recorded as task-local and not persisted.",
                },
            ],
            expected_steps=[
                {"action": "memory_write"},
                {
                    "action": "respond",
                    "required_terms": ["task-local", "not persisted"],
                },
            ],
            allow_memory_write=True,
        ),
        _case(
            external_case_id="agent-ops-007",
            title="Create a simulated follow-up from retrieval",
            request="Check critical review policy and create a simulated follow-up.",
            steps=[
                {
                    "action": "retrieve",
                    "query": "critical evaluation cases explicit review production readiness",
                },
                {
                    "action": "tool",
                    "tool_name": "create_ticket",
                    "arguments": {
                        "query": "Review critical evaluation evidence",
                        "priority": "high",
                    },
                },
                {
                    "action": "respond",
                    "content": (
                        "Critical cases require explicit review; a simulated ticket was created."
                    ),
                },
            ],
            expected_steps=[
                {"action": "retrieve", "relevant_chunk_ids": ["ops-review-001"]},
                {
                    "action": "tool",
                    "tool_name": "create_ticket",
                    "arguments": {
                        "type": "object",
                        "required": ["query", "priority"],
                        "properties": {
                            "query": {"type": "string"},
                            "priority": {
                                "type": "string",
                                "enum": ["low", "normal", "high"],
                            },
                        },
                    },
                },
                {
                    "action": "respond",
                    "required_terms": ["explicit review", "simulated ticket"],
                },
            ],
            allowed_tools=["create_ticket"],
        ),
        _case(
            external_case_id="agent-ops-008",
            title="Summarize post-release monitoring",
            request="Retrieve monitoring policy and summarize the task context.",
            steps=[
                {
                    "action": "retrieve",
                    "query": "post-release monitoring error rate latency every five minutes",
                },
                {
                    "action": "tool",
                    "tool_name": "summarize_thread",
                    "arguments": {"query": "Summarize monitoring evidence"},
                },
                {
                    "action": "respond",
                    "content": "Monitor error rate and latency every five minutes after release.",
                },
            ],
            expected_steps=[
                {
                    "action": "retrieve",
                    "relevant_chunk_ids": ["ops-monitoring-001"],
                },
                {
                    "action": "tool",
                    "tool_name": "summarize_thread",
                    "arguments": query_schema,
                },
                {
                    "action": "respond",
                    "required_terms": ["error rate", "latency", "five minutes"],
                },
            ],
            allowed_tools=["summarize_thread"],
        ),
    ]


def _ensure_metric_definitions(db: Session) -> dict[str, MetricDefinition]:
    specs = [
        (
            "agent_task_success_rate",
            "Agent task success rate",
            "reliability",
            "higher_is_better",
            "Completed bounded agent tasks.",
        ),
        (
            "agent_plan_validity_rate",
            "Agent plan validity rate",
            "governance",
            "higher_is_better",
            "Plans that satisfy action, sequence, and limit contracts.",
        ),
        (
            "agent_step_success_rate",
            "Agent step success rate",
            "reliability",
            "higher_is_better",
            "Successfully executed bounded agent steps.",
        ),
        (
            "agent_action_sequence_accuracy",
            "Agent action sequence accuracy",
            "quality",
            "higher_is_better",
            "Plans whose action order matches the case contract.",
        ),
        (
            "agent_policy_violation_rate",
            "Agent policy violation rate",
            "governance",
            "lower_is_better",
            "Agent cases containing an allowlist, sequence, or limit violation.",
        ),
        (
            "agent_final_response_rate",
            "Agent final response rate",
            "quality",
            "higher_is_better",
            "Agent cases producing a validated final response.",
        ),
        (
            "agent_memory_provenance_rate",
            "Agent memory provenance rate",
            "evidence",
            "higher_is_better",
            "Memory actions with versioned registry or task-local provenance.",
        ),
        (
            "agent_tool_retry_recovery_rate",
            "Agent tool retry recovery rate",
            "reliability",
            "higher_is_better",
            "Retried agent tool steps that recover within bounds.",
        ),
    ]
    definitions: dict[str, MetricDefinition] = {}
    for key, display_name, domain, direction, description in specs:
        definition = db.scalar(select(MetricDefinition).where(MetricDefinition.key == key))
        if definition is None:
            definition = MetricDefinition(
                key=key,
                display_name=display_name,
                domain=domain,
                aggregation="rate",
                direction=direction,
                unit=None,
                description=description,
                calculation_version="agent-execution-metrics-v1",
                is_active=True,
            )
            db.add(definition)
            db.flush()
        definitions[key] = definition
    return definitions


def _create_configuration(
    db: Session,
    workload: WorkloadProfile,
) -> DeploymentConfiguration:
    base_configuration = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.name == DEPLOYMENT_NAMES[0]
        )
    )
    if base_configuration is None:
        raise RuntimeError("The base demo deployment configuration is required.")
    payload = {
        "name": AGENT_DEPLOYMENT_NAME,
        "workload_profile_id": workload.id,
        "hardware_profile_id": base_configuration.hardware_profile_id,
        "model_artifact_id": base_configuration.model_artifact_id,
        "runtime_name": "bounded-agent-runtime",
        "runtime_version": AGENT_RUNTIME_VERSION,
        "runtime_config_json": dict(base_configuration.runtime_config_json or {}),
        "context_length": base_configuration.context_length,
        "generation_config_json": dict(base_configuration.generation_config_json or {}),
        "prompt_bundle_json": {
            "bundle": "model-atlas-bounded-agent",
            "version": "agent-v1",
        },
        "output_schema_version": "agent-plan-v1",
        "tool_schema_version": "local-tool-registry-v1",
        "retrieval_config_json": {
            "corpus_id": DEFAULT_RAG_CORPUS.corpus_id,
            "corpus_version": DEFAULT_RAG_CORPUS.corpus_version,
            "corpus_hash": DEFAULT_RAG_CORPUS.corpus_hash,
            "retriever_id": DEFAULT_RETRIEVER_DESCRIPTOR.retriever_id,
            "retriever_version": DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version,
            "top_k": 3,
            "min_score": 0.05,
        },
        "concurrency_target": 1,
        "status": "ready",
        "notes": "Locally authored Sprint 5A bounded agent operations fixture.",
    }
    configuration = DeploymentConfiguration(
        **payload,
        configuration_hash=deployment_configuration_hash(payload),
    )
    db.add(configuration)
    db.flush()
    return configuration


def seed_agent_operations_pack(db: Session) -> dict[str, Any]:
    workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    if workload is None:
        seed_demo_data(db)
        workload = db.scalar(
            select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG)
        )
    if workload is None:
        raise RuntimeError("The demo workload is required before agent-pack seeding.")

    existing_suite = db.scalar(
        select(EvaluationSuite).where(EvaluationSuite.name == AGENT_SUITE_NAME)
    )
    existing_policy = db.scalar(
        select(AcceptancePolicy).where(AcceptancePolicy.name == AGENT_POLICY_NAME)
    )
    existing_configuration = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.name == AGENT_DEPLOYMENT_NAME
        )
    )
    if existing_suite and existing_policy and existing_configuration:
        case_count = len(
            list(
                db.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.evaluation_suite_id == existing_suite.id
                    )
                ).all()
            )
        )
        return {
            "deployment_configuration_id": str(existing_configuration.id),
            "evaluation_suite_id": str(existing_suite.id),
            "acceptance_policy_id": str(existing_policy.id),
            "case_count": case_count,
            "created": False,
        }
    if existing_suite or existing_policy or existing_configuration:
        raise RuntimeError(
            "Agent Operations seed is partially present. Reset the demo seed, then retry."
        )

    metric_definitions = _ensure_metric_definitions(db)
    case_payloads = _case_payloads()
    suite_payload = {
        "workload_profile_id": workload.id,
        "name": AGENT_SUITE_NAME,
        "version_label": AGENT_SUITE_VERSION,
        "description": (
            "Bounded operational-agent cases covering memory, retrieval, registered tools, retry "
            "recovery, task-local writes, and final response validation."
        ),
        "status": "active",
        "dataset_source": AGENT_DATA_SOURCE,
        "is_synthetic": False,
    }
    suite = EvaluationSuite(
        **suite_payload,
        suite_hash=stable_hash({**suite_payload, "case_contracts": case_payloads}),
    )
    db.add(suite)
    db.flush()
    db.add_all(EvaluationCase(evaluation_suite_id=suite.id, **case) for case in case_payloads)

    policy_payload = {
        "workload_profile_id": workload.id,
        "name": AGENT_POLICY_NAME,
        "version_label": AGENT_POLICY_VERSION,
        "description": (
            "Blocks agent release on invalid plans, failed steps, sequence mismatch, policy "
            "violations, missing responses, or unproven memory actions."
        ),
        "allow_conditional": True,
        "is_active": True,
    }
    policy = AcceptancePolicy(
        **policy_payload,
        policy_hash=stable_hash(policy_payload),
    )
    db.add(policy)
    db.flush()
    rule_specs = [
        ("agent_task_success_rate", "Every agent task must succeed", "gte", 1.0, 8, "blocker"),
        ("agent_plan_validity_rate", "Every plan must be valid", "gte", 1.0, 8, "blocker"),
        ("agent_step_success_rate", "Every agent step must succeed", "gte", 1.0, 20, "blocker"),
        (
            "agent_action_sequence_accuracy",
            "Every action sequence must match",
            "gte",
            1.0,
            8,
            "blocker",
        ),
        (
            "agent_policy_violation_rate",
            "Agent policy violations are blocked",
            "lte",
            0.0,
            8,
            "blocker",
        ),
        (
            "agent_final_response_rate",
            "Every task must return a final response",
            "gte",
            1.0,
            8,
            "blocker",
        ),
        (
            "agent_memory_provenance_rate",
            "Every memory action needs provenance",
            "gte",
            1.0,
            5,
            "blocker",
        ),
        (
            "agent_tool_retry_recovery_rate",
            "Retryable agent tools should recover",
            "gte",
            1.0,
            1,
            "warning",
        ),
    ]
    db.add_all(
        AcceptancePolicyRule(
            acceptance_policy_id=policy.id,
            metric_definition_id=metric_definitions[metric_key].id,
            rule_name=rule_name,
            operator=operator,
            threshold_value=threshold,
            severity=severity,
            minimum_sample_size=minimum_sample_size,
            required=True,
            enabled=True,
            message_on_fail=f"{rule_name}. Inspect the bounded agent trace.",
        )
        for (
            metric_key,
            rule_name,
            operator,
            threshold,
            minimum_sample_size,
            severity,
        ) in rule_specs
    )
    configuration = _create_configuration(db, workload)
    db.commit()
    return {
        "deployment_configuration_id": str(configuration.id),
        "deployment_configuration_name": configuration.name,
        "evaluation_suite_id": str(suite.id),
        "evaluation_suite_name": suite.name,
        "evaluation_suite_version": suite.version_label,
        "acceptance_policy_id": str(policy.id),
        "acceptance_policy_name": policy.name,
        "case_count": len(case_payloads),
        "critical_case_count": sum(
            1 for case in case_payloads if case["criticality"] == "critical"
        ),
        "memory_record_count": len(DEFAULT_OPERATIONAL_MEMORY_REGISTRY.records),
        "created": True,
    }


def main() -> None:
    with SessionLocal() as db:
        summary = seed_agent_operations_pack(db)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
