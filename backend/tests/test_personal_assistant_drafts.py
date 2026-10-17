import pytest

from app.services.personal_assistant.contracts import GuardError, canonical
from app.services.personal_assistant.drafts import DraftAssistantService, parse_draft
from app.services.personal_assistant.sandbox import Sandbox


@pytest.fixture
def service(tmp_path):
    sandbox = Sandbox.create(tmp_path / "draft-test")
    (sandbox.root / "files/Inbox").mkdir()
    (sandbox.root / "files/Archive").mkdir()
    return DraftAssistantService(sandbox)


def raw(fields):
    return canonical({"decision": "propose", "intent": fields, "reason": "Review draft"})


def execute(service, preview):
    return service.approve(preview["proposal_id"], preview["approval_token"], preview["plan_hash"])


def test_model_does_not_supply_converted_time_or_end_time(service):
    fields = {
        "operation": "calendar.create",
        "title": "Call",
        "source_timezone": "America/New_York",
        "local_start": "2026-11-05T08:10:00",
        "duration_minutes": 50,
    }
    before = service.state()
    preview = service.prepare(fields, raw(fields))
    assert service.state() == before
    assert preview["action"]["arguments"] == {
        "title": "Call",
        "start_at": "2026-11-05T22:10:00+09:00",
        "end_at": "2026-11-05T23:00:00+09:00",
    }
    assert execute(service, preview)["event"]["end_at"] == "2026-11-05T23:00:00+09:00"


@pytest.mark.parametrize("operation", ["files.move", "files.trash"])
def test_relative_draft_paths_compile_and_restore(service, operation):
    source = service.sandbox.file_path("Inbox/test.txt")
    source.write_bytes(b"preserve")
    fields = (
        {"operation": operation, "source": "Inbox/test.txt", "destination": "Archive/test.txt"}
        if operation == "files.move"
        else {"operation": operation, "path": "Inbox/test.txt"}
    )
    before = service.state()
    preview = service.prepare(fields, raw(fields))
    arg = "source" if operation == "files.move" else "path"
    assert preview["action"]["arguments"][arg] == "C:/AssistantSandbox/Inbox/test.txt"
    execute(service, preview)
    undo = service.prepare_undo(preview["proposal_id"])
    execute(service, undo)
    assert service.state() == before


def test_default_timezone_does_not_fill_optional_task_arguments(service):
    confirmed = {"operation": "todo.create", "title": "Review"}
    extracted = {**confirmed, "source_timezone": "Asia/Tokyo", "local_due": None, "priority": None}
    preview = service.prepare(confirmed, raw(extracted))
    assert preview["action"]["arguments"] == {"title": "Review"}


@pytest.mark.parametrize(
    "injection",
    [
        {"priority": "high"},
        {"title": "Different"},
        {"operation": "todo.complete", "task_id": "x"},
    ],
)
def test_unconfirmed_draft_values_never_execute(service, injection):
    confirmed = {"operation": "todo.create", "title": "Review"}
    extracted = {**confirmed, **injection}
    if extracted["operation"] == "todo.complete":
        extracted.pop("title")
    before = service.state()
    with pytest.raises(GuardError, match="match_confirmed"):
        service.prepare(confirmed, raw(extracted))
    assert service.state() == before


@pytest.mark.parametrize(
    "payload",
    [
        "null",
        '{"decision":"propose","decision":"refuse","intent":null,"reason":"x"}',
        '{"intent":NaN}',
        '{"decision":"propose","intent":null,"reason":"x"}',
        '{"decision":"clarify","intent":{"operation":"todo.create","title":"x"},"reason":"x"}',
        '{"decision":"refuse","intent":null,"reason":" "}',
    ],
)
def test_draft_envelope_is_strict(payload):
    with pytest.raises(GuardError):
        parse_draft(payload)


def test_invalid_paths_and_ambiguous_dst_still_block(service):
    for fields in (
        {"operation": "files.trash", "path": "../outside.txt"},
        {
            "operation": "calendar.create",
            "title": "Call",
            "source_timezone": "America/New_York",
            "local_start": "2026-11-01T01:30:00",
            "duration_minutes": 30,
        },
    ):
        before = service.state()
        with pytest.raises(GuardError):
            service.prepare(fields, raw(fields))
        assert service.state() == before
