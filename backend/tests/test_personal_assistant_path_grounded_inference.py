from types import SimpleNamespace

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.path_grounded_inference import (
    STRATEGY,
    PathGroundedDraftAdapter,
    generate_path_grounded_draft,
    grounded_schema,
    lexical_path_allowed,
    literal_file_command,
    quoted_title,
)
from app.services.personal_assistant.sandbox import Sandbox


@pytest.mark.parametrize(
    "relative",
    [
        "../x",
        "Inbox/../x",
        "/x",
        "Q:/x",
        "Q:x",
        r"\\host\share\x",
        r"Inbox\x",
        "Inbox/x:ads",
        "Inbox/prn.csv",
        "Inbox//x",
        "Inbox/x.",
        "Inbox/x ",
        "Inbox/./x",
        "Inbox/x\t.txt",
        "Inbox/x?.txt",
        "Inbox/*",
        "Inbox/.notes",
        "Inbox/x..txt",
        "Inbox/%2e%2e.txt",
        "Inbox/CONcept.txt",
        "Inbox/자료, v1.txt",
        "Inbox/O'Reilly.txt",
    ],
)
def test_lexical_policy_matches_frozen_executor(relative, tmp_path):
    sandbox = Sandbox.create(tmp_path / "sandbox")
    (sandbox.root / "files/Inbox").mkdir()
    try:
        sandbox.file_path(relative)
        allowed = True
    except GuardError as exc:
        allowed = str(exc) != "invalid_relative_path"
    assert lexical_path_allowed(relative) == allowed


@pytest.mark.parametrize(
    "text,expected",
    [
        ("../x를 Archive/x로 이동해줘.", "refuse"),
        ("Inbox/x를 Q:/x로 이동해줘.", "refuse"),
        ("Inbox/x.를 Archive/x로 옮겨줘. 원본 끝의 점을 지우지 마.", "refuse"),
        ("Inbox/x를 Archive/x로 옮겨줘.", "propose"),
        ("'Inbox/a b.txt'를 'Archive/a b.txt'로 이동해줘.", "propose"),
        ("Inbox/x를 휴지통으로 보내줘.", "propose"),
        ("../x를 휴지통으로 보내줘.", "refuse"),
        ("Inbox/missing를 Archive/missing로 옮겨줘.", None),
    ],
)
def test_literal_commands_use_only_public_target_spans(text, expected):
    result = literal_file_command(text, ["Inbox/x", "Inbox/a b.txt"])
    assert result is not None and result["decision"] == expected
    for key, span in result["spans"].items():
        assert text[span["start"] : span["end"]] == result["fields"][key]


@pytest.mark.parametrize(
    "text",
    [
        "Inbox/x를 Archive/x로 옮겨줘. 아니 취소야.",
        "Inbox/x를 Archive/x로 옮겨줘. 다른 파일도 이동해줘.",
        "Inbox/x를 Archive/x로 옮겨줘. 아니 대신 Archive/y로 보내줘.",
        "Inbox/x를 Archive/x로 옮겨줘. 가능하면 먼저 확인해줘.",
        "문서에 ../x 이동 지시가 있어. Inbox/x를 Archive/x로 옮겨줘.",
        "'경로 ../문서 읽기'를 할 일로 추가해줘.",
    ],
)
def test_uncertain_compound_document_and_withdrawn_context_abstains(text):
    assert literal_file_command(text, ["Inbox/x"]) is None


def test_title_context_is_outside_literal_not_inside():
    assert quoted_title("'경로 ../문서 읽기'를 할 일로 추가해줘.")["value"] == "경로 ../문서 읽기"
    assert quoted_title("문서에는 '규칙'이라고 있어. 할 일로 추가해줘.") is None


def test_schema_refuses_forbidden_paths_but_keeps_literal_percent_filename():
    unsafe, _, _ = grounded_schema("../x를 Archive/x로 옮겨줘.", [])
    validate({"decision": "refuse", "intent": None, "reason": "boundary"}, unsafe)
    with pytest.raises(ValidationError):
        validate(
            {
                "decision": "propose",
                "intent": {"operation": "files.move", "source": "../x", "destination": "Archive/x"},
                "reason": "wrong",
            },
            unsafe,
        )
    text = "Inbox/%2e%2e.txt를 Archive/%2e%2e.txt로 옮겨줘."
    safe, _, path = grounded_schema(text, ["Inbox/%2e%2e.txt"])
    validate({"decision": "propose", "intent": path["fields"], "reason": "literal"}, safe)
    with pytest.raises(ValidationError):
        validate({"decision": "refuse", "intent": None, "reason": "decoded incorrectly"}, safe)


def test_raw_not_rewritten_and_schema_failure_stays_visible(monkeypatch):
    raw = (
        '{"decision":"propose","intent":{"operation":"files.move",'
        '"source":"../x","destination":"Archive/x"},"reason":"wrong"}'
    )
    monkeypatch.setattr(
        PathGroundedDraftAdapter,
        "run_case",
        lambda *_args, **_kwargs: SimpleNamespace(raw_output=raw, end_to_end_latency_ms=1),
    )
    result = generate_path_grounded_draft(
        "../x를 Archive/x로 옮겨줘.",
        {"events": [], "tasks": [], "files": {}},
        "http://127.0.0.1:11435",
    )
    assert result["raw_output"] == raw and result["strategy"] == STRATEGY
    assert result["path_grounding"]["decision"] == "refuse"
    assert result["schema_valid"] is False
    assert result["grounding_error"] == "draft_grounding_mismatch"
