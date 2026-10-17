import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from app.services.personal_assistant.contracts import (
    INTENT,
    LOGICAL_ROOT,
    GuardError,
    canonical,
    parse_plan,
)
from app.services.personal_assistant.planning import compile_action, local_instant
from app.services.personal_assistant.sandbox import Sandbox
from app.services.personal_assistant.service import AssistantService


@pytest.fixture
def service(tmp_path):
    sandbox = Sandbox.create(tmp_path / "isolated")
    (sandbox.root / "files" / "Inbox").mkdir()
    (sandbox.root / "files" / "Archive").mkdir()
    return AssistantService(sandbox)


def plan(tool="todo.create", **arguments):
    return canonical(
        {
            "decision": "propose",
            "requires_confirmation": True,
            "actions": [{"tool": tool, "arguments": arguments}],
            "reason": "Preview only",
        }
    )


def approve(service, preview):
    return service.approve(preview["proposal_id"], preview["approval_token"], preview["plan_hash"])


def todo_preview(service):
    return service.prepare({"operation": "todo.create", "title": "Review"}, plan(title="Review"))


def seed(service, table, item):
    key = "event_id" if table == "events" else "task_id"
    assert table in {"events", "tasks"}
    with service.sandbox.connect() as db:
        db.execute(f"INSERT INTO {table} VALUES(?,?)", (item[key], canonical(item)))


def test_preview_approval_persistence_and_replay(service):
    before = service.state()
    preview = todo_preview(service)
    assert service.state() == before
    assert preview["action"]["arguments"] == {"title": "Review"}
    receipt = approve(service, preview)
    reopened = AssistantService(Sandbox(service.sandbox.root))
    assert reopened.state()["tasks"] == [receipt["task"]]
    assert approve(reopened, preview)["replayed"]
    assert len(reopened.state()["tasks"]) == 1
    assert [a["event"] for a in reopened.audit()] == ["preview", "executed"]


def test_cancel_and_wrong_token_and_changed_hash(service):
    preview = todo_preview(service)
    before = service.state()
    with pytest.raises(GuardError, match="token"):
        service.approve(preview["proposal_id"], "wrong", preview["plan_hash"])
    with pytest.raises(GuardError, match="hash"):
        service.approve(preview["proposal_id"], preview["approval_token"], "changed")
    service.cancel(preview["proposal_id"], preview["approval_token"])
    with pytest.raises(GuardError, match="not_pending"):
        approve(service, preview)
    assert service.state() == before


def test_expired_approval(service):
    preview = todo_preview(service)
    with service.sandbox.connect() as db:
        db.execute("UPDATE proposals SET expires=0")
    with pytest.raises(GuardError, match="expired"):
        approve(service, preview)
    assert not service.state()["tasks"]


def test_changed_state_requires_new_preview(service):
    preview = todo_preview(service)
    (service.sandbox.root / "files" / "Inbox" / "new.txt").write_text("new")
    before = service.state()
    with pytest.raises(GuardError, match="state_changed"):
        approve(service, preview)
    assert service.state() == before


def test_concurrent_approval_executes_once(service):
    preview = todo_preview(service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(service, preview), range(2)))
    assert sum(not r["replayed"] for r in results) == 1
    assert len(service.state()["tasks"]) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "[]",
        "null",
        '{"a":1,"a":2}',
        '{"a":NaN}',
        "```json\n{}\n```",
        '{"decision":"clarify","requires_confirmation":false,"actions":[],"reason":"Ask"}',
    ],
)
def test_malformed_or_nonproposal_is_not_executable(raw):
    with pytest.raises(GuardError):
        parse_plan(raw)


@pytest.mark.parametrize("change", ["extra_argument", "extra_action", "no_approval", "wrong_title"])
def test_model_cannot_broaden_confirmed_scope(service, change):
    value = json.loads(plan(title="Review"))
    if change == "extra_argument":
        value["actions"][0]["arguments"]["priority"] = "high"
    elif change == "extra_action":
        value["actions"].append(value["actions"][0])
    elif change == "no_approval":
        value["requires_confirmation"] = False
    else:
        value["actions"][0]["arguments"]["title"] = "Different"
    before = service.state()
    with pytest.raises(GuardError):
        service.prepare({"operation": "todo.create", "title": "Review"}, canonical(value))
    assert service.state() == before


@pytest.mark.parametrize(
    "value,zone",
    [
        ("2026-03-08T02:30:00", "America/New_York"),
        ("2026-11-01T01:30:00", "America/New_York"),
        (None, "Asia/Tokyo"),
        ("2026-09-20", "Asia/Tokyo"),
        ("2026-09-20T10:00:00+09:00", "Asia/Tokyo"),
        ("2026-09-20T10:00:00", "Not/AZone"),
    ],
)
def test_ambiguous_or_invalid_local_times(value, zone):
    with pytest.raises(GuardError):
        local_instant(value, zone)


def test_timezone_conversion_and_calendar_persistence(service):
    fields = {
        "operation": "calendar.create",
        "title": "Call",
        "local_start": "2026-10-06T08:30:00",
        "source_timezone": "America/New_York",
        "duration_minutes": 45,
    }
    assert local_instant(fields["local_start"], fields["source_timezone"]) == datetime(
        2026, 10, 6, 12, 30, tzinfo=UTC
    )
    raw = plan(
        "calendar.create",
        title="Call",
        start_at="2026-10-06T21:30:00+09:00",
        end_at="2026-10-06T22:15:00+09:00",
    )
    preview = service.prepare(fields, raw)
    receipt = approve(service, preview)
    assert service.state()["events"] == [receipt["event"]]
    with pytest.raises(GuardError, match="duplicate_event"):
        service.prepare(fields, raw)
    with pytest.raises(GuardError, match="calendar_conflict"):
        service.prepare({**fields, "title": "Another call"}, raw)


def test_duplicate_and_ambiguous_tasks(service):
    for key in ("a", "b"):
        seed(service, "tasks", {"task_id": key, "title": "Review", "status": "open"})
    with pytest.raises(GuardError, match="duplicate_task"):
        todo_preview(service)
    with pytest.raises(GuardError, match="not_unique"):
        service.prepare(
            {"operation": "todo.complete", "title": "Review"},
            plan("todo.complete", task_id="a"),
        )
    receipt = approve(
        service,
        service.prepare(
            {"operation": "todo.complete", "task_id": "b"}, plan("todo.complete", task_id="b")
        ),
    )
    assert receipt["task"]["status"] == "complete"
    assert service.state()["tasks"][0]["status"] == "open"


@pytest.mark.parametrize(
    "path",
    [
        "../escape",
        "Inbox/../../escape",
        "C:/Windows/file",
        "/tmp/file",
        "//host/share/file",
        "Inbox/file:stream",
        "Inbox\\file",
        "Inbox/CON.txt",
        "Inbox/file.",
        "Inbox//file",
        "",
    ],
)
def test_restricted_paths(service, path):
    with pytest.raises(GuardError):
        service.sandbox.file_path(path)


def file_preview(service, trash=False):
    (service.sandbox.root / "files" / "Inbox" / "sample.txt").write_bytes(b"original\x00content")
    if trash:
        fields = {"operation": "files.trash", "path": "Inbox/sample.txt"}
        raw = plan("files.trash", path=f"{LOGICAL_ROOT}/Inbox/sample.txt")
    else:
        fields = {
            "operation": "files.move",
            "source": "Inbox/sample.txt",
            "destination": "Archive/sample.txt",
        }
        raw = plan(
            "files.move",
            source=f"{LOGICAL_ROOT}/Inbox/sample.txt",
            destination=f"{LOGICAL_ROOT}/Archive/sample.txt",
        )
    return service.prepare(fields, raw)


@pytest.mark.parametrize("trash", [False, True])
def test_real_file_change_replay_restore(service, trash):
    preview = file_preview(service, trash)
    before = service.state()
    receipt = approve(service, preview)
    assert not (service.sandbox.root / "files" / "Inbox" / "sample.txt").exists()
    change = receipt["file_change"]
    target = service.sandbox.root / change["destination_area"] / change["destination"]
    assert target.read_bytes() == b"original\x00content"
    assert approve(service, preview)["replayed"]
    undo = service.prepare_undo(preview["proposal_id"])
    assert target.exists()
    approve(service, undo)
    assert service.state() == before


def test_overwrite_blocked_at_preview_and_after_preview(service):
    preview = file_preview(service)
    target = service.sandbox.root / "files" / "Archive" / "sample.txt"
    target.write_text("keep")
    with pytest.raises(GuardError, match="state_changed"):
        approve(service, preview)
    assert target.read_text() == "keep"
    with pytest.raises(GuardError, match="destination_exists"):
        compile_action(
            INTENT.validate_python(
                {
                    "operation": "files.move",
                    "source": "Inbox/sample.txt",
                    "destination": "Archive/sample.txt",
                }
            ),
            service.state(),
            service.sandbox,
        )


def test_modified_file_not_restored(service):
    preview = file_preview(service)
    approve(service, preview)
    (service.sandbox.root / "files" / "Archive" / "sample.txt").write_bytes(b"edited")
    with pytest.raises(GuardError, match="changed_file"):
        service.prepare_undo(preview["proposal_id"])


def test_failed_file_operation_is_not_retried(service, monkeypatch):
    preview = file_preview(service)
    before = service.state()

    def fail(*args):
        raise OSError("simulated disk error")

    monkeypatch.setattr(service.sandbox, "move_exclusive", fail)
    with pytest.raises(GuardError, match="execution_failed"):
        approve(service, preview)
    assert service.state() == before
    with pytest.raises(GuardError, match="not_pending:failed"):
        approve(service, preview)


def test_interrupted_file_operation_cannot_replay(service):
    preview = file_preview(service)
    with service.sandbox.connect() as db:
        db.execute("UPDATE proposals SET status='executing'")
    with pytest.raises(GuardError, match="not_pending:executing"):
        approve(service, preview)


def test_hardlink_escape_blocked(service, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"private")
    link = service.sandbox.root / "files" / "linked.txt"
    link.hardlink_to(outside)
    with pytest.raises(GuardError, match="hardlinked"):
        service.sandbox.file_path("linked.txt", must_exist=True)


def test_symlink_escape_blocked(service, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"private")
    link = service.sandbox.root / "files" / "linked.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Host does not allow symlink creation")
    with pytest.raises(GuardError, match="linked"):
        service.sandbox.file_path("linked.txt", must_exist=True)


def test_does_not_adopt_existing_directory(tmp_path):
    with pytest.raises(FileExistsError):
        Sandbox.create(tmp_path)
