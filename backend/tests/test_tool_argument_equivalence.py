import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.reference_workload.runtime_matrix import RuntimeMatrixEntry
from app.reference_workload.tool_argument_equivalence import (
    compare_argument_contract,
    validate_default_policy,
)
from app.reference_workload.tool_default_semantics_diagnostic import (
    attach_comparison,
    case_stratum,
    main,
    summary,
)
from app.reference_workload.tool_fault_cases import FaultBaselineCase, load_baseline_pack
from app.reference_workload.tool_two_stage_diagnostic import configuration_for, observe
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.tool_execution import (
    ToolExecutionContext,
    build_fault_tool_registry,
)

CONTEXT = {"corpus_hash": "a" * 64, "document_ids": ["docs/example.md"]}


def item(arguments=None, tool="create_ticket"):
    return FaultBaselineCase(
        id="TFB-201",
        request="Create ticket, query=Investigate Retry, priority=normal.",
        expected_tool=tool,
        expected_arguments=arguments or {"query": "Investigate Retry", "priority": "normal"},
    )


def call(arguments, tool="create_ticket"):
    return json.dumps({"tool_name": tool, "arguments": arguments})


@pytest.mark.parametrize(
    "expected,actual,exact,equivalent",
    [
        ({"query": "a", "priority": "normal"}, {"query": "a"}, False, True),
        ({"query": "a"}, {"query": "a", "priority": "normal"}, False, True),
        ({"query": "a"}, {"query": "a"}, True, True),
        ({"query": "a", "priority": "high"}, {"query": "a"}, False, False),
        ({"query": "a", "priority": "low"}, {"query": "a"}, False, False),
        ({"query": "a"}, {"query": "a", "priority": "high"}, False, False),
        ({"query": "a"}, {"query": "a", "priority": "low"}, False, False),
        ({"query": "a"}, {"query": "A"}, False, False),
        ({"query": "a"}, {"query": " a "}, False, False),
        ({"query": "a"}, {"query": "different", "priority": "normal"}, False, False),
        ({"query": "a", "priority": "normal"}, {"query": "a", "priority": "normal"}, True, True),
    ],
)
def test_only_declared_default_differences_are_equivalent(expected, actual, exact, equivalent):
    before = copy.deepcopy((expected, actual))
    output = call(actual)
    result = compare_argument_contract(output, item(expected), build_fault_tool_registry(), CONTEXT)
    assert result["exact_call"] is exact
    assert result["default_equivalent_call"] is equivalent
    assert result["default_only_difference"] is (equivalent and not exact)
    assert result["applied_to_execution"] is False
    assert result["comparison_only"] is True
    assert (expected, actual) == before
    assert output == call(actual)


@pytest.mark.parametrize(
    "output",
    [
        None,
        "not json",
        '{"tool_name":"create_ticket","arguments":{"query":"a","query":"b"}}',
        call({"query": "Investigate Retry", "priority": None}),
        call({"query": "Investigate Retry", "priority": "urgent"}),
        call({"query": "Investigate Retry", "extra": "x"}),
        call({"priority": "normal"}),
        call({"query": "Investigate Retry", "simulate_failure": "permanent"}),
    ],
)
def test_invalid_calls_never_receive_default_equivalence(output):
    result = compare_argument_contract(output, item(), build_fault_tool_registry(), CONTEXT)
    assert not result["default_equivalent_call"]
    assert not result["execution_eligible"]
    assert result["comparison_actual_hash"] is None


def test_wrong_tool_and_unregistered_document_are_not_rescued():
    registry = build_fault_tool_registry()
    wrong = compare_argument_contract(
        call({"query": "Investigate Retry"}, "lookup_customer"), item(), registry, CONTEXT
    )
    assert wrong["reason"] == "wrong_tool" and not wrong["default_equivalent_call"]
    document = item({"document_id": "docs/example.md"}, "lookup_internal_document")
    invalid = compare_argument_contract(
        call({"document_id": "missing.md"}, "lookup_internal_document"), document, registry, CONTEXT
    )
    assert invalid["reason"] == "guard_rejected" and not invalid["default_equivalent_call"]


def test_no_default_inference_for_other_tools_or_invalid_expected_labels():
    registry = build_fault_tool_registry()
    policy = item({"query": "normal"}, "lookup_policy")
    correct = compare_argument_contract(
        call({"query": "normal"}, "lookup_policy"), policy, registry, CONTEXT
    )
    assert correct["default_equivalent_call"] and correct["exact_call"]
    assert correct["comparison_defaulted_actual_keys"] == []
    with pytest.raises(ValueError, match="invalid evaluator"):
        compare_argument_contract(
            call({"query": "x"}), item({"priority": "normal"}), registry, CONTEXT
        )


@pytest.mark.parametrize("change", ["required", "enum", "version", "handler", "source"])
def test_default_policy_rejects_changed_contract_or_handler(monkeypatch, change):
    registry = build_fault_tool_registry()
    ticket = registry.get("create_ticket")
    descriptor = ticket.descriptor
    schema = copy.deepcopy(descriptor.argument_schema)
    if change == "required":
        schema["required"].append("priority")
    if change == "enum":
        schema["properties"]["priority"]["enum"].remove("normal")
    descriptor = replace(
        descriptor,
        argument_schema=schema,
        tool_version="changed" if change == "version" else descriptor.tool_version,
    )
    registry.tools["create_ticket"] = replace(
        ticket,
        descriptor=descriptor,
        handler=(lambda *a: {}) if change == "handler" else ticket.handler,
    )
    if change == "source":
        monkeypatch.setattr(
            "app.reference_workload.tool_argument_equivalence.HANDLER_SOURCE_SHA256", "bad"
        )
    with pytest.raises(ValueError, match="changed|replacement|pinned"):
        validate_default_policy(registry)


def test_declared_default_agrees_with_the_real_local_handler():
    registry = build_fault_tool_registry()
    policy = validate_default_policy(registry)
    context = ToolExecutionContext("test", 1, 1, ())
    handler = registry.get("create_ticket").handler
    implicit = handler({"query": "a"}, context)
    explicit = handler({"query": "a", **policy["defaults"]["create_ticket"]}, context)
    assert implicit == explicit
    assert implicit != handler({"query": "a", "priority": "high"}, context)


def test_scoring_never_fills_the_executed_call_or_leaks_policy_into_model_input(monkeypatch):
    bodies = []
    outputs = iter(
        [
            call({"query": "Investigate Retry", "priority": "normal"}),
            '{"query":"Investigate Retry"}',
        ]
    )

    def respond(self, configuration, base_url, path, body, *, deadline):
        bodies.append(copy.deepcopy(body))
        return {
            "choices": [{"message": {"content": next(outputs)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr(OpenAICompatibleAdapter, "_post_json", respond)
    monkeypatch.setattr(OpenAICompatibleAdapter, "_resolve_base_url", lambda *a, **k: "http://test")
    registry = build_fault_tool_registry()
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
    original = observe(
        item(), config, registry, CONTEXT, variant="candidate", seed=42, tool_order="registered"
    )
    before = copy.deepcopy(original)
    result = attach_comparison(original, item(), registry, CONTEXT)
    assert original == before
    assert result["argument_comparison"]["reason"] == "declared_default_only"
    assert result["selection_and_arguments_exact"] is False
    assert summary([result])["default_equivalent_call"] == 1
    for trace in result["traces"].values():
        assert trace["steps"][0]["arguments"] == {"query": "Investigate Retry"}
    assert "local-tool-default-equivalence" not in json.dumps(bodies)
    assert len(bodies) == 2
    assert result["traces"]["normal"]["steps"][0]["output"]["data"]["priority"] == "normal"


@pytest.mark.parametrize("existing", ["report", "journal"])
def test_existing_output_is_rejected_before_reading_evidence_or_calling_model(
    monkeypatch, tmp_path, existing
):
    output = tmp_path / "evidence.json"
    protected = output if existing == "report" else output.with_suffix(".observations.jsonl")
    protected.write_text("do not overwrite", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["diagnostic", "--output", str(output)])
    monkeypatch.setattr(
        "app.reference_workload.tool_default_semantics_diagnostic.load_previous",
        lambda *a: pytest.fail("preflight did not stop"),
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert protected.read_text("utf-8") == "do not overwrite"


def test_fresh_pack_covers_default_and_nondefault_strata():
    root = Path(__file__).resolve().parents[2]
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    manifest = json.loads(
        (root / "reference_workload/revisions/1.0.4/manifest.json").read_text("utf-8")
    )
    context = {
        "corpus_hash": "2772ab9a898529c052337ad6d06e4f0950333a316d72d79778dbc6cfe8cf0642",
        "document_ids": [f["path"] for f in manifest["corpus"]["files"]],
    }
    pack = load_baseline_pack(
        root / "reference_workload/diagnostics/tool-default-semantics-v1.json",
        build_fault_tool_registry(),
        context,
    )
    assert len(pack.cases) == 14
    assert {case_stratum(c) for c in pack.cases if c.expected_tool == "create_ticket"} == {
        "ticket_explicit_normal",
        "ticket_omitted_default",
        "ticket_explicit_high",
        "ticket_explicit_low",
    }
