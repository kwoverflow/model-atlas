from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    EvaluationCase,
    EvaluationSuite,
    MetricDefinition,
    WorkloadProfile,
)
from app.seed.demo import (
    TOOL_POLICY_NAME,
    TOOL_SUITE_NAME,
    WORKLOAD_SLUG,
    seed_demo_data,
)
from app.services.deployment_gate.evidence import stable_hash

TOOL_SUITE_VERSION = "v1-executable-tools"
TOOL_POLICY_VERSION = "v1-executable-tools"
TOOL_DATA_SOURCE = "local_authored"


def _query_schema(*, include_failure_mode: bool = False) -> dict[str, Any]:
    properties: dict[str, Any] = {"query": {"type": "string"}}
    if include_failure_mode:
        properties["simulate_failure"] = {
            "type": "string",
            "enum": ["transient_once", "permanent"],
        }
    return {
        "type": "object",
        "required": ["query"],
        "properties": properties,
        "additionalProperties": False,
    }


def _single_case(
    *,
    external_case_id: str,
    title: str,
    tool_name: str,
    request: str,
    criticality: str,
    example_arguments: dict[str, Any] | None = None,
    argument_schema: dict[str, Any] | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    expected_schema: dict[str, Any] = {
        "tool_name": tool_name,
        "arguments": argument_schema or _query_schema(),
        "example_arguments": example_arguments or {"query": request},
    }
    if max_attempts is not None:
        expected_schema["max_attempts"] = max_attempts
    return {
        "external_case_id": external_case_id,
        "category": "executable_tool_calling",
        "title": title,
        "input_payload_json": {
            "request": request,
            "available_tools": [
                "lookup_internal_document",
                "lookup_policy",
                "search_incidents",
                "create_ticket",
                "lookup_customer",
                "summarize_thread",
            ],
        },
        "expected_output_json": None,
        "reference_context_json": {"expected_tool": tool_name},
        "expected_tool_schema_json": expected_schema,
        "tags_json": ["tool", "executable", tool_name],
        "criticality": criticality,
        "weight": 1.5 if criticality == "critical" else 1.0,
        "is_active": True,
        "data_source": TOOL_DATA_SOURCE,
    }


def _case_payloads() -> list[dict[str, Any]]:
    ticket_schema = {
        "type": "object",
        "required": ["query", "priority"],
        "properties": {
            "query": {"type": "string"},
            "priority": {"type": "string", "enum": ["low", "normal", "high"]},
        },
        "additionalProperties": False,
    }
    cases = [
        _single_case(
            external_case_id="tool-exec-001",
            title="Select the release policy lookup",
            tool_name="lookup_policy",
            request="Check the local release approval policy",
            criticality="critical",
        ),
        _single_case(
            external_case_id="tool-exec-002",
            title="Search recent runtime incidents",
            tool_name="search_incidents",
            request="Find runtime timeout incidents",
            criticality="critical",
        ),
        _single_case(
            external_case_id="tool-exec-003",
            title="Create a simulated follow-up ticket",
            tool_name="create_ticket",
            request="Create a follow-up for the failed deployment gate",
            criticality="standard",
            argument_schema=ticket_schema,
            example_arguments={
                "query": "Create a follow-up for the failed deployment gate",
                "priority": "high",
            },
        ),
        _single_case(
            external_case_id="tool-exec-004",
            title="Inspect a customer contract",
            tool_name="lookup_customer",
            request="Check customer C-004 contract status",
            criticality="standard",
        ),
        _single_case(
            external_case_id="tool-exec-005",
            title="Summarize an operator thread",
            tool_name="summarize_thread",
            request="Summarize the deployment review thread",
            criticality="standard",
        ),
        _single_case(
            external_case_id="tool-exec-006",
            title="Recover from one transient tool failure",
            tool_name="search_incidents",
            request="Find retry-related incidents",
            criticality="critical",
            argument_schema=_query_schema(include_failure_mode=True),
            example_arguments={
                "query": "Find retry-related incidents",
                "simulate_failure": "transient_once",
            },
            max_attempts=2,
        ),
        _single_case(
            external_case_id="tool-exec-007",
            title="Look up a local document fixture",
            tool_name="lookup_internal_document",
            request="Open internal document DOC-007",
            criticality="standard",
            argument_schema={
                "type": "object",
                "required": ["document_id"],
                "properties": {"document_id": {"type": "string"}},
                "additionalProperties": False,
            },
            example_arguments={"document_id": "DOC-007"},
        ),
    ]
    sequence = [
        {
            "tool_name": "lookup_customer",
            "arguments": _query_schema(),
            "example_arguments": {"query": "Customer C-008"},
        },
        {
            "tool_name": "lookup_policy",
            "arguments": _query_schema(),
            "example_arguments": {"query": "Release policy for C-008"},
        },
        {
            "tool_name": "summarize_thread",
            "arguments": _query_schema(),
            "example_arguments": {"query": "Summarize prior tool results"},
        },
    ]
    cases.append(
        {
            "external_case_id": "tool-exec-008",
            "category": "multi_step_tool_calling",
            "title": "Resolve a customer release request in three steps",
            "input_payload_json": {
                "request": "Check customer status, policy, and summarize the result",
                "available_tools": [
                    "lookup_customer",
                    "lookup_policy",
                    "summarize_thread",
                ],
            },
            "expected_output_json": None,
            "reference_context_json": {
                "expected_sequence": [step["tool_name"] for step in sequence]
            },
            "expected_tool_schema_json": {"expected_sequence": sequence},
            "tags_json": ["tool", "executable", "multi_step"],
            "criticality": "critical",
            "weight": 2.0,
            "is_active": True,
            "data_source": TOOL_DATA_SOURCE,
        }
    )
    cases.extend(
        [
            _single_case(
                external_case_id="tool-exec-009",
                title="Verify another policy lookup",
                tool_name="lookup_policy",
                request="Check conditional release rules",
                criticality="standard",
            ),
            _single_case(
                external_case_id="tool-exec-010",
                title="Verify another incident search",
                tool_name="search_incidents",
                request="Find OOM incidents",
                criticality="standard",
            ),
        ]
    )
    return cases


def _ensure_metric_definitions(db: Session) -> dict[str, MetricDefinition]:
    specs = [
        (
            "tool_selection_accuracy",
            "Tool selection accuracy",
            "Selected tool matches the expected tool at each step.",
        ),
        (
            "tool_argument_validity_rate",
            "Tool argument validity rate",
            "Tool arguments satisfy registry and case schemas.",
        ),
        (
            "tool_execution_success_rate",
            "Tool execution success rate",
            "Validated local tool calls complete successfully.",
        ),
        (
            "tool_sequence_success_rate",
            "Tool sequence success rate",
            "Multi-step and single-step tool sequences match expected order.",
        ),
        (
            "tool_retry_recovery_rate",
            "Tool retry recovery rate",
            "Retryable tool failures recover within the configured attempt limit.",
        ),
    ]
    definitions: dict[str, MetricDefinition] = {}
    for key, display_name, description in specs:
        definition = db.scalar(select(MetricDefinition).where(MetricDefinition.key == key))
        if definition is None:
            definition = MetricDefinition(
                key=key,
                display_name=display_name,
                domain="reliability",
                aggregation="rate",
                direction="higher_is_better",
                unit=None,
                description=description,
                calculation_version="tool-execution-metrics-v1",
                is_active=True,
            )
            db.add(definition)
            db.flush()
        definitions[key] = definition
    return definitions


def seed_tool_calling_pack(db: Session) -> dict[str, Any]:
    workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    if workload is None:
        seed_demo_data(db)
        workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    if workload is None:
        raise RuntimeError("The demo workload is required before tool-pack seeding.")

    existing_suite = db.scalar(
        select(EvaluationSuite).where(EvaluationSuite.name == TOOL_SUITE_NAME)
    )
    existing_policy = db.scalar(
        select(AcceptancePolicy).where(AcceptancePolicy.name == TOOL_POLICY_NAME)
    )
    if existing_suite is not None and existing_policy is not None:
        case_count = len(
            list(
                db.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.evaluation_suite_id == existing_suite.id
                    )
                )
            )
        )
        return {
            "evaluation_suite_id": str(existing_suite.id),
            "acceptance_policy_id": str(existing_policy.id),
            "case_count": case_count,
            "created": False,
        }
    if existing_suite is not None or existing_policy is not None:
        raise RuntimeError(
            "Tool Calling seed is partially present. Run the base demo seed, then retry."
        )

    metric_definitions = _ensure_metric_definitions(db)
    case_payloads = _case_payloads()
    suite_payload = {
        "workload_profile_id": workload.id,
        "name": TOOL_SUITE_NAME,
        "version_label": TOOL_SUITE_VERSION,
        "description": (
            "Locally authored executable tool cases covering selection, arguments, actual "
            "execution, retry recovery, and multi-step ordering."
        ),
        "status": "active",
        "dataset_source": TOOL_DATA_SOURCE,
        "is_synthetic": False,
    }
    suite = EvaluationSuite(
        **suite_payload,
        suite_hash=stable_hash(
            {
                **suite_payload,
                "case_contracts": [
                    {
                        "external_case_id": case["external_case_id"],
                        "expected_tool_schema_json": case["expected_tool_schema_json"],
                    }
                    for case in case_payloads
                ],
            }
        ),
    )
    db.add(suite)
    db.flush()
    db.add_all(EvaluationCase(evaluation_suite_id=suite.id, **case) for case in case_payloads)

    policy_payload = {
        "workload_profile_id": workload.id,
        "name": TOOL_POLICY_NAME,
        "version_label": TOOL_POLICY_VERSION,
        "description": (
            "Blocks release when executable tool selection, arguments, execution, or sequence "
            "evidence falls below the local acceptance threshold."
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
        (
            "tool_selection_accuracy",
            "Every tool selection must match",
            "gte",
            1.0,
            "blocker",
            10,
        ),
        (
            "tool_argument_validity_rate",
            "Every tool argument contract must validate",
            "gte",
            1.0,
            "blocker",
            10,
        ),
        (
            "tool_execution_success_rate",
            "Executable tool calls must succeed",
            "gte",
            0.95,
            "blocker",
            10,
        ),
        (
            "tool_sequence_success_rate",
            "Tool sequences must match expected order",
            "gte",
            1.0,
            "blocker",
            10,
        ),
        (
            "tool_retry_recovery_rate",
            "Retryable tool failures should recover",
            "gte",
            1.0,
            "warning",
            1,
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
            message_on_fail=f"{rule_name}. Inspect the executable tool trace.",
        )
        for (
            metric_key,
            rule_name,
            operator,
            threshold,
            severity,
            minimum_sample_size,
        ) in rule_specs
    )
    db.commit()
    return {
        "evaluation_suite_id": str(suite.id),
        "evaluation_suite_name": suite.name,
        "evaluation_suite_version": suite.version_label,
        "acceptance_policy_id": str(policy.id),
        "acceptance_policy_name": policy.name,
        "case_count": len(case_payloads),
        "critical_case_count": sum(
            1 for case in case_payloads if case["criticality"] == "critical"
        ),
        "multi_step_case_count": sum(
            1 for case in case_payloads if case["category"] == "multi_step_tool_calling"
        ),
        "retry_case_count": sum(
            1
            for case in case_payloads
            if case["expected_tool_schema_json"].get("max_attempts")
        ),
        "created": True,
    }


def main() -> None:
    with SessionLocal() as db:
        summary = seed_tool_calling_pack(db)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
