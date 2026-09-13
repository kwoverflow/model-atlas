import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.reference_workload.runtime_matrix import RuntimeMatrixEntry
from app.reference_workload.ticket_priority_diagnostic import (
    IntentCase,
    IntentPack,
    load_cases,
    main,
    measured_usage,
    observe_intent,
    summarize,
)
from app.reference_workload.tool_fault_cases import prepare_baseline_cases
from app.reference_workload.tool_two_stage_diagnostic import configuration_for
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.ticket_priority_verification import (
    PriorityIntent,
    TicketPriorityVerifier,
    classifier_response_schema,
    parse_priority_intent,
    priority_block_reason,
)
from app.services.tool_execution import build_fault_tool_registry

CONTEXT = {"corpus_hash": "a" * 64, "document_ids": ["docs/example.md"]}


def item():
    return IntentCase(
        id="TCI-001",
        cohort="development",
        stratum="set",
        request="Create a ticket. query='Keep original'. priority=low. Do not omit priority.",
        expected_tool="create_ticket",
        expected_action="execute",
        expected_arguments={"query": "Keep original", "priority": "low"},
        expected_intent="set",
    )


def config():
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


def decision(action="set", value="low", evidence="priority=low"):
    return json.dumps({"action": action, "value": value, "evidence": evidence})


def install(monkeypatch, outputs):
    stream = iter(outputs)
    bodies = []

    def response(self, configuration, base_url, path, body, *, deadline):
        bodies.append(copy.deepcopy(body))
        output = next(stream)
        if isinstance(output, Exception):
            raise output
        raw, finish = output if isinstance(output, tuple) else (output, "stop")
        return {
            "choices": [{"message": {"content": raw}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr(OpenAICompatibleAdapter, "_post_json", response)
    monkeypatch.setattr(OpenAICompatibleAdapter, "_resolve_base_url", lambda *a, **k: "http://test")
    return bodies


def outputs(priority=None, check=None, tool="create_ticket"):
    args = {"query": "Keep original"}
    if tool == "create_ticket":
        args["priority"] = priority
    return [
        json.dumps({"tool_name": tool, "arguments": {"query": "stage one"}}),
        json.dumps(args),
        check or decision(),
    ]


def observe(case=None):
    return observe_intent(
        case or item(), config(), build_fault_tool_registry(), CONTEXT, seed=42, order="registered"
    )


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"set","value":"low","evidence":"priority=low","extra":true}',
        '{"action":"set","value":"low","value":"high","evidence":"priority=low"}',
        decision("set", "none"),
        decision("omit", "low"),
        decision("set", "low", ""),
        decision("set", "low", "invented priority=low"),
        decision("set", "high", "priority=low"),
        decision("unspecified", "none", "priority=low"),
        decision("clarify", "none", ""),
        '{"action":"set","value":NaN,"evidence":"priority=low"}',
        "[]",
    ],
)
def test_invalid_classifier_contract_fails_closed(raw):
    with pytest.raises(ValueError):
        parse_priority_intent(raw, item().request)


@pytest.mark.parametrize(
    "action,value,evidence,args,reason",
    [
        ("set", "low", "priority=low", {"priority": "low"}, None),
        ("set", "low", "priority=low", {}, "explicit_priority_mismatch"),
        ("set", "high", "priority=high", {"priority": "low"}, "explicit_priority_mismatch"),
        ("omit", "none", "omit", {}, None),
        ("omit", "none", "omit", {"priority": "normal"}, "priority_should_be_absent"),
        ("unspecified", "none", "", {}, None),
        (
            "clarify",
            "none",
            "conflict",
            {"priority": "low"},
            "priority_intent_requires_clarification",
        ),
    ],
)
def test_veto_never_changes_arguments(action, value, evidence, args, reason):
    before = copy.deepcopy(args)
    intent = PriorityIntent(action=action, value=value, evidence=evidence)
    assert priority_block_reason(intent, args) == reason
    assert args == before


def test_wrong_null_is_blocked_without_repair_and_model_sees_no_proposal(monkeypatch):
    bodies = install(monkeypatch, outputs())
    row = observe()
    assert "error" not in row
    assert row["verification"]["reason"] == "explicit_priority_mismatch"
    assert json.loads(row["proposal"])["arguments"] == {"query": "Keep original"}
    payload = json.loads(bodies[2]["messages"][1]["content"])
    assert payload["request"] == item().request
    assert "expected_arguments" not in json.dumps(payload) and "stage one" not in json.dumps(
        payload
    )
    assert "proposal" not in payload
    assert row["proposal_tokens"] == {"prompt_tokens": 20, "completion_tokens": 10}
    assert row["verification_tokens"] == {"prompt_tokens": 10, "completion_tokens": 5}
    assert row["traces"]["v3"]["normal"]["fault_scenario"]["handler_invocation_count"] == 1
    for trace in row["traces"]["v3_verified"].values():
        assert trace["fault_scenario"]["handler_invocation_count"] == 0
        assert trace["fault_scenario"]["injected_failure_count"] == 0
        assert trace["steps"][0]["arguments"] == {"query": "Keep original"}


def test_correct_call_is_passed_unchanged(monkeypatch):
    install(monkeypatch, outputs("low"))
    row = observe()
    assert row["verification"]["execution_allowed"]
    for variant in row["traces"].values():
        assert variant["normal"]["steps"][0]["arguments"] == item().expected_arguments
    stats = summarize([row], [item()])
    assert stats["v3_verified"]["exact_completed"] == 1
    assert stats["v3_verified"]["correct_proposal_blocked"] == 0


@pytest.mark.parametrize(
    "bad",
    [
        TimeoutError("budget exhausted"),
        "{}",
        (decision(), "length"),
        decision("set", "low", "fabricated"),
    ],
)
def test_classifier_failures_cannot_execute(monkeypatch, bad):
    install(monkeypatch, outputs("low", bad))
    row = observe()
    assert row["verification"]["status"] == "failed"
    assert not row["verification"]["execution_allowed"]
    assert row["traces"]["v3_verified"]["normal"]["fault_scenario"]["handler_invocation_count"] == 0
    assert summarize([row], [item()])["v3_verified"]["correct_proposal_blocked"] == 1


def test_clarification_is_a_block_not_a_successful_completion(monkeypatch):
    case = item().model_copy(
        update={
            "request": "priority=low and priority=high conflict",
            "expected_action": "clarify",
            "expected_intent": "clarify",
            "expected_arguments": None,
        }
    )
    install(monkeypatch, outputs("low", decision("clarify", "none", case.request)))
    row = observe(case)
    stats = summarize([row], [case])
    assert row["comparison"] is None
    assert stats["v3"]["unsafe_accepted"] == 1
    assert stats["v3_verified"]["clarification_blocked"] == 1
    assert stats["v3_verified"]["exact_completed"] == 0


def test_private_labels_do_not_change_requests_or_execution(monkeypatch):
    bodies = install(monkeypatch, outputs("low") * 2)
    first = observe()
    changed = item().model_copy(
        update={"expected_arguments": {"query": "Private answer", "priority": "high"}}
    )
    second = observe(changed)
    assert bodies[:3] == bodies[3:]
    assert first["verification"]["reason"] == second["verification"]["reason"]
    for row in (first, second):
        assert (
            row["traces"]["v3_verified"]["normal"]["fault_scenario"]["handler_invocation_count"]
            == 1
        )
    assert first["comparison"]["exact_call"] and not second["comparison"]["exact_call"]


def test_wrong_tool_is_not_blocked_by_evaluator_selection(monkeypatch):
    bodies = install(monkeypatch, outputs(tool="lookup_policy")[:2])
    row = observe()
    assert len(bodies) == 2
    assert row["verification"]["status"] == "out_of_scope"
    assert row["traces"]["v3_verified"]["normal"]["fault_scenario"]["handler_invocation_count"] == 1
    assert summarize([row], [item()])["v3_verified"]["unsafe_accepted"] == 1


def test_public_guard_rejection_skips_classifier(monkeypatch):
    bodies = install(monkeypatch, [json.dumps({"tool_name": "unknown", "arguments": {}})])
    row = observe()
    assert len(bodies) == 1
    assert row["verification"]["reason"] == "public_guard_rejected"
    assert not row["verification"]["execution_allowed"]


def test_expired_shared_deadline_blocks_before_classifier_call(monkeypatch):
    bodies = install(monkeypatch, [])
    case, _ = prepare_baseline_cases(item(), build_fault_tool_registry(), CONTEXT)
    result = TicketPriorityVerifier().verify(
        configuration=config(),
        input_payload=case.input_payload_json,
        proposal=json.dumps({"tool_name": "create_ticket", "arguments": item().expected_arguments}),
        deadline=0,
    )
    assert not bodies and not result["execution_allowed"]
    assert result["error"]["type"] == "TimeoutError"


def test_literal_evidence_does_not_guarantee_correct_semantic_interpretation(monkeypatch):
    install(monkeypatch, outputs(check=decision("omit", "none", "Do not omit priority.")))
    row = observe()
    assert row["verification"]["execution_allowed"]
    assert summarize([row], [item()])["v3_verified"]["unsafe_accepted"] == 1


def test_missing_usage_is_not_reported_as_zero():
    assert measured_usage([]) == {"prompt_tokens": 0, "completion_tokens": 0}
    assert measured_usage([{"error": {}}]) is None


def test_wire_schema_avoids_grammar_expansion_but_local_limit_remains():
    schema = classifier_response_schema()
    assert "maxLength" not in schema["properties"]["evidence"]
    assert PriorityIntent.model_json_schema()["properties"]["evidence"]["maxLength"] == 2000
    with pytest.raises(ValueError):
        parse_priority_intent(decision("omit", "none", "x" * 2001), "x" * 2001)


def test_changed_priority_schema_is_not_silently_supported(monkeypatch):
    bodies = install(monkeypatch, [])
    case, _ = prepare_baseline_cases(item(), build_fault_tool_registry(), CONTEXT)
    descriptor = next(
        d for d in case.input_payload_json["available_tools"] if d["tool_name"] == "create_ticket"
    )
    descriptor["argument_schema"]["required"].append("priority")
    result = TicketPriorityVerifier().verify(
        configuration=config(),
        input_payload=case.input_payload_json,
        proposal=json.dumps({"tool_name": "create_ticket", "arguments": item().expected_arguments}),
    )
    assert not bodies and not result["execution_allowed"]
    assert result["error"]["message"] == "unsupported public priority contract"


def test_case_pack_is_valid_and_has_disjoint_cohorts():
    root = Path(__file__).resolve().parents[2]
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    manifest = json.loads(
        (root / "reference_workload/revisions/1.0.4/manifest.json").read_text("utf-8")
    )
    data = json.loads(
        (root / "reference_workload/diagnostics/ticket-priority-intent-v1.json").read_text("utf-8")
    )
    context = {
        "corpus_hash": data["corpus_hash"],
        "document_ids": [f["path"] for f in manifest["corpus"]["files"]],
    }
    pack = load_cases(root, build_fault_tool_registry(), context)
    assert sum(c.cohort == "development" for c in pack.cases) == 8
    assert sum(c.cohort == "fresh" for c in pack.cases) == 16
    bad = copy.deepcopy(data)
    bad["cases"].append(bad["cases"][0])
    with pytest.raises(ValueError):
        IntentPack.model_validate(bad)


@pytest.mark.parametrize("existing", ["report", "journal"])
def test_preflight_prevents_overwrite_and_inference(monkeypatch, tmp_path, existing):
    path = tmp_path / "result.json"
    protected = path if existing == "report" else path.with_suffix(".observations.jsonl")
    protected.write_text("keep", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["intent", "--cohort", "fresh", "--output", str(path)])
    monkeypatch.setattr(
        "app.reference_workload.ticket_priority_diagnostic.load_previous",
        lambda *a: pytest.fail("must not load"),
    )
    with pytest.raises(SystemExit):
        main()
    assert protected.read_text("utf-8") == "keep"
