import pytest

from app.api.v1.routes import personal_assistant as routes
from app.core.config import Settings
from app.schemas.personal_assistant import ReviewInput
from app.services.personal_assistant import generation
from app.services.personal_assistant.complete_grounded_inference import (
    STRATEGY as COMPLETE_STRATEGY,
)
from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.decision_grounded_inference import (
    STRATEGY as DECISION_STRATEGY,
)
from app.services.personal_assistant.field_grounded_inference import STRATEGY as FIELD_STRATEGY
from app.services.personal_assistant.path_grounded_inference import STRATEGY as GROUNDED_STRATEGY
from app.services.personal_assistant.path_safe_inference import STRATEGY as PATH_STRATEGY
from app.services.personal_assistant.release_generation import (
    DEFAULT_STRATEGY as APP_DEFAULT_STRATEGY,
)
from app.services.personal_assistant.role_grounded_inference import STRATEGY as ROLE_STRATEGY
from app.services.personal_assistant.semantic_grounded_inference import (
    STRATEGY as SEMANTIC_STRATEGY,
)
from app.services.personal_assistant.stable_inference import STRATEGY

STRATEGIES = [
    "legacy",
    STRATEGY,
    PATH_STRATEGY,
    GROUNDED_STRATEGY,
    ROLE_STRATEGY,
    FIELD_STRATEGY,
    COMPLETE_STRATEGY,
    DECISION_STRATEGY,
    SEMANTIC_STRATEGY,
]


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_dispatch_keeps_raw_output_and_uses_only_selected_strategy(monkeypatch, strategy):
    calls = []

    def generator(name):
        def run(text, state, base_url, *, seed):
            calls.append((name, text, state, base_url, seed))
            return {"raw_output": "RAW_UNCHANGED", "schema_valid": True, "strategy": name}

        return run

    monkeypatch.setattr(generation, "generate_draft", generator("legacy"))
    monkeypatch.setattr(generation, "generate_stable_draft", generator(STRATEGY))
    monkeypatch.setattr(generation, "generate_path_safe_draft", generator(PATH_STRATEGY))
    monkeypatch.setattr(generation, "generate_path_grounded_draft", generator(GROUNDED_STRATEGY))
    monkeypatch.setattr(generation, "generate_role_grounded_draft", generator(ROLE_STRATEGY))
    monkeypatch.setattr(generation, "generate_field_grounded_draft", generator(FIELD_STRATEGY))
    monkeypatch.setattr(
        generation, "generate_complete_grounded_draft", generator(COMPLETE_STRATEGY)
    )
    monkeypatch.setattr(
        generation, "generate_decision_grounded_draft", generator(DECISION_STRATEGY)
    )
    monkeypatch.setattr(
        generation, "generate_semantic_grounded_draft", generator(SEMANTIC_STRATEGY)
    )
    state = {"events": [], "tasks": [], "files": {}}
    result = generation.generate_review_draft("text", state, "local", strategy, seed=1729)
    assert result["raw_output"] == "RAW_UNCHANGED" and result["strategy"] == strategy
    assert calls == [(strategy, "text", state, "local", 1729)]


def test_unknown_strategy_never_falls_back_or_calls_a_model(monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Unknown strategy must not call inference")

    monkeypatch.setattr(generation, "generate_draft", unexpected)
    monkeypatch.setattr(generation, "generate_stable_draft", unexpected)
    monkeypatch.setattr(generation, "generate_path_safe_draft", unexpected)
    monkeypatch.setattr(generation, "generate_path_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_role_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_field_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_complete_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_decision_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_semantic_grounded_draft", unexpected)
    with pytest.raises(GuardError, match="unknown_draft_strategy"):
        generation.generate_review_draft("text", {}, "local", "typo")


@pytest.mark.parametrize("strategy", STRATEGIES[1:])
def test_generation_error_never_triggers_fallback_or_retry(monkeypatch, strategy):
    calls = []

    def fail(*_args, **_kwargs):
        calls.append("candidate")
        raise GuardError("draft_generation_incomplete")

    def fallback(*_args, **_kwargs):
        pytest.fail("No silent fallback after failed inference")

    for name, selected in (
        ("generate_stable_draft", STRATEGY),
        ("generate_path_safe_draft", PATH_STRATEGY),
        ("generate_path_grounded_draft", GROUNDED_STRATEGY),
        ("generate_role_grounded_draft", ROLE_STRATEGY),
        ("generate_field_grounded_draft", FIELD_STRATEGY),
        ("generate_complete_grounded_draft", COMPLETE_STRATEGY),
        ("generate_decision_grounded_draft", DECISION_STRATEGY),
        ("generate_semantic_grounded_draft", SEMANTIC_STRATEGY),
    ):
        monkeypatch.setattr(generation, name, fail if strategy == selected else fallback)
    monkeypatch.setattr(generation, "generate_draft", fallback)
    with pytest.raises(GuardError, match="draft_generation_incomplete"):
        generation.generate_review_draft("text", {}, "local", strategy)
    assert calls == ["candidate"]


def test_settings_default_and_explicit_rollback(monkeypatch):
    monkeypatch.delenv("PERSONAL_ASSISTANT_DRAFT_STRATEGY", raising=False)
    assert Settings().personal_assistant_draft_strategy == APP_DEFAULT_STRATEGY
    monkeypatch.setenv("PERSONAL_ASSISTANT_DRAFT_STRATEGY", "legacy")
    assert Settings().personal_assistant_draft_strategy == "legacy"


def test_historical_factory_retains_its_original_legacy_default(monkeypatch):
    def unexpected(*_args, **_kwargs):
        pytest.fail("Failed candidates require explicit opt-in, never default dispatch")

    monkeypatch.setattr(generation, "generate_stable_draft", unexpected)
    monkeypatch.setattr(generation, "generate_path_safe_draft", unexpected)
    monkeypatch.setattr(generation, "generate_path_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_role_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_field_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_complete_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_decision_grounded_draft", unexpected)
    monkeypatch.setattr(generation, "generate_semantic_grounded_draft", unexpected)
    monkeypatch.setattr(
        generation, "generate_draft", lambda *_args, **_kwargs: {"raw_output": "legacy-raw"}
    )
    assert generation.DEFAULT_STRATEGY == "legacy"
    assert generation.generate_review_draft("request", {}, "local") == {
        "raw_output": "legacy-raw",
        "strategy": "legacy",
    }


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_workspace_reports_selected_strategy_without_inference(monkeypatch, strategy):
    from types import SimpleNamespace

    state = {"events": [], "tasks": [], "files": {}}
    monkeypatch.setattr(routes, "review_service", lambda _: SimpleNamespace(state=lambda: state))
    monkeypatch.setattr(
        routes, "get_settings", lambda: SimpleNamespace(personal_assistant_draft_strategy=strategy)
    )
    assert routes.workspace(None) == {
        "mode": "isolated_local_workspace",
        "model": "qwen3.5:9b",
        "application_version": "1.0.0",
        "draft_strategy": strategy,
        "state": state,
    }


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_review_route_passes_explicit_strategy_without_changing_execution(monkeypatch, strategy):
    from types import SimpleNamespace

    settings = SimpleNamespace(
        personal_assistant_runtime_url="local", personal_assistant_draft_strategy=strategy
    )
    state = {"events": [], "tasks": [], "files": {}}
    service = SimpleNamespace(create=lambda text, generator: generator(text, state))
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "review_service", lambda _: service)
    calls = []

    def generator(text, actual_state, url, selected):
        calls.append((text, actual_state, url, selected))
        return {"raw_output": "unchanged"}

    monkeypatch.setattr(routes, "generate_draft", generator)
    result = routes.create_review(ReviewInput(request="request"), None)
    assert result == {"raw_output": "unchanged"}
    assert calls == [("request", state, "local", strategy)]
