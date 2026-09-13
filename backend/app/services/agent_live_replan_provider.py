from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.services.agent_execution import (
    AgentLiveReplanRequest,
    AgentLiveReplanResponse,
)
from app.validators import DomainValidationError

OPENAI_LIVE_REPLAN_PROVIDER_VERSION = "openai-compatible-live-replan-v1"


class OpenAICompatibleLiveReplanCallback:
    def __init__(self, configuration: dict[str, Any]) -> None:
        self.configuration = dict(configuration)
        self.called = False

    def __call__(
        self,
        request: AgentLiveReplanRequest,
    ) -> AgentLiveReplanResponse | None:
        if self.called:
            return None
        self.called = True
        base_url = _required_base_url(self.configuration)
        model_name = str(
            self.configuration.get("agent_replan_model")
            or self.configuration.get("model")
            or ""
        ).strip()
        if not model_name:
            raise DomainValidationError("agent_replan_model is required")
        timeout_seconds = max(
            1.0,
            min(float(self.configuration.get("agent_replan_timeout_seconds") or 15), 60.0),
        )
        body = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return one strict JSON object with a steps array for bounded recovery. "
                        "Use no more than the supplied recovery_step_limit. Do not include "
                        "markdown, explanations, hidden reasoning, approvals, or extra keys."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "schema_version": request.schema_version,
                            "case_id": request.external_case_id,
                            "trigger_step_index": request.trigger_step_index,
                            "trigger_error_type": request.trigger_error_type,
                            "observation": request.observation,
                            "expected_recovery_steps": request.expected_recovery_steps,
                            "prior_outputs": request.prior_outputs,
                            "recovery_step_limit": request.recovery_step_limit,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": max(
                64,
                min(int(self.configuration.get("agent_replan_max_tokens") or 512), 2048),
            ),
        }
        api_key_env = str(
            self.configuration.get("agent_replan_api_key_env")
            or "AGENT_REPLAN_API_KEY"
        ).strip()
        if api_key_env != "AGENT_REPLAN_API_KEY":
            raise DomainValidationError(
                "agent_replan_api_key_env must be AGENT_REPLAN_API_KEY"
            )
        api_key = os.getenv(api_key_env)
        headers = {"content-type": "application/json"}
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        http_request = Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urlopen(http_request, timeout=timeout_seconds) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("OpenAI-compatible live replan request failed") from exc
        elapsed_ms = max(0.0, (time.perf_counter() - started) * 1000)
        content = _response_content(payload)
        try:
            normalized = json.loads(content)
        except json.JSONDecodeError as exc:
            raise DomainValidationError("live replan response is not strict JSON") from exc
        steps = normalized.get("steps") if isinstance(normalized, dict) else None
        if not isinstance(steps, list) or not steps:
            raise DomainValidationError("live replan response must contain recovery steps")
        normalized_steps = [dict(step) for step in steps if isinstance(step, dict)]
        if len(normalized_steps) != len(steps):
            raise DomainValidationError("live replan recovery steps must be objects")
        usage = payload.get("usage") if isinstance(payload, dict) else {}
        usage = usage if isinstance(usage, dict) else {}
        prompt_tokens = _non_negative_int(usage.get("prompt_tokens"))
        completion_tokens = _non_negative_int(usage.get("completion_tokens"))
        estimated_cost = (
            prompt_tokens
            * _non_negative_float(
                self.configuration.get("agent_replan_input_cost_per_million")
            )
            + completion_tokens
            * _non_negative_float(
                self.configuration.get("agent_replan_output_cost_per_million")
            )
        ) / 1_000_000
        return AgentLiveReplanResponse(
            steps=normalized_steps,
            provider_id="openai_compatible",
            provider_version=OPENAI_LIVE_REPLAN_PROVIDER_VERSION,
            model_name=str(payload.get("model") or model_name),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model_call_latency_ms=elapsed_ms,
            estimated_cost_usd=estimated_cost,
        )


def _required_base_url(configuration: dict[str, Any]) -> str:
    value = str(
        configuration.get("agent_replan_base_url")
        or configuration.get("resolved_base_url")
        or configuration.get("base_url")
        or os.getenv("AGENT_REPLAN_BASE_URL")
        or ""
    ).strip().rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3]
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise DomainValidationError("agent_replan_base_url must be an HTTP(S) endpoint")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise DomainValidationError("agent_replan_base_url must not contain credentials or query")
    return value


def _response_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise DomainValidationError("live replan response must be an object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise DomainValidationError("live replan response is missing choices")
    message = choices[0].get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise DomainValidationError("live replan response is missing message content")
    return str(message["content"])


def _non_negative_int(value: Any) -> int:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0
    return max(0, int(value))


def _non_negative_float(value: Any) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0.0
    return max(0.0, float(value))
