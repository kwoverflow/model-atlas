from __future__ import annotations

import json

from app.services.inference_adapters.base import (
    AdapterCaseResult,
    AdapterConfiguration,
    AdapterDescriptor,
    AdapterEvaluationCase,
    AdapterHealth,
)


class MockInferenceAdapter:
    name = "mock"
    descriptor = AdapterDescriptor(
        adapter_id="mock",
        adapter_version="mock-adapter-v6",
        display_name="Deterministic Mock Adapter",
        capabilities=frozenset(
            {
                "text_generation",
                "structured_output",
                "tool_call_json",
                "multi_step_tool_calling",
                "rag_grounded_generation",
                "citation_json",
                "usage_metrics",
                "runtime_reliability_trials",
                "bounded_agent_plan",
                "operational_memory",
                "human_approval_checkpoint",
                "bounded_recovery_plan",
                "observation_feedback",
            }
        ),
        input_schema_version="evaluation-case-v1",
        output_schema_version="adapter-case-result-v1",
    )

    def health_check(self, configuration: AdapterConfiguration) -> AdapterHealth:
        return AdapterHealth(
            adapter_name=self.name,
            healthy=True,
            message="Mock adapter is available for deterministic local execution.",
            details={
                "configuration_hash": configuration.configuration_hash,
                "runtime_name": configuration.runtime_name,
                "adapter_descriptor": self.descriptor.to_dict(),
            },
        )

    def run_case(
        self,
        *,
        configuration: AdapterConfiguration,
        evaluation_case: AdapterEvaluationCase,
        seed: int | None = None,
    ) -> AdapterCaseResult:
        category = evaluation_case.category.lower()
        profile = self._reliability_profile(evaluation_case)
        trial_index = int(evaluation_case.input_payload_json.get("_execution_trial") or 1)
        output = self._output_for_case(evaluation_case)
        quality = self._quality_for_case(evaluation_case, seed)
        latency_base = float(
            profile.get("base_latency_ms")
            or 720 + len(evaluation_case.external_case_id) * 7
        )
        if "long" in category or "latency" in category:
            latency_base += 420
        latency_base += self._trial_jitter(profile, trial_index)
        latency_multiplier = float(
            configuration.runtime_config_json.get("reliability_latency_multiplier", 1.0)
        )
        latency_base = max(1.0, latency_base * latency_multiplier)
        completion_tokens = int(
            profile.get("completion_tokens")
            or (96 if "long" not in category else 192)
        )
        tokens_per_second = round(completion_tokens / max(latency_base / 1000, 0.001), 2)
        is_tool_case = "tool" in category or evaluation_case.expected_tool_schema_json is not None
        is_agent_case = "agent" in category or isinstance(
            evaluation_case.input_payload_json.get("agent_context"), dict
        )
        is_json_case = (
            "json" in category
            or evaluation_case.expected_output_json is not None
            or is_tool_case
            or is_agent_case
        )

        timeout_trials = self._trial_numbers(profile, "timeout_trials")
        oom_trials = self._trial_numbers(profile, "oom_trials")
        error_trials = self._trial_numbers(profile, "error_trials")
        case_timeout_ms = float(
            evaluation_case.input_payload_json.get("_case_timeout_ms") or 120_000
        )
        error_type: str | None = None
        oom_occurred = False
        if trial_index in timeout_trials:
            error_type = "timeout"
            latency_base = max(latency_base, case_timeout_ms)
        elif trial_index in oom_trials:
            error_type = "out_of_memory"
            oom_occurred = True
        elif trial_index in error_trials:
            error_type = "runtime_error"
        if error_type:
            output = ""

        return AdapterCaseResult(
            raw_output=output,
            normalized_output=output,
            quality_score=0.0 if error_type else quality,
            exact_match=None if error_type else True,
            json_valid=is_json_case and error_type is None,
            tool_call_valid=is_tool_case and error_type is None,
            groundedness_score=0.0 if error_type else round(max(0, quality - 0.02), 3),
            faithfulness_score=0.0 if error_type else round(max(0, quality - 0.01), 3),
            human_label="mock-fail" if error_type else "mock-pass",
            error_type=error_type,
            ttft_ms=float(profile.get("ttft_ms") or 95 + len(evaluation_case.external_case_id)),
            end_to_end_latency_ms=latency_base,
            prompt_tokens=int(
                profile.get("context_tokens")
                or 256 + len(json.dumps(evaluation_case.input_payload_json)) // 4
            ),
            completion_tokens=completion_tokens,
            tokens_per_second=tokens_per_second,
            gpu_vram_used_mb=float(
                profile.get("gpu_vram_used_mb") or 8400 + len(category) * 24
            ),
            gpu_utilization_pct=58.0,
            cpu_utilization_pct=18.0,
            peak_memory_mb=float(profile.get("peak_memory_mb") or 22000.0),
            oom_occurred=oom_occurred,
            retry_count=0,
            logs=[
                {
                    "event_type": "case_executed",
                    "level": "info",
                    "message": f"Mock executed {evaluation_case.external_case_id}.",
                    "payload_json": {
                        "adapter": self.name,
                        "category": evaluation_case.category,
                        "configuration_hash": configuration.configuration_hash,
                        "trial_index": trial_index,
                        "error_type": error_type,
                    },
                }
            ],
            metadata={
                "adapter": self.name,
                "adapter_descriptor": self.descriptor.to_dict(),
                "seed": seed,
                "mock": True,
                **(
                    {"reliability_error_message": f"Simulated {error_type} trial."}
                    if error_type
                    else {}
                ),
            },
        )

    def _output_for_case(self, evaluation_case: AdapterEvaluationCase) -> str:
        category = evaluation_case.category.lower()
        if "agent" in category or isinstance(
            evaluation_case.input_payload_json.get("agent_context"), dict
        ):
            return json.dumps(self._agent_output(evaluation_case), ensure_ascii=False)
        if "tool" in category or evaluation_case.expected_tool_schema_json is not None:
            return json.dumps(self._tool_output(evaluation_case), ensure_ascii=False)
        if "rag" in category or isinstance(
            evaluation_case.input_payload_json.get("rag_context"), dict
        ):
            return json.dumps(self._rag_output(evaluation_case), ensure_ascii=False)
        if "json" in category or evaluation_case.expected_output_json is not None:
            return json.dumps(
                {
                    "answer": f"mock answer for {evaluation_case.external_case_id}",
                    "evidence": [evaluation_case.external_case_id],
                    "confidence": 0.91,
                },
                ensure_ascii=False,
            )
        return f"mock grounded answer for {evaluation_case.external_case_id}"

    def _agent_output(self, evaluation_case: AdapterEvaluationCase) -> dict:
        forced_plan = evaluation_case.input_payload_json.get("mock_agent_plan")
        if isinstance(forced_plan, dict):
            return dict(forced_plan)
        request = str(
            evaluation_case.input_payload_json.get("request")
            or evaluation_case.external_case_id
        )
        return {
            "steps": [
                {
                    "action": "respond",
                    "content": f"Completed bounded agent request: {request}",
                }
            ]
        }

    def _rag_output(self, evaluation_case: AdapterEvaluationCase) -> dict:
        forced_output = evaluation_case.input_payload_json.get("mock_rag_output")
        if isinstance(forced_output, dict):
            return dict(forced_output)
        rag_context = evaluation_case.input_payload_json.get("rag_context")
        rag_context = rag_context if isinstance(rag_context, dict) else {}
        retrieved_chunks = rag_context.get("retrieved_chunks")
        retrieved_chunks = retrieved_chunks if isinstance(retrieved_chunks, list) else []
        candidate_chunks = [chunk for chunk in retrieved_chunks if isinstance(chunk, dict)]
        top_score = max(
            (
                float(chunk.get("score") or 0)
                for chunk in candidate_chunks
                if isinstance(chunk.get("score"), int | float)
            ),
            default=0.0,
        )
        valid_chunks = [
            chunk
            for chunk in candidate_chunks
            if float(chunk.get("score") or 0) >= top_score * 0.5
        ]
        citations = [
            str(chunk["chunk_id"]) for chunk in valid_chunks if chunk.get("chunk_id")
        ]
        claims = [str(chunk["text"]) for chunk in valid_chunks if chunk.get("text")]
        return {
            "answer": " ".join(claims),
            "citations": citations,
            "claims": claims,
        }

    def _tool_output(self, evaluation_case: AdapterEvaluationCase) -> dict:
        input_payload = evaluation_case.input_payload_json or {}
        forced_calls = input_payload.get("mock_tool_calls")
        if isinstance(forced_calls, list):
            return {"tool_calls": forced_calls}

        expected_schema = evaluation_case.expected_tool_schema_json or {}
        expected_sequence = expected_schema.get("expected_sequence")
        if isinstance(expected_sequence, list) and expected_sequence:
            calls = []
            for index, step in enumerate(expected_sequence):
                if isinstance(step, str):
                    step = {"tool_name": step}
                if not isinstance(step, dict):
                    continue
                calls.append(
                    {
                        "call_id": f"mock-call-{index + 1}",
                        "tool_name": str(step.get("tool_name", "lookup_policy")),
                        "arguments": self._tool_arguments(evaluation_case, step),
                    }
                )
            return {"tool_calls": calls}

        tool_name = str(expected_schema.get("tool_name", "lookup_policy"))
        return {
            "tool_name": tool_name,
            "arguments": self._tool_arguments(evaluation_case, expected_schema),
            "rationale": "deterministic local tool selection",
        }

    def _tool_arguments(
        self,
        evaluation_case: AdapterEvaluationCase,
        schema: dict,
    ) -> dict:
        example_arguments = schema.get("example_arguments")
        if isinstance(example_arguments, dict):
            return dict(example_arguments)
        argument_schema = schema.get("arguments")
        if not isinstance(argument_schema, dict):
            required_arguments = schema.get("required_arguments")
            if isinstance(required_arguments, list):
                argument_schema = {
                    "type": "object",
                    "required": required_arguments,
                    "properties": {
                        str(item): {"type": "string"} for item in required_arguments
                    },
                }
        if not isinstance(argument_schema, dict):
            return {"query": evaluation_case.external_case_id}
        properties = argument_schema.get("properties", {})
        required = argument_schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            return {"query": evaluation_case.external_case_id}
        arguments: dict[str, object] = {}
        for key in required:
            property_schema = properties.get(key, {})
            property_type = (
                property_schema.get("type") if isinstance(property_schema, dict) else None
            )
            if key == "query":
                arguments[key] = str(
                    evaluation_case.input_payload_json.get("request")
                    or evaluation_case.external_case_id
                )
            elif key == "document_id":
                arguments[key] = str(
                    evaluation_case.reference_context_json.get("document_id")
                    if evaluation_case.reference_context_json
                    else evaluation_case.external_case_id
                )
            elif property_type == "integer":
                arguments[key] = 1
            elif property_type == "number":
                arguments[key] = 1.0
            elif property_type == "boolean":
                arguments[key] = True
            elif property_type == "array":
                arguments[key] = []
            elif property_type == "object":
                arguments[key] = {}
            else:
                arguments[key] = str(key)
        return arguments

    def _quality_for_case(
        self, evaluation_case: AdapterEvaluationCase, seed: int | None
    ) -> float:
        seed_offset = (seed or 0) % 3
        case_offset = len(evaluation_case.external_case_id) % 5
        return round(min(0.98, 0.9 + seed_offset * 0.01 + case_offset * 0.005), 3)

    def _reliability_profile(
        self, evaluation_case: AdapterEvaluationCase
    ) -> dict[str, object]:
        profile = evaluation_case.input_payload_json.get("reliability")
        return profile if isinstance(profile, dict) else {}

    def _trial_numbers(self, profile: dict[str, object], key: str) -> set[int]:
        values = profile.get(key)
        if not isinstance(values, list):
            return set()
        return {
            int(value)
            for value in values
            if isinstance(value, int | float) and not isinstance(value, bool)
        }

    def _trial_jitter(self, profile: dict[str, object], trial_index: int) -> float:
        values = profile.get("latency_jitter_ms")
        if isinstance(values, list) and values:
            value = values[(trial_index - 1) % len(values)]
            return float(value) if isinstance(value, int | float) else 0.0
        if isinstance(values, int | float) and not isinstance(values, bool):
            return float(values) * ((trial_index - 1) % 3 - 1)
        return 0.0
