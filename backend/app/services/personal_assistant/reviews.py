"""Persist user edits separately from model output and bind approval to a saved revision."""

import json
import time
import uuid

from pydantic import ValidationError

from .contracts import INTENT, GuardError, canonical, digest
from .drafts import parse_draft
from .locking import workspace_lock
from .planning import compile_action
from .recovery import reconcile_file
from .service import AssistantService

REVIEW_VERSION = "personal-assistant-user-review-v1"


class ReviewService(AssistantService):
    def __init__(self, sandbox):
        super().__init__(sandbox)
        with sandbox.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS assistant_reviews (
                    id TEXT PRIMARY KEY, request TEXT NOT NULL, raw TEXT NOT NULL,
                    initial_fields TEXT NOT NULL, fields TEXT NOT NULL, revision INTEGER NOT NULL,
                    phase TEXT NOT NULL, proposal_id TEXT, approval_token TEXT,
                    metadata TEXT NOT NULL, created REAL NOT NULL, parent_id TEXT
                );
                CREATE TABLE IF NOT EXISTS assistant_review_events (
                    sequence INTEGER PRIMARY KEY, review_id TEXT NOT NULL,
                    event TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL
                );
            """)

    @staticmethod
    def _event(db, review_id, event, payload):
        db.execute(
            "INSERT INTO assistant_review_events(review_id,event,payload,created) VALUES(?,?,?,?)",
            (review_id, event, canonical(payload), time.time()),
        )

    @staticmethod
    def _row(db, review_id):
        row = db.execute("SELECT * FROM assistant_reviews WHERE id=?", (review_id,)).fetchone()
        if row is None:
            raise GuardError("review_not_found")
        return row

    @staticmethod
    def _hash(row):
        return digest(
            {
                "id": row["id"],
                "revision": row["revision"],
                "fields": json.loads(row["fields"]),
                "raw_hash": digest(row["raw"]),
                "parent_id": row["parent_id"],
            }
        )

    def _binding(self, db, review_id, revision, content_hash):
        row = self._row(db, review_id)
        if row["revision"] != revision or self._hash(row) != content_hash:
            raise GuardError("stale_review_revision")
        return row

    @staticmethod
    def _proposal(db, row):
        return (
            db.execute("SELECT * FROM proposals WHERE id=?", (row["proposal_id"],)).fetchone()
            if row["proposal_id"]
            else None
        )

    def _read(self, db, row):
        proposal = self._proposal(db, row)
        status = proposal["status"] if proposal else row["phase"]
        if proposal and status == "pending" and proposal["expires"] < time.time():
            status = "expired"
        preview = (
            None
            if proposal is None
            else {
                "proposal_id": proposal["id"],
                "action": json.loads(proposal["action"]),
                "plan_hash": digest(json.loads(proposal["action"])),
                "expires_at": proposal["expires"],
            }
        )
        return {
            "id": row["id"],
            "request": row["request"],
            "raw_output": row["raw"],
            "initial_fields": json.loads(row["initial_fields"]),
            "fields": json.loads(row["fields"]),
            "revision": row["revision"],
            "content_hash": self._hash(row),
            "status": status,
            "metadata": json.loads(row["metadata"]),
            "created_at": row["created"],
            "parent_id": row["parent_id"],
            "preview": preview,
            "receipt": json.loads(proposal["receipt"])
            if proposal and proposal["receipt"]
            else None,
            "events": [
                {**dict(r), "payload": json.loads(r["payload"])}
                for r in db.execute(
                    "SELECT event,payload,created FROM assistant_review_events "
                    "WHERE review_id=? ORDER BY sequence",
                    (row["id"],),
                )
            ],
        }

    def get(self, review_id):
        with self.sandbox.connect() as db:
            return self._read(db, self._row(db, review_id))

    def list_reviews(self):
        with self.sandbox.connect() as db:
            return [
                self._read(db, row)
                for row in db.execute(
                    "SELECT * FROM assistant_reviews ORDER BY created DESC LIMIT 50"
                )
            ]

    def create(self, request_text, generator):
        metadata = {}
        raw, initial = "", {}
        try:
            generated = generator(request_text, self.state())
            raw = generated["raw_output"]
            metadata = {k: v for k, v in generated.items() if k != "raw_output"}
            draft = parse_draft(raw)
            initial = (
                draft.intent.model_dump(exclude_none=True, exclude_unset=True)
                if draft.intent
                else {}
            )
            metadata.update(decision=draft.decision, reason=draft.reason)
            if metadata.get("schema_valid") is False:
                raise GuardError("runtime_schema_validation_failed")
        except Exception as exc:
            metadata["generation_error"] = f"{type(exc).__name__}: {str(exc)[:1500]}"
        review_id = uuid.uuid4().hex
        with self.sandbox.connect() as db:
            db.execute(
                "INSERT INTO assistant_reviews VALUES(?,?,?,?,?,1,'draft',NULL,NULL,?,?,NULL)",
                (
                    review_id,
                    request_text,
                    raw,
                    canonical(initial),
                    canonical(initial),
                    canonical(metadata),
                    time.time(),
                ),
            )
            self._event(
                db, review_id, "draft_created", {"raw_hash": digest(raw), "metadata": metadata}
            )
        return self.get(review_id)

    def save(self, review_id, revision, content_hash, fields):
        if len(canonical(fields)) > 16000:
            raise GuardError("review_fields_too_large")
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._binding(db, review_id, revision, content_hash)
            proposal = self._proposal(db, row)
            if row["parent_id"] or (
                proposal and proposal["status"] in {"executed", "executing", "failed"}
            ):
                raise GuardError("completed_review_cannot_be_edited")
            if proposal:
                db.execute("UPDATE proposals SET status='superseded' WHERE id=?", (proposal["id"],))
            db.execute(
                "UPDATE assistant_reviews SET fields=?,revision=revision+1,phase='draft',"
                "proposal_id=NULL,approval_token=NULL WHERE id=?",
                (canonical(fields), review_id),
            )
            before = json.loads(row["fields"])
            changes = {
                key: {"before": before.get(key), "after": fields.get(key)}
                for key in before.keys() | fields.keys()
                if before.get(key) != fields.get(key)
            }
            self._event(
                db, review_id, "user_edited", {"revision": revision + 1, "changes": changes}
            )
        return self.get(review_id)

    def confirm(self, review_id, revision, content_hash):
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._binding(db, review_id, revision, content_hash)
            if row["parent_id"]:
                raise GuardError("restore_preview_already_created")
            previous = self._proposal(db, row)
            if previous and previous["status"] in {"executed", "executing", "failed"}:
                raise GuardError("completed_review_cannot_be_confirmed")
            try:
                confirmed = INTENT.validate_python(json.loads(row["fields"]))
                state = self.state(db)
                action = compile_action(confirmed, state, self.sandbox)
            except ValidationError as exc:
                raise GuardError("invalid_review_fields") from exc
            if previous:
                db.execute("UPDATE proposals SET status='superseded' WHERE id=?", (previous["id"],))
            preview = self._preview(db, action, state)
            db.execute(
                "UPDATE assistant_reviews SET revision=revision+1,phase='confirmed',"
                "proposal_id=?,approval_token=? "
                "WHERE id=?",
                (preview["proposal_id"], preview["approval_token"], review_id),
            )
            initial = json.loads(row["initial_fields"])
            confirmed_row = self._row(db, review_id)
            self._event(
                db,
                review_id,
                "user_confirmed",
                {
                    "revision": confirmed_row["revision"],
                    "content_hash": self._hash(confirmed_row),
                    "confirmed_fields": confirmed.model_dump(),
                    "model_draft_changed": initial != json.loads(row["fields"]),
                    "proposal_id": preview["proposal_id"],
                    "before_files": state["files"],
                },
            )
        return self.get(review_id)

    def approve(self, proposal_id, token, plan_hash):
        with workspace_lock(self.sandbox):
            return super().approve(proposal_id, token, plan_hash)

    def approve_review(self, review_id, revision, content_hash, plan_hash):
        with self.sandbox.connect() as db:
            row = self._binding(db, review_id, revision, content_hash)
            if row["phase"] != "confirmed" or not row["proposal_id"]:
                raise GuardError("review_confirmation_required")
            proposal_id, token = row["proposal_id"], row["approval_token"]
        try:
            receipt = self.approve(proposal_id, token, plan_hash)
        except GuardError as exc:
            # The live executor may hold a SQLite write transaction. Do not turn
            # its fast OS-lock rejection into a blocking audit write or HTTP 500.
            if str(exc) == "workspace_execution_in_progress":
                raise
            with self.sandbox.connect() as db:
                self._event(db, review_id, "execution_rejected", {"reason": str(exc)})
            raise
        with self.sandbox.connect() as db:
            event = "execution_replayed" if receipt["replayed"] else "executed"
            self._event(db, review_id, event, {"receipt": receipt})
        return self.get(review_id)

    def cancel_review(self, review_id, revision, content_hash):
        with self.sandbox.connect() as db:
            row = self._binding(db, review_id, revision, content_hash)
            if not row["proposal_id"]:
                raise GuardError("review_confirmation_required")
            proposal_id, token = row["proposal_id"], row["approval_token"]
        self.cancel(proposal_id, token)
        with self.sandbox.connect() as db:
            self._event(db, review_id, "cancelled", {})
        return self.get(review_id)

    def restore_preview(self, review_id, revision, content_hash):
        with self.sandbox.connect() as db:
            row = self._binding(db, review_id, revision, content_hash)
            if row["parent_id"]:
                raise GuardError("restore_of_restore_not_supported")
            original = row["proposal_id"]
        preview = self.prepare_undo(original)
        restore_id = uuid.uuid4().hex
        with self.sandbox.connect() as db:
            db.execute(
                "INSERT INTO assistant_reviews VALUES(?,?,?,?,?,1,'confirmed',?,?,?,?,?)",
                (
                    restore_id,
                    "복구: " + row["request"],
                    row["raw"],
                    row["initial_fields"],
                    row["fields"],
                    preview["proposal_id"],
                    preview["approval_token"],
                    row["metadata"],
                    time.time(),
                    review_id,
                ),
            )
            self._event(
                db,
                restore_id,
                "restore_preview",
                {
                    "parent_id": review_id,
                    "before_files": self.state(db)["files"],
                },
            )
        return self.get(restore_id)

    def recover(self, review_id, revision, content_hash):
        with workspace_lock(self.sandbox):
            return self._recover(review_id, revision, content_hash)

    def _recover(self, review_id, revision, content_hash):
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._binding(db, review_id, revision, content_hash)
            proposal = self._proposal(db, row)
            if proposal is None or proposal["status"] not in {"executing", "failed"}:
                raise GuardError("interrupted_file_operation_required")
            event = db.execute(
                "SELECT payload FROM assistant_review_events WHERE review_id=? "
                "AND event IN ('user_confirmed','restore_preview') ORDER BY sequence DESC LIMIT 1",
                (review_id,),
            ).fetchone()
            if event is None:
                raise GuardError("recovery_evidence_missing")
            outcome = reconcile_file(
                self.sandbox,
                db,
                proposal,
                json.loads(event["payload"])["before_files"],
                json.loads(proposal["action"]),
            )
            self._event(db, review_id, "reconciled", {"outcome": outcome})
            self._audit(db, proposal["id"], "reconciled", {"outcome": outcome})
        return self.get(review_id)
