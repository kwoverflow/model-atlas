"""Restricted test storage. This is not a connector for arbitrary user folders."""

import hashlib
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from .contracts import VERSION, GuardError


class Sandbox:
    @classmethod
    def create(cls, root: Path):
        # Exclusive creation prevents accidentally adopting an existing user directory.
        root = root.absolute()
        if root.parent.resolve() != root.parent:
            raise GuardError("sandbox_parent_must_not_be_linked")
        root.mkdir(parents=False, exist_ok=False)
        (root / ".assistant-sandbox").write_text(VERSION, encoding="utf-8")
        (root / "files").mkdir()
        (root / "trash").mkdir()
        sandbox = cls(root)
        with sandbox.connect() as db:
            db.executescript("""
                CREATE TABLE events (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE proposals (
                    id TEXT PRIMARY KEY, action TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    token_hash TEXT NOT NULL, expires REAL NOT NULL, status TEXT NOT NULL,
                    receipt TEXT
                );
                CREATE TABLE audit (
                    sequence INTEGER PRIMARY KEY, proposal_id TEXT, event TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
            """)
        return sandbox

    def __init__(self, root: Path):
        self.root = root.absolute()
        if self.root.resolve() != self.root or self._linked(self.root):
            raise GuardError("linked_sandbox_root")
        if (self.root / ".assistant-sandbox").read_text(encoding="utf-8") != VERSION:
            raise GuardError("not_an_assistant_sandbox")

    @staticmethod
    def _linked(path: Path) -> bool:
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )

    @contextmanager
    def connect(self):
        path = self.root / "state.sqlite3"
        if path.exists() and self._linked(path):
            raise GuardError("linked_database")
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def file_path(self, relative: str, *, must_exist=False, area="files") -> Path:
        parts = relative.split("/")
        if (
            area not in {"files", "trash"}
            or not relative
            or PurePosixPath(relative).is_absolute()
            or any(
                p in {"", ".", ".."}
                or p.endswith((" ", "."))
                or re.search(r'[\\:*?"<>|\x00-\x1f]', p)
                or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p)
                for p in parts
            )
        ):
            raise GuardError("invalid_relative_path")
        path = self.root / area
        if self._linked(self.root) or self._linked(path):
            raise GuardError("linked_root")
        for part in parts:
            path = path / part
            if path.is_symlink() or (path.exists() and self._linked(path)):
                raise GuardError("linked_path")
        if not path.parent.is_dir():
            raise GuardError("parent_directory_missing")
        if must_exist and not path.is_file():
            raise GuardError("source_file_missing")
        if path.is_file() and path.stat().st_nlink != 1:
            raise GuardError("hardlinked_file")
        return path

    def check_move(self, source: str, destination: str, *, source_area="files"):
        src = self.file_path(source, must_exist=True, area=source_area)
        dst = self.file_path(destination)
        if dst.exists() or src == dst:
            raise GuardError("destination_exists")
        return src, dst

    def files_snapshot(self) -> dict:
        result = {}
        for area in ("files", "trash"):
            base = self.root / area
            if self._linked(base):
                raise GuardError("linked_root")
            for folder, dirs, files in os.walk(base, followlinks=False):
                for name in sorted(dirs + files):
                    path = Path(folder) / name
                    if self._linked(path):
                        raise GuardError("linked_path")
                    if path.is_file():
                        self.file_path(
                            path.relative_to(base).as_posix(), must_exist=True, area=area
                        )
                        result[path.relative_to(self.root).as_posix()] = {
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            "size": path.stat().st_size,
                        }
        return result

    @staticmethod
    def move_exclusive(source: Path, destination: Path):
        # Same-volume link/unlink refuses overwrite on both Windows and POSIX.
        # A process crash between calls can leave both names; journal blocks replay.
        os.link(source, destination, follow_symlinks=False)
        try:
            source.unlink()
        except OSError:
            destination.unlink()
            raise
