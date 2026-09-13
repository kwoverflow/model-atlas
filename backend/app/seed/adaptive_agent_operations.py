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
    ADAPTIVE_AGENT_DEPLOYMENT_NAME,
    ADAPTIVE_AGENT_POLICY_NAME,
    ADAPTIVE_AGENT_SUITE_NAME,
    DEPLOYMENT_NAMES,
    WORKLOAD_SLUG,
    seed_demo_data,
)
from app.services.agent_execution import AGENT_RUNTIME_VERSION
from app.services.deployment_gate.evidence import (
    deployment_configuration_hash,
    stable_hash,
)
from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS,
    DEFAULT_RETRIEVER_DESCRIPTOR,
)

ADAPTIVE_AGENT_SUITE_VERSION = "v1-agent-observation-recovery"
ADAPTIVE_AGENT_POLICY_VERSION = "v1-agent-observation-recovery"
ADAPTIVE_AGENT_DATA_SOURCE = "local_authored"


def _query_schema(*, failure_mode: bool = False) -> dict[str, Any]:
    properties: dict[str, Any] = {"query": {"type": "string"}}
    required = ["query"]
    if failure_mode:
        properties["simulate_failure"] = {
            "type": "string",
            "enum": ["permanent"],
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
    plan: dict[str, Any],
    contract: dict[str, Any],
    criticality: str = "critical",
) -> dict[str, Any]:
    actions = [
        str(step.get("action"))
        for step in contract.get("expected_steps", [])
        if isinstance(step, dict) and step.get("action")
    ]
    return {
        "external_case_id": external_case_id,
        "category": "adaptive_agent_task",
        "title": title,
        "input_payload_json": {
            "request": request,
            "mock_agent_plan": plan,
        },
        "expected_output_json": None,
        "reference_context_json": {"agent": contract},
        "expected_tool_schema_json": None,
        "tags_json": [
            "agent",
            "adaptive",
            "approval",
            "recovery",
            *list(dict.fromkeys(actions)),
            criticality,
        ],
        "criticality": criticality,
        "weight": 1.5 if criticality == "critical" else 1.0,
        "is_active": True,
        "data_source": ADAPTIVE_AGENT_DATA_SOURCE,
    }


def _case_payloads() -> list[dict[str, Any]]:
    query_schema = _query_schema()
    failure_query_schema = _query_schema(failure_mode=True)
    return [
        _case(
            external_case_id="agent-adaptive-001",
            title="Approve a guarded release policy lookup",
            request="Validate a production policy change after human approval.",
            plan={
                "steps": [
                    {
                        "action": "approval_checkpoint",
                        "checkpoint_id": "release-change",
                        "reason": "Production release policy access",
                    },
                    {
                        "action": "tool",
                        "tool_name": "lookup_policy",
                        "arguments": {"query": "production release approval"},
                        "requires_approval": "release-change",
                    },
                    {
                        "action": "respond",
                        "content": "The release policy lookup was approved and completed.",
                    },
                ]
            },
            contract={
                "max_steps": 3,
                "max_approval_checkpoints": 1,
                "max_tool_calls": 1,
                "allowed_actions": ["approval_checkpoint", "tool", "respond"],
                "allowed_checkpoint_ids": ["release-change"],
                "allowed_tools": ["lookup_policy"],
                "expected_steps": [
                    {
                        "action": "approval_checkpoint",
                        "checkpoint_id": "release-change",
                    },
                    {
                        "action": "tool",
                        "tool_name": "lookup_policy",
                        "requires_approval": "release-change",
                        "arguments": query_schema,
                    },
                    {
                        "action": "respond",
                        "required_terms": ["approved", "completed"],
                    },
                ],
            },
        ),
        _case(
            external_case_id="agent-adaptive-002",
            title="Approve a task-local operational note",
            request="Record an approved task-local release note.",
            plan={
                "steps": [
                    {
                        "action": "approval_checkpoint",
                        "checkpoint_id": "task-memory-write",
                        "reason": "Task-local operational note",
                    },
                    {
                        "action": "memory_write",
                        "key": "release-note",
                        "value": "Approved during CAB review",
                        "requires_approval": "task-memory-write",
                    },
                    {
                        "action": "respond",
                        "content": "The approved task-local note was recorded without persistence.",
                    },
                ]
            },
            contract={
                "max_steps": 3,
                "max_approval_checkpoints": 1,
                "max_memory_writes": 1,
                "allowed_actions": [
                    "approval_checkpoint",
                    "memory_write",
                    "respond",
                ],
                "allowed_checkpoint_ids": ["task-memory-write"],
                "allow_memory_write": True,
                "expected_steps": [
                    {
                        "action": "approval_checkpoint",
                        "checkpoint_id": "task-memory-write",
                    },
                    {
                        "action": "memory_write",
                        "requires_approval": "task-memory-write",
                    },
                    {
                        "action": "respond",
                        "required_terms": ["approved", "without persistence"],
                    },
                ],
            },
        ),
        _case(
            external_case_id="agent-adaptive-003",
            title="Recover a failed incident search with a policy fallback",
            request="Recover safely when the primary incident search fails.",
            plan={
                "steps": [
                    {
                        "action": "tool",
                        "tool_name": "search_incidents",
                        "arguments": {
                            "query": "release timeout",
                            "simulate_failure": "permanent",
                        },
                    },
                    {
                        "action": "respond",
                        "content": "The bounded fallback recovered the incident request.",
                    },
                ],
                "recovery_plans": [
                    {
                        "trigger_step_index": 0,
                        "on_error_types": ["permanent_tool_error"],
                        "strategy": "fallback_tool",
                        "steps": [
                            {
                                "action": "tool",
                                "tool_name": "lookup_policy",
                                "arguments": {
                                    "query": "incident search fallback policy"
                                },
                            }
                        ],
                    }
                ],
            },
            contract={
                "max_steps": 2,
                "allow_replanning": True,
                "max_replans": 1,
                "max_recovery_steps": 1,
                "max_tool_calls": 2,
                "allowed_actions": ["tool", "respond"],
                "allowed_tools": ["search_incidents", "lookup_policy"],
                "expected_steps": [
                    {
                        "action": "tool",
                        "tool_name": "search_incidents",
                        "arguments": failure_query_schema,
                        "max_attempts": 1,
                    },
                    {
                        "action": "respond",
                        "required_terms": ["fallback", "recovered"],
                    },
                ],
                "expected_recovery_plans": [
                    {
                        "trigger_step_index": 0,
                        "steps": [
                            {
                                "action": "tool",
                                "tool_name": "lookup_policy",
                                "arguments": query_schema,
                            }
                        ],
                    }
                ],
            },
        ),
        _case(
            external_case_id="agent-adaptive-004",
            title="Recover an empty retrieval with a bounded query",
            request="Recover release evidence after an empty retrieval.",
            plan={
                "steps": [
                    {"action": "retrieve", "query": ""},
                    {
                        "action": "respond",
                        "content": "The recovery query found approved deployment gate evidence.",
                        "citations": ["ops-release-001"],
                    },
                ],
                "recovery_plans": [
                    {
                        "trigger_step_index": 0,
                        "on_error_types": ["agent_retrieval_failed"],
                        "strategy": "refine_query",
                        "steps": [
                            {
                                "action": "retrieve",
                                "query": (
                                    "approved deployment gate verified evidence release"
                                ),
                            }
                        ],
                    }
                ],
            },
            contract={
                "max_steps": 2,
                "allow_replanning": True,
                "max_replans": 1,
                "max_recovery_steps": 1,
                "max_retrievals": 2,
                "allowed_actions": ["retrieve", "respond"],
                "expected_steps": [
                    {
                        "action": "retrieve",
                        "relevant_chunk_ids": ["ops-release-001"],
                    },
                    {
                        "action": "respond",
                        "required_terms": ["approved deployment gate", "evidence"],
                    },
                ],
                "expected_recovery_plans": [
                    {
                        "trigger_step_index": 0,
                        "steps": [
                            {
                                "action": "retrieve",
                                "relevant_chunk_ids": ["ops-release-001"],
                            }
                        ],
                    }
                ],
            },
        ),
        _case(
            external_case_id="agent-adaptive-005",
            title="Preserve observations on a standard memory task",
            request="Read rollback ownership and return a bounded answer.",
            plan={
                "steps": [
                    {
                        "action": "memory_read",
                        "memory_id": "memory-rollback-owner",
                    },
                    {
                        "action": "respond",
                        "content": "The platform team owns rollback within 30 minutes.",
                    },
                ]
            },
            contract={
                "max_steps": 2,
                "max_memory_reads": 1,
                "allowed_actions": ["memory_read", "respond"],
                "allowed_memory_ids": ["memory-rollback-owner"],
                "expected_steps": [
                    {
                        "action": "memory_read",
                        "memory_id": "memory-rollback-owner",
                    },
                    {
                        "action": "respond",
                        "required_terms": ["platform team", "30 minutes"],
                    },
                ],
            },
            criticality="standard",
        ),
    ]


def _ensure_metric_definitions(db: Session) -> dict[str, MetricDefinition]:
    specs = [
        (
            "agent_task_success_rate",
            "Agent task success rate",
            "reliability",
            "higher_is_better",
            "Completed bounded agent tasks, including recovered tasks.",
        ),
        (
            "agent_plan_validity_rate",
            "Agent plan validity rate",
            "governance",
            "higher_is_better",
            "Plans satisfying base and recovery sequence contracts.",
        ),
        (
            "agent_step_success_rate",
            "Agent raw step success rate",
            "reliability",
            "higher_is_better",
            "Raw execution success before recovery credit is applied.",
        ),
        (
            "agent_action_sequence_accuracy",
            "Agent action sequence accuracy",
            "quality",
            "higher_is_better",
            "Base action sequences matching the evaluation contract.",
        ),
        (
            "agent_policy_violation_rate",
            "Agent policy violation rate",
            "governance",
            "lower_is_better",
            "Agent cases containing an allowlist, approval, sequence, or limit violation.",
        ),
        (
            "agent_final_response_rate",
            "Agent final response rate",
            "quality",
            "higher_is_better",
            "Agent cases producing a validated final response.",
        ),
        (
            "agent_replan_success_rate",
            "Agent replan success rate",
            "reliability",
            "higher_is_better",
            "Observation-triggered replans that recover within the configured budget.",
        ),
        (
            "agent_recovery_step_success_rate",
            "Agent recovery step success rate",
            "reliability",
            "higher_is_better",
            "Recovery branch steps that execute successfully.",
        ),
        (
            "agent_approval_compliance_rate",
            "Agent approval compliance rate",
            "governance",
            "higher_is_better",
            "Approval checkpoints receiving an explicit approved decision.",
        ),
        (
            "agent_approval_provenance_rate",
            "Agent approval provenance rate",
            "evidence",
            "higher_is_better",
            "Approval checkpoints carrying actor, reason, policy, and decision hash.",
        ),
        (
            "agent_pending_approval_rate",
            "Agent pending approval rate",
            "governance",
            "lower_is_better",
            "Approval checkpoints with no external human decision.",
        ),
        (
            "agent_observation_coverage_rate",
            "Agent observation coverage rate",
            "evidence",
            "higher_is_better",
            "Executed Agent steps containing a versioned observation envelope.",
        ),
        (
            "agent_unrecovered_failure_rate",
            "Agent unrecovered failure rate",
            "reliability",
            "lower_is_better",
            "Agent cases retaining an execution failure after bounded recovery.",
        ),
    ]
    definitions: dict[str, MetricDefinition] = {}
    for key, display_name, domain, direction, description in specs:
        definition = db.scalar(
            select(MetricDefinition).where(MetricDefinition.key == key)
        )
        if definition is None:
            definition = MetricDefinition(
                key=key,
                display_name=display_name,
                domain=domain,
                aggregation="rate",
                direction=direction,
                unit=None,
                description=description,
                calculation_version="agent-execution-metrics-v2",
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
        "name": ADAPTIVE_AGENT_DEPLOYMENT_NAME,
        "workload_profile_id": workload.id,
        "hardware_profile_id": base_configuration.hardware_profile_id,
        "model_artifact_id": base_configuration.model_artifact_id,
        "runtime_name": "bounded-agent-runtime",
        "runtime_version": AGENT_RUNTIME_VERSION,
        "runtime_config_json": dict(base_configuration.runtime_config_json or {}),
        "context_length": base_configuration.context_length,
        "generation_config_json": dict(
            base_configuration.generation_config_json or {}
        ),
        "prompt_bundle_json": {
            "bundle": "model-atlas-adaptive-agent",
            "version": "agent-v2",
        },
        "output_schema_version": "agent-plan-v2",
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
        "notes": "Locally authored Sprint 5B approval and recovery fixture.",
    }
    configuration = DeploymentConfiguration(
        **payload,
        configuration_hash=deployment_configuration_hash(payload),
    )
    db.add(configuration)
    db.flush()
    return configuration


def seed_adaptive_agent_operations_pack(db: Session) -> dict[str, Any]:
    workload = db.scalar(
        select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG)
    )
    if workload is None:
        seed_demo_data(db)
        workload = db.scalar(
            select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG)
        )
    if workload is None:
        raise RuntimeError("The demo workload is required before adaptive Agent seeding.")

    existing_suite = db.scalar(
        select(EvaluationSuite).where(
            EvaluationSuite.name == ADAPTIVE_AGENT_SUITE_NAME
        )
    )
    existing_policy = db.scalar(
        select(AcceptancePolicy).where(
            AcceptancePolicy.name == ADAPTIVE_AGENT_POLICY_NAME
        )
    )
    existing_configuration = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.name == ADAPTIVE_AGENT_DEPLOYMENT_NAME
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
            "Adaptive Agent seed is partially present. Reset the demo seed, then retry."
        )

    metric_definitions = _ensure_metric_definitions(db)
    cases = _case_payloads()
    suite_payload = {
        "workload_profile_id": workload.id,
        "name": ADAPTIVE_AGENT_SUITE_NAME,
        "version_label": ADAPTIVE_AGENT_SUITE_VERSION,
        "description": (
            "Bounded Agent cases covering external human approval, guarded actions, versioned "
            "observations, one-shot replanning, and recovery branches."
        ),
        "status": "active",
        "dataset_source": ADAPTIVE_AGENT_DATA_SOURCE,
        "is_synthetic": False,
    }
    suite = EvaluationSuite(
        **suite_payload,
        suite_hash=stable_hash({**suite_payload, "case_contracts": cases}),
    )
    db.add(suite)
    db.flush()
    db.add_all(
        EvaluationCase(evaluation_suite_id=suite.id, **case) for case in cases
    )

    policy_payload = {
        "workload_profile_id": workload.id,
        "name": ADAPTIVE_AGENT_POLICY_NAME,
        "version_label": ADAPTIVE_AGENT_POLICY_VERSION,
        "description": (
            "Blocks adaptive Agent release on invalid plans, approval gaps, missing provenance, "
            "unrecovered failures, or out-of-policy replanning."
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
        ("agent_task_success_rate", "Every adaptive task must succeed", "gte", 1.0, 5),
        ("agent_plan_validity_rate", "Every adaptive plan must be valid", "gte", 1.0, 5),
        ("agent_step_success_rate", "Raw step success must remain bounded", "gte", 0.8, 10),
        (
            "agent_action_sequence_accuracy",
            "Every base action sequence must match",
            "gte",
            1.0,
            5,
        ),
        (
            "agent_policy_violation_rate",
            "Adaptive Agent policy violations are blocked",
            "lte",
            0.0,
            5,
        ),
        ("agent_final_response_rate", "Every task must respond", "gte", 1.0, 5),
        ("agent_replan_success_rate", "Every triggered replan must recover", "gte", 1.0, 2),
        (
            "agent_recovery_step_success_rate",
            "Every recovery step must succeed",
            "gte",
            1.0,
            2,
        ),
        (
            "agent_approval_compliance_rate",
            "Every checkpoint must be approved",
            "gte",
            1.0,
            2,
        ),
        (
            "agent_approval_provenance_rate",
            "Every checkpoint needs decision provenance",
            "gte",
            1.0,
            2,
        ),
        (
            "agent_pending_approval_rate",
            "Pending approvals block release",
            "lte",
            0.0,
            2,
        ),
        (
            "agent_observation_coverage_rate",
            "Every executed step needs an observation",
            "gte",
            1.0,
            10,
        ),
        (
            "agent_unrecovered_failure_rate",
            "Unrecovered Agent failures are blocked",
            "lte",
            0.0,
            5,
        ),
    ]
    db.add_all(
        AcceptancePolicyRule(
            acceptance_policy_id=policy.id,
            metric_definition_id=metric_definitions[metric_key].id,
            rule_name=rule_name,
            operator=operator,
            threshold_value=threshold,
            severity="blocker",
            minimum_sample_size=minimum_sample_size,
            required=True,
            enabled=True,
            message_on_fail=(
                f"{rule_name}. Inspect approval, observation, and recovery evidence."
            ),
        )
        for metric_key, rule_name, operator, threshold, minimum_sample_size in rule_specs
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
        "case_count": len(cases),
        "critical_case_count": sum(
            1 for case in cases if case["criticality"] == "critical"
        ),
        "created": True,
    }


def main() -> None:
    with SessionLocal() as db:
        summary = seed_adaptive_agent_operations_pack(db)
        print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
