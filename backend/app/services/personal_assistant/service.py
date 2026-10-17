"""Persisted preview -> explicit approval/cancel -> one execution -> receipt."""

import hashlib
import json
import secrets
import time
import uuid

from pydantic import ValidationError

from .contracts import INTENT, LOGICAL_ROOT, GuardError, canonical, digest, parse_plan
from .planning import compile_action
from .sandbox import Sandbox


class AssistantService:
    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox

    def state(self, db=None) -> dict:
        if db is None:
            with self.sandbox.connect() as connection:
                return self.state(connection)
        return {
            "events": [
                json.loads(r[0]) for r in db.execute("SELECT payload FROM events ORDER BY id")
            ],
            "tasks": [
                json.loads(r[0]) for r in db.execute("SELECT payload FROM tasks ORDER BY id")
            ],
            "files": self.sandbox.files_snapshot(),
        }

    @staticmethod
    def _audit(db, proposal_id, event, payload):
        db.execute(
            "INSERT INTO audit(proposal_id,event,payload) VALUES(?,?,?)",
            (proposal_id, event, canonical(payload)),
        )

    def prepare(self, confirmed_fields: dict, raw_plan: str) -> dict:
        """Fields must come from a confirmed form, NEVER directly from model output."""
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                intent = INTENT.validate_python(confirmed_fields)
                state = self.state(db)
                required = compile_action(intent, state, self.sandbox)
                plan = parse_plan(raw_plan)
                if plan.actions[0].model_dump() != required:
                    raise GuardError("plan_does_not_match_confirmed_fields")
            except (GuardError, ValidationError) as exc:
                self._audit(
                    db, None, "rejected", {"reason": str(exc), "raw_hash": digest(raw_plan)}
                )
                db.commit()
                raise GuardError(str(exc)) from exc
            return self._preview(db, required, state)

    def _preview(self, db, action, state):
        proposal_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        expires = time.time() + 300
        fingerprint = digest(state)
        db.execute(
            "INSERT INTO proposals VALUES(?,?,?,?,?,?,NULL)",
            (proposal_id, canonical(action), fingerprint, digest(token), expires, "pending"),
        )
        self._audit(db, proposal_id, "preview", {"action": action, "before_hash": fingerprint})
        return {
            "proposal_id": proposal_id,
            "action": action,
            "plan_hash": digest(action),
            "before_hash": fingerprint,
            "approval_token": token,
            "expires_at": expires,
            "status": "pending",
        }

    def _authorized(self, db, proposal_id, token):
        row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if row is None or not secrets.compare_digest(row["token_hash"], digest(token)):
            raise GuardError("invalid_approval_token")
        return row

    def cancel(self, proposal_id: str, token: str):
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._authorized(db, proposal_id, token)
            if row["status"] != "pending":
                raise GuardError("proposal_not_pending")
            db.execute("UPDATE proposals SET status='cancelled' WHERE id=?", (proposal_id,))
            self._audit(db, proposal_id, "cancelled", {})

    def approve(self, proposal_id: str, token: str, plan_hash: str) -> dict:
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._authorized(db, proposal_id, token)
            action = json.loads(row["action"])
            if digest(action) != plan_hash:
                raise GuardError("approval_plan_hash_mismatch")
            if row["status"] == "executed":
                return {**json.loads(row["receipt"]), "replayed": True}
            if row["status"] != "pending":
                raise GuardError(f"proposal_not_pending:{row['status']}")
            if row["expires"] < time.time() or digest(self.state(db)) != row["fingerprint"]:
                db.execute("UPDATE proposals SET status='stale' WHERE id=?", (proposal_id,))
                self._audit(db, proposal_id, "stale", {})
                db.commit()
                raise GuardError("approval_expired_or_state_changed")
            if action["tool"].startswith("files."):
                # Persist intent before filesystem effects: interrupted execution is never retried.
                db.execute("UPDATE proposals SET status='executing' WHERE id=?", (proposal_id,))
                self._audit(db, proposal_id, "executing", {"action": action})
                db.commit()
                db.execute("BEGIN IMMEDIATE")
                if digest(self.state(db)) != row["fingerprint"]:
                    db.execute("UPDATE proposals SET status='stale' WHERE id=?", (proposal_id,))
                    db.commit()
                    raise GuardError("state_changed_before_file_execution")
            try:
                receipt = self._execute(db, proposal_id, action)
            except (OSError, GuardError) as exc:
                db.execute("UPDATE proposals SET status='failed' WHERE id=?", (proposal_id,))
                self._audit(db, proposal_id, "failed", {"error": str(exc)})
                db.commit()
                raise GuardError(f"execution_failed:{exc}") from exc
            receipt.update(proposal_id=proposal_id, status="executed", replayed=False)
            db.execute(
                "UPDATE proposals SET status='executed',receipt=? WHERE id=?",
                (canonical(receipt), proposal_id),
            )
            self._audit(db, proposal_id, "executed", receipt)
            return receipt

    def _execute(self, db, proposal_id, action):
        tool, args = action["tool"], action["arguments"]
        if tool == "calendar.create":
            value = {"event_id": proposal_id, **args}
            db.execute("INSERT INTO events VALUES(?,?)", (proposal_id, canonical(value)))
            return {"event": value}
        if tool == "todo.create":
            value = {"task_id": proposal_id, "status": "open", **args}
            db.execute("INSERT INTO tasks VALUES(?,?)", (proposal_id, canonical(value)))
            return {"task": value}
        if tool == "todo.complete":
            row = db.execute("SELECT payload FROM tasks WHERE id=?", (args["task_id"],)).fetchone()
            if row is None:
                raise GuardError("task_missing")
            value = {**json.loads(row[0]), "status": "complete"}
            db.execute("UPDATE tasks SET payload=? WHERE id=?", (canonical(value), args["task_id"]))
            return {"task": value}
        if tool == "files.restore":
            source, destination = args["source"], args["destination"]
            source_area = args["source_area"]
        elif tool == "files.move":
            source = args["source"].removeprefix(LOGICAL_ROOT + "/")
            destination = args["destination"].removeprefix(LOGICAL_ROOT + "/")
            source_area = "files"
        elif tool == "files.trash":
            source = args["path"].removeprefix(LOGICAL_ROOT + "/")
            destination, source_area = proposal_id, "files"
        else:
            raise GuardError("unsupported_tool")
        src = self.sandbox.file_path(source, must_exist=True, area=source_area)
        destination_area = "trash" if tool == "files.trash" else "files"
        dst = self.sandbox.file_path(destination, area=destination_area)
        if dst.exists():
            raise GuardError("destination_exists")
        checksum = hashlib.sha256(src.read_bytes()).hexdigest()
        self.sandbox.move_exclusive(src, dst)
        return {
            "file_change": {
                "source": source,
                "source_area": source_area,
                "destination": destination,
                "destination_area": destination_area,
                "sha256": checksum,
            },
        }

    def prepare_undo(self, proposal_id: str) -> dict:
        """A new approval is required for restoring a prior move/quarantine operation."""
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            if row is None or row["status"] != "executed":
                raise GuardError("no_executed_change")
            if json.loads(row["action"])["tool"] not in {"files.move", "files.trash"}:
                raise GuardError("undo_only_supported_for_file_changes")
            change = json.loads(row["receipt"])["file_change"]
            src, _ = self.sandbox.check_move(
                change["destination"], change["source"], source_area=change["destination_area"]
            )
            if hashlib.sha256(src.read_bytes()).hexdigest() != change["sha256"]:
                raise GuardError("changed_file_cannot_be_undone")
            action = {
                "tool": "files.restore",
                "arguments": {
                    "source": change["destination"],
                    "source_area": change["destination_area"],
                    "destination": change["source"],
                },
            }
            return self._preview(db, action, self.state(db))

    def audit(self) -> list[dict]:
        with self.sandbox.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM audit ORDER BY sequence")]
