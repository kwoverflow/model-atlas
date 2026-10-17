"""Bind supported decision certificates and explanations in the actual decoder."""

import json

from jsonschema import ValidationError, validate

from .complete_grounded_inference import complete_schema
from .contracts import digest
from .decision_evidence import decision_evidence
from .inference import MODEL, draft_schema
from .stable_inference import PROMPT, StableDraftAdapter, generate_stable_draft, public_payload

STRATEGY = "compact-decision-grounded-v7"


def decision_schema(public):
    hints, title, path, role, fields = complete_schema(public)
    evidence = {**decision_evidence(public), "public_input_sha256": digest(public)}
    if evidence["decision"]:
        decision = evidence["decision"]
        if decision == "propose":
            intent = hints["oneOf"][0]["properties"]["intent"]
        else:
            intent = {"type": "null"}
        hints["oneOf"] = [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["decision", "intent", "reason"],
                "properties": {
                    "decision": {"const": decision},
                    "intent": intent,
                    "reason": {"const": evidence["reason"]},
                },
            }
        ]
    return hints, title, path, role, fields, evidence


def configuration_hash(public, seed):
    return digest(
        {
            "strategy": STRATEGY,
            "model": MODEL,
            "prompt": PROMPT,
            "validation_schema": draft_schema(),
            "decoding_schema": decision_schema(public)[0],
            "generation": {"seed": seed, "max_tokens": 768, "context": 8192},
        }
    )


class DecisionGroundedDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    @staticmethod
    def generate_body(configuration, body):
        native = StableDraftAdapter.generate_body(configuration, body)
        public = json.loads(body["messages"][1]["content"])
        native["format"] = decision_schema(public)[0]
        return native


def generate_decision_grounded_draft(request_text, state, base_url, *, seed=42, now=None):
    public = public_payload(request_text, state, now=now)
    result = generate_stable_draft(
        request_text,
        state,
        base_url,
        seed=seed,
        now=public["now"],
        adapter=DecisionGroundedDraftAdapter(),
    )
    hints, title, path, role, fields, evidence = decision_schema(public)
    error = None
    if result["schema_valid"]:
        try:
            validate(json.loads(result["raw_output"]), hints)
        except (ValueError, ValidationError):
            result["schema_valid"] = False
            error = "draft_decision_evidence_mismatch"
    return {
        **result,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(public, seed),
        "decoding_schema_sha256": digest(hints),
        "title_grounding": title,
        "path_grounding": path,
        "role_grounding": role,
        "field_evidence": fields,
        "decision_evidence": evidence,
        "decision_evidence_sha256": digest(evidence),
        "explanation_bound": evidence["reason"] is not None,
        "grounding_error": error,
    }
