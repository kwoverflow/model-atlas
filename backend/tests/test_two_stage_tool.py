import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.reference_workload.runtime_matrix import RuntimeMatrixEntry
from app.reference_workload.tool_fault_baseline import measure_generation
from app.reference_workload.tool_fault_cases import (
    FaultBaselineCase,
    load_baseline_pack,
    prepare_baseline_cases,
)
from app.reference_workload.tool_two_stage_diagnostic import (
    CapturedCandidate,
    configuration_for,
    observe,
    verify_baseline,
)
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.inference_adapters.two_stage_tool import TwoStageToolAdapter
from app.services.tool_argument_generation import build_argument_payload
from app.services.tool_execution import build_fault_tool_registry

CONTEXT = {"corpus_hash": "a" * 64, "document_ids": ["docs/example.md"]}
ITEM = FaultBaselineCase(
    id="TFB-001",
    request="Find policy. Set query to release approval.",
    expected_tool="lookup_policy",
    expected_arguments={"query": "release approval"},
)


@pytest.fixture
def setup():
    registry = build_fault_tool_registry()
    public, evaluator = prepare_baseline_cases(ITEM, registry, CONTEXT)
    entry = RuntimeMatrixEntry(
        name="test",
        base_url_env="BASE",
        model_env="MODEL",
        context_length=4096,
        prompt_bundle="operator-assistant-ko-v1",
        trials=2,
    )
    config = configuration_for(
        entry, SimpleNamespace(base_url="http://test", model_name="test"), CONTEXT
    )
    return registry, public, evaluator, config


def install_responses(monkeypatch, outputs, *, usage=True):
    calls = []
    iterator = iter(outputs)

    def respond(self, configuration, base_url, path, body, *, deadline):
        calls.append({"body": copy.deepcopy(body), "deadline": deadline})
        output = next(iterator)
        if isinstance(output, Exception):
            raise output
        payload = {"choices": [{"message": {"content": output}, "finish_reason": "stop"}]}
        if usage:
            payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 5}
        return payload

    monkeypatch.setattr(OpenAICompatibleAdapter, "_post_json", respond)
    monkeypatch.setattr(OpenAICompatibleAdapter, "_resolve_base_url", lambda *a, **k: "http://test")
    return calls


def first_output(tool="lookup_policy", arguments=None):
    return json.dumps({"tool_name": tool, "arguments": arguments or {"query": "discard-me"}})


def test_two_stage_has_unchanged_selection_request_and_public_only_argument_request(
    monkeypatch, setup
):
    registry, public, evaluator, config = setup
    calls = install_responses(monkeypatch, [first_output(), '{"query":"release approval"}'])
    result = TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public, seed=42)
    assert len(calls) == 2
    assert calls[1]["deadline"] <= calls[0]["deadline"]
    assert [c["body"]["seed"] for c in calls] == [42, 42]
    request = json.loads(calls[1]["body"]["messages"][1]["content"])
    assert request["request"] == ITEM.request
    assert request["selected_tool"]["tool_name"] == "lookup_policy"
    assert "available_tools" not in request
    assert "document_catalog" not in request
    assert "discard-me" not in json.dumps(calls[1])
    assert "expected" not in json.dumps(request)
    assert result.prompt_tokens == 20 and result.completion_tokens == 10
    audit = result.metadata["tool_argument_generation"]
    assert audit["first_stage"]["raw_output"] == first_output()
    assert audit["second_stage"]["raw_output"] == '{"query":"release approval"}'
    assert audit["output_representation"] == "assembled_envelope"
    row = measure_generation(ITEM, public, evaluator, result, registry, CONTEXT)
    assert row["selection_and_arguments_exact"] and row["normal_tool_success"]
    assert row["argument_preservation_verified"]
    baseline_calls = install_responses(monkeypatch, [first_output()])
    OpenAICompatibleAdapter().run_case(configuration=config, evaluation_case=public, seed=42)
    assert len(baseline_calls) == 1
    assert baseline_calls[0]["body"] == calls[0]["body"]


def test_private_labels_cannot_change_either_request(monkeypatch, setup):
    registry, public, _, config = setup
    changed = ITEM.model_copy(
        update={"expected_tool": "private", "expected_arguments": {"x": "secret"}}
    )
    another, _ = prepare_baseline_cases(changed, registry, CONTEXT)
    calls = install_responses(monkeypatch, [first_output(), '{"query":"x"}'] * 2)
    for case in (public, another):
        TwoStageToolAdapter().run_case(configuration=config, evaluation_case=case, seed=42)
    assert calls[0]["body"] == calls[2]["body"]
    assert calls[1]["body"] == calls[3]["body"]


@pytest.mark.parametrize(
    "bad",
    [
        '{"query":"a","query":"b"}',
        '{"query":NaN}',
        '```json\n{"query":"a"}\n```',
        "[]",
        "null",
        '{"query":',
        "{}",
        '{"query":12}',
        '{"query":"a","extra":true}',
        '{"tool_name":"lookup_customer","arguments":{"query":"release approval"}}',
        '{"query":"a","simulate_failure":"permanent"}',
    ],
)
def test_bad_second_stage_cannot_execute_or_fall_back(monkeypatch, setup, bad):
    registry, public, evaluator, config = setup
    install_responses(monkeypatch, [first_output(arguments=ITEM.expected_arguments), bad])
    result = TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public)
    row = measure_generation(ITEM, public, evaluator, result, registry, CONTEXT)
    assert not row["guard_eligible"]
    assert not row["normal_tool_success"]
    for trace in row["traces"].values():
        assert trace["fault_scenario"]["handler_invocation_count"] == 0
    assert result.metadata["tool_argument_generation"]["second_stage"]["raw_output"] == bad


def test_wrong_tool_selection_is_not_corrected(monkeypatch, setup):
    registry, public, evaluator, config = setup
    install_responses(
        monkeypatch, [first_output("lookup_customer"), '{"query":"release approval"}']
    )
    result = TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public)
    assert result.metadata["tool_call_contract"]["tool_name"] == "lookup_customer"
    row = measure_generation(ITEM, public, evaluator, result, registry, CONTEXT)
    assert row["arguments_exact"] and not row["selection_correct"]
    assert not row["normal_tool_success"]


@pytest.mark.parametrize("output", ["not json", first_output("unknown")])
def test_unrecognized_selection_skips_second_call(monkeypatch, setup, output):
    _, public, _, config = setup
    calls = install_responses(monkeypatch, [output])
    result = TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public)
    assert len(calls) == 1
    assert not result.metadata["tool_call_contract"]["execution_allowed"]
    assert result.metadata["tool_argument_generation"]["status"] == "skipped"


def test_invalid_first_arguments_can_be_replaced_only_by_new_model_generation(monkeypatch, setup):
    _, public, _, config = setup
    install_responses(
        monkeypatch, ['{"tool_name":"lookup_policy","arguments":{}}', '{"query":"new"}']
    )
    result = TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public)
    audit = result.metadata["tool_argument_generation"]
    assert not audit["first_stage"]["guard"]["execution_allowed"]
    assert result.metadata["tool_call_contract"]["execution_allowed"]
    assert json.loads(result.normalized_output)["arguments"] == {"query": "new"}
    assert audit["deterministic_argument_repair"] is False


def test_trusted_document_catalog_and_unknown_id_guard(monkeypatch, setup):
    _, public, _, config = setup
    public.input_payload_json["available_document_ids"] = ["injected.md"]
    request = build_argument_payload(public.input_payload_json, "lookup_internal_document", CONTEXT)
    assert request["document_catalog"] == CONTEXT
    install_responses(
        monkeypatch, [first_output("lookup_internal_document"), '{"document_id":"injected.md"}']
    )
    result = TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public)
    assert not result.metadata["tool_call_contract"]["execution_allowed"]
    assert result.metadata["tool_call_contract"]["document_reference_status"] == "not_in_catalog"


def test_second_stage_exception_retains_first_usage_and_capture(monkeypatch, setup):
    _, public, _, config = setup
    install_responses(monkeypatch, [first_output(), TimeoutError("test timeout")])
    adapter = CapturedCandidate()
    adapter.reset_capture()
    result = adapter.run_case(configuration=config, evaluation_case=public)
    assert len(adapter.requests) == 2
    assert adapter.requests[1]["error"]["type"] == "TimeoutError"
    assert result.prompt_tokens == 10 and result.completion_tokens == 5
    assert result.error_type == "tool_argument_generation_failed"
    assert not result.metadata["tool_call_contract"]["execution_allowed"]


def test_expired_shared_deadline_does_not_make_second_http_call(monkeypatch, setup):
    _, public, _, config = setup
    calls = install_responses(monkeypatch, [first_output()])
    monkeypatch.setattr(TwoStageToolAdapter, "_case_timeout_seconds", lambda *a: 0)
    result = TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public)
    assert len(calls) == 1
    assert result.metadata["tool_argument_generation"]["error"]["type"] == "TimeoutError"


@pytest.mark.parametrize("usage", [True, False])
def test_observation_counts_only_complete_http_usage_as_measured(monkeypatch, setup, usage):
    registry, _, _, config = setup
    install_responses(monkeypatch, [first_output(), '{"query":"release approval"}'], usage=usage)
    row = observe(
        ITEM, config, registry, CONTEXT, variant="candidate", seed=42, tool_order="reversed"
    )
    assert len(row["requests"]) == 2
    assert row["http_usage_complete"] is usage
    assert row["measured_tokens"] == (
        {"prompt_tokens": 20, "completion_tokens": 10} if usage else None
    )


def test_non_tool_workflows_are_rejected_before_network(monkeypatch, setup):
    _, public, _, config = setup
    public.category = "rag_grounded"
    calls = install_responses(monkeypatch, [])
    with pytest.raises(ValueError, match="standalone"):
        TwoStageToolAdapter().run_case(configuration=config, evaluation_case=public)
    assert calls == []


def test_challenge_and_frozen_baseline_are_valid():
    root = Path(__file__).resolve().parents[2]
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    # Historical artifacts are local evidence, not required in a clean source checkout.
    if (root / "artifacts/reference-workload/tool-fault-model-baseline-v1.json").exists():
        verify_baseline(root)
    manifest = json.loads(
        (root / "reference_workload/revisions/1.0.4/manifest.json").read_text("utf-8")
    )
    context = {
        "corpus_hash": "2772ab9a898529c052337ad6d06e4f0950333a316d72d79778dbc6cfe8cf0642",
        "document_ids": [item["path"] for item in manifest["corpus"]["files"]],
    }
    pack = load_baseline_pack(
        root / "reference_workload/diagnostics/tool-two-stage-challenge-v1.json",
        build_fault_tool_registry(),
        context,
    )
    assert len(pack.cases) == 6
