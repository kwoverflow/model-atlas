"""Serialize first-use initialization before any request opens an owner workspace."""

import errno
import os
import time
from contextlib import contextmanager
from pathlib import Path

from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.reviews import ReviewService
from app.services.personal_assistant.sandbox import Sandbox


@contextmanager
def initialization_lock(base: Path, *, timeout=5):
    path = base / ".assistant-initialization.lock"
    if path.is_symlink() or (
        path.exists() and (Sandbox._linked(path) or path.stat().st_nlink != 1)
    ):
        raise GuardError("linked_initialization_lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    locked = False
    try:
        if os.fstat(fd).st_nlink != 1:
            raise GuardError("linked_initialization_lock")
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        deadline = time.monotonic() + timeout
        while not locked:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise GuardError("assistant_workspace_initializing") from exc
                time.sleep(0.01)
        yield
    finally:
        try:
            if locked:
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def open_review_service(base: Path, owner: str) -> ReviewService:
    # An existing directory may still belong to an in-progress creator.
    with initialization_lock(base):
        root = base / owner
        sandbox = Sandbox(root) if root.exists() else Sandbox.create(root)
        if not (root / "state.sqlite3").is_file():
            raise GuardError("assistant_workspace_not_initialized")
        with sandbox.connect() as db:
            tables = {
                row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if not {"events", "tasks", "proposals", "audit"}.issubset(tables):
                raise GuardError("assistant_workspace_not_initialized")
        return ReviewService(sandbox)
