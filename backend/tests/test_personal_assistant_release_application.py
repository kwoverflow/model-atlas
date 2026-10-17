import pytest

from app.api.v1.routes import personal_assistant as routes
from app.core.config import Settings
from app.services.personal_assistant import release_generation
from app.services.personal_assistant.contracts import GuardError


def test_application_entry_point_and_default_select_the_validated_release(monkeypatch):
    monkeypatch.delenv("PERSONAL_ASSISTANT_DRAFT_STRATEGY", raising=False)
    assert Settings().personal_assistant_draft_strategy == release_generation.STRATEGY
    assert routes.generate_draft is release_generation.generate_review_draft


def test_rollback_is_explicit_and_unknown_strategy_never_calls_a_model(monkeypatch):
    monkeypatch.setenv("PERSONAL_ASSISTANT_DRAFT_STRATEGY", "legacy")
    assert Settings().personal_assistant_draft_strategy == "legacy"
    with pytest.raises(GuardError, match="unknown_draft_strategy"):
        release_generation.generate_review_draft("request", {}, "not-a-runtime", "typo")
