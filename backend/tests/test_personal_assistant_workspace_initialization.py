import copy
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.routes import personal_assistant as routes
from app.api.v1.routes import structured_requests as ticket_routes
from app.core.config import get_settings
from app.services.personal_assistant.contracts import VERSION, GuardError
from app.services.personal_assistant_workspace import initialization_lock

BASE = "/api/v1/personal-assistant"


@pytest.fixture
def client(tmp_path, monkeypatch):
    settings = copy.copy(get_settings())
    settings.personal_assistant_workspace = str(tmp_path)
    settings.oidc_jwt_enabled = False
    settings.oidc_browser_login_enabled = False
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(ticket_routes, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(routes.router, prefix=BASE)
    with TestClient(app, raise_server_exceptions=False) as browser:
        yield browser


def test_first_workspace_reads_wait_for_complete_initialization(client, monkeypatch):
    entered, second_entered, release = Event(), Event(), Event()
    original = Path.write_text
    original_service = routes.open_review_service

    def observe_service(*args):
        if entered.is_set():
            second_entered.set()
        return original_service(*args)

    def pause_marker(path, *args, **kwargs):
        if path.name == ".assistant-sandbox":
            entered.set()
            assert release.wait(5)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", pause_marker)
    monkeypatch.setattr(routes, "open_review_service", observe_service)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.get, BASE + "/workspace")
        try:
            assert entered.wait(5)
            second = pool.submit(client.get, BASE + "/reviews")
            assert second_entered.wait(5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.1)
        finally:
            release.set()
        workspace, reviews = first.result(timeout=5), second.result(timeout=5)
    assert workspace.status_code == reviews.status_code == 200
    assert workspace.json()["state"] == {"events": [], "tasks": [], "files": {}}
    assert reviews.json() == []


def test_initialization_lock_is_bounded_and_released(tmp_path):
    with initialization_lock(tmp_path):
        with pytest.raises(GuardError, match="assistant_workspace_initializing"):
            with initialization_lock(tmp_path, timeout=0):
                pytest.fail("Initialization lock was acquired twice")
    with initialization_lock(tmp_path, timeout=0):
        pass


def test_initialization_lock_excludes_another_process(tmp_path):
    code = (
        "from pathlib import Path; "
        "from app.services.personal_assistant_workspace import initialization_lock; "
        f"lock = initialization_lock(Path({str(tmp_path)!r}), timeout=0); "
        "lock.__enter__()"
    )
    with initialization_lock(tmp_path):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            timeout=10,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        )
    assert result.returncode != 0
    assert b"assistant_workspace_initializing" in result.stderr


def test_initialization_lock_is_released_after_failure(tmp_path):
    with pytest.raises(RuntimeError, match="initialization_failed"):
        with initialization_lock(tmp_path):
            raise RuntimeError("initialization_failed")
    with initialization_lock(tmp_path, timeout=0):
        pass


def test_initialization_timeout_is_a_service_unavailable_response(client, monkeypatch):
    def unavailable(*_args):
        raise GuardError("assistant_workspace_initializing")

    monkeypatch.setattr(routes, "open_review_service", unavailable)
    response = client.get(BASE + "/workspace")
    assert response.status_code == 503
    assert response.json()["detail"] == "assistant_workspace_initializing"


def test_hardlinked_initialization_lock_is_rejected(tmp_path):
    source = tmp_path / "sentinel"
    source.write_bytes(b"unchanged")
    os.link(source, tmp_path / ".assistant-initialization.lock")
    with pytest.raises(GuardError, match="linked_initialization_lock"):
        with initialization_lock(tmp_path):
            pytest.fail("Linked lock accepted")
    assert source.read_bytes() == b"unchanged"


def test_partial_workspace_is_not_adopted_or_overwritten(client, tmp_path):
    from app.services.operator_identity import local_operator_identity
    from app.services.structured_requests import owner_key

    root = tmp_path / owner_key(local_operator_identity())
    root.mkdir()
    sentinel = root / "sentinel"
    sentinel.write_bytes(b"unchanged")
    assert client.get(BASE + "/workspace").status_code == 503
    assert sentinel.read_bytes() == b"unchanged"
    assert not (root / ".assistant-sandbox").exists()


@pytest.mark.parametrize("create_database", [False, True])
def test_incomplete_database_is_not_reinitialized(client, tmp_path, create_database):
    from app.services.operator_identity import local_operator_identity
    from app.services.structured_requests import owner_key

    root = tmp_path / owner_key(local_operator_identity())
    root.mkdir()
    (root / ".assistant-sandbox").write_text(VERSION, encoding="utf-8")
    database = root / "state.sqlite3"
    if create_database:
        sqlite3.connect(database).close()
    before = database.read_bytes() if create_database else None
    assert client.get(BASE + "/workspace").status_code == 503
    assert client.get(BASE + "/reviews").status_code == 503
    assert (database.read_bytes() if database.exists() else None) == before
