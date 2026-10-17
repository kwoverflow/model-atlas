"""Explicit draft strategy selection, independent of approval and execution."""

from .complete_grounded_inference import STRATEGY as COMPLETE_STRATEGY
from .complete_grounded_inference import generate_complete_grounded_draft
from .contracts import GuardError
from .decision_grounded_inference import STRATEGY as DECISION_STRATEGY
from .decision_grounded_inference import generate_decision_grounded_draft
from .field_grounded_inference import STRATEGY as FIELD_STRATEGY
from .field_grounded_inference import generate_field_grounded_draft
from .inference import generate_draft
from .path_grounded_inference import STRATEGY as GROUNDED_STRATEGY
from .path_grounded_inference import generate_path_grounded_draft
from .path_safe_inference import STRATEGY as PATH_STRATEGY
from .path_safe_inference import generate_path_safe_draft
from .role_grounded_inference import STRATEGY as ROLE_STRATEGY
from .role_grounded_inference import generate_role_grounded_draft
from .semantic_grounded_inference import STRATEGY as SEMANTIC_STRATEGY
from .semantic_grounded_inference import generate_semantic_grounded_draft
from .stable_inference import STRATEGY, generate_stable_draft

DEFAULT_STRATEGY = "legacy"


def generate_review_draft(request_text, state, base_url, strategy=DEFAULT_STRATEGY, *, seed=42):
    if strategy == "legacy":
        return {**generate_draft(request_text, state, base_url, seed=seed), "strategy": "legacy"}
    if strategy == STRATEGY:
        return generate_stable_draft(request_text, state, base_url, seed=seed)
    if strategy == PATH_STRATEGY:
        return generate_path_safe_draft(request_text, state, base_url, seed=seed)
    if strategy == GROUNDED_STRATEGY:
        return generate_path_grounded_draft(request_text, state, base_url, seed=seed)
    if strategy == ROLE_STRATEGY:
        return generate_role_grounded_draft(request_text, state, base_url, seed=seed)
    if strategy == FIELD_STRATEGY:
        return generate_field_grounded_draft(request_text, state, base_url, seed=seed)
    if strategy == COMPLETE_STRATEGY:
        return generate_complete_grounded_draft(request_text, state, base_url, seed=seed)
    if strategy == DECISION_STRATEGY:
        return generate_decision_grounded_draft(request_text, state, base_url, seed=seed)
    if strategy == SEMANTIC_STRATEGY:
        return generate_semantic_grounded_draft(request_text, state, base_url, seed=seed)
    raise GuardError("unknown_draft_strategy")
