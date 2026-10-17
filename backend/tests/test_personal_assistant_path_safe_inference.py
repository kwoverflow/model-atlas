import json
from types import SimpleNamespace

import pytest

from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.path_safe_inference import (
    PROMPT,
    STRATEGY,
    PathSafeDraftAdapter,
    configuration_hash,
    generate_path_safe_draft,
)
from app.services.personal_assistant.stable_inference import public_payload


@pytest.mark.parametrize("seed", [42, 1729])
def test_successor_keeps_raw_output_and_records_actual_prompt_hash(monkeypatch, seed):
    raw = '{"decision":"refuse","intent":null,"reason":"경계 위반"}'
    captured = {}

    def run(self, *, configuration, evaluation_case, seed):
        captured["system"] = self._system_prompt(configuration, evaluation_case)
        captured["public"] = self._user_message_payload(evaluation_case)
        captured["seed"] = seed
        return SimpleNamespace(raw_output=raw, end_to_end_latency_ms=12)

    monkeypatch.setattr(PathSafeDraftAdapter, "run_case", run)
    text = "../a.txt를 Archive/a.txt로 옮겨줘."
    state = {"events": [], "tasks": [], "files": {}}
    result = generate_path_safe_draft(text, state, "http://127.0.0.1:11435", seed=seed, now="fixed")
    assert result["raw_output"] == raw and result["schema_valid"]
    assert result["strategy"] == STRATEGY
    assert result["configuration_hash"] == configuration_hash(text, seed)
    assert captured == {
        "system": PROMPT,
        "public": public_payload(text, state, now="fixed"),
        "seed": seed,
    }


def test_no_post_output_refusal_repair(monkeypatch):
    raw = json.dumps(
        {
            "decision": "propose",
            "intent": {"operation": "files.move", "source": "../x", "destination": "Archive/x"},
            "reason": "Wrong model output must remain visible",
        }
    )
    monkeypatch.setattr(
        PathSafeDraftAdapter,
        "run_case",
        lambda *_args, **_kwargs: SimpleNamespace(raw_output=raw, end_to_end_latency_ms=12),
    )
    result = generate_path_safe_draft(
        "request", {"events": [], "tasks": [], "files": {}}, "http://127.0.0.1:11435"
    )
    assert result["raw_output"] == raw
    assert json.loads(result["raw_output"])["decision"] == "propose"


def test_successor_preserves_isolated_runtime_requirement():
    with pytest.raises(GuardError, match="isolated_runtime_required"):
        generate_path_safe_draft("request", {}, "https://elsewhere.example")


def test_configuration_hash_is_sensitive_to_seed_and_public_grounding():
    assert configuration_hash("'x'를 추가해줘.", 42) != configuration_hash("'y'를 추가해줘.", 42)
    assert configuration_hash("request", 42) != configuration_hash("request", 1729)
