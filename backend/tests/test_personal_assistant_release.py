import copy
import json

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant import release_generation as release
from app.services.personal_assistant.semantic_grounded_inference import semantic_schema
from app.services.personal_assistant.stable_inference import public_payload


def public(request):
    return public_payload(
        request, {"tasks": [], "events": [], "files": {}}, now="2026-10-15T09:00:00+09:00"
    )


def test_release_keeps_supported_evidence_and_historical_sources_unchanged():
    data = public("'검토'를 할 일로 추가해줘.")
    previous = semantic_schema(data)
    current = release.release_schema(data)
    assert current[:6] == previous
    assert current[-1]["policy"] == "source_bound"
    assert not current[-1]["authorizes_execution"]


@pytest.mark.parametrize("decision", ["propose", "clarify", "refuse", "no_change"])
def test_unverified_semantics_cannot_create_specific_claims(decision):
    data = public("무엇을 해야 할지 아직 모르겠어")
    hints, *_, evidence, policy = release.release_schema(data)
    assert evidence["explanation_evidence"]["status"] == "unverified"
    assert policy["policy"] == "neutral_decision_only"
    draft = {
        "decision": decision,
        "intent": {"operation": "todo.create", "title": "점검"} if decision == "propose" else None,
        "reason": release.NEUTRAL_REASONS[decision],
    }
    validate(draft, hints)
    with pytest.raises(ValidationError):
        validate({**draft, "reason": "마감 시각이 없으므로 요청이 불완전합니다."}, hints)


def test_legacy_is_explicit_rollback_and_unknown_strategy_does_not_silently_fallback(monkeypatch):
    calls = []
    monkeypatch.setattr(
        release,
        "generate_historical_draft",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"raw_output": "legacy"},
    )
    assert release.generate_review_draft("r", {}, "url", "legacy")["raw_output"] == "legacy"
    assert calls[0][0] == ("r", {}, "url", "legacy")


def test_actual_native_schema_rejects_free_explanation_without_rewriting(monkeypatch):
    data = public("'긴급 분류 확인'을 할 일로 추가해줘. priority=urgent로 넣어줘.")
    bodies = []
    raw = json.dumps({"decision": "clarify", "intent": None, "reason": "마감을 정해 주세요."})

    def post(self, configuration, base_url, body, **kwargs):
        bodies.append(copy.deepcopy(body))
        return {"done": True, "done_reason": "stop", "response": raw}

    monkeypatch.setattr(release.ReleaseDraftAdapter, "_post_generate", post)
    monkeypatch.setattr(
        release.ReleaseDraftAdapter,
        "_resolve_base_url",
        lambda *args, **kwargs: "http://127.0.0.1:11435",
    )
    result = release.generate_review_draft(
        data["request"],
        {"tasks": [], "events": [], "files": {}},
        "http://127.0.0.1:11435",
        now=data["now"],
    )
    assert len(bodies) == 1 and bodies[0]["format"] == release.release_schema(data)[0]
    assert result["raw_output"] == raw and not result["schema_valid"]
    assert result["grounding_error"] == "draft_release_evidence_mismatch"
