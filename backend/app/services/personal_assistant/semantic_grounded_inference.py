"""V8: distinguish verified content meaning, quotation and action-role grounding."""

import json

from jsonschema import ValidationError, validate

from .contracts import digest
from .decision_grounded_inference import decision_schema
from .inference import MODEL, draft_schema
from .semantic_evidence import semantic_evidence
from .stable_inference import PROMPT, StableDraftAdapter, generate_stable_draft, public_payload

STRATEGY = "compact-semantic-grounded-v8"


def semantic_schema(public):
    hints, title, path, role, fields, _previous = decision_schema(public)
    evidence = {**semantic_evidence(public), "public_input_sha256": digest(public)}
    if evidence["action_evidence"]["decision"]:
        hints["oneOf"][0]["properties"]["reason"] = {
            "const": evidence["explanation_evidence"]["reason"]
        }
    return hints, title, path, role, fields, evidence


def configuration_hash(public, seed):
    return digest(
        {
            "strategy": STRATEGY,
            "model": MODEL,
            "prompt": PROMPT,
            "validation_schema": draft_schema(),
            "decoding_schema": semantic_schema(public)[0],
            "generation": {"seed": seed, "max_tokens": 768, "context": 8192},
        }
    )


class SemanticGroundedDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    @staticmethod
    def generate_body(configuration, body):
        native = StableDraftAdapter.generate_body(configuration, body)
        public = json.loads(body["messages"][1]["content"])
        native["format"] = semantic_schema(public)[0]
        return native


def generate_semantic_grounded_draft(request_text, state, base_url, *, seed=42, now=None):
    public = public_payload(request_text, state, now=now)
    result = generate_stable_draft(
        request_text,
        state,
        base_url,
        seed=seed,
        now=public["now"],
        adapter=SemanticGroundedDraftAdapter(),
    )
    hints, title, path, role, fields, evidence = semantic_schema(public)
    error = None
    if result["schema_valid"]:
        try:
            validate(json.loads(result["raw_output"]), hints)
        except (ValueError, ValidationError):
            result["schema_valid"] = False
            error = "draft_semantic_evidence_mismatch"
    return {
        **result,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(public, seed),
        "decoding_schema_sha256": digest(hints),
        "title_grounding": title,
        "path_grounding": path,
        "role_grounding": role,
        "field_evidence": fields,
        "semantic_evidence": evidence,
        "semantic_evidence_sha256": digest(evidence),
        "explanation_bound": evidence["explanation_evidence"]["status"] == "bound",
        "grounding_error": error,
    }
