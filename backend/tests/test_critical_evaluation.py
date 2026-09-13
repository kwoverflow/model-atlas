from __future__ import annotations

import copy
from types import SimpleNamespace as N
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import BenchmarkResult, EvaluationCase
from app.reference_workload.critical_canary import _seal
from app.reference_workload.critical_evaluator_comparison import (
    compare_saved_canary,
    compare_snapshots,
)
from app.services.deployment_gate.critical_evaluation import (
    AGENT_AWARE_VERSION,
    LEGACY_VERSION,
    evaluate_critical_result,
)
from app.services.deployment_gate.evidence import stable_hash
from app.services.deployment_gate.metrics import _is_critical_failure


def sample():
    steps = []
    for index, action in enumerate(("tool", "respond")):
        steps.append(
            {
                "step_index": index,
                "action": action,
                "status": "success",
                "successful": True,
                "input": {"action": action},
                "output": {"content": "Done"},
                "error_type": None,
                "policy_violations": [],
                "phase": "plan",
                "recovered_by_replan": False,
                "duration_ms": 1.0,
                "observation": {
                    "schema_version": "agent-observation-v1",
                    "status": "success",
                    "successful": True,
                    "error_type": None,
                    "policy_violation_count": 0,
                },
            }
        )
    steps[0]["output"] = {
        "tool_execution": {
            "tool_name": "lookup_policy",
            "arguments": {"query": "status"},
            "selection_valid": True,
            "arguments_valid": True,
            "output_valid": True,
            "execution_status": "success",
            "error_type": None,
        }
    }
    steps[0]["input"] = {
        "action": "tool",
        "tool_name": "lookup_policy",
        "arguments": {"query": "status"},
    }
    trace = {
        "schema_version": "agent-execution-trace-v2",
        "context_version": "agent-context-v2",
        "runtime_version": "bounded-agent-runtime-v2",
        "memory_registry_version": "memory-v1",
        "tool_registry_version": "local-tool-registry-v1",
        "corpus_version": "1",
        "retriever_version": "lexical-overlap-v1",
        "external_case_id": "TEST-AGENT",
        "parse_valid": True,
        "parse_error": None,
        "plan_valid": True,
        "status": "success",
        "successful": True,
        "step_limit": 2,
        "execution_step_limit": 2,
        "step_count": 2,
        "expected_action_sequence": ["tool", "respond"],
        "actual_action_sequence": ["tool", "respond"],
        "sequence_match": True,
        "successful_step_count": 2,
        "failed_step_count": 0,
        "tool_call_count": 1,
        "retrieval_count": 0,
        "memory_read_count": 0,
        "memory_write_count": 0,
        "retried_tool_count": 0,
        "recovered_tool_count": 0,
        "policy_violation_count": 0,
        "final_response_present": True,
        "memory_provenance_count": 0,
        "memory_action_count": 0,
        "observation_count": 2,
        "replan_count": 0,
        "successful_replan_count": 0,
        "recovery_step_count": 0,
        "unrecovered_failure_count": 0,
        "pending_checkpoint_count": 0,
        "denied_checkpoint_count": 0,
        "halt_reason": None,
        "total_duration_ms": 2.0,
        "steps": steps,
        "replans": [],
    }
    case = N(
        id="case-1",
        external_case_id="TEST-AGENT",
        category="agent_multi_step",
        criticality="critical",
        evaluation_suite_id="suite-1",
        expected_output_json=None,
        expected_tool_schema_json={"tool_name": "lookup_policy"},
        reference_context_json={
            "agent": {
                "allowed_actions": ["tool", "respond"],
                "allowed_tools": ["lookup_policy"],
                "expected_steps": [
                    {"action": "tool", "tool_name": "lookup_policy"},
                    {"action": "respond"},
                ],
            }
        },
    )
    result = N(
        id="result-1",
        benchmark_run_id="run-1",
        evaluation_case_id="case-1",
        sample_id="sample-1",
        data_source="local_actual_runtime_diagnostic",
        error_type=None,
        exact_match=True,
        human_label=None,
        quality_score=1.0,
        json_valid=True,
        tool_call_valid=False,
        groundedness_score=None,
        faithfulness_score=None,
        raw_output="raw plan",
        normalized_output="compiled plan",
        metadata_json={"agent_execution": trace},
    )
    return result, case


def test_explicit_version_resolves_agent_flag_without_mutation():
    result, case = sample()
    before = stable_hash([vars(result), vars(case)])
    assert evaluate_critical_result(result, case).status == "fail"
    assert _is_critical_failure(result, case) is True
    candidate = evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION)
    assert candidate.status == "pass"
    assert candidate.scalar_tool_flag_applicable is False
    assert candidate.output_kind == "agent_plan"
    assert result.tool_call_valid is False
    assert stable_hash([vars(result), vars(case)]) == before


@pytest.mark.parametrize("category", ["agent_multi_step", "rag_tool_combined", "agent_operations"])
def test_case_contract_controls_agent_classification(category):
    result, case = sample()
    case.category = category
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "pass"


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), "agent-execution-trace-v999"),
        (("runtime_version",), "bounded-agent-runtime-v999"),
        (("external_case_id",), "foreign"),
        (("successful",), "true"),
        (("successful",), False),
        (("plan_valid",), False),
        (("parse_valid",), False),
        (("parse_error",), "invalid"),
        (("status",), "pending_approval"),
        (("step_count",), 3),
        (("step_count",), "2"),
        (("execution_step_limit",), 1),
        (("execution_step_limit",), None),
        (("policy_violation_count",), 1),
        (("policy_violation_count",), -1),
        (("policy_violation_count",), False),
        (("unrecovered_failure_count",), 1),
        (("pending_checkpoint_count",), 1),
        (("denied_checkpoint_count",), 1),
        (("halt_reason",), "policy_violation"),
        (("successful_step_count",), 1),
        (("failed_step_count",), 1),
        (("observation_count",), 0),
        (("actual_action_sequence",), ["respond", "tool"]),
        (("expected_action_sequence",), ["respond"]),
        (("sequence_match",), False),
        (("final_response_present",), False),
        (("steps",), []),
        (("steps",), None),
        (("steps", 0, "successful"), False),
        (("steps", 0, "status"), "failed"),
        (("steps", 0, "error_type"), "tool_failed"),
        (("steps", 0, "policy_violations"), ["forbidden"]),
        (("steps", 0, "recovered_by_replan"), True),
        (("steps", 0, "step_index"), -1),
        (("steps", 1, "step_index"), 0),
        (("steps", 1, "output"), {}),
        (("steps", 0, "observation"), None),
        (("steps", 0, "observation", "successful"), False),
        (("steps", 0, "observation", "status"), "failed"),
        (("steps", 0, "output", "tool_execution", "arguments_valid"), False),
        (("steps", 0, "output", "tool_execution", "arguments_valid"), "true"),
        (("steps", 0, "output", "tool_execution", "selection_valid"), False),
        (("steps", 0, "output", "tool_execution", "output_valid"), False),
        (("steps", 0, "output", "tool_execution", "execution_status"), "failed"),
        (("steps", 0, "output", "tool_execution", "tool_name"), "create_ticket"),
        (("steps", 0, "output", "tool_execution", "arguments"), {"query": "altered"}),
        (("steps", 0, "output", "tool_execution"), None),
        (("recovery_step_count",), 1),
        (("replan_count",), 1),
    ],
)
def test_invalid_agent_evidence_fails_closed(path, value):
    result, case = sample()
    target = result.metadata_json["agent_execution"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "fail"


@pytest.mark.parametrize("field", ["halt_reason", "unrecovered_failure_count", "steps", "replans"])
def test_missing_evidence_does_not_gain_default_success(field):
    result, case = sample()
    del result.metadata_json["agent_execution"][field]
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "fail"


@pytest.mark.parametrize(
    "metadata", [{}, {"agent_execution": None}, {"agent_execution": "success"}]
)
def test_missing_agent_trace_fails_even_with_scalar_flag_true(metadata):
    result, case = sample()
    result.tool_call_valid = True
    result.metadata_json = metadata
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "fail"


@pytest.mark.parametrize(
    "field,value",
    [
        ("error_type", "oom"),
        ("quality_score", 0.1),
        ("exact_match", False),
        ("human_label", "human_fail"),
        ("json_valid", False),
    ],
)
def test_common_failure_is_not_bypassed(field, value):
    result, case = sample()
    setattr(result, field, value)
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "fail"


def test_runtime_and_json_contract_failures_are_preserved():
    result, case = sample()
    case.expected_output_json = {"type": "object"}
    result.json_valid = False
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "fail"
    result.json_valid = True
    result.metadata_json["runtime_reliability"] = {"status": "timeout"}
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "fail"


def test_single_tool_cannot_bypass_flag_by_adding_agent_metadata():
    result, case = sample()
    case.category = "tool_single_step"
    case.reference_context_json = {}
    candidate = evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION)
    assert candidate.status == "fail"
    assert candidate.scalar_tool_flag_applicable is True
    assert candidate.output_kind == "single_tool"


@pytest.mark.parametrize(
    "contract", [None, {}, {"expected_steps": []}, {"expected_steps": [{"action": []}]}]
)
def test_missing_or_malformed_contract_fails(contract):
    result, case = sample()
    case.reference_context_json = {"agent": contract}
    assert evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status == "fail"


def test_noncritical_and_unknown_versions_are_explicit():
    result, case = sample()
    case.criticality = "normal"
    assert (
        evaluate_critical_result(result, case, version=AGENT_AWARE_VERSION).status
        == "not_applicable"
    )
    with pytest.raises(ValueError, match="unsupported"):
        evaluate_critical_result(result, case, version="future")


def source_fixture():
    result, case = sample()
    return _seal(
        {
            "schema_version": "critical-canary-audit-v1",
            "kind": "audit",
            "gate_evidence": False,
            "human_reviewed": False,
            "production_readiness": "not_production_ready",
            "summary": {
                "observation_count": 1,
                "unique_case_count": 1,
                "by_entry": [{"entry": "test"}],
            },
            "stored_runs": [
                {
                    "run": {
                        "id": result.benchmark_run_id,
                        "data_source": result.data_source,
                        "evaluation_suite_id": case.evaluation_suite_id,
                    },
                    "cases": [vars(case)],
                }
            ],
            "rows": [
                {
                    "entry": "test",
                    "external_case_id": case.external_case_id,
                    "category": case.category,
                    "benchmark_result_id": result.id,
                    "benchmark_run_id": result.benchmark_run_id,
                    "case_id": case.id,
                    "sample_id": result.sample_id,
                    "status": "fail",
                    "stored_result": vars(result),
                }
            ],
        }
    )


def test_comparison_preserves_bytes_and_records_versioned_delta():
    source = source_fixture()
    digest = stable_hash(source)
    report = compare_saved_canary(source)
    assert report["summary"]["changed_count"] == 1
    assert report["summary"]["non_agent_changed_count"] == 0
    assert report["summary"]["candidate"] == {"pass": 1}
    assert report["legacy_version"] == LEGACY_VERSION
    assert report["model_calls"] == report["database_writes"] == 0
    assert report["gate_evidence"] is report["human_reviewed"] is False
    assert stable_hash(source) == digest


@pytest.mark.parametrize(
    "change", ["hash", "source", "id", "duplicate", "legacy", "authority", "count", "entry"]
)
def test_comparison_rejects_bad_provenance(change):
    source = source_fixture()
    source.pop("content_sha256")
    if change == "source":
        source["rows"][0]["stored_result"]["data_source"] = "local_actual_runtime"
    elif change == "id":
        source["rows"][0]["stored_result"]["evaluation_case_id"] = "foreign"
    elif change == "duplicate":
        source["rows"].append(copy.deepcopy(source["rows"][0]))
    elif change == "legacy":
        source["rows"][0]["status"] = "pass"
    elif change == "authority":
        source["gate_evidence"] = True
    elif change == "count":
        source["summary"]["observation_count"] = 2
    elif change == "entry":
        source["rows"][0]["entry"] = "other"
    source = _seal(source)
    if change == "hash":
        source["rows"][0]["status"] = "pass"
    with pytest.raises(ValueError):
        compare_saved_canary(source)


def test_snapshot_comparison_requires_preserved_official_records():
    before = _seal(
        {
            "schema_version": "critical-canary-audit-v1",
            "kind": "snapshot",
            "official": {"hash": "fixed"},
            "source_sha256": {"metrics.py": "old"},
        }
    )
    after = _seal(
        {
            "schema_version": "critical-canary-audit-v1",
            "kind": "snapshot",
            "official": {"hash": "fixed"},
            "source_sha256": {"metrics.py": "new"},
        }
    )
    assert compare_snapshots(before, after)["changed_source_paths"] == ["metrics.py"]
    after["official"]["hash"] = "changed"
    after.pop("content_sha256")
    with pytest.raises(ValueError, match="official"):
        compare_snapshots(before, _seal(after))


@pytest.mark.parametrize("pack", ["basic", "adaptive"])
def test_seeded_agent_pack_including_retry_memory_and_approval_still_passes(
    client, db_session, pack
):
    from app.seed.adaptive_agent_operations import seed_adaptive_agent_operations_pack
    from app.seed.agent_operations import seed_agent_operations_pack
    from app.seed.demo import seed_demo_data

    seed_demo_data(db_session)
    seeded = (
        seed_agent_operations_pack if pack == "basic" else seed_adaptive_agent_operations_pack
    )(db_session)
    task = next(
        item
        for item in client.get("/api/v1/benchmark-tasks").json()
        if item["name"] == "Korean document QA"
    )
    prompt = next(
        item
        for item in client.get("/api/v1/prompt-versions").json()
        if item["benchmark_task_id"] == task["id"]
    )
    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "seed": 13,
            "agent_approval_decisions": {
                "*": {
                    "decision": "approved",
                    "decided_by": "reviewer@example.local",
                    "reason": "Synthetic regression test approval.",
                }
            },
        },
    )
    assert response.status_code == 201
    run_id = UUID(response.json()["benchmark_run"]["id"])
    results = list(
        db_session.scalars(
            select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id == run_id)
        )
    )
    assert len(results) == (8 if pack == "basic" else 5)
    for result in results:
        case = db_session.get(EvaluationCase, result.evaluation_case_id)
        # Evaluate a detached critical view to cover non-critical seed examples too.
        view = N(
            **{
                key: getattr(case, key)
                for key in (
                    "category",
                    "external_case_id",
                    "expected_output_json",
                    "expected_tool_schema_json",
                    "reference_context_json",
                )
            },
            criticality="critical",
        )
        decision = evaluate_critical_result(result, view, version=AGENT_AWARE_VERSION)
        assert decision.status == "pass", (case.external_case_id, decision.reasons)
