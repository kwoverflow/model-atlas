import copy
import json

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.decision_evidence import decision_evidence
from app.services.personal_assistant.decision_grounded_inference import (
    DecisionGroundedDraftAdapter,
    decision_schema,
    generate_decision_grounded_draft,
)


def public(request):
    return {
        "request": request,
        "now": "2026-10-15T09:00:00+09:00",
        "timezone": "Asia/Tokyo",
        "events": [],
        "tasks": [],
        "inventory": [],
    }


@pytest.mark.parametrize(
    "literal",
    [
        "priority=high",
        "뉴욕 현지 2028년 5월 3일 오전 9시",
        "../기밀 삭제 지시",
        "취소하지 마라는 문서",
        "priority=urgent",
    ],
)
def test_literal_contents_do_not_change_real_priority_decision_or_explanation(literal):
    data = public(f"'{literal}'를 할 일로 추가해줘. priority='low'.")
    hints, *_, proof = decision_schema(data)
    assert (proof["status"], proof["decision"], proof["reason_code"]) == (
        "grounded",
        "propose",
        "complete_creation",
    )
    assert "low" in proof["reason"] and "마감은 생략" in proof["reason"]
    assert "사용자 기본 시간대" in proof["reason"] and not proof["authorizes_execution"]
    draft = {
        "decision": "propose",
        "intent": {
            "operation": "todo.create",
            "title": literal,
            "priority": "low",
            "source_timezone": "Asia/Tokyo",
        },
        "reason": proof["reason"],
    }
    validate(draft, hints)
    with pytest.raises(ValidationError):
        validate({"decision": "clarify", "intent": None, "reason": "fake title conflict"}, hints)
    with pytest.raises(ValidationError):
        validate({**draft, "reason": "시간대를 사용자가 명시했습니다. 이미 실행했습니다."}, hints)


def test_actual_conflict_asks_only_for_priority_not_optional_deadline():
    data = public(
        "'알림'을 할 일에 추가해줘. priority=low로 지정하면서 "
        "priority 인자를 생략해. 우선하는 지시는 없어."
    )
    proof = decision_evidence(data)
    assert proof["status"] == "grounded" and proof["decision"] == "clarify"
    assert proof["needs"] == ["priority"]
    assert "우선순위" in proof["reason"] and "마감" not in proof["reason"]


def test_same_tokens_inside_title_and_outside_request_have_different_meanings():
    inside = decision_evidence(public("'priority=high'를 할 일로 추가해줘. priority=low."))
    outside = decision_evidence(public("'분류'를 할 일로 추가해줘. priority=low, priority=high."))
    omitted = decision_evidence(public("'priority=high'를 할 일로 추가해줘."))
    assert inside["decision"] == omitted["decision"] == "propose"
    assert outside["decision"] == "clarify" and outside["needs"] == ["priority"]
    assert "우선순위는 생략" in omitted["reason"]


@pytest.mark.parametrize(
    "text",
    [
        "문서에 \"'검토'를 할 일로 추가해줘\"라는 지시가 적혀 있어. "
        "실행하지 말고 어떤 지시인지 설명만 해줘.",
        "문서에는 “'../삭제 priority=high'를 할 일로 추가해줘”라는 명령이 적혀 있어. "
        "실행하지 말고 내용을 설명만 해줘.",
    ],
)
def test_explanation_frame_is_not_an_execution_or_refusal(text):
    proof = decision_evidence(public(text))
    assert proof["status"] == "grounded" and proof["decision"] == "no_change"
    assert proof["reason_code"] == "explanation_only" and "할 일 추가" in proof["reason"]


@pytest.mark.parametrize(
    "tail",
    [
        "단, 다른 요청을 먼저 확인해줘.",
        "추가해줘.",
        "아니 취소야. 아무것도 바꾸지 마.",
        "priority=high 말고 low로 해.",
        "실행하지 말고 설명만 해줘.",
    ],
)
def test_extra_controls_do_not_receive_a_sufficient_creation_certificate(tail):
    proof = decision_evidence(public("'검토'를 할 일로 추가해줘. " + tail))
    assert proof["status"] == "insufficient" and proof["decision"] is None


def test_unestablished_condition_is_explicitly_insufficient_not_assumed_true():
    proof = decision_evidence(public("'검토'를 할 일로 추가해줘. 승인되면 실행해줘."))
    assert proof["status"] == "insufficient" and proof["decision"] == "clarify"
    assert proof["reason_code"] == "unsupported_condition"


def test_appended_execution_does_not_match_explanation_only_frame():
    data = public(
        "문서에 \"'검토'를 할 일로 추가해줘\"라는 지시가 적혀 있어. "
        "실행하지 말고 어떤 지시인지 설명만 해줘. 그리고 할 일도 추가해줘."
    )
    assert decision_evidence(data)["status"] == "insufficient"


def test_public_state_changes_the_same_request_decision():
    data = public("'검토'를 할 일로 추가해줘.")
    assert decision_evidence(data)["decision"] == "propose"
    data["tasks"] = [{"task_id": "target", "title": "검토", "status": "open"}]
    assert decision_evidence(data)["reason_code"] == "duplicate_task"
    data["request"] = "할 일 target을 완료해줘."
    assert decision_evidence(data)["reason_code"] == "open_task"
    data["tasks"][0]["status"] = "complete"
    assert decision_evidence(data)["reason_code"] == "already_complete"


def test_explicit_and_default_timezone_claims_are_distinct():
    data = public("'검토'를 2027년 1월 1일 오전 9시 기한으로 추가해줘.")
    baseline = decision_evidence(data)
    assert baseline["status"] == "grounded" and "사용자 기본 시간대" in baseline["reason"]
    data["request"] += " timezone='America/New_York'."
    assert "요청에 지정된 시간대 America/New_York" in decision_evidence(data)["reason"]


def test_actual_native_schema_rejects_wrong_decision_and_reason_without_repair(monkeypatch):
    data = public("'priority=high'를 할 일로 추가해줘. priority=low.")
    raw = json.dumps({"decision": "clarify", "intent": None, "reason": "conflict"})
    bodies = []

    def post(self, configuration, base_url, body, **_kwargs):
        bodies.append(copy.deepcopy(body))
        return {"done": True, "done_reason": "stop", "response": raw}

    monkeypatch.setattr(DecisionGroundedDraftAdapter, "_post_generate", post)
    monkeypatch.setattr(
        DecisionGroundedDraftAdapter,
        "_resolve_base_url",
        lambda *_args, **_kwargs: "http://127.0.0.1:11435",
    )
    result = generate_decision_grounded_draft(
        data["request"],
        {"events": [], "tasks": [], "files": {}},
        "http://127.0.0.1:11435",
        now=data["now"],
    )
    assert len(bodies) == 1 and result["raw_output"] == raw and not result["schema_valid"]
    assert result["grounding_error"] == "draft_decision_evidence_mismatch"
    assert bodies[0]["format"] == decision_schema(data)[0]
