import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.reference_workload.runtime_matrix import RuntimeMatrixEntry
from app.reference_workload.tool_fault_baseline import (
    CapturingToolAdapter,
    measure_generation,
    run_entry,
    summarize_rows,
)
from app.reference_workload.tool_fault_cases import (
    FaultBaselineCase,
    FaultBaselinePack,
    load_baseline_pack,
    prepare_baseline_cases,
)
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.tool_call_contract import compile_bounded_tool_call
from app.services.tool_execution import build_fault_tool_registry

CONTEXT = {"corpus_hash": "a" * 64, "document_ids": ["docs/example.md"]}
ITEM = FaultBaselineCase(
    id="TFB-001",
    request="Find policy. Set query to release approval.",
    expected_tool="lookup_policy",
    expected_arguments={"query": "release approval"},
)


def generation(output, public):
    guard = compile_bounded_tool_call(
        output, input_payload=public.input_payload_json, document_context=CONTEXT
    )
    return SimpleNamespace(
        raw_output=output,
        normalized_output=guard.normalized_output,
        metadata={"tool_call_contract": guard.audit_record()},
        prompt_tokens=10,
        completion_tokens=10,
        end_to_end_latency_ms=10,
    )


@pytest.mark.parametrize(
    "kind", ["valid", "wrong_value", "wrong_tool", "missing", "unknown_id", "invalid_json"]
)
def test_metrics_separate_selection_arguments_and_fixture_outcomes(kind):
    registry = build_fault_tool_registry()
    public, evaluator = prepare_baseline_cases(ITEM, registry, CONTEXT)
    output = {
        "valid": '{"tool_name":"lookup_policy","arguments":{"query":"release approval"}}',
        "wrong_value": '{"tool_name":"lookup_policy","arguments":{"query":"unrelated"}}',
        "wrong_tool": '{"tool_name":"lookup_customer","arguments":{"query":"release approval"}}',
        "missing": '{"tool_name":"lookup_policy","arguments":{}}',
        "unknown_id": (
            '{"tool_name":"lookup_internal_document",'
            '"arguments":{"document_id":"missing.md"}}'
        ),
        "invalid_json": '{"tool_name":',
    }[kind]
    result = generation(output, public)
    before = copy.deepcopy(result)
    row = measure_generation(ITEM, public, evaluator, result, registry, CONTEXT)
    assert result.__dict__ == before.__dict__
    assert row["normal_tool_success"] is (kind in {"valid", "wrong_value"})
    assert row["selection_and_arguments_exact"] is (kind == "valid")
    assert row["guard_eligible"] is (kind in {"valid", "wrong_value", "wrong_tool"})
    assert row["traces"]["permanent"]["successful"] is False
    assert row["traces"]["permanent"]["fault_scenario"]["passed"] is (
        kind in {"valid", "wrong_value"}
    )
    hashes = [t["steps"][0]["arguments"] for t in row["traces"].values() if t["steps"]]
    assert all(arguments == hashes[0] for arguments in hashes)
    summary = summarize_rows([row, {"error": {"type": "TimeoutError"}}])
    assert summary["observation_count"] == 2
    assert summary["generated_count"] == 1
    assert summary["error_count"] == 1
    assert summary["mode_outcomes"]["normal"]["trace_count"] == 1


def test_public_input_is_invariant_to_private_labels():
    registry = build_fault_tool_registry()
    public, _ = prepare_baseline_cases(ITEM, registry, CONTEXT)
    changed = ITEM.model_copy(
        update={"expected_tool": "secret-tool", "expected_arguments": {"secret": "value"}}
    )
    another, _ = prepare_baseline_cases(changed, registry, CONTEXT)
    assert public.__dict__ == another.__dict__
    assert public.expected_tool_schema_json == {}
    serialized = json.dumps(public.__dict__)
    assert "simulate_failure" not in serialized
    assert "tool_fault_scenario" not in serialized
    assert "secret" not in serialized


def test_live_adapter_is_called_once_per_trial_and_actual_body_is_captured(monkeypatch):
    bodies = []

    def respond(self, configuration, base_url, path, body, *, deadline):
        bodies.append(copy.deepcopy(body))
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"tool_name": "lookup_policy", "arguments": ITEM.expected_arguments}
                        )
                    },
                    "finish_reason": "stop",
                }
            ]
        }

    monkeypatch.setattr(OpenAICompatibleAdapter, "_post_json", respond)
    monkeypatch.setattr(OpenAICompatibleAdapter, "_resolve_base_url", lambda *a, **k: "http://test")
    entry = RuntimeMatrixEntry(
        name="test",
        base_url_env="BASE",
        model_env="MODEL",
        context_length=4096,
        prompt_bundle="operator-assistant-ko-v1",
        trials=2,
    )
    pack = FaultBaselinePack(
        schema_version="tool-fault-baseline-cases-v1",
        authority="local_authored_diagnostic",
        human_reviewed=False,
        gate_evidence=False,
        corpus_hash=CONTEXT["corpus_hash"],
        cases=(ITEM,),
    )
    outcome = run_entry(
        entry,
        SimpleNamespace(base_url="http://test", model_name="test"),
        pack,
        build_fault_tool_registry(),
        CONTEXT,
        adapter=CapturingToolAdapter(),
    )
    assert len(bodies) == 2
    assert [b["seed"] for b in bodies] == [42, 43]
    assert bodies[0]["messages"] == bodies[1]["messages"]
    assert outcome["summary"]["normal_tool_success"] == 2
    for row, body in zip(outcome["rows"], bodies, strict=True):
        assert row["request_body"] == body
        assert row["finish_reason"] == "stop"
        assert len(row["traces"]) == 3
        assert "expected_tool" not in json.dumps(body)
        assert "simulate_failure" not in json.dumps(body)


def test_missing_adapter_audit_is_not_silently_treated_as_eligible():
    registry = build_fault_tool_registry()
    public, evaluator = prepare_baseline_cases(ITEM, registry, CONTEXT)
    result = generation(
        '{"tool_name":"lookup_policy","arguments":{"query":"release approval"}}', public
    )
    result.metadata = {}
    with pytest.raises(ValueError, match="guard audit"):
        measure_generation(ITEM, public, evaluator, result, registry, CONTEXT)


def test_pack_rejects_duplicate_ids_and_claims_of_approval():
    data = dict(
        schema_version="tool-fault-baseline-cases-v1",
        authority="local_authored_diagnostic",
        human_reviewed=False,
        gate_evidence=False,
        corpus_hash=CONTEXT["corpus_hash"],
    )
    with pytest.raises(ValueError, match="unique"):
        FaultBaselinePack(**data, cases=[ITEM, ITEM])
    with pytest.raises(ValueError):
        FaultBaselinePack(**{**data, "human_reviewed": True}, cases=[ITEM])


def test_versioned_case_pack_is_compatible_with_real_registry_and_corpus(tmp_path):
    # Source pack is mounted separately in Docker, not copied into the backend image.
    root = Path(__file__).resolve().parents[2]
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    source = root / "reference_workload/diagnostics/tool-fault-baseline-v1.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    manifest = json.loads(
        (root / "reference_workload/revisions/1.0.4/manifest.json").read_text(encoding="utf-8")
    )
    context = {
        "corpus_hash": data["corpus_hash"],
        "document_ids": [f["path"] for f in manifest["corpus"]["files"]],
    }
    registry = build_fault_tool_registry()
    pack = load_baseline_pack(source, registry, context)
    assert len(pack.cases) == 12
    data["cases"][0]["expected_arguments"]["simulate_failure"] = "transient_once"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid expected"):
        load_baseline_pack(bad, registry, context)
    with pytest.raises(ValueError, match="corpus hash"):
        load_baseline_pack(source, registry, {**context, "corpus_hash": "b" * 64})
