"""Bind explicit literal todo titles without treating their contents as tool targets."""

import json
import re

from jsonschema import ValidationError, validate

from .contracts import digest
from .inference import MODEL, draft_schema
from .path_grounded_inference import grounded_schema, quoted_title
from .stable_inference import PROMPT, StableDraftAdapter, generate_stable_draft, public_payload

STRATEGY = "compact-role-grounded-v4"
TODO_SUFFIX = re.compile(
    r"\s*(?:을|를)\s*(?:(?:기한|마감)(?:과|및)\s*우선순위\s*없이\s*)?"
    r"할\s*일(?:로|에)\s*추가해\s*(?:줘|주세요)[.!]?\s*"
    r"(?:파일\s*작업(?:은|이)\s*아니(?:야|에요|다)[.!]?\s*)?"
)


def literal_todo_role(request, tasks):
    """Only a complete, single, quoted creation command with no optional fields."""
    title = quoted_title(request)
    if title is None:
        return None
    # The quote boundaries are one character; title spans preserve the literal verbatim.
    prefix, suffix = request[: title["start"] - 1], request[title["end"] + 1 :]
    if prefix.strip() or TODO_SUFFIX.fullmatch(suffix) is None:
        return None
    duplicate = any(t["title"] == title["value"] and t["status"] == "open" for t in tasks)
    return {
        "role": "todo_title",
        "operation": "todo.create",
        "title": title,
        "decision": "clarify" if duplicate else "propose",
        "basis": "complete-quoted-todo-command-and-public-open-tasks",
    }


def role_schema(public):
    hints, title, path = grounded_schema(public["request"], public["inventory"])
    role = literal_todo_role(public["request"], public["tasks"])
    if role:
        assert path is None
        intent = {"type": "null"}
        if role["decision"] == "propose":
            intent = {
                "type": "object",
                "additionalProperties": False,
                "required": ["operation", "title"],
                "properties": {
                    "operation": {"const": "todo.create"},
                    "title": {"const": role["title"]["value"]},
                },
            }
        hints["oneOf"] = [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["decision", "intent", "reason"],
                "properties": {
                    "decision": {"const": role["decision"]},
                    "intent": intent,
                    "reason": hints["oneOf"][0]["properties"]["reason"],
                },
            }
        ]
    return hints, title, path, role


def configuration_hash(public, seed):
    hints, _, _, _ = role_schema(public)
    return digest(
        {
            "strategy": STRATEGY,
            "model": MODEL,
            "prompt": PROMPT,
            "validation_schema": draft_schema(),
            "decoding_schema": hints,
            "generation": {"seed": seed, "max_tokens": 768, "context": 8192},
        }
    )


class RoleGroundedDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    @staticmethod
    def generate_body(configuration, body):
        native = StableDraftAdapter.generate_body(configuration, body)
        public = json.loads(body["messages"][1]["content"])
        native["format"], _, _, _ = role_schema(public)
        return native


def generate_role_grounded_draft(request_text, state, base_url, *, seed=42, now=None):
    public = public_payload(request_text, state, now=now)
    result = generate_stable_draft(
        request_text,
        state,
        base_url,
        seed=seed,
        now=public["now"],
        adapter=RoleGroundedDraftAdapter(),
    )
    hints, title, path, role = role_schema(public)
    grounding_error = None
    if result["schema_valid"]:
        try:
            validate(json.loads(result["raw_output"]), hints)
        except (ValueError, ValidationError):
            result["schema_valid"] = False
            grounding_error = "draft_grounding_mismatch"
    return {
        **result,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(public, seed),
        "decoding_schema_sha256": digest(hints),
        "title_grounding": title,
        "path_grounding": path,
        "role_grounding": role,
        "path_policy": "public-literal-boundary-v3",
        "role_policy": "complete-quoted-todo-role-v4",
        "grounding_error": grounding_error,
    }
