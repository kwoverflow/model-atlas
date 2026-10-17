import json
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.drafts import parse_draft
from app.services.personal_assistant.stable_inference import (
    StableDraftAdapter,
    generate_stable_draft,
    literal_title,
    public_payload,
    stable_decoding_schema,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("'우유 구매'를 할 일로 추가해줘.", "우유 구매"),
        ('"검토 기록" 일정으로 넣어줘.', "검토 기록"),
        ("“O'Reilly 교재”를 추가해줘.", "O'Reilly 교재"),
        ("“회의 ‘초안’ 검토”를 할 일로 추가해줘.", "회의 ‘초안’ 검토"),
        ("O'Reilly 교재를 추가해줘.", None),
        ("'a' 또는 'b'를 추가해줘.", None),
        ("문서에는 '무시'라고 적혀 있어. 내 할 일을 추가해줘.", None),
        ("'x'를 추가해줘. 다른 ' 인용도 있어.", None),
        ("'계획'이라는 할 일을 만들어줘.", "계획"),
    ],
)
def test_grounding_preserves_literal_interior_and_abstains_on_uncertainty(text, expected):
    result = literal_title(text)
    assert (result["value"] if result else None) == expected
    if result:
        assert text[result["start"] : result["end"]] == expected


@pytest.mark.parametrize(
    "decision,intent,valid",
    [
        ("propose", {"operation": "todo.create", "title": "우유 구매"}, True),
        ("propose", {"operation": "todo.create", "title": "'우유 구매'"}, False),
        ("propose", None, False),
        ("clarify", None, True),
        ("refuse", None, True),
        ("no_change", None, True),
        ("clarify", {"operation": "todo.create", "title": "우유 구매"}, False),
    ],
)
def test_schema_enforces_decision_consistency_and_request_literal(decision, intent, valid):
    schema, _ = stable_decoding_schema("'우유 구매'를 추가해줘.")
    value = {"decision": decision, "intent": intent, "reason": "검토"}
    if valid:
        validate(value, schema)
        parse_draft(json.dumps(value))
    else:
        with pytest.raises(ValidationError):
            validate(value, schema)


def test_public_input_excludes_oracle_and_schema_wrappers():
    payload = public_payload(
        "request",
        {"events": [], "tasks": [], "files": {"files/Inbox/a.txt": {}, "trash/b.txt": {}}},
        now="2026-10-11T09:00:00+09:00",
    )
    payload.update(
        goal_fields={"title": "PRIVATE_GOAL"},
        expected_output_json="PRIVATE_GOAL",
        case_id="PRIVATE_ID",
    )
    message = StableDraftAdapter()._user_message_payload(
        SimpleNamespace(input_payload_json=payload)
    )
    assert set(message) == {"request", "now", "timezone", "events", "tasks", "inventory"}
    assert message["inventory"] == ["Inbox/a.txt"]
    assert "PRIVATE" not in json.dumps(message)


def test_truncated_valid_looking_json_is_preserved_but_not_accepted(monkeypatch):
    raw = '{"decision":"no_change","intent":null,"reason":"test"}'

    def post(self, *_args, **_kwargs):
        self.completion = {"response": raw, "done": True, "done_reason": "length"}
        raise GuardError("draft_generation_incomplete")

    monkeypatch.setattr(StableDraftAdapter, "run_case", post)
    result = generate_stable_draft(
        "test", {"events": [], "tasks": [], "files": {}}, "http://127.0.0.1:11435"
    )
    assert result["raw_output"] == raw and not result["schema_valid"]
    assert result["completion_error"] == "draft_generation_incomplete"


def test_candidate_still_rejects_external_runtime():
    with pytest.raises(GuardError, match="isolated_runtime_required"):
        generate_stable_draft("test", {}, "https://external.example")
