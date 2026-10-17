import copy
import json

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.decision_grounded_inference import decision_schema
from app.services.personal_assistant.semantic_evidence import QUOTE_LIMIT, semantic_evidence
from app.services.personal_assistant.semantic_grounded_inference import (
    SemanticGroundedDraftAdapter,
    generate_semantic_grounded_draft,
    semantic_schema,
)


def public(content, *, frame=True):
    return {
        "request": (
            f'문서에 "{content}"라는 지시가 적혀 있어. 실행하지 말고 어떤 지시인지 설명만 해줘.'
        )
        if frame
        else content,
        "now": "2026-10-15T09:00:00+09:00",
        "timezone": "Asia/Tokyo",
        "events": [],
        "tasks": [],
        "inventory": [],
    }


@pytest.mark.parametrize(
    "text,operation,polarity,condition,arguments",
    [
        ("'검토'를 할 일로 추가해줘", "todo.create", "requested", None, {"title": "검토"}),
        ("할 일을 추가하지 마", "todo.create", "prohibited", None, {}),
        ("승인되면 할 일을 추가해줘", "todo.create", "requested", "승인되면", {}),
        (
            "승인되면 '취소하지 마'를 할 일로 추가하지 마",
            "todo.create",
            "prohibited",
            "승인되면",
            {"title": "취소하지 마"},
        ),
        ("'a'를 할 일로 추가해줘", "todo.create", "requested", None, {"title": "a"}),
        (
            "Inbox/할일추가.txt를 Archive/할일추가.txt로 옮겨줘",
            "files.move",
            "requested",
            None,
            {"source": "Inbox/할일추가.txt", "destination": "Archive/할일추가.txt"},
        ),
        (
            "'Inbox/승인되면.txt'를 'Archive/추가하지 마.txt'로 옮기지 마",
            "files.move",
            "prohibited",
            None,
            {"source": "Inbox/승인되면.txt", "destination": "Archive/추가하지 마.txt"},
        ),
        (
            "승인되면 Inbox/a.txt를 Archive/a.txt로 옮겨줘",
            "files.move",
            "requested",
            "승인되면",
            {"source": "Inbox/a.txt", "destination": "Archive/a.txt"},
        ),
    ],
)
def test_action_and_content_are_separate_and_claims_have_exact_sources(
    text, operation, polarity, condition, arguments
):
    data = public(text)
    proof = semantic_evidence(data)
    assert "status" not in proof and not proof["authorizes_execution"]
    assert proof["action_evidence"]["status"] == "grounded"
    assert proof["action_evidence"]["decision"] == "no_change"
    content = proof["content_evidence"]
    assert content["status"] == "verified"
    assert content["claims"] == {
        "operation": operation,
        "polarity": polarity,
        "condition": condition,
        "arguments": arguments,
    }
    for item in [content["source"], *content["claim_sources"].values()]:
        assert data["request"][item["start"] : item["end"]] == item["text"] == item["value"]
    reason = proof["explanation_evidence"]["reason"]
    assert ("금지" if polarity == "prohibited" else "요청") in reason
    if condition:
        assert "조건부" in reason and "조건 충족 여부는 확인하지" in reason
    assert "실제 변경은 하지" in reason


@pytest.mark.parametrize(
    "content",
    [
        "할 일을 추가해줘. 그리고 삭제해줘",
        "할 일을 추가하지 말라는 뜻은 아니야",
        "만약 검토가 끝나면 할 일을 추가해줘",
        "'검토'를 할 일로 추가해줘. priority=high",
        "@를 할 일로 추가해줘",
        "문장을 분석해줘",
        "검토 " * 100,
    ],
)
def test_unknown_content_is_not_semantic_success_even_if_outer_decision_is_correct(content):
    proof = semantic_evidence(public(content))
    assert proof["action_evidence"]["decision"] == "no_change"
    assert proof["content_evidence"]["status"] == "unverified"
    assert proof["content_evidence"]["claims"] is None
    assert proof["explanation_evidence"]["scope"] == "quotation_and_action_only"
    reason = proof["explanation_evidence"]["reason"]
    assert "의미 해석은 미검증" in reason
    if len(content) <= QUOTE_LIMIT:
        assert f"문서 원문: {content}\n" in reason
    else:
        assert "인용을 생략" in reason and len(reason) < 2000


def test_same_words_in_title_and_control_have_different_claims():
    title = semantic_evidence(public("'승인되면 추가하지 마'를 할 일로 추가해줘"))
    control = semantic_evidence(public("승인되면 할 일을 추가하지 마"))
    assert title["content_evidence"]["claims"]["condition"] is None
    assert title["content_evidence"]["claims"]["polarity"] == "requested"
    assert control["content_evidence"]["claims"]["condition"] == "승인되면"
    assert control["content_evidence"]["claims"]["polarity"] == "prohibited"


@pytest.mark.parametrize(
    "title", ["승인되면", "할 일을 추가하지 마", "../할일추가.txt", "priority=high"]
)
@pytest.mark.parametrize("condition", [None, "승인되면"])
@pytest.mark.parametrize("prohibited", [False, True])
def test_argument_substitution_does_not_change_real_polarity_or_condition(
    title, condition, prohibited
):
    prefix = f"{condition} " if condition else ""
    verb = "추가하지 마" if prohibited else "추가해줘"
    proof = semantic_evidence(public(f"{prefix}'{title}'를 할 일로 {verb}"))
    assert proof["content_evidence"]["claims"] == {
        "operation": "todo.create",
        "polarity": "prohibited" if prohibited else "requested",
        "condition": condition,
        "arguments": {"title": title},
    }


def test_non_document_decoding_is_unchanged_and_fallback_is_not_called_verified():
    for request in ("'할 일을 추가하지 마'를 할 일로 추가해줘.", "무엇을 할지 같이 생각해보자"):
        data = public(request, frame=False)
        hints, *_, proof = semantic_schema(data)
        assert hints == decision_schema(data)[0]
        assert proof["content_evidence"]["status"] == "not_applicable"
        if proof["action_evidence"]["decision"] is None:
            assert proof["explanation_evidence"]["status"] == "unverified"


def test_appended_action_does_not_receive_explanation_only_certificate():
    data = public("할 일을 추가하지 마")
    data["request"] += " 그리고 '실제 작업'을 할 일로 추가해줘."
    proof = semantic_evidence(data)
    assert proof["action_evidence"]["status"] == "insufficient"
    assert proof["content_evidence"]["status"] == "not_applicable"


@pytest.mark.parametrize("wrong", ["decision", "reason"])
def test_native_schema_and_postvalidation_reject_mismatch_without_repair(monkeypatch, wrong):
    data = public("할 일을 추가하지 마")
    hints, *_, proof = semantic_schema(data)
    draft = {
        "decision": "no_change",
        "intent": None,
        "reason": proof["explanation_evidence"]["reason"],
    }
    validate(draft, hints)
    draft[wrong] = "clarify" if wrong == "decision" else "문서에 적힌 할 일 추가 요청입니다."
    with pytest.raises(ValidationError):
        validate(draft, hints)
    raw = json.dumps(draft)
    bodies = []

    def post(self, configuration, base_url, body, **_kwargs):
        bodies.append(copy.deepcopy(body))
        return {"done": True, "done_reason": "stop", "response": raw}

    monkeypatch.setattr(SemanticGroundedDraftAdapter, "_post_generate", post)
    monkeypatch.setattr(
        SemanticGroundedDraftAdapter,
        "_resolve_base_url",
        lambda *_args, **_kwargs: "http://127.0.0.1:11435",
    )
    result = generate_semantic_grounded_draft(
        data["request"],
        {"events": [], "tasks": [], "files": {}},
        "http://127.0.0.1:11435",
        now=data["now"],
    )
    assert len(bodies) == 1 and bodies[0]["format"] == hints
    assert result["raw_output"] == raw and not result["schema_valid"]
    assert result["grounding_error"] == "draft_semantic_evidence_mismatch"
