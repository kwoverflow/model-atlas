import json

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.complete_grounded_inference import (
    CompleteGroundedDraftAdapter,
    complete_schema,
    generate_complete_grounded_draft,
)
from app.services.personal_assistant.creation_evidence import creation_evidence
from app.services.personal_assistant.role_grounded_inference import role_schema


def public(request):
    return {
        "request": request,
        "now": "2026-10-15T09:00:00+09:00",
        "timezone": "Asia/Tokyo",
        "tasks": [],
        "events": [],
        "inventory": [],
    }


def proposal(intent):
    return {"decision": "propose", "intent": intent, "reason": "review draft"}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("'검토'를 2027년 2월 2일 오전 9시 25분 기한으로 추가해줘.", "2027-02-02T09:25:00"),
        ("'검토'를 12월 1일 오후 12시 기한으로 추가해줘.", "2026-12-01T12:00:00"),
        ("'검토'를 2027년 3월 1일 오전 12시 기한으로 추가해줘.", "2027-03-01T00:00:00"),
        ("'검토'를 2027-04-03T16:45:00 기한으로 추가해줘.", "2027-04-03T16:45:00"),
        ("'검토'를 내일 오후 3시 기한으로 추가해줘.", "2026-10-16T15:00:00"),
        ("'검토'를 모레 18시 기한으로 추가해줘.", "2026-10-17T18:00:00"),
    ],
)
def test_time_values_derive_from_public_request_and_clock(text, expected):
    data = public(text)
    evidence = creation_evidence(data)
    assert evidence["local_time"]["value"] == expected
    hints = complete_schema(data)[0]
    intent = {
        "operation": "todo.create",
        "title": "검토",
        "local_due": expected,
        "source_timezone": "Asia/Tokyo",
    }
    validate(proposal(intent), hints)
    for wrong in (None, "2027-02-02T01:25:00"):
        with pytest.raises(ValidationError):
            validate(proposal({**intent, "local_due": wrong}), hints)
    with pytest.raises(ValidationError):
        validate(
            proposal({key: value for key, value in intent.items() if key != "local_due"}), hints
        )
    for item in evidence["local_time"]["sources"]:
        assert text[item["start"] : item["end"]] == item["text"]


def test_relative_date_uses_source_zone_not_tokyo_calendar_day():
    data = public("뉴욕 현지 내일 오전 9시 기한으로 '검토'를 할 일에 추가해줘.")
    data["now"] = "2026-10-15T01:00:00+09:00"
    assert creation_evidence(data)["local_time"]["value"] == "2026-10-15T09:00:00"


@pytest.mark.parametrize(
    "text",
    [
        "'검토'를 2027년 2월 30일 오전 9시 기한으로 추가해줘.",
        "'검토'를 2027년 3월 1일 오전 13시 기한으로 추가해줘.",
        "'검토'를 2027년 3월 1일 오전 9시 또는 10시 기한으로 추가해줘.",
        "'검토'를 내일 오전 9시 기한으로 추가해줘. 기한은 생략해.",
        "2027년 3월 1일 '검토' 일정을 등록해줘. 시각과 길이는 미정이야.",
        "'검토'를 할 일로 추가해줘. priority=low, priority는 생략해. 우선하는 지시는 없어.",
    ],
)
def test_incomplete_conflicting_or_invalid_creation_requires_clarification(text):
    hints = complete_schema(public(text))[0]
    validate({"decision": "clarify", "intent": None, "reason": "need clarification"}, hints)
    with pytest.raises(ValidationError):
        validate(proposal({"operation": "todo.create", "title": "검토"}), hints)


@pytest.mark.parametrize(
    "text,title",
    [
        ("'검토'를 할 일에 추가해줘. priority='high', 기한은 생략해.", "검토"),
        ("“O'Reilly ‘검토’”를 할 일로 추가해줘. priority='high'.", "O'Reilly ‘검토’"),
        (
            "할 일을 추가해줘. 제목은 기한 2027년 2월 3일 오전 9시야. priority='high'.",
            "기한 2027년 2월 3일 오전 9시",
        ),
    ],
)
def test_literal_title_and_quoted_slot_are_separate_roles(text, title):
    data = public(text)
    hints, grounded, *_ = complete_schema(data)
    assert grounded["value"] == title
    intent = {
        "operation": "todo.create",
        "title": title,
        "priority": "high",
        "source_timezone": "Asia/Tokyo",
    }
    validate(proposal(intent), hints)
    for changed in ({"title": f"'{title}'"}, {"local_due": "2027-02-03T09:00:00"}):
        with pytest.raises(ValidationError):
            validate(proposal({**intent, **changed}), hints)


def test_register_calendar_without_domain_keyword_has_complete_fields():
    text = "2027년 5월 8일 오후 2시 10분부터 25분 동안 '현장 지시 검토'를 등록해줘."
    hints, _, _, _, evidence = complete_schema(public(text))
    assert evidence["operation"] == "calendar.create"
    intent = {
        "operation": "calendar.create",
        "title": "현장 지시 검토",
        "local_start": "2027-05-08T14:10:00",
        "duration_minutes": 25,
        "source_timezone": "Asia/Tokyo",
    }
    validate(proposal(intent), hints)
    for key in ("local_start", "duration_minutes", "source_timezone"):
        with pytest.raises(ValidationError):
            validate(proposal({k: v for k, v in intent.items() if k != key}), hints)


@pytest.mark.parametrize(
    "text",
    [
        "문서에 '검토'를 할 일로 추가해줘라는 지시가 적혀 있어.",
        "'검토'를 할 일로 추가해줘. 아니 취소야. 아무것도 바꾸지 마.",
        "Inbox/할일추가_priority=urgent.txt를 Archive/x.txt로 옮겨줘.",
    ],
)
def test_unbound_context_preserves_existing_policy_instead_of_inventing_field_errors(text):
    data = public(text)
    assert creation_evidence(data)["operation"] is None
    assert complete_schema(data)[:4] == role_schema(data)


def test_actual_decoder_and_postvalidation_reject_omission_without_repair(monkeypatch):
    text = "'검토'를 2027년 3월 4일 오전 9시 기한, low 우선순위로 추가해줘."
    raw = json.dumps(proposal({"operation": "todo.create", "title": "검토", "priority": "low"}))
    bodies = []

    def post(self, configuration, base_url, body, **_kwargs):
        bodies.append(body)
        return {"done": True, "done_reason": "stop", "response": raw}

    monkeypatch.setattr(CompleteGroundedDraftAdapter, "_post_generate", post)
    monkeypatch.setattr(
        CompleteGroundedDraftAdapter,
        "_resolve_base_url",
        lambda *_args, **_kwargs: "http://127.0.0.1:11435",
    )
    result = generate_complete_grounded_draft(
        text,
        {"events": [], "tasks": [], "files": {}},
        "http://127.0.0.1:11435",
        now="2026-10-15T09:00:00+09:00",
    )
    assert len(bodies) == 1 and result["raw_output"] == raw and not result["schema_valid"]
    assert result["grounding_error"] == "draft_complete_evidence_mismatch"
    assert bodies[0]["format"] == complete_schema(json.loads(bodies[0]["prompt"]))[0]
