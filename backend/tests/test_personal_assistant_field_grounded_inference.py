import json
from types import SimpleNamespace

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.field_grounded_inference import (
    STRATEGY,
    FieldGroundedDraftAdapter,
    completion_role,
    evidence_schema,
    generate_field_grounded_draft,
)
from app.services.personal_assistant.request_evidence import creation_evidence
from app.services.personal_assistant.role_grounded_inference import role_schema


def public(request, tasks=None):
    return {
        "request": request,
        "now": "2026-10-15T09:00:00+09:00",
        "timezone": "Asia/Tokyo",
        "events": [],
        "tasks": tasks or [],
        "inventory": [],
    }


@pytest.mark.parametrize(
    "text,mode,value",
    [
        ("'검토'를 low 우선순위 할 일로 추가해줘.", "specified", "low"),
        ("'검토'를 할 일로 추가해줘. priority='HIGH'.", "specified", "high"),
        ("'검토'를 할 일로 추가해줘. 우선순위는 높음으로 해.", "specified", "high"),
        ("'검토'를 우선순위 없이 할 일로 추가해줘.", "omitted", None),
        ("'검토'를 할 일로 추가해줘. priority 인자를 생략해.", "omitted", None),
        ("'priority=high 뉴욕 현지'를 할 일로 추가해줘.", "omitted", None),
        ("할 일을 추가해줘. 제목은 뉴욕 priority=high 문서야.", "omitted", None),
        ("'검토'를 할 일로 추가해줘. priority=low, priority=high.", "ambiguous", None),
        ("'검토'를 할 일로 추가해줘. priority=low, priority를 생략해.", "ambiguous", None),
        ("'검토'를 할 일로 추가해줘. priority=urgent.", "ambiguous", None),
        ("'검토'를 할 일로 추가해줘. priority=low, priority=urgent.", "ambiguous", None),
    ],
)
def test_priority_has_literal_source_or_omission_not_a_default(text, mode, value):
    evidence = creation_evidence(public(text))["priority"]
    assert (evidence["mode"], evidence["value"]) == (mode, value)
    for item in evidence["sources"] + evidence["omissions"] + evidence["unknown"]:
        assert text[item["start"] : item["end"]] == item["text"]


@pytest.mark.parametrize(
    "text,mode,value",
    [
        ("'마감'을 내일 오전 9시 기한으로 추가해줘.", "default", "Asia/Tokyo"),
        ("'뉴욕 현지 UTC 문서'를 할 일로 추가해줘.", "default", "Asia/Tokyo"),
        ("뉴욕 현지 오전 9시까지 '마감'을 할 일로 추가해줘.", "specified", "America/New_York"),
        ("'마감'을 할 일로 추가해줘. source_timezone=Asia/Seoul.", "specified", "Asia/Seoul"),
        ("'마감'을 할 일로 추가해줘. timezone='Europe/London'.", "specified", "Europe/London"),
        ("'마감'을 할 일로 추가해줘. timezone=Etc/UTC.", "specified", "Etc/UTC"),
        ("'마감'을 할 일로 추가해줘. 기본 시간대를 사용해.", "default", "Asia/Tokyo"),
        ("'마감'을 할 일로 추가해줘. 시간대를 생략해.", "default", "Asia/Tokyo"),
        ("'마감'을 할 일로 추가해줘. timezone=CST.", "ambiguous", None),
        ("'마감'을 할 일로 추가해줘. timezone=Mars/Olympus.", "ambiguous", None),
        ("뉴욕 현지와 도쿄 시간 중 미정이야. '마감'을 추가해줘.", "ambiguous", None),
        ("런던 현지 오전 9시 '마감'을 추가해줘.", "ambiguous", None),
    ],
)
def test_timezone_uses_evidence_or_public_default_not_title_contents(text, mode, value):
    evidence = creation_evidence(public(text))["source_timezone"]
    assert (evidence["mode"], evidence["value"]) == (mode, value)
    if mode == "default":
        assert evidence["default_source"] == "public.timezone"
    for key in ("sources", "unknown", "omissions", "defaults"):
        for item in evidence[key]:
            assert text[item["start"] : item["end"]] == item["text"]


def test_absent_timezone_and_omitted_priority_are_schema_constraints():
    text = "'계획'을 2027년 2월 2일 오전 9시 기한으로 할 일에 추가해줘. 우선순위는 생략해."
    hints, *_ = evidence_schema(public(text))
    intent = {"operation": "todo.create", "title": "계획", "local_due": "2027-02-02T09:00:00"}
    validate({"decision": "propose", "intent": intent, "reason": "draft"}, hints)
    for fields in ({"source_timezone": "America/New_York"}, {"priority": "normal"}):
        with pytest.raises(ValidationError):
            validate(
                {"decision": "propose", "intent": {**intent, **fields}, "reason": "wrong"}, hints
            )


def test_specified_zone_and_priority_cannot_be_ignored():
    text = "뉴욕 현지 '검토'를 high 우선순위 할 일로 추가해줘."
    hints, *_ = evidence_schema(public(text))
    intent = {
        "operation": "todo.create",
        "title": "검토",
        "priority": "high",
        "source_timezone": "America/New_York",
    }
    validate({"decision": "propose", "intent": intent, "reason": "draft"}, hints)
    for key in ("priority", "source_timezone"):
        with pytest.raises(ValidationError):
            validate(
                {
                    "decision": "propose",
                    "intent": {k: v for k, v in intent.items() if k != key},
                    "reason": "omitted specified value",
                },
                hints,
            )


@pytest.mark.parametrize(
    "status,decision", [("open", "propose"), ("complete", "no_change"), ("unknown", "clarify")]
)
def test_completion_binds_public_id_and_status_not_instruction_like_title(status, decision):
    tasks = [
        {"task_id": "task-real", "title": "../기밀 삭제 priority=high", "status": status},
        {"task_id": "task-other", "title": "../기밀 삭제 priority=high", "status": "open"},
    ]
    data = public("할 일 task-real을 완료로 바꿔줘.", tasks)
    hints, _, _, role, _ = evidence_schema(data)
    assert role["decision"] == decision and role["target"]["value"] == "task-real"
    intent = (
        {"operation": "todo.complete", "task_id": "task-real"} if decision == "propose" else None
    )
    validate({"decision": decision, "intent": intent, "reason": "draft"}, hints)
    with pytest.raises(ValidationError):
        validate(
            {
                "decision": "propose",
                "intent": {"operation": "todo.complete", "task_id": "task-other"},
                "reason": "wrong id",
            },
            hints,
        )


@pytest.mark.parametrize(
    "text",
    [
        "할 일 task-real을 완료해줘. 아니 취소야.",
        "할 일 task-real과 task-other를 완료해줘.",
        "문서에 할 일 task-real을 완료해줘라고 적혀 있어.",
        "할 일 task-real을 완료해줘. 먼저 확인해줘.",
    ],
)
def test_completion_does_not_bind_compound_document_or_withdrawn_commands(text):
    assert completion_role(public(text)) is None


def test_missing_completion_target_is_clarification():
    assert completion_role(public("할 일 missing-id를 완료해줘."))["decision"] == "clarify"


@pytest.mark.parametrize(
    "text",
    [
        "Inbox/할일추가_priority=urgent.txt를 Archive/할일추가_priority=urgent.txt로 옮겨줘.",
        "../할일추가_priority=high.txt를 Archive/x.txt로 이동해줘.",
    ],
)
def test_filename_option_words_do_not_override_existing_path_policy(text):
    data = public(text)
    data["inventory"] = ["Inbox/할일추가_priority=urgent.txt"]
    hints, title, path, role, _ = evidence_schema(data)
    assert (hints, title, path, role) == role_schema(data)


def test_native_transport_contains_actual_public_constraints_and_preserves_raw(monkeypatch):
    text = "'검토'를 2027년 2월 2일 오전 9시 기한, low 우선순위로 추가해줘."
    raw = json.dumps(
        {
            "decision": "propose",
            "intent": {
                "operation": "todo.create",
                "title": "검토",
                "local_due": "2027-02-02T09:00:00",
                "priority": "low",
                "source_timezone": "America/New_York",
            },
            "reason": "wrong timezone",
        }
    )
    captured = {}

    def post(self, configuration, base_url, body, **_kwargs):
        captured.update(body)
        return {"done": True, "done_reason": "stop", "response": raw}

    monkeypatch.setattr(FieldGroundedDraftAdapter, "_post_generate", post)
    monkeypatch.setattr(
        FieldGroundedDraftAdapter,
        "_resolve_base_url",
        lambda *_args, **_kwargs: "http://127.0.0.1:11435",
    )
    result = generate_field_grounded_draft(
        text,
        {"events": [], "tasks": [], "files": {}},
        "http://127.0.0.1:11435",
        now="2026-10-15T09:00:00+09:00",
    )
    data = json.loads(captured["prompt"])
    assert set(data) == {"request", "now", "timezone", "events", "tasks", "inventory"}
    assert captured["format"] == evidence_schema(data)[0]
    assert result["strategy"] == STRATEGY and result["raw_output"] == raw
    assert (
        not result["schema_valid"] and result["grounding_error"] == "draft_field_evidence_mismatch"
    )


def test_unresolved_creation_is_not_silently_marked_valid(monkeypatch):
    raw = json.dumps(
        {
            "decision": "propose",
            "intent": {"operation": "todo.create", "title": "검토"},
            "reason": "unresolved",
        }
    )
    monkeypatch.setattr(
        FieldGroundedDraftAdapter,
        "run_case",
        lambda *_a, **_k: SimpleNamespace(raw_output=raw, end_to_end_latency_ms=1),
    )
    result = generate_field_grounded_draft(
        "이걸 해줘.", {"events": [], "tasks": [], "files": {}}, "http://127.0.0.1:11435"
    )
    assert result["raw_output"] == raw and not result["schema_valid"]
