"""Evidence-bound optional fields and ID-bound completion; output remains unmodified."""

import json
import re

from jsonschema import ValidationError, validate

from .contracts import digest
from .inference import MODEL, draft_schema
from .request_evidence import creation_evidence, source
from .role_grounded_inference import role_schema
from .stable_inference import PROMPT, StableDraftAdapter, generate_stable_draft, public_payload

STRATEGY = "compact-field-grounded-v5"
COMPLETE_ID = re.compile(
    r"\s*할\s*일\s+(?P<task_id>[A-Za-z0-9][A-Za-z0-9_.:-]{0,127})(?:을|를)\s*"
    r"(?:완료해|완료(?:로)?\s*바꿔)\s*(?:줘|주세요)[.!]?\s*"
)


def completion_role(public):
    match = COMPLETE_ID.fullmatch(public["request"])
    if match is None:
        return None
    matches = [task for task in public["tasks"] if task["task_id"] == match["task_id"]]
    status = matches[0]["status"] if len(matches) == 1 else None
    decision = "propose" if status == "open" else "no_change" if status == "complete" else "clarify"
    return {
        "role": "todo_task_id",
        "operation": "todo.complete",
        "decision": decision,
        "target": source(public["request"], *match.span("task_id"), match["task_id"]),
        "state_evidence": {"matches": len(matches), "status": status, "source": "public.tasks"},
    }


def bind_decision(hints, decision, fields=None):
    reason = hints["oneOf"][0]["properties"]["reason"]
    intent = (
        {"type": "null"}
        if fields is None
        else {
            "type": "object",
            "additionalProperties": False,
            "required": list(fields),
            "properties": {key: {"const": value} for key, value in fields.items()},
        }
    )
    hints["oneOf"] = [
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["decision", "intent", "reason"],
            "properties": {"decision": {"const": decision}, "intent": intent, "reason": reason},
        }
    ]


def evidence_schema(public):
    hints, title, path, role = role_schema(public)
    fields = creation_evidence(public)
    completion = completion_role(public)
    if completion:
        values = {"operation": "todo.complete", "task_id": completion["target"]["value"]}
        bind_decision(
            hints, completion["decision"], values if completion["decision"] == "propose" else None
        )
        role = completion
    elif fields["operation"] and path is None:
        zone, priority = fields["source_timezone"], fields["priority"]
        ambiguous = zone["mode"] == "ambiguous" or (
            fields["operation"] == "todo.create" and priority["mode"] == "ambiguous"
        )
        if ambiguous:
            bind_decision(hints, "clarify")
        else:
            for definition in ("CalendarCreate", "TodoCreate"):
                schema = hints["$defs"][definition]
                schema["properties"]["source_timezone"] = {"const": zone["value"]}
                if zone["mode"] == "specified":
                    schema["required"] = list(
                        dict.fromkeys([*schema["required"], "source_timezone"])
                    )
            schema = hints["$defs"]["TodoCreate"]
            schema["properties"]["priority"] = (
                {"const": priority["value"]}
                if priority["mode"] == "specified"
                else {"type": "null"}
            )
            if priority["mode"] == "specified":
                schema["required"] = list(dict.fromkeys([*schema["required"], "priority"]))
    return hints, title, path, role, fields


def configuration_hash(public, seed):
    hints, _, _, _, _ = evidence_schema(public)
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


class FieldGroundedDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    @staticmethod
    def generate_body(configuration, body):
        native = StableDraftAdapter.generate_body(configuration, body)
        public = json.loads(body["messages"][1]["content"])
        native["format"], _, _, _, _ = evidence_schema(public)
        return native


def generate_field_grounded_draft(request_text, state, base_url, *, seed=42, now=None):
    public = public_payload(request_text, state, now=now)
    result = generate_stable_draft(
        request_text,
        state,
        base_url,
        seed=seed,
        now=public["now"],
        adapter=FieldGroundedDraftAdapter(),
    )
    hints, title, path, role, fields = evidence_schema(public)
    error = None
    if result["schema_valid"]:
        try:
            raw = json.loads(result["raw_output"])
            validate(raw, hints)
            if (
                raw["decision"] == "propose"
                and raw["intent"]["operation"] in {"todo.create", "calendar.create"}
                and not fields["operation"]
            ):
                raise ValueError("unresolved_creation_evidence")
        except (ValueError, ValidationError):
            result["schema_valid"] = False
            error = "draft_field_evidence_mismatch"
    return {
        **result,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(public, seed),
        "decoding_schema_sha256": digest(hints),
        "title_grounding": title,
        "path_grounding": path,
        "role_grounding": role,
        "field_evidence": fields,
        "path_policy": "public-literal-boundary-v3",
        "role_policy": "public-task-id-and-title-v5",
        "field_policy": "source-omission-default-v5",
        "grounding_error": error,
    }
