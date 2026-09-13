import copy
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.reference_workload.tool_fault_diagnostic import run_fixture_checks
from app.services.benchmark_execution import _prepare_trials
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.tool_execution import (
    DEFAULT_TOOL_REGISTRY,
    ToolExecutionError,
    build_default_tool_registry,
    build_fault_tool_registry,
    execute_tool_calls,
    summarize_tool_traces,
)
from app.services.tool_fault_scenarios import (
    TOOL_FAULT_REGISTRY_VERSION,
    ToolFaultScenario,
    parse_tool_fault_scenario,
    validate_fault_case,
)


def case():
    return SimpleNamespace(
        external_case_id="fixture-case",
        category="tool_single_step",
        title="Fixture case",
        input_payload_json={"query": "policy", "instruction": "Use the registered local tools."},
        reference_context_json=None,
        expected_output_json=None,
        expected_tool_schema_json={"tool_name": "lookup_policy", "max_attempts": 1},
    )


OUTPUT = '{"tool_name":"lookup_policy","arguments":{"query":"policy"}}'


@pytest.mark.parametrize(
    "mode,attempts,handlers,success,retried",
    [("normal", 1, 1, True, 0), ("transient_once", 2, 1, True, 1), ("permanent", 1, 0, False, 0)],
)
def test_environment_controls_faults_without_changing_arguments(
    mode, attempts, handlers, success, retried
):
    registry = build_default_tool_registry()
    registered = registry.get("lookup_policy")
    seen = []

    def handle(arguments, context):
        seen.append(copy.deepcopy(arguments))
        return registered.handler(arguments, context)

    registry.tools["lookup_policy"] = replace(registered, handler=handle)
    trace = execute_tool_calls(case(), OUTPUT, registry, fault_scenario=ToolFaultScenario(mode))
    assert trace.schema_version == "tool-execution-trace-v2"
    assert trace.registry_version == TOOL_FAULT_REGISTRY_VERSION
    assert trace.successful is success
    assert trace.fault_scenario["passed"] is True
    assert trace.fault_scenario["handler_invocation_count"] == handlers == len(seen)
    assert trace.steps[0].attempt_count == attempts
    assert trace.steps[0].retry_count == retried
    assert trace.steps[0].arguments == {"query": "policy"}
    assert all(arguments == {"query": "policy"} for arguments in seen)
    assert trace.fault_scenario["gate_evidence"] is False
    summary = summarize_tool_traces([trace.to_dict()])
    assert summary["fault_scenario_summary"]["passed_count"] == 1
    assert summary["successful_call_count"] == int(success)


@pytest.mark.parametrize("mode", ["normal", "transient_once", "permanent"])
@pytest.mark.parametrize(
    "bad_output",
    [
        '{"tool_name":"lookup_policy","arguments":{"query":"policy","simulate_failure":"normal"}}',
        '{"tool_name":"lookup_policy","arguments":{}}',
        '{"tool_name":"lookup_customer","arguments":{"query":"policy"}}',
        '{"tool_calls":[]}',
        '{"tool_calls":[{"name":"lookup_policy","arguments":{"query":"a"}},'
        '{"name":"lookup_policy","arguments":{"query":"b"}}]}',
        "not json",
    ],
)
def test_invalid_calls_cannot_pass_a_fault_scenario_or_trigger_injection(mode, bad_output):
    trace = execute_tool_calls(case(), bad_output, fault_scenario=ToolFaultScenario(mode))
    assert trace.fault_scenario["status"] == "not_exercised"
    assert trace.fault_scenario["passed"] is False
    assert all(step.attempt_count == 0 for step in trace.steps)


def test_guard_rejection_precedes_faults_and_real_handler_errors_are_not_reported_as_recovery():
    blocked = execute_tool_calls(
        case(),
        OUTPUT,
        fault_scenario=ToolFaultScenario("transient_once"),
        execution_block_reason="document membership rejected",
    )
    assert blocked.fault_scenario["status"] == "not_exercised"
    registry = build_default_tool_registry()

    def broken_handler(arguments, context):
        raise ToolExecutionError(
            "real fixture failure", error_type="handler_failure", retryable=False
        )

    registry.tools["lookup_policy"] = replace(registry.get("lookup_policy"), handler=broken_handler)
    trace = execute_tool_calls(
        case(), OUTPUT, registry, fault_scenario=ToolFaultScenario("transient_once")
    )
    assert trace.fault_scenario["status"] == "failed"
    assert trace.fault_scenario["injected_failure_count"] == 1
    assert trace.fault_scenario["handler_invocation_count"] == 1
    assert trace.steps[0].error_type == "handler_failure"


def test_external_side_effect_tools_are_not_subject_to_fixture_retries():
    registry = build_default_tool_registry()
    tool = registry.get("lookup_policy")
    registry.tools["lookup_policy"] = replace(
        tool,
        descriptor=replace(tool.descriptor, side_effect_mode="external_write"),
    )
    trace = execute_tool_calls(
        case(), OUTPUT, registry, fault_scenario=ToolFaultScenario("transient_once")
    )
    assert trace.fault_scenario["status"] == "not_exercised"
    assert trace.steps[0].attempt_count == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"mode": "guess"},
        {"mode": True},
        {"max_attempts": True},
        {"max_attempts": 4},
        {"max_attempts": 1, "mode": "transient_once"},
        {"schema_version": "unknown"},
        {"expected_tool": "private"},
    ],
)
def test_invalid_fault_configuration_fails_closed(patch):
    value = {**ToolFaultScenario("normal").to_dict(), **patch}
    with pytest.raises(ValueError):
        parse_tool_fault_scenario(value)


def test_policy_identity_and_registry_projection_are_stable_and_leave_legacy_unchanged():
    normal = ToolFaultScenario("normal")
    assert parse_tool_fault_scenario(dict(reversed(list(normal.to_dict().items())))) == normal
    assert normal.scenario_hash != ToolFaultScenario("permanent").scenario_hash
    original = copy.deepcopy(DEFAULT_TOOL_REGISTRY.descriptor())
    projected = build_fault_tool_registry()
    for tool in projected.tools.values():
        assert "simulate_failure" not in tool.descriptor.argument_schema["properties"]
    assert DEFAULT_TOOL_REGISTRY.descriptor() == original
    legacy = execute_tool_calls(case(), OUTPUT).to_dict()
    assert legacy["schema_version"] == "tool-execution-trace-v1"
    assert "fault_scenario" not in legacy
    assert "fault_injected" not in legacy["steps"][0]["attempts"][0]


@pytest.mark.parametrize(
    "contract",
    [
        {"required_arguments": ["simulate_failure"]},
        {"arguments": {"properties": {"simulate_failure": {"type": "string"}}}},
        {"example_arguments": {"simulate_failure": "transient_once"}},
        {"expected_sequence": [{"tool_name": "lookup_policy"}]},
    ],
)
def test_legacy_labels_are_rejected_not_silently_migrated(contract):
    evaluation_case = case()
    evaluation_case.expected_tool_schema_json.update(contract)
    before = copy.deepcopy(evaluation_case.expected_tool_schema_json)
    with pytest.raises(ValueError):
        validate_fault_case(evaluation_case)
    assert evaluation_case.expected_tool_schema_json == before


@pytest.mark.parametrize("category", ["agent_multi_step", "rag_tool_combined", "json_output"])
def test_unsupported_workflows_are_rejected(category):
    evaluation_case = case()
    evaluation_case.category = category
    with pytest.raises(ValueError):
        execute_tool_calls(evaluation_case, OUTPUT, fault_scenario=ToolFaultScenario("normal"))


def test_parallel_trials_have_independent_failure_state():
    scenario = ToolFaultScenario("transient_once")
    with ThreadPoolExecutor(max_workers=4) as executor:
        traces = list(
            executor.map(
                lambda _: execute_tool_calls(case(), OUTPUT, fault_scenario=scenario), range(12)
            )
        )
    assert all(t.steps[0].attempt_count == 2 and t.fault_scenario["passed"] for t in traces)


def test_fault_mode_and_evaluator_labels_do_not_enter_model_input():
    configuration = SimpleNamespace(
        runtime_name="ollama",
        generation_config_json={},
        configuration_hash="test",
        context_length=4096,
        retrieval_config_json={},
        model_artifact=SimpleNamespace(artifact_name="test-model"),
    )
    observed = []
    for index, mode in enumerate(("normal", "transient_once", "permanent")):
        evaluation_case = case()
        evaluation_case.expected_tool_schema_json["tool_name"] = f"private-label-{index}"
        prepared = _prepare_trials(
            configuration,
            [evaluation_case],
            runtime_config={
                "tool_fault_scenario": ToolFaultScenario(mode).to_dict(),
                "tool_selection_prompt": "public-tool-selection-prompt-v1",
            },
            trials_per_case=1,
            case_timeout_ms=1000,
            include_mock_agent_plan=False,
            agent_approval_decisions={},
        )[0]
        assert "tool_fault_scenario" not in prepared.configuration.runtime_config_json
        assert prepared.fault_scenario.mode == mode
        payload = OpenAICompatibleAdapter()._user_message_payload(
            prepared.adapter_case,
            configuration=prepared.configuration,
        )
        serialized = json.dumps(payload)
        assert "simulate_failure" not in serialized
        assert "private-label" not in serialized
        observed.append(payload)
    assert observed[0] == observed[1] == observed[2]


def test_scripted_diagnostic_reports_fault_checks_not_model_accuracy():
    report = run_fixture_checks(
        document_context={"document_ids": ["known.md"], "corpus_hash": "test"}
    )
    assert report["model_inference_performed"] is False
    assert report["database_writes_performed"] is False
    assert report["summary"]["observation_count"] == 54
    assert report["summary"]["fixture_passed_count"] == 54
    assert report["summary"]["tool_success_count"] == 36
    assert report["summary"]["injected_failure_count"] == 36
    assert report["summary"]["handler_invocation_count"] == 36
    assert all("simulate_failure" not in row["scripted_output"] for row in report["rows"])


def test_trace_summary_ignores_nullable_legacy_fault_metadata():
    trace = execute_tool_calls(case(), OUTPUT).to_dict()
    expected = summarize_tool_traces([trace])
    trace["fault_scenario"] = None
    assert summarize_tool_traces([trace]) == expected
    assert "fault_scenario_summary" not in expected
