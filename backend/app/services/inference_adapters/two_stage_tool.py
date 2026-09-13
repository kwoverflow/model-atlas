"""Opt-in diagnostic candidate; deliberately not registered with the application factory."""

from __future__ import annotations

import json
import time
from dataclasses import replace

from app.services.inference_adapters.base import AdapterDescriptor
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.tool_argument_generation import (
    ARGUMENT_GENERATION_VERSION,
    SYSTEM_PROMPT,
    build_argument_payload,
    parse_generated_arguments,
)
from app.services.tool_call_contract import compile_bounded_tool_call


class TwoStageToolAdapter(OpenAICompatibleAdapter):
    name = "diagnostic_two_stage_tool"
    descriptor = AdapterDescriptor(
        adapter_id=name,
        adapter_version="diagnostic-two-stage-tool-v1",
        display_name="Diagnostic Selected Tool Argument Generation",
        capabilities=frozenset({"tool_call_json", "non_repairing_tool_argument_guard"}),
        input_schema_version="evaluation-case-v1",
        output_schema_version="adapter-case-result-v1",
    )

    def run_case(self, *, configuration, evaluation_case, seed=None):
        if not self._is_standalone_tool_case(evaluation_case):
            raise ValueError("two-stage candidate supports standalone tool cases only")
        started = time.perf_counter()
        deadline = started + self._case_timeout_seconds(configuration)
        first = super().run_case(
            configuration=configuration, evaluation_case=evaluation_case, seed=seed
        )
        runtime = configuration.runtime_config_json
        context = runtime.get("_tool_document_context")
        audit = {
            "version": ARGUMENT_GENERATION_VERSION,
            "status": "skipped",
            "uses_expected_labels": False,
            "deterministic_argument_repair": False,
            "first_stage": {
                "raw_output": first.raw_output,
                "normalized_output": first.normalized_output,
                "guard": first.metadata["tool_call_contract"],
                "prompt_tokens": first.prompt_tokens,
                "completion_tokens": first.completion_tokens,
                "latency_ms": first.end_to_end_latency_ms,
            },
            "usage_note": "Adapter token counts may contain estimates; use captured HTTP usage.",
        }
        selected = first.metadata["tool_call_contract"]["tool_name"]
        audit["selected_tool"] = selected
        try:
            if selected is None:
                raise ValueError("first stage did not produce a single tool selection")
            user_payload = build_argument_payload(
                evaluation_case.input_payload_json, selected, context
            )
        except ValueError as exc:
            audit["skip_reason"] = str(exc)
            return replace(first, metadata={**first.metadata, "tool_argument_generation": audit})

        body = {
            "model": first.metadata["model"],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            **self._generation_config(configuration),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "selected_tool_arguments",
                    "strict": True,
                    "schema": user_payload["selected_tool"]["argument_schema"],
                },
            },
        }
        if seed is not None:
            body["seed"] = seed
        second_started = time.perf_counter()
        second = {"raw_output": None, "usage": None, "finish_reason": None}
        second_prompt = second_completion = 0
        error = None
        try:
            self._remaining_timeout(deadline)
            payload = self._post_json(
                configuration,
                first.metadata["base_url"],
                "/v1/chat/completions",
                body,
                deadline=deadline,
            )
            second["raw_output"] = self._message_output(payload["choices"][0]["message"])
            second["finish_reason"] = payload["choices"][0].get("finish_reason")
            second["usage"] = payload.get("usage")
            usage = second["usage"] or {}
            second_prompt = int(usage.get("prompt_tokens") or 0)
            second_completion = int(
                usage.get("completion_tokens") or max(1, len(second["raw_output"]) // 4)
            )
            arguments = parse_generated_arguments(second["raw_output"])
            # This is an assembled envelope, never represented as a native model tool call.
            output = json.dumps(
                {"tool_name": selected, "arguments": arguments},
                ensure_ascii=False,
                allow_nan=False,
            )
            audit["status"] = "generated"
        except Exception as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
            audit["status"] = "failed"
            audit["error"] = error
            # Do not interpret a malformed argument response as a replacement tool call.
            output = json.dumps({"argument_generation_failed": error}, ensure_ascii=False)
        second["latency_ms"] = max(0.0, (time.perf_counter() - second_started) * 1000)
        audit["second_stage"] = second
        audit["output_representation"] = "assembled_envelope" if error is None else "error_envelope"
        guard = compile_bounded_tool_call(
            output,
            input_payload=evaluation_case.input_payload_json,
            document_context=context,
            allowed_failure_mode=runtime.get("tool_failure_simulation"),
        )
        json_valid, _ = self._validation_flags(evaluation_case, guard.normalized_output)
        elapsed = max(1.0, (time.perf_counter() - started) * 1000)
        completion = first.completion_tokens + second_completion
        return replace(
            first,
            raw_output=output,
            normalized_output=guard.normalized_output,
            json_valid=json_valid,
            tool_call_valid=guard.execution_allowed,
            error_type=(
                "tool_argument_generation_failed"
                if error
                else "tool_argument_guard_rejected"
                if not guard.execution_allowed
                else None
            ),
            end_to_end_latency_ms=elapsed,
            prompt_tokens=first.prompt_tokens + second_prompt,
            completion_tokens=completion,
            tokens_per_second=completion / (elapsed / 1000),
            logs=[
                *first.logs,
                {
                    "event_type": "tool_argument_generation",
                    "level": "info",
                    "message": f"Argument generation: {audit['status']}; tool fixed to {selected}.",
                    "payload_json": {"status": audit["status"], "selected_tool": selected},
                },
            ],
            metadata={
                **first.metadata,
                "tool_call_contract": guard.audit_record(),
                "tool_argument_generation": audit,
            },
        )
