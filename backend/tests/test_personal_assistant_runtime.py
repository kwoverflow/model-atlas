import json
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.contracts import GuardError, canonical
from app.services.personal_assistant.drafts import parse_draft
from app.services.personal_assistant.inference import (
    OllamaGenerateDraftAdapter,
    decoding_schema,
    draft_schema,
)


def body():
    return {
        "model": "qwen3.5:9b",
        "messages": [
            {"role": "system", "content": "Fixed public prompt"},
            {"role": "user", "content": '{"request":"User request"}'},
        ],
        "temperature": 0,
        "top_p": 1,
        "max_tokens": 768,
        "reasoning_effort": "none",
        "seed": 42,
    }


def test_decoding_hints_are_separate_from_strict_acceptance():
    strict, hints = draft_schema(), decoding_schema()
    assert strict["properties"]["reason"]["maxLength"] == 2000
    assert "maxLength" not in hints["properties"]["reason"]
    for name, field in (("CalendarCreate", "local_start"), ("TodoCreate", "local_due")):
        assert "[0-9]" in hints["$defs"][name]["properties"][field]["anyOf"][0]["pattern"]
        hints["$defs"][name]["properties"][field]["anyOf"][0]["pattern"] = strict["$defs"][name][
            "properties"
        ][field]["anyOf"][0]["pattern"]
    hints["properties"]["reason"]["maxLength"] = 2000
    assert hints == strict


def test_reason_hint_does_not_weaken_postvalidation():
    value = {"decision": "clarify", "intent": None, "reason": "x" * 2001}
    validate(value, decoding_schema())
    with pytest.raises(ValidationError):
        validate(value, draft_schema())
    with pytest.raises(GuardError, match="invalid_draft_reason"):
        parse_draft(canonical(value))


def test_native_request_preserves_roles_input_seed_and_context(monkeypatch):
    adapter = OllamaGenerateDraftAdapter()
    request = body()
    expected = json.loads(json.dumps(request))
    config = SimpleNamespace(context_length=8192)
    captured = {}

    def transport(configuration, base_url, native, *, deadline):
        captured.update(url=base_url, body=native, deadline=deadline)
        return {
            "done": True,
            "done_reason": "stop",
            "response": "  RAW  ",
            "prompt_eval_count": 20,
            "eval_count": 10,
        }

    monkeypatch.setattr(adapter, "_post_generate", transport)
    response = adapter._post_json(
        config, "http://127.0.0.1:11435", "/v1/chat/completions", request, deadline=123
    )
    assert request == expected
    assert captured["deadline"] == 123
    native = captured["body"]
    assert native["system"] == request["messages"][0]["content"]
    assert native["prompt"] == request["messages"][1]["content"]
    assert native["think"] is False and native["truncate"] is False
    assert "raw" not in native and "context" not in native
    assert native["format"] == decoding_schema()
    assert native["options"] == {
        "num_ctx": 8192,
        "num_predict": 768,
        "temperature": 0,
        "top_p": 1,
        "seed": 42,
    }
    assert response["choices"][0]["message"]["content"] == "  RAW  "
    assert response["usage"] == {"prompt_tokens": 20, "completion_tokens": 10}


@pytest.mark.parametrize("done,reason", [(False, "stop"), (True, "length"), (True, None)])
def test_incomplete_native_response_is_not_accepted(monkeypatch, done, reason):
    adapter = OllamaGenerateDraftAdapter()
    monkeypatch.setattr(
        adapter,
        "_post_generate",
        lambda *_a, **_k: {
            "done": done,
            "done_reason": reason,
            "response": '{"valid":"looking JSON"}',
        },
    )
    with pytest.raises(GuardError, match="draft_generation_incomplete"):
        adapter._post_json(
            SimpleNamespace(context_length=8192),
            "http://127.0.0.1:11435",
            "/v1/chat/completions",
            body(),
        )


@pytest.mark.parametrize(
    "change,error",
    [
        ("roles", "single_turn_draft_required"),
        ("thinking", "nonthinking_draft_required"),
    ],
)
def test_adapter_rejects_unreviewed_modes(change, error):
    request = body()
    if change == "roles":
        request["messages"].append({"role": "assistant", "content": "Earlier action"})
    else:
        request["reasoning_effort"] = "high"
    with pytest.raises(GuardError, match=error):
        OllamaGenerateDraftAdapter.generate_body(SimpleNamespace(context_length=8192), request)
