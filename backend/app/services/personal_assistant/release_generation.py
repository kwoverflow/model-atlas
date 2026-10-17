"""1.0 application entry point; preserve frozen experiments and never repair model output."""

import copy
import json

from jsonschema import ValidationError, validate

from .contracts import digest
from .generation import generate_review_draft as generate_historical_draft
from .inference import MODEL, draft_schema
from .semantic_grounded_inference import semantic_schema
from .stable_inference import PROMPT, StableDraftAdapter, generate_stable_draft, public_payload

STRATEGY = "assistant-release-v1"
DEFAULT_STRATEGY = STRATEGY
NEUTRAL_REASONS = {
    "propose": "모델이 제안한 실행 전 초안입니다. 요청과 일치하는지는 자동으로 확정하지 "
    "못했습니다. 내용을 확인하고 확정·승인하기 전에는 실행하지 않습니다.",
    "clarify": "모델이 확인이 필요한 요청으로 분류했습니다. 구체적인 누락·충돌 원인은 "
    "자동 검증되지 않았습니다. 내용을 확인해 주세요. 변경하지 않습니다.",
    "refuse": "모델이 거절로 분류했습니다. 거절 사유의 의미 해석은 자동 검증되지 "
    "않았습니다. 변경하지 않습니다.",
    "no_change": "이 응답은 실행 초안을 제안하지 않습니다. 요청 문맥의 해석은 자동 "
    "검증되지 않았습니다. 변경하지 않습니다.",
}


def release_schema(public):
    hints, title, path, role, fields, evidence = semantic_schema(public)
    fallback = evidence["explanation_evidence"]["status"] == "unverified"
    if fallback:
        branches = []
        for branch in hints["oneOf"]:
            choice = branch["properties"]["decision"]
            decisions = [choice["const"]] if "const" in choice else choice["enum"]
            for decision in decisions:
                constrained = copy.deepcopy(branch)
                constrained["properties"]["decision"] = {"const": decision}
                constrained["properties"]["reason"] = {"const": NEUTRAL_REASONS[decision]}
                branches.append(constrained)
        hints["oneOf"] = branches
    policy = {
        "policy": "neutral_decision_only" if fallback else "source_bound",
        "bound_in_native_schema": True,
        "source_semantics_upgraded": False,
        "authorizes_execution": False,
    }
    return hints, title, path, role, fields, evidence, policy


def configuration_hash(public, seed):
    return digest(
        {
            "strategy": STRATEGY,
            "model": MODEL,
            "prompt": PROMPT,
            "validation_schema": draft_schema(),
            "decoding_schema": release_schema(public)[0],
            "generation": {"seed": seed, "max_tokens": 768, "context": 8192},
        }
    )


class ReleaseDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    @staticmethod
    def generate_body(configuration, body):
        native = StableDraftAdapter.generate_body(configuration, body)
        public = json.loads(body["messages"][1]["content"])
        native["format"] = release_schema(public)[0]
        return native


def generate_review_draft(
    request_text, state, base_url, strategy=DEFAULT_STRATEGY, *, seed=42, now=None
):
    if strategy != STRATEGY:
        return generate_historical_draft(request_text, state, base_url, strategy, seed=seed)
    public = public_payload(request_text, state, now=now)
    generated = generate_stable_draft(
        request_text,
        state,
        base_url,
        seed=seed,
        now=public["now"],
        adapter=ReleaseDraftAdapter(),
    )
    hints, title, path, role, fields, evidence, policy = release_schema(public)
    error = None
    if generated["schema_valid"]:
        try:
            validate(json.loads(generated["raw_output"]), hints)
        except (ValueError, ValidationError):
            generated["schema_valid"] = False
            error = "draft_release_evidence_mismatch"
    return {
        **generated,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(public, seed),
        "decoding_schema_sha256": digest(hints),
        "title_grounding": title,
        "path_grounding": path,
        "role_grounding": role,
        "field_evidence": fields,
        "semantic_evidence": evidence,
        "semantic_evidence_sha256": digest(evidence),
        "release_explanation": policy,
        "explanation_bound": True,
        "grounding_error": error,
    }
