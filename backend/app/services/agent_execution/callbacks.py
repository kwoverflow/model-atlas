from __future__ import annotations

from typing import Any

from app.models import EvaluationCase

from .contracts import (
    AgentLiveReplanCallback,
    AgentLiveReplanRequest,
    AgentLiveReplanResponse,
)
from .utils import (
    _non_negative_float,
    _non_negative_int,
)


class _FixtureLiveReplanCallback:
    def __init__(self, fixture: dict[str, Any]) -> None:
        self.fixture = fixture
        self.called = False

    def __call__(
        self,
        request: AgentLiveReplanRequest,
    ) -> AgentLiveReplanResponse | None:
        if self.called:
            return None
        self.called = True
        trigger_step_index = self.fixture.get("trigger_step_index")
        if isinstance(trigger_step_index, int) and (
            trigger_step_index != request.trigger_step_index
        ):
            return None
        trigger_error_type = str(self.fixture.get("trigger_error_type") or "").strip()
        if trigger_error_type and trigger_error_type != request.trigger_error_type:
            return None
        steps = self.fixture.get("steps")
        if not isinstance(steps, list) or not steps:
            return None
        normalized_steps = [dict(step) for step in steps if isinstance(step, dict)]
        if len(normalized_steps) != len(steps):
            return None
        return AgentLiveReplanResponse(
            steps=normalized_steps,
            provider_id=str(self.fixture.get("provider_id") or "model_atlas_mock_replanner"),
            provider_version=str(self.fixture.get("provider_version") or "mock-replanner-v1"),
            model_name=str(self.fixture.get("model_name") or "mock-replan-model"),
            prompt_tokens=_non_negative_int(self.fixture.get("prompt_tokens")),
            completion_tokens=_non_negative_int(self.fixture.get("completion_tokens")),
            model_call_latency_ms=_non_negative_float(self.fixture.get("model_call_latency_ms")),
            estimated_cost_usd=_non_negative_float(self.fixture.get("estimated_cost_usd")),
        )


class _RecordedLiveReplanCallback:
    def __init__(self, trace: dict[str, Any]) -> None:
        self.trace = trace
        self.called = False

    def __call__(
        self,
        request: AgentLiveReplanRequest,
    ) -> AgentLiveReplanResponse | None:
        if self.called:
            return None
        self.called = True
        replans = self.trace.get("replans")
        if not isinstance(replans, list):
            return None
        event = next(
            (
                item
                for item in replans
                if isinstance(item, dict)
                and item.get("source") == "live_callback"
                and item.get("trigger_step_index") == request.trigger_step_index
                and item.get("trigger_error_type") == request.trigger_error_type
            ),
            None,
        )
        if event is None or event.get("status") in {"callback_error", "no_recovery"}:
            return None
        trace_steps = self.trace.get("steps")
        recovery_indices = event.get("recovery_step_indices")
        model_call = event.get("model_call")
        if not isinstance(trace_steps, list) or not isinstance(recovery_indices, list):
            return None
        if not isinstance(model_call, dict):
            return None
        recovery_steps: list[dict[str, Any]] = []
        for index in recovery_indices:
            if not isinstance(index, int) or index < 0 or index >= len(trace_steps):
                return None
            recorded_step = trace_steps[index]
            if not isinstance(recorded_step, dict) or not isinstance(
                recorded_step.get("input"), dict
            ):
                return None
            recovery_steps.append(dict(recorded_step["input"]))
        if not recovery_steps:
            return None
        return AgentLiveReplanResponse(
            steps=recovery_steps,
            provider_id=str(model_call.get("provider_id") or "recorded-provider"),
            provider_version=str(model_call.get("provider_version") or "recorded-provider-v1"),
            model_name=str(model_call.get("model_name") or "recorded-model"),
            prompt_tokens=_non_negative_int(model_call.get("prompt_tokens")),
            completion_tokens=_non_negative_int(model_call.get("completion_tokens")),
            model_call_latency_ms=_non_negative_float(model_call.get("model_call_latency_ms")),
            estimated_cost_usd=_non_negative_float(model_call.get("estimated_cost_usd")),
        )


def _recorded_live_replan_callback(
    trace: dict[str, Any],
) -> AgentLiveReplanCallback | None:
    replans = trace.get("replans")
    if not isinstance(replans, list) or not any(
        isinstance(item, dict) and item.get("source") == "live_callback" for item in replans
    ):
        return None
    return _RecordedLiveReplanCallback(trace)


def build_agent_live_replan_callback(
    evaluation_case: EvaluationCase,
    *,
    mode: str,
    provider_config: dict[str, Any] | None = None,
) -> AgentLiveReplanCallback | None:
    if mode == "openai_compatible":
        from app.services.agent_live_replan_provider import (
            OpenAICompatibleLiveReplanCallback,
        )

        return OpenAICompatibleLiveReplanCallback(provider_config or {})
    if mode != "mock_fixture":
        return None
    input_payload = (
        evaluation_case.input_payload_json
        if isinstance(evaluation_case.input_payload_json, dict)
        else {}
    )
    fixture = input_payload.get("mock_agent_live_replan")
    if not isinstance(fixture, dict):
        return None
    return _FixtureLiveReplanCallback(dict(fixture))
