import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.reference_workload.runtime_matrix import RuntimeMatrixEntry
from app.reference_workload.tool_default_semantics_diagnostic import attach_comparison
from app.reference_workload.tool_fault_cases import FaultBaselineCase, load_baseline_pack
from app.reference_workload.tool_presence_diagnostic import main, observe_presence
from app.reference_workload.tool_two_stage_diagnostic import configuration_for
from app.services.inference_adapters.nullable_presence_tool import (
    decode_nullable_arguments,
    nullable_wire_schema,
)
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.inference_adapters.presence_aware_tool import SYSTEM_PROMPT
from app.services.tool_execution import build_fault_tool_registry

CONTEXT = {"corpus_hash": "a" * 64, "document_ids": ["docs/example.md"]}


def example(tool="create_ticket", arguments=None):
    return FaultBaselineCase(
        id="TFB-203",
        request="Create a ticket. query is repair webhook. priority is high.",
        expected_tool=tool,
        expected_arguments=arguments or {"query": "repair webhook", "priority": "high"},
    )


def configuration():
    entry = RuntimeMatrixEntry(
        name="test",
        base_url_env="BASE",
        model_env="MODEL",
        context_length=4096,
        prompt_bundle="operator-assistant-ko-v1",
    )
    return configuration_for(
        entry, SimpleNamespace(base_url="http://test", model_name="test"), CONTEXT
    )


def install(monkeypatch, outputs):
    actual_bodies = []
    stream = iter(outputs)

    def response(self, config, base_url, path, body, *, deadline):
        actual_bodies.append(copy.deepcopy(body))
        output = next(stream)
        if isinstance(output, Exception):
            raise output
        return {
            "choices": [{"message": {"content": output}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr(OpenAICompatibleAdapter, "_post_json", response)
    monkeypatch.setattr(OpenAICompatibleAdapter, "_resolve_base_url", lambda *a, **k: "http://test")
    return actual_bodies


def first(tool="create_ticket"):
    return json.dumps({"tool_name": tool, "arguments": {"query": "discard first value"}})


def run(item, variant="candidate_v2"):
    registry = build_fault_tool_registry()
    row = observe_presence(
        item, configuration(), registry, CONTEXT, variant=variant, seed=42, order="registered"
    )
    return attach_comparison(row, item, registry, CONTEXT)


def test_only_optional_second_stage_changes_and_capture_sees_actual_request(monkeypatch):
    second = '{"query":"repair webhook","priority":"high"}'
    bodies = install(monkeypatch, [first(), second, first(), second])
    v1 = run(example(), "candidate_v1")
    v2 = run(example())
    assert bodies[0] == bodies[2]
    assert bodies[1]["response_format"] == bodies[3]["response_format"]
    assert bodies[1]["seed"] == bodies[3]["seed"] == 42
    assert bodies[1]["max_tokens"] == bodies[3]["max_tokens"]
    assert bodies[3]["messages"][0]["content"] == SYSTEM_PROMPT
    payload = json.loads(bodies[3]["messages"][1]["content"])
    assert payload["optional_field_presence"] == [
        {
            "field": "priority",
            "if_explicitly_assigned": "include the exact requested value",
            "if_not_assigned_or_requested_omitted": "omit; do not invent a default",
        }
    ]
    assert payload["request"] == example().request
    assert "discard first value" not in json.dumps(payload)
    assert "expected_arguments" not in json.dumps(payload)
    assert "available_tools" not in payload
    assert [r["body"] for r in v1["requests"]] == bodies[:2]
    assert [r["body"] for r in v2["requests"]] == bodies[2:]
    assert v2["argument_comparison"]["exact_call"]
    assert (
        v2["metadata"]["tool_argument_generation"]["version"]
        == "explicit-optional-argument-presence-v2"
    )


def test_required_only_tool_requests_are_identical_to_v1(monkeypatch):
    bodies = install(monkeypatch, [first("lookup_policy"), '{"query":"repair webhook"}'] * 2)
    item = example("lookup_policy", {"query": "repair webhook"})
    run(item, "candidate_v1")
    row = run(item)
    assert bodies[:2] == bodies[2:]
    assert not row["metadata"]["tool_argument_generation"]["optional_presence_policy"][
        "configured_for_second_stage"
    ]


def test_private_label_changes_do_not_change_prompts(monkeypatch):
    bodies = install(monkeypatch, [first(), '{"query":"repair webhook"}'] * 2)
    original = example()
    changed = original.model_copy(
        update={"expected_arguments": {"query": "private", "priority": "low"}}
    )
    run(original)
    run(changed)
    assert bodies[:2] == bodies[2:]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "repair webhook"},
        {"query": "repair webhook", "priority": "normal"},
        {"query": "repair webhook", "priority": "low"},
    ],
)
def test_wrong_model_values_are_not_repaired_or_hidden(monkeypatch, arguments):
    install(monkeypatch, [first(), json.dumps(arguments)])
    row = run(example())
    assert json.loads(row["normalized_output"])["arguments"] == arguments
    assert not row["argument_comparison"]["default_equivalent_call"]
    assert row["argument_comparison"]["execution_eligible"]
    assert row["traces"]["normal"]["steps"][0]["arguments"] == arguments


@pytest.mark.parametrize(
    "response",
    [
        '{"query":"a","query":"b"}',
        '{"query":true}',
        '{"query":"x","priority":"urgent"}',
        "[]",
        TimeoutError("second stage failed"),
    ],
)
def test_bad_second_stage_still_fails_closed(monkeypatch, response):
    install(monkeypatch, [first(), response])
    row = run(example())
    assert not row["argument_comparison"]["execution_eligible"]
    for trace in row["traces"].values():
        assert trace["fault_scenario"]["handler_invocation_count"] == 0


def test_unknown_tool_does_not_trigger_second_call(monkeypatch):
    bodies = install(monkeypatch, [first("unknown")])
    row = run(example())
    assert len(bodies) == 1
    assert not row["argument_comparison"]["execution_eligible"]
    assert row["metadata"]["tool_argument_generation"]["status"] == "skipped"


@pytest.mark.parametrize("priority", ["high", "low", "normal", None])
def test_nullable_protocol_copies_values_and_uses_model_null_as_omission(monkeypatch, priority):
    expected = example().model_copy(update={"expected_arguments": {"query": "repair webhook"}})
    if priority is not None:
        expected = expected.model_copy(
            update={"expected_arguments": {"query": "repair webhook", "priority": priority}}
        )
    raw = json.dumps({"query": "repair webhook", "priority": priority})
    bodies = install(monkeypatch, [first(), raw])
    row = run(expected, "candidate_v3")
    assert row["argument_comparison"]["exact_call"]
    assert row["metadata"]["tool_argument_generation"]["second_stage"]["raw_output"] == raw
    schema = bodies[1]["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["query", "priority"]
    assert schema["properties"]["priority"]["anyOf"][1] == {"type": "null"}
    public = json.loads(bodies[1]["messages"][1]["content"])["selected_tool"]["argument_schema"]
    assert public["required"] == ["query"]
    audit = row["metadata"]["tool_argument_generation"]["presence_decoding"]
    assert audit["omitted_optional_fields"] == (["priority"] if priority is None else [])
    assert audit["values_repaired"] is False
    assert row["traces"]["normal"]["steps"][0]["arguments"] == expected.expected_arguments
    assert row["measured_tokens"] == {"prompt_tokens": 20, "completion_tokens": 10}


def test_nullable_protocol_does_not_replace_null_with_expected_high(monkeypatch):
    install(monkeypatch, [first(), '{"query":"repair webhook","priority":null}'])
    row = run(example(), "candidate_v3")
    assert not row["argument_comparison"]["default_equivalent_call"]
    assert json.loads(row["normalized_output"])["arguments"] == {"query": "repair webhook"}


@pytest.mark.parametrize(
    "bad",
    [
        '{"query":"repair webhook"}',
        '{"query":null,"priority":"high"}',
        '{"query":"x","priority":"high","extra":null}',
        '{"query":"x","priority":null,"priority":"high"}',
        TimeoutError("timeout"),
    ],
)
def test_nullable_protocol_rejects_incomplete_or_invalid_wire_responses(monkeypatch, bad):
    install(monkeypatch, [first(), bad])
    row = run(example(), "candidate_v3")
    assert not row["argument_comparison"]["execution_eligible"]
    assert row["traces"]["normal"]["fault_scenario"]["handler_invocation_count"] == 0


def test_nullable_required_only_requests_match_v1(monkeypatch):
    bodies = install(monkeypatch, [first("lookup_policy"), '{"query":"repair webhook"}'] * 2)
    item = example("lookup_policy", {"query": "repair webhook"})
    run(item, "candidate_v1")
    run(item, "candidate_v3")
    assert bodies[:2] == bodies[2:]


def test_nullable_schema_and_decoder_do_not_mutate_public_schema():
    public = build_fault_tool_registry().get("create_ticket").descriptor.argument_schema
    before = copy.deepcopy(public)
    wire, optional = nullable_wire_schema(public)
    assert public == before and optional == ["priority"]
    assert wire != public
    values, _ = decode_nullable_arguments('{"query":"x","priority":null}', public)
    assert values == {"query": "x"} and public == before


def test_nullable_requests_are_invariant_to_private_labels(monkeypatch):
    bodies = install(monkeypatch, [first(), '{"query":"repair webhook","priority":"high"}'] * 2)
    original = example()
    changed = original.model_copy(
        update={"expected_arguments": {"query": "private", "priority": "low"}}
    )
    run(original, "candidate_v3")
    run(changed, "candidate_v3")
    assert bodies[:2] == bodies[2:]


def test_fresh_pack_has_two_cases_per_priority_condition():
    root = Path(__file__).resolve().parents[2]
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    path = root / "reference_workload/diagnostics/tool-presence-fresh-v1.json"
    data = json.loads(path.read_text("utf-8"))
    manifest = json.loads(
        (root / "reference_workload/revisions/1.0.4/manifest.json").read_text("utf-8")
    )
    context = {
        "corpus_hash": data["corpus_hash"],
        "document_ids": [f["path"] for f in manifest["corpus"]["files"]],
    }
    pack = load_baseline_pack(path, build_fault_tool_registry(), context)
    assert len(pack.cases) == 14
    for priority in ("high", "low", "normal", None):
        assert (
            sum(
                c.expected_tool == "create_ticket"
                and c.expected_arguments.get("priority") == priority
                for c in pack.cases
            )
            == 2
        )


@pytest.mark.parametrize("existing", ["report", "journal"])
def test_output_preflight_prevents_inference(monkeypatch, tmp_path, existing):
    path = tmp_path / "result.json"
    protected = path if existing == "report" else path.with_suffix(".observations.jsonl")
    protected.write_text("keep", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["presence", "--cohort", "development", "--output", str(path)])
    monkeypatch.setattr(
        "app.reference_workload.tool_presence_diagnostic.load_previous",
        lambda *a: pytest.fail("should not load"),
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    assert protected.read_text("utf-8") == "keep"
