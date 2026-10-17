"""V2: model extracts a form draft; code derives the executable action."""

import json
from typing import Literal

from pydantic import ValidationError

from .contracts import INTENT, GuardError, Intent, StrictModel, digest
from .planning import compile_action
from .service import AssistantService

DRAFT_VERSION = "personal-assistant-draft-v2"


class Draft(StrictModel):
    decision: Literal["propose", "clarify", "refuse", "no_change"]
    intent: Intent | None
    reason: str


def parse_draft(raw: str) -> Draft:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise GuardError("duplicate_json_key")
            result[key] = value
        return result

    def reject(value):
        raise GuardError("non_finite_json")

    try:
        if len(raw) > 16000:
            raise GuardError("response_too_large")
        parsed = Draft.model_validate(
            json.loads(raw, object_pairs_hook=unique, parse_constant=reject)
        )
    except ValueError as exc:
        raise GuardError(f"invalid_draft:{exc}") from exc
    if not parsed.reason.strip() or len(parsed.reason) > 2000:
        raise GuardError("invalid_draft_reason")
    if (parsed.decision == "propose") != (parsed.intent is not None):
        raise GuardError("only_propose_may_have_intent")
    return parsed


class DraftAssistantService(AssistantService):
    def prepare(self, confirmed_fields: dict, raw_draft: str) -> dict:
        """Confirmed fields are a separate user input, never an automatic copy of the draft."""
        with self.sandbox.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                confirmed = INTENT.validate_python(confirmed_fields)
                state = self.state(db)
                action = compile_action(confirmed, state, self.sandbox)
                draft = parse_draft(raw_draft)
                if draft.decision != "propose":
                    raise GuardError("model_did_not_propose_draft")
                if draft.intent.model_dump() != confirmed.model_dump():
                    raise GuardError("draft_does_not_match_confirmed_fields")
            except (GuardError, ValidationError) as exc:
                self._audit(
                    db, None, "rejected", {"reason": str(exc), "raw_hash": digest(raw_draft)}
                )
                db.commit()
                raise GuardError(str(exc)) from exc
            self._audit(
                db,
                None,
                "draft_confirmed",
                {
                    "contract": DRAFT_VERSION,
                    "intent_hash": digest(confirmed.model_dump()),
                    "raw_hash": digest(raw_draft),
                },
            )
            return self._preview(db, action, state)
