import copy
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import personal_assistant as routes
from app.api.v1.routes import structured_requests as ticket_routes
from app.core.config import get_settings
from app.services.operator_identity import local_operator_identity
from app.services.personal_assistant.contracts import GuardError, canonical
from app.services.personal_assistant.inference import (
    AssistantDraftAdapter,
    draft_schema,
    generate_draft,
)
from app.services.personal_assistant.locking import workspace_lock
from app.services.personal_assistant.reviews import ReviewService
from app.services.personal_assistant.sandbox import Sandbox

BASE = "/api/v1/personal-assistant"
HEADERS = {"x-model-atlas-lab-action": "1", "origin": "http://localhost:3000"}
TODO = {"operation": "todo.create", "title": '"Draft"'}
MOVE = {"operation": "files.move", "source": "Inbox/test.txt", "destination": "Archive/test.txt"}


def generated(fields=TODO):
    return {
        "raw_output": canonical({"decision": "propose", "intent": fields, "reason": "Review"}),
        "model": "unit-test-fixture",
    }


@pytest.fixture
def service(tmp_path):
    sandbox = Sandbox.create(tmp_path / "review")
    (sandbox.root / "files" / "Inbox").mkdir()
    (sandbox.root / "files" / "Archive").mkdir()
    (sandbox.root / "files" / "Inbox" / "test.txt").write_bytes(b"fixture bytes\n")
    return ReviewService(sandbox)


def binding(record):
    return {"revision": record["revision"], "content_hash": record["content_hash"]}


def create(service, fields=TODO):
    return service.create("User request", lambda *_: generated(fields))


def confirm(service, record):
    return service.confirm(record["id"], **binding(record))


def approve(service, record):
    return service.approve_review(
        record["id"], **binding(record), plan_hash=record["preview"]["plan_hash"]
    )


def test_real_edit_keeps_raw_and_requires_separate_approval(service):
    before = service.state()
    record = create(service)
    assert set(record["initial_fields"]) == set(TODO)
    with pytest.raises(GuardError, match="confirmation_required"):
        service.approve_review(record["id"], **binding(record), plan_hash="x" * 64)
    corrected = {"operation": "todo.create", "title": "Reviewed title", "priority": "low"}
    saved = service.save(record["id"], **binding(record), fields=corrected)
    assert saved["raw_output"] == record["raw_output"]
    assert saved["initial_fields"]["title"] == '"Draft"'
    assert saved["fields"] == corrected and saved["revision"] == record["revision"] + 1
    pending = confirm(service, saved)
    assert service.state() == before
    assert pending["preview"]["action"]["arguments"] == {
        "title": "Reviewed title",
        "priority": "low",
    }
    assert pending["events"][-1]["payload"]["model_draft_changed"]
    assert "approval_token" not in canonical(pending)
    executed = approve(service, pending)
    reopened = ReviewService(Sandbox(service.sandbox.root))
    assert reopened.get(record["id"])["raw_output"] == record["raw_output"]
    assert reopened.state()["tasks"] == [executed["receipt"]["task"]]
    approve(reopened, executed)
    assert len(reopened.state()["tasks"]) == 1
    events = reopened.get(record["id"])["events"]
    assert sum(e["event"] == "executed" for e in events) == 1
    assert events[-1]["event"] == "execution_replayed"
    with pytest.raises(GuardError, match="cannot_be_edited"):
        reopened.save(executed["id"], **binding(executed), fields=TODO)


def test_edit_invalidates_previous_proposal_and_stale_tabs(service):
    pending = confirm(service, create(service))
    with service.sandbox.connect() as db:
        token = db.execute("SELECT approval_token FROM assistant_reviews").fetchone()[0]
    saved = service.save(pending["id"], **binding(pending), fields={**TODO, "title": "Correct"})
    with pytest.raises(GuardError, match="stale_review_revision"):
        approve(service, pending)
    with pytest.raises(GuardError, match="not_pending:superseded"):
        service.approve(pending["preview"]["proposal_id"], token, pending["preview"]["plan_hash"])
    with pytest.raises(GuardError, match="stale_review_revision"):
        service.save(pending["id"], **binding(pending), fields=TODO)
    assert saved["preview"] is None and not service.state()["tasks"]


def test_reconfirm_same_fields_cannot_be_approved_by_old_tab(service):
    original = confirm(service, create(service))
    refreshed = confirm(service, original)
    assert refreshed["preview"]["plan_hash"] == original["preview"]["plan_hash"]
    assert refreshed["revision"] > original["revision"]
    with pytest.raises(GuardError, match="stale_review_revision"):
        approve(service, original)
    assert not service.state()["tasks"]
    approve(service, refreshed)


@pytest.mark.parametrize("cause", ["cancel", "expired", "state_changed", "wrong_hash"])
def test_rejected_approval_does_not_change_state(service, cause):
    pending = confirm(service, create(service))
    if cause == "cancel":
        service.cancel_review(pending["id"], **binding(pending))
    elif cause == "expired":
        with service.sandbox.connect() as db:
            db.execute("UPDATE proposals SET expires=0")
        assert service.get(pending["id"])["status"] == "expired"
    elif cause == "state_changed":
        (service.sandbox.root / "files" / "Inbox" / "new.txt").write_bytes(b"new")
    else:
        pending["preview"]["plan_hash"] = "x" * 64
    before = service.state()
    with pytest.raises(GuardError):
        approve(service, pending)
    assert service.state() == before


def test_model_failure_can_be_reviewed_but_not_implicitly_executed(service):
    record = service.create("User request", lambda *_: {"raw_output": "not JSON"})
    assert record["raw_output"] == "not JSON" and record["metadata"]["generation_error"]
    assert record["fields"] == {}
    with pytest.raises(GuardError, match="invalid_review_fields"):
        confirm(service, record)
    saved = service.save(record["id"], **binding(record), fields={**TODO, "title": "Manual"})
    assert not service.state()["tasks"]
    assert confirm(service, saved)["status"] == "pending"


@pytest.mark.parametrize(
    "fields,error",
    [
        ({**TODO, "unexpected": True}, "invalid_review_fields"),
        (
            {"operation": "files.move", "source": "../outside", "destination": "Archive/test.txt"},
            "invalid_relative_path",
        ),
        ({**MOVE, "destination": "Inbox/test.txt"}, "destination_exists"),
        (
            {
                "operation": "calendar.create",
                "title": "DST",
                "duration_minutes": 30,
                "local_start": "2026-11-01T01:30:00",
                "source_timezone": "America/New_York",
            },
            "nonexistent_or_ambiguous_local_time",
        ),
        (
            {
                "operation": "calendar.create",
                "title": "Offset",
                "duration_minutes": 30,
                "local_start": "2026-11-05T08:00:00-05:00",
                "source_timezone": "America/New_York",
            },
            "invalid_local_time_or_timezone",
        ),
    ],
)
def test_confirmed_edits_still_pass_deterministic_guards(service, fields, error):
    record = create(service)
    saved = service.save(record["id"], **binding(record), fields=fields)
    before = service.state()
    with pytest.raises(GuardError, match=error):
        confirm(service, saved)
    assert service.state() == before


@pytest.mark.parametrize("operation", ["files.move", "files.trash"])
def test_file_undo_has_own_preview_and_approval(service, operation):
    fields = (
        MOVE if operation == "files.move" else {"operation": operation, "path": "Inbox/test.txt"}
    )
    executed = approve(service, confirm(service, create(service, fields)))
    before_restore = service.state()
    restored = service.restore_preview(executed["id"], **binding(executed))
    assert restored["parent_id"] == executed["id"]
    assert restored["preview"]["action"]["tool"] == "files.restore"
    assert service.state() == before_restore
    assert approve(service, restored)["status"] == "executed"
    assert (
        service.sandbox.root / "files" / "Inbox" / "test.txt"
    ).read_bytes() == b"fixture bytes\n"
    assert service.get(executed["id"])["status"] == "executed"


class Crash(BaseException):
    pass


@pytest.mark.parametrize("phase", ["before", "linked", "moved", "modified", "independent_copy"])
def test_interrupted_file_effect_reconciliation(service, monkeypatch, phase):
    pending = confirm(service, create(service, MOVE))

    def interrupted(src, dst):
        if phase in {"linked", "moved", "modified"}:
            os.link(src, dst)
        if phase in {"moved", "modified"}:
            src.unlink()
        if phase == "modified":
            dst.write_bytes(b"changed after crash")
        if phase == "independent_copy":
            dst.write_bytes(src.read_bytes())
        raise Crash()

    monkeypatch.setattr(service.sandbox, "move_exclusive", interrupted)
    with pytest.raises(Crash):
        approve(service, pending)
    reopened = ReviewService(Sandbox(service.sandbox.root))
    crashed = reopened.get(pending["id"])
    assert crashed["status"] == "executing"
    src = service.sandbox.root / "files" / "Inbox" / "test.txt"
    dst = service.sandbox.root / "files" / "Archive" / "test.txt"
    before = [(p.exists(), p.read_bytes() if p.exists() else None) for p in (src, dst)]
    if phase in {"modified", "independent_copy"}:
        with pytest.raises(GuardError, match="recovery_state_ambiguous"):
            reopened.recover(crashed["id"], **binding(crashed))
        assert [(p.exists(), p.read_bytes() if p.exists() else None) for p in (src, dst)] == before
    else:
        recovered = reopened.recover(crashed["id"], **binding(crashed))
        assert recovered["status"] == ("executed" if phase == "moved" else "cancelled")
        assert (dst if phase == "moved" else src).read_bytes() == b"fixture bytes\n"
        assert not (src if phase == "moved" else dst).exists()
        if phase == "moved":
            assert recovered["receipt"]["recovered"]
            assert approve(reopened, recovered)["status"] == "executed"


def test_recovery_cannot_overlap_live_execution(service, monkeypatch):
    pending = confirm(service, create(service, MOVE))
    started, release = Event(), Event()
    execute = service._execute

    def slow(*args):
        started.set()
        assert release.wait(5)
        return execute(*args)

    monkeypatch.setattr(service, "_execute", slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(approve, service, pending)
        try:
            assert started.wait(5)
            with pytest.raises(GuardError, match="workspace_execution_in_progress"):
                service.recover(pending["id"], **binding(pending))
        finally:
            release.set()
        assert future.result()["status"] == "executed"


def test_os_lock_released_on_process_exit(service):
    code = (
        "import os; from pathlib import Path; "
        "from app.services.personal_assistant.sandbox import Sandbox; "
        "from app.services.personal_assistant.locking import workspace_lock; "
        f"lock=workspace_lock(Sandbox(Path({str(service.sandbox.root)!r}))); "
        "lock.__enter__(); os._exit(0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        timeout=10,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )
    assert result.returncode == 0, result.stderr
    with workspace_lock(service.sandbox):
        with pytest.raises(GuardError, match="workspace_execution_in_progress"):
            with workspace_lock(service.sandbox):
                pytest.fail("Lock unexpectedly acquired")


def test_busy_review_approval_does_not_attempt_a_locked_sqlite_audit(service):
    pending = confirm(service, create(service, MOVE))
    with workspace_lock(service.sandbox), service.sandbox.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(GuardError, match="workspace_execution_in_progress"):
            approve(service, pending)
    assert not any(e["event"] == "executed" for e in service.get(pending["id"])["events"])
    assert approve(service, pending)["status"] == "executed"


def test_schema_and_runtime_payload_do_not_include_confirmed_or_expected_fields(monkeypatch):
    captured = {}

    def run_case(self, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(raw_output=generated()["raw_output"], end_to_end_latency_ms=1)

    monkeypatch.setattr(AssistantDraftAdapter, "run_case", run_case)
    state = {"tasks": [], "events": [], "files": {"files/Inbox/a.txt": {}}}
    result = generate_draft("Draft", state, "http://127.0.0.1:11435")
    assert result["schema_requested"] and result["schema_valid"]
    payload = captured["evaluation_case"].input_payload_json
    assert set(payload) == {
        "request",
        "now",
        "timezone",
        "intent_contract",
        "draft_contract",
        "events",
        "tasks",
        "inventory",
    }
    assert payload["now"].endswith("+09:00")
    response_format = AssistantDraftAdapter()._response_format(None)
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["schema"] == draft_schema()
    assert (
        "pattern"
        in draft_schema()["$defs"]["CalendarCreate"]["properties"]["local_start"]["anyOf"][0]
    )
    with pytest.raises(GuardError, match="isolated_runtime_required"):
        generate_draft("Draft", state, "https://example.com")


@pytest.mark.parametrize("kind", ["valid", "invalid_decision", "offset", "extra"])
def test_actual_adapter_transport_requests_schema_and_postvalidates(monkeypatch, kind):
    raw = generated()["raw_output"]
    if kind == "invalid_decision":
        raw = canonical({"decision": None, "intent": None, "reason": "Bad decision"})
    elif kind == "offset":
        raw = generated({**TODO, "local_due": "2026-12-15T08:30:00-05:00"})["raw_output"]
    elif kind == "extra":
        raw = generated({**TODO, "extra": "unexpected"})["raw_output"]
    captured = {}

    def post(self, configuration, base_url, path, body, **kwargs):
        captured.update(url=base_url + path, body=body)
        return {"choices": [{"message": {"content": raw}}]}

    monkeypatch.setattr(AssistantDraftAdapter, "_post_json", post)
    monkeypatch.setattr(
        AssistantDraftAdapter, "_resolve_base_url", lambda *_a, **_k: "http://127.0.0.1:11435"
    )
    monkeypatch.setattr(AssistantDraftAdapter, "_model_name", lambda *_a, **_k: "qwen3.5:9b")
    result = generate_draft(
        "Request", {"tasks": [], "events": [], "files": {}}, "http://127.0.0.1:11435"
    )
    assert captured["body"]["response_format"]["json_schema"]["schema"] == draft_schema()
    assert result["schema_requested"] and result["schema_valid"] == (kind == "valid")
    assert result["raw_output"] == raw
    assert "schema_constrained" not in result


@pytest.fixture
def review_client(tmp_path, monkeypatch):
    settings = copy.copy(get_settings())
    settings.cors_origins = ["http://localhost:3000"]
    settings.personal_assistant_workspace = str(tmp_path)
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(ticket_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "generate_draft", lambda *_: generated())
    app = FastAPI()
    app.include_router(routes.router, prefix=BASE)

    @app.middleware("http")
    async def trusted_test_actor(request, call_next):
        # This fixture injects trusted server state, not production authentication headers.
        actor = replace(
            local_operator_identity(), subject_id=request.headers.get("test-actor", "local-ui")
        )
        request.state.operator_identity = actor
        return await call_next(request)

    with TestClient(app) as client:
        yield client, settings, app


def test_api_confirmation_binding_isolation_and_no_hidden_approval_token(review_client):
    client, _, _ = review_client
    record = client.post(f"{BASE}/reviews", json={"request": "Draft"}, headers=HEADERS).json()
    url = f"{BASE}/reviews/{record['id']}"
    assert client.post(url + "/confirm", json=binding(record), headers=HEADERS).status_code == 422
    assert (
        client.post(
            url + "/confirm", json={**binding(record), "acknowledged": False}, headers=HEADERS
        ).status_code
        == 422
    )
    response = client.post(
        url + "/confirm", json={**binding(record), "acknowledged": True}, headers=HEADERS
    )
    assert response.status_code == 200, response.text
    pending = response.json()
    assert "approval_token" not in response.text
    assert client.get(url, headers={"test-actor": "another"}).status_code == 404
    assert client.get(f"{BASE}/reviews", headers={"test-actor": "another"}).json() == []
    response = client.post(
        url + "/approve",
        json={**binding(pending), "plan_hash": pending["preview"]["plan_hash"]},
        headers=HEADERS,
    )
    assert response.status_code == 200 and response.json()["status"] == "executed"


def test_api_explicit_action_origin_and_feature_flag(review_client):
    client, settings, app = review_client
    payload = {"request": "Draft"}
    assert client.post(f"{BASE}/reviews", json=payload).status_code == 403
    assert (
        client.post(
            f"{BASE}/reviews",
            json=payload,
            headers={**HEADERS, "origin": "https://elsewhere.example"},
        ).status_code
        == 403
    )
    with TestClient(app, client=("203.0.113.2", 8000)) as remote:
        assert remote.get(f"{BASE}/workspace").status_code == 403
    settings.personal_assistant_workspace = None
    assert client.get(f"{BASE}/workspace").status_code == 503
