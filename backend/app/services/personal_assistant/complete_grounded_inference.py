"""Preserve literal field roles and require all provable requested creation fields."""

import json

from jsonschema import ValidationError, validate

from .contracts import digest
from .creation_evidence import creation_evidence
from .field_grounded_inference import bind_decision, completion_role
from .inference import MODEL, draft_schema
from .role_grounded_inference import role_schema
from .stable_inference import PROMPT, StableDraftAdapter, generate_stable_draft, public_payload

STRATEGY = "compact-complete-grounded-v6"


def require(schema, name, value):
    schema["properties"][name] = {"const": value}
    schema["required"] = list(dict.fromkeys([*schema["required"], name]))


def complete_schema(public):
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
        operation = fields["operation"]
        names = ["source_timezone", "local_time"]
        names.append("priority" if operation == "todo.create" else "duration_minutes")
        duplicate = fields["title"] and any(
            task["title"] == fields["title"]["value"] and task["status"] == "open"
            for task in public["tasks"]
        )
        if (
            any(fields[name]["mode"] == "ambiguous" for name in names)
            or len(fields["title_candidates"]) > 1
            or (operation == "todo.create" and duplicate)
        ):
            bind_decision(hints, "clarify")
        else:
            definition = "TodoCreate" if operation == "todo.create" else "CalendarCreate"
            schema = hints["$defs"][definition]
            title = fields["title"] or title
            if title:
                require(schema, "title", title["value"])
            require(schema, "source_timezone", fields["source_timezone"]["value"])
            temporal_name = "local_due" if operation == "todo.create" else "local_start"
            temporal = fields["local_time"]
            if temporal["mode"] == "specified":
                require(schema, temporal_name, temporal["value"])
            else:
                schema["properties"][temporal_name] = {"type": "null"}
            if operation == "todo.create":
                priority = fields["priority"]
                if priority["mode"] == "specified":
                    require(schema, "priority", priority["value"])
                else:
                    schema["properties"]["priority"] = {"type": "null"}
            else:
                require(schema, "duration_minutes", fields["duration_minutes"]["value"])
            # Retain V4's proven single-command role; otherwise allow conservative decisions.
            reason = hints["oneOf"][0]["properties"]["reason"]
            hints["oneOf"] = [
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["decision", "intent", "reason"],
                    "properties": {
                        "decision": {"const": "propose"},
                        "intent": {"$ref": f"#/$defs/{definition}"},
                        "reason": reason,
                    },
                },
                {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["decision", "intent", "reason"],
                    "properties": {
                        "decision": {"enum": ["clarify", "refuse", "no_change"]},
                        "intent": {"type": "null"},
                        "reason": reason,
                    },
                },
            ]
            if role and role["decision"] == "propose":
                hints["oneOf"] = hints["oneOf"][:1]
    return hints, title, path, role, fields


def configuration_hash(public, seed):
    return digest(
        {
            "strategy": STRATEGY,
            "model": MODEL,
            "prompt": PROMPT,
            "validation_schema": draft_schema(),
            "decoding_schema": complete_schema(public)[0],
            "generation": {"seed": seed, "max_tokens": 768, "context": 8192},
        }
    )


class CompleteGroundedDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    @staticmethod
    def generate_body(configuration, body):
        native = StableDraftAdapter.generate_body(configuration, body)
        public = json.loads(body["messages"][1]["content"])
        native["format"] = complete_schema(public)[0]
        return native


def generate_complete_grounded_draft(request_text, state, base_url, *, seed=42, now=None):
    public = public_payload(request_text, state, now=now)
    result = generate_stable_draft(
        request_text,
        state,
        base_url,
        seed=seed,
        now=public["now"],
        adapter=CompleteGroundedDraftAdapter(),
    )
    hints, title, path, role, fields = complete_schema(public)
    error = None
    if result["schema_valid"]:
        try:
            validate(json.loads(result["raw_output"]), hints)
        except (ValueError, ValidationError):
            result["schema_valid"] = False
            error = "draft_complete_evidence_mismatch"
    return {
        **result,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(public, seed),
        "decoding_schema_sha256": digest(hints),
        "title_grounding": title,
        "path_grounding": path,
        "role_grounding": role,
        "field_evidence": fields,
        "evidence_scope": "bound_creation" if fields["operation"] else "unbound_fallback",
        "field_policy": "complete-literal-fields-v6",
        "grounding_error": error,
    }
