from __future__ import annotations

import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.services.inference_adapters.base import (
    AdapterCaseResult,
    AdapterConfiguration,
    AdapterDescriptor,
    AdapterEvaluationCase,
    AdapterHealth,
)
from app.services.rag_answer_contract import compile_bounded_rag_answer
from app.services.tool_call_contract import compile_bounded_tool_call
from app.services.tool_selection_prompt import (
    SYSTEM_PROMPT as TOOL_SELECTION_SYSTEM_PROMPT,
)
from app.services.tool_selection_prompt import (
    TOOL_SELECTION_PROMPT_VERSION,
    ToolSelectionPrompt,
    build_tool_selection_prompt,
)


class OpenAICompatibleAdapter:
    name = "openai_compatible"
    descriptor = AdapterDescriptor(
        adapter_id="openai_compatible",
        adapter_version="openai-compatible-v21",
        display_name="OpenAI-compatible Local Runtime",
        capabilities=frozenset(
            {
                "text_generation",
                "structured_output",
                "tool_call_json",
                "native_tool_call_response",
                "multi_step_tool_calling",
                "rag_grounded_generation",
                "citation_json",
                "compact_rag_response_contract",
                "selected_evidence_contract",
                "source_claim_enum",
                "deterministic_refusal_answer_contract",
                "deterministic_scope_answer_contract",
                "usage_metrics",
                "runtime_reliability_trials",
                "bounded_agent_plan",
                "operational_memory",
                "human_approval_checkpoint",
                "bounded_recovery_plan",
                "observation_feedback",
                "bounded_tool_call_contract",
                "non_repairing_tool_argument_guard",
                "public_tool_selection_prompt",
            }
        ),
        input_schema_version="evaluation-case-v1",
        output_schema_version="adapter-case-result-v1",
    )
    default_base_urls = [
        "http://ollama:11434",
        "http://localhost:1234",
        "http://127.0.0.1:1234",
        "http://localhost:11434",
        "http://127.0.0.1:11434",
        "http://host.docker.internal:1234",
        "http://host.docker.internal:11434",
    ]

    def health_check(self, configuration: AdapterConfiguration) -> AdapterHealth:
        attempted: list[str] = []
        for base_url in self._candidate_base_urls(configuration):
            attempted.append(base_url)
            try:
                payload = self._get_json(configuration, base_url, "/v1/models", timeout=2)
            except (HTTPError, URLError, TimeoutError, OSError):
                continue
            models = self._model_ids(payload)
            return AdapterHealth(
                adapter_name=self.name,
                healthy=True,
                message="Local OpenAI-compatible runtime responded.",
                details={
                    "base_url": base_url,
                    "models": models[:10],
                    "model_count": len(models),
                    "attempted_base_urls": attempted,
                    "adapter_descriptor": self.descriptor.to_dict(),
                },
            )
        return AdapterHealth(
            adapter_name=self.name,
            healthy=False,
            message=(
                "No local OpenAI-compatible runtime responded. Start LM Studio or Ollama, "
                "or provide runtime_config_json.base_url / OPENAI_COMPATIBLE_BASE_URL."
            ),
            details={
                "attempted_base_urls": attempted,
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
        started = time.perf_counter()
        deadline = started + self._case_timeout_seconds(configuration)
        base_url = self._resolve_base_url(configuration, deadline=deadline)
        if base_url is None:
            raise RuntimeError("No local OpenAI-compatible runtime responded")
        model_name = self._model_name(configuration, base_url, deadline=deadline)
        body = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": self._system_prompt(configuration, evaluation_case),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        self._user_message_payload(evaluation_case, configuration=configuration),
                        ensure_ascii=False,
                    ),
                },
            ],
            **self._generation_config(configuration),
        }
        if seed is not None:
            body["seed"] = seed
        if self._expects_json(evaluation_case):
            body["response_format"] = self._response_format(
                evaluation_case, configuration=configuration
            )
        payload = self._post_json(
            configuration,
            base_url,
            "/v1/chat/completions",
            body,
            deadline=deadline,
        )
        elapsed_ms = max(1.0, (time.perf_counter() - started) * 1000)
        message = payload["choices"][0]["message"]
        raw_output = self._message_output(message)
        normalized_output, json_valid, tool_valid = self._normalize_output(
            evaluation_case,
            raw_output,
        )
        tool_compilation = None
        tool_selection_prompt = self._tool_selection_prompt(evaluation_case, configuration)
        if self._is_standalone_tool_case(evaluation_case):
            tool_compilation = compile_bounded_tool_call(
                normalized_output,
                input_payload=evaluation_case.input_payload_json,
                document_context=configuration.runtime_config_json.get("_tool_document_context"),
                allowed_failure_mode=configuration.runtime_config_json.get(
                    "tool_failure_simulation"
                ),
            )
            if tool_compilation is not None:
                normalized_output = tool_compilation.normalized_output
                json_valid, tool_valid = self._validation_flags(
                    evaluation_case,
                    normalized_output,
                )
                tool_valid = tool_valid and tool_compilation.execution_allowed
        usage = payload.get("usage", {})
        completion_tokens = int(usage.get("completion_tokens") or max(1, len(raw_output) // 4))
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        gpu_vram_used_mb = configuration.runtime_config_json.get("gpu_vram_used_mb", 0.0)
        return AdapterCaseResult(
            raw_output=raw_output,
            normalized_output=normalized_output,
            quality_score=None,
            exact_match=None,
            json_valid=json_valid,
            tool_call_valid=tool_valid,
            groundedness_score=None,
            faithfulness_score=None,
            human_label="captured-needs-scoring",
            error_type=(
                "tool_argument_guard_rejected"
                if tool_compilation is not None and not tool_compilation.execution_allowed
                else None
            ),
            ttft_ms=elapsed_ms,
            end_to_end_latency_ms=elapsed_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            tokens_per_second=round(completion_tokens / (elapsed_ms / 1000), 2),
            gpu_vram_used_mb=float(gpu_vram_used_mb) if gpu_vram_used_mb is not None else None,
            gpu_utilization_pct=configuration.runtime_config_json.get("gpu_utilization_pct"),
            cpu_utilization_pct=None,
            peak_memory_mb=None,
            oom_occurred=False,
            retry_count=0,
            logs=[
                {
                    "event_type": "case_executed",
                    "level": "info",
                    "message": (
                        f"OpenAI-compatible runtime executed {evaluation_case.external_case_id}."
                    ),
                    "payload_json": {
                        "adapter": self.name,
                        "model": model_name,
                        "base_url": base_url,
                    },
                }
            ],
            metadata={
                "adapter": self.name,
                "adapter_descriptor": self.descriptor.to_dict(),
                "response_id": payload.get("id"),
                "base_url": base_url,
                "model": model_name,
                **(
                    {"tool_call_contract": tool_compilation.audit_record()}
                    if tool_compilation is not None
                    else {}
                ),
                **(
                    {"tool_selection_prompt": tool_selection_prompt.audit_record()}
                    if tool_selection_prompt is not None
                    else {}
                ),
            },
        )

    def _system_prompt(
        self,
        configuration: AdapterConfiguration,
        evaluation_case: AdapterEvaluationCase,
    ) -> str:
        prompt_bundle = configuration.runtime_config_json.get("prompt_bundle")
        configured_prompt = (
            str(prompt_bundle.get("system_prompt", "")).strip()
            if isinstance(prompt_bundle, dict)
            else ""
        )
        prefix = f"{configured_prompt}\n\n" if configured_prompt else ""
        if self._tool_selection_prompt(evaluation_case, configuration) is not None:
            return prefix + TOOL_SELECTION_SYSTEM_PROMPT
        if "agent" in (evaluation_case.category or "").lower() or isinstance(
            evaluation_case.input_payload_json.get("agent_context"), dict
        ):
            return prefix + self._agent_plan_prompt(evaluation_case)
        if "rag" in (evaluation_case.category or "").lower() or isinstance(
            evaluation_case.input_payload_json.get("rag_context"), dict
        ):
            rag_context = evaluation_case.input_payload_json.get("rag_context")
            rag_context = rag_context if isinstance(rag_context, dict) else {}
            selection = rag_context.get("evidence_selection")
            selection = selection if isinstance(selection, dict) else {}
            answer_candidates = self._rag_answer_candidates(evaluation_case, rag_context)
            claim_instruction = (
                "claims에는 evidence_selection이 선택한 claim 문장을 그대로 하나만 넣으세요. "
                if selection.get("applied_to_generation") is True
                else "claims에는 인용 본문이 직접 뒷받침하는 짧은 원자적 사실을 넣으세요. "
            )
            answer_instruction = (
                "answer에는 response schema가 허용한 고정 경계 문장을 그대로 넣으세요. "
                if answer_candidates
                else ""
            )
            return prefix + (
                "검색 근거 기반 평가입니다. rag_context.retrieved_chunks만 사용하세요. 정확히 "
                '{"answer":"...","citations":["chunk-id"],"claims":["..."]} '
                "형태의 짧은 JSON 객체 하나만 출력하세요. answer는 비어 있거나 null이면 안 "
                "됩니다. citations에는 근거로 사용한 chunk_id 문자열만 넣고 객체, 문서 제목, "
                "본문을 넣지 마세요. "
                + claim_instruction
                + answer_instruction
                + "근거가 없거나 요청된 사실을 확인할 수 없으면 answer에서 "
                "명시적으로 거절하고 그 경계를 설명하는 chunk를 인용하세요. 입력 질문이나 "
                "검색 본문을 반복하지 말고 markdown과 추가 필드를 출력하지 마세요."
            )
        if evaluation_case.expected_tool_schema_json is not None:
            expected_sequence = evaluation_case.expected_tool_schema_json.get("expected_sequence")
            if isinstance(expected_sequence, list) and len(expected_sequence) > 1:
                return prefix + (
                    "You are executing a multi-step tool-selection evaluation case. "
                    "Return only one valid JSON object with a tool_calls array. Each item "
                    "must contain tool_name and arguments, in execution order. Do not include "
                    "markdown, prose, or code fences."
                )
            return prefix + (
                "You are executing a tool-selection evaluation case. "
                "Return only one valid JSON object with keys tool_name and arguments. "
                "Do not include markdown, prose, or code fences."
            )
        if (
            evaluation_case.expected_output_json is not None
            or "json" in (evaluation_case.category or "").lower()
        ):
            return prefix + (
                "You are executing a JSON extraction evaluation case. "
                "Return only one valid JSON object matching the requested schema. "
                "Do not include markdown, prose, or code fences."
            )
        return prefix + (
            "You are executing a Korean document QA evaluation case. "
            "Answer concisely using only the provided input and reference context."
        )

    def _user_message_payload(
        self,
        evaluation_case: AdapterEvaluationCase,
        *,
        configuration: AdapterConfiguration | None = None,
    ) -> dict[str, Any]:
        input_payload = evaluation_case.input_payload_json
        tool_selection_prompt = self._tool_selection_prompt(evaluation_case, configuration)
        if tool_selection_prompt is not None:
            return tool_selection_prompt.user_payload
        rag_context = input_payload.get("rag_context")
        if isinstance(rag_context, dict):
            allowed_citation_ids = self._rag_citation_candidates(rag_context)
            single_citation = self._uses_single_rag_citation(evaluation_case)
            selection = rag_context.get("evidence_selection")
            selection = selection if isinstance(selection, dict) else {}
            answer_candidates = self._rag_answer_candidates(evaluation_case, rag_context)
            selection_instruction = (
                " 이 거부 평가에서는 response schema가 허용한 고정 거부문을 그대로 사용하고 "
                "요청된 정보를 추측하거나 생성하지 마세요."
                if (evaluation_case.category or "").lower() == "insufficient_evidence_refusal"
                and answer_candidates
                else " 이 범위 평가에서는 response schema가 허용한 고정 경계문을 그대로 "
                "사용하고 선택 근거의 범위를 확대하지 마세요."
                if (evaluation_case.category or "").lower() == "rag_version_or_scope"
                and answer_candidates
                else " 선택 confidence가 낮으므로 요청된 사실을 확인할 수 없다고 명시적으로 "
                "거절하고 정보를 추측하거나 생성하지 마세요."
                if selection.get("applied_to_generation") is True
                and selection.get("abstain_recommended") is True
                else " 선택 근거가 직접 뒷받침하는 범위 안에서만 답하세요."
                if selection.get("applied_to_generation") is True
                else ""
            )
            return {
                "case_id": evaluation_case.external_case_id,
                "category": evaluation_case.category,
                "query": str(
                    input_payload.get("query")
                    or input_payload.get("question")
                    or evaluation_case.title
                ).strip(),
                "instruction": (
                    "rag_context만 근거로 사용하세요. answer, citations, claims 세 필드를 모두 "
                    "채우고 각 문자열을 간결하게 작성하세요. citations에는 "
                    "allowed_citation_ids 중 가장 직접적인 근거 ID 하나만 넣으세요."
                    + selection_instruction
                    if single_citation
                    else "rag_context만 근거로 사용하세요. answer, citations, claims 세 필드를 "
                    "모두 채우고 각 문자열을 간결하게 작성하세요. citations에는 "
                    "allowed_citation_ids 중 실제 답변에 꼭 필요한 최소 ID만 넣으세요."
                    + selection_instruction
                ),
                "allowed_citation_ids": allowed_citation_ids,
                "rag_context": rag_context,
            }
        context = input_payload.get("agent_context")
        context = context if isinstance(context, dict) else {}
        allowed_actions = self._string_values(context.get("allowed_actions"))
        allowed_tools = self._string_values(context.get("allowed_tools"))
        if set(allowed_actions) == {"retrieve", "tool", "respond"} and allowed_tools:
            request_text = str(
                input_payload.get("request") or input_payload.get("query") or evaluation_case.title
            ).strip()
            template = self._minimal_agent_plan_example(
                input_payload=input_payload,
                context=context,
                allowed_actions=allowed_actions,
                allowed_tools=allowed_tools,
                request_text=request_text,
            )
            payload: dict[str, Any] = {
                "case_id": evaluation_case.external_case_id,
                "category": evaluation_case.category,
                "title": evaluation_case.title,
                "request": request_text,
                "instruction": (
                    "required_output_template의 JSON 구조와 값을 그대로 출력하세요. "
                    "필드를 추가하거나 단계를 반복하지 마세요."
                ),
                "required_output_template": template,
            }
            retrieval_query = str(context.get("retrieval_query") or "").strip()
            if retrieval_query:
                payload["retrieval_contract"] = {
                    "query": retrieval_query,
                    "strategy": context.get("retrieval_query_strategy"),
                }
            return payload
        return {
            "case_id": evaluation_case.external_case_id,
            "category": evaluation_case.category,
            "title": evaluation_case.title,
            "input": input_payload,
        }

    def _response_format(
        self,
        evaluation_case: AdapterEvaluationCase,
        *,
        configuration: AdapterConfiguration | None = None,
    ) -> dict[str, Any]:
        tool_selection_prompt = self._tool_selection_prompt(evaluation_case, configuration)
        if tool_selection_prompt is not None:
            return tool_selection_prompt.response_format()
        rag_context = evaluation_case.input_payload_json.get("rag_context")
        if not isinstance(rag_context, dict):
            return {"type": "json_object"}
        citation_candidates = self._rag_citation_candidates(rag_context)
        maximum_citations = 1 if self._uses_single_rag_citation(evaluation_case) else 3
        answer_candidates = self._rag_answer_candidates(evaluation_case, rag_context)
        answer_schema: dict[str, Any] = {"type": "string", "minLength": 1}
        if answer_candidates:
            answer_schema["enum"] = answer_candidates
        citation_item_schema: dict[str, Any] = {"type": "string"}
        if citation_candidates:
            citation_item_schema["enum"] = citation_candidates
        claim_candidates = self._rag_claim_candidates(rag_context)
        claim_item_schema: dict[str, Any] = {"type": "string", "minLength": 1}
        if claim_candidates:
            claim_item_schema["enum"] = claim_candidates
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "rag_grounded_response",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "answer": answer_schema,
                        "citations": {
                            "type": "array",
                            "items": citation_item_schema,
                            "minItems": 1,
                            "maxItems": maximum_citations,
                            "uniqueItems": True,
                        },
                        "claims": {
                            "type": "array",
                            "items": claim_item_schema,
                            "minItems": 1,
                            "maxItems": 1 if claim_candidates else 2,
                        },
                    },
                    "required": ["answer", "citations", "claims"],
                    "additionalProperties": False,
                },
            },
        }

    @staticmethod
    def _rag_citation_candidates(rag_context: dict[str, Any]) -> list[str]:
        chunks = rag_context.get("retrieved_chunks")
        if not isinstance(chunks, list):
            return []
        candidates: list[str] = []
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            chunk_id = chunk.get("chunk_id")
            if isinstance(chunk_id, str) and chunk_id.strip():
                candidates.append(chunk_id.strip())
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _rag_claim_candidates(rag_context: dict[str, Any]) -> list[str]:
        selection = rag_context.get("evidence_selection")
        selection = selection if isinstance(selection, dict) else {}
        if selection.get("applied_to_generation") is not True:
            return []
        selections = selection.get("selections")
        if not isinstance(selections, list):
            return []
        claims: list[str] = []
        for item in selections:
            if not isinstance(item, dict):
                continue
            claim = item.get("claim")
            if isinstance(claim, str) and claim.strip():
                claims.append(claim.strip())
        return list(dict.fromkeys(claims))

    @classmethod
    def _rag_answer_candidates(
        cls,
        evaluation_case: AdapterEvaluationCase,
        rag_context: dict[str, Any],
    ) -> list[str]:
        prepared_contract = rag_context.get("answer_contract")
        if isinstance(prepared_contract, dict):
            prepared_answer = prepared_contract.get("answer")
            if isinstance(prepared_answer, str) and prepared_answer.strip():
                return [prepared_answer.strip()]
        selection = rag_context.get("evidence_selection")
        selection = selection if isinstance(selection, dict) else {}
        if selection.get("applied_to_generation") is not True:
            return []
        claims = cls._rag_claim_candidates(rag_context)
        query = str(
            evaluation_case.input_payload_json.get("query")
            or evaluation_case.input_payload_json.get("question")
            or evaluation_case.title
        ).strip()
        if not claims or not query:
            return []
        contract = compile_bounded_rag_answer(
            category=evaluation_case.category or "",
            query=query,
            claims=claims,
        )
        return [contract.answer] if contract is not None else []

    @staticmethod
    def _uses_single_rag_citation(evaluation_case: AdapterEvaluationCase) -> bool:
        return (evaluation_case.category or "").lower() in {
            "rag_version_or_scope",
            "insufficient_evidence_refusal",
        }

    @staticmethod
    def _tool_selection_prompt(
        evaluation_case: AdapterEvaluationCase,
        configuration: AdapterConfiguration | None = None,
    ) -> ToolSelectionPrompt | None:
        mode = (
            configuration.runtime_config_json.get("tool_selection_prompt")
            if configuration is not None
            else None
        )
        if mode not in (None, "legacy", TOOL_SELECTION_PROMPT_VERSION):
            raise ValueError(f"unsupported tool_selection_prompt: {mode}")
        if mode != TOOL_SELECTION_PROMPT_VERSION:
            return None
        if (evaluation_case.category or "").lower() not in {
            "tool_single_step",
            "tool_failure_recovery",
        } or not OpenAICompatibleAdapter._is_standalone_tool_case(evaluation_case):
            return None
        expected = evaluation_case.expected_tool_schema_json or {}
        sequence = expected.get("expected_sequence")
        if isinstance(sequence, list) and len(sequence) > 1:
            return None
        return build_tool_selection_prompt(evaluation_case.input_payload_json)

    @staticmethod
    def _is_standalone_tool_case(evaluation_case: AdapterEvaluationCase) -> bool:
        input_payload = evaluation_case.input_payload_json
        schema = evaluation_case.expected_tool_schema_json or {}
        sequence = schema.get("expected_sequence")
        return (
            evaluation_case.expected_tool_schema_json is not None
            and not isinstance(input_payload.get("agent_context"), dict)
            and not isinstance(input_payload.get("rag_context"), dict)
            and "agent" not in (evaluation_case.category or "").lower()
            and "rag" not in (evaluation_case.category or "").lower()
            and not (isinstance(sequence, list) and len(sequence) > 1)
        )

    def _agent_plan_prompt(self, evaluation_case: AdapterEvaluationCase) -> str:
        input_payload = evaluation_case.input_payload_json
        context = input_payload.get("agent_context")
        context = context if isinstance(context, dict) else {}
        allowed_actions = self._string_values(context.get("allowed_actions"))
        allowed_tools = self._string_values(context.get("allowed_tools"))
        step_limit = context.get("step_limit")
        step_limit = step_limit if isinstance(step_limit, int) and step_limit > 0 else 1
        request_text = str(
            input_payload.get("request") or input_payload.get("query") or evaluation_case.title
        ).strip()
        example = self._minimal_agent_plan_example(
            input_payload=input_payload,
            context=context,
            allowed_actions=allowed_actions,
            allowed_tools=allowed_tools,
            request_text=request_text,
        )
        allowed_action_text = ", ".join(allowed_actions) or "respond"
        allowed_tool_text = ", ".join(allowed_tools) or "none"
        example_text = json.dumps(example, ensure_ascii=False, separators=(",", ":"))
        return (
            "제한된 Agent 실행 계획을 만드세요. JSON 객체 하나만 출력하고 markdown과 설명은 "
            "출력하지 마세요. steps는 최대 "
            f"{step_limit}개이며 허용 action은 [{allowed_action_text}], 허용 tool은 "
            f"[{allowed_tool_text}]입니다. 같은 action을 불필요하게 반복하지 마세요. "
            "각 step에는 아래 필드만 사용하세요: retrieve={action,query}, "
            "tool={action,tool_name,arguments}, respond={action,content,citations}, "
            "memory_read={action,memory_id}, memory_write={action,key,value}, "
            "approval_checkpoint={action,checkpoint_id}. args, description, step_index는 "
            "사용하지 마세요. 검색 후 도구를 실행하고 답하는 요청이며 retrieve/tool/respond가 "
            "모두 허용되면 그 순서로 각각 한 번만 사용하세요. tool arguments는 "
            "available_tools의 argument_schema에서 required인 필드만 포함하세요. 마지막은 항상 "
            "content가 비어 있지 않은 respond여야 하며 content에는 수행한 action 순서와 tool "
            "이름을 간단히 명시하세요. 다음 JSON은 현재 공개 실행 컨텍스트로 만든 형식 예시이며 "
            f"그 구조를 그대로 따르세요: {example_text}"
        )

    def _minimal_agent_plan_example(
        self,
        *,
        input_payload: dict[str, Any],
        context: dict[str, Any],
        allowed_actions: list[str],
        allowed_tools: list[str],
        request_text: str,
    ) -> dict[str, Any]:
        actions = set(allowed_actions)
        if {"retrieve", "tool", "respond"}.issubset(actions) and allowed_tools:
            tool_name = allowed_tools[0]
            retrieval_query = str(context.get("retrieval_query") or "").strip()
            arguments = self._example_tool_arguments(
                input_payload.get("available_tools"),
                tool_name=tool_name,
                request_text=request_text,
            )
            return {
                "steps": [
                    {"action": "retrieve", "query": retrieval_query or request_text},
                    {
                        "action": "tool",
                        "tool_name": tool_name,
                        "arguments": arguments,
                    },
                    {
                        "action": "respond",
                        "content": (
                            f"retrieve 후 {tool_name} 실행, retrieve, tool, respond 순서 완료"
                        ),
                    },
                ]
            }
        sequence = [action for action in allowed_actions if action != "respond"]
        if "respond" in actions:
            sequence.append("respond")
        step_limit = context.get("step_limit")
        if isinstance(step_limit, int) and step_limit > 0:
            sequence = sequence[:step_limit]
            if "respond" in actions and sequence and sequence[-1] != "respond":
                sequence[-1] = "respond"
        steps = [
            self._example_agent_step(
                action,
                context=context,
                input_payload=input_payload,
                allowed_tools=allowed_tools,
                request_text=request_text,
                sequence=sequence,
            )
            for action in sequence
        ]
        return {"steps": steps or [{"action": "respond", "content": "허용 범위에서 응답 완료"}]}

    def _example_agent_step(
        self,
        action: str,
        *,
        context: dict[str, Any],
        input_payload: dict[str, Any],
        allowed_tools: list[str],
        request_text: str,
        sequence: list[str],
    ) -> dict[str, Any]:
        if action == "retrieve":
            retrieval_query = str(context.get("retrieval_query") or "").strip()
            return {"action": action, "query": retrieval_query or request_text}
        if action == "tool" and allowed_tools:
            tool_name = allowed_tools[0]
            return {
                "action": action,
                "tool_name": tool_name,
                "arguments": self._example_tool_arguments(
                    input_payload.get("available_tools"),
                    tool_name=tool_name,
                    request_text=request_text,
                ),
            }
        if action == "memory_read":
            memory_ids = self._string_values(context.get("allowed_memory_ids"))
            return {
                "action": action,
                "memory_id": memory_ids[0] if memory_ids else "allowed-memory",
            }
        if action == "memory_write":
            return {"action": action, "key": "task_note", "value": request_text}
        if action == "approval_checkpoint":
            checkpoint_ids = self._string_values(context.get("allowed_checkpoint_ids"))
            return {
                "action": action,
                "checkpoint_id": checkpoint_ids[0] if checkpoint_ids else "operator-approval",
            }
        tool_receipt = f", tool={allowed_tools[0]}" if allowed_tools else ""
        return {
            "action": "respond",
            "content": f"action 순서: {', '.join(sequence)}{tool_receipt}",
        }

    def _example_tool_arguments(
        self,
        descriptors: Any,
        *,
        tool_name: str,
        request_text: str,
    ) -> dict[str, Any]:
        descriptor = (
            next(
                (
                    item
                    for item in descriptors
                    if isinstance(item, dict) and item.get("tool_name") == tool_name
                ),
                None,
            )
            if isinstance(descriptors, list)
            else None
        )
        schema = descriptor.get("argument_schema") if isinstance(descriptor, dict) else None
        if not isinstance(schema, dict):
            return {"query": request_text}
        properties = schema.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        required = schema.get("required")
        required = required if isinstance(required, list) else []
        return {
            str(name): self._example_argument_value(
                str(name),
                properties.get(name),
                request_text=request_text,
            )
            for name in required
        }

    def _example_argument_value(
        self,
        name: str,
        schema: Any,
        *,
        request_text: str,
    ) -> Any:
        schema = schema if isinstance(schema, dict) else {}
        enum = schema.get("enum")
        if isinstance(enum, list) and enum:
            return enum[0]
        if name == "query":
            return request_text
        if name == "document_id":
            return "model-atlas-operator-runbook"
        return {
            "integer": 1,
            "number": 1.0,
            "boolean": True,
            "array": [],
            "object": {},
        }.get(str(schema.get("type")), name)

    def _string_values(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _message_output(self, message: dict[str, Any]) -> str:
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            return json.dumps({"tool_calls": tool_calls}, ensure_ascii=False)
        content = message.get("content")
        return str(content) if content is not None else ""

    def _candidate_base_urls(self, configuration: AdapterConfiguration) -> list[str]:
        configured = configuration.runtime_config_json.get("base_url")
        environment = os.getenv("OPENAI_COMPATIBLE_BASE_URL")
        if configured:
            return [self._normalize_base_url(str(configured))]
        candidates = [value for value in [environment, *self.default_base_urls] if value]
        normalized: list[str] = []
        for candidate in candidates:
            value = self._normalize_base_url(candidate)
            if value not in normalized:
                normalized.append(value)
        return normalized

    def _normalize_base_url(self, value: str) -> str:
        base_url = value.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
        return base_url

    def _resolve_base_url(
        self,
        configuration: AdapterConfiguration,
        *,
        deadline: float | None = None,
    ) -> str | None:
        for base_url in self._candidate_base_urls(configuration):
            try:
                timeout = (
                    min(2.0, self._remaining_timeout(deadline)) if deadline is not None else 2.0
                )
                self._get_json(
                    configuration,
                    base_url,
                    "/v1/models",
                    timeout=timeout,
                )
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                if deadline is not None and time.perf_counter() >= deadline:
                    raise TimeoutError("case timeout exceeded while resolving the runtime") from exc
                continue
            return base_url
        return None

    def _model_name(
        self,
        configuration: AdapterConfiguration,
        base_url: str,
        *,
        deadline: float | None = None,
    ) -> str:
        configured = configuration.runtime_config_json.get(
            "model"
        ) or configuration.runtime_config_json.get("model_name")
        if configured:
            return str(configured)
        try:
            timeout = min(2.0, self._remaining_timeout(deadline)) if deadline is not None else 2.0
            payload = self._get_json(
                configuration,
                base_url,
                "/v1/models",
                timeout=timeout,
            )
        except (HTTPError, URLError, TimeoutError, OSError):
            return configuration.model_artifact.artifact_name
        models = self._model_ids(payload)
        return models[0] if models else configuration.model_artifact.artifact_name

    def _headers(self, configuration: AdapterConfiguration) -> dict[str, str]:
        headers = {"content-type": "application/json"}
        configured_env = configuration.runtime_config_json.get("api_key_env")
        api_key_env = (
            str(configured_env)
            if isinstance(configured_env, str) and configured_env
            else "OPENAI_COMPATIBLE_API_KEY"
        )
        api_key = os.getenv(api_key_env)
        if api_key:
            headers["authorization"] = f"Bearer {api_key}"
        return headers

    def _generation_config(self, configuration: AdapterConfiguration) -> dict[str, Any]:
        config = dict(configuration.generation_config_json or {})
        if "max_new_tokens" in config and "max_tokens" not in config:
            config["max_tokens"] = config.pop("max_new_tokens")
        else:
            config.pop("max_new_tokens", None)
        return config

    def _get_json(
        self,
        configuration: AdapterConfiguration,
        base_url: str,
        path: str,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        request = Request(
            f"{base_url}{path}",
            headers=self._headers(configuration),
            method="GET",
        )
        with urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def _post_json(
        self,
        configuration: AdapterConfiguration,
        base_url: str,
        path: str,
        body: dict[str, Any],
        *,
        deadline: float | None = None,
    ) -> dict[str, Any]:
        request = Request(
            f"{base_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(configuration),
            method="POST",
        )
        timeout_seconds = (
            self._remaining_timeout(deadline)
            if deadline is not None
            else self._case_timeout_seconds(configuration)
        )
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def _case_timeout_seconds(self, configuration: AdapterConfiguration) -> float:
        timeout_ms = configuration.runtime_config_json.get("_case_timeout_ms", 120_000)
        return max(0.1, float(timeout_ms) / 1000)

    def _remaining_timeout(self, deadline: float | None) -> float:
        if deadline is None:
            raise ValueError("deadline is required")
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise TimeoutError("case timeout exceeded before inference completed")
        return remaining

    def _model_ids(self, payload: dict[str, Any]) -> list[str]:
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        model_ids: list[str] = []
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                model_ids.append(str(item["id"]))
        return model_ids

    def _normalize_output(
        self,
        evaluation_case: AdapterEvaluationCase,
        output: str,
    ) -> tuple[str, bool, bool]:
        normalized = output.strip()
        if not self._expects_json(evaluation_case):
            return normalized, False, False
        json_text = self._extract_json_text(normalized)
        if json_text is None:
            return normalized, False, False
        json_valid, tool_valid = self._validation_flags(evaluation_case, json_text)
        return (json_text if json_valid else normalized), json_valid, tool_valid

    def _expects_json(self, evaluation_case: AdapterEvaluationCase) -> bool:
        return (
            evaluation_case.expected_output_json is not None
            or evaluation_case.expected_tool_schema_json is not None
            or "agent" in (evaluation_case.category or "").lower()
            or isinstance(evaluation_case.input_payload_json.get("agent_context"), dict)
            or "json" in (evaluation_case.category or "").lower()
        )

    def _extract_json_text(self, output: str) -> str | None:
        try:
            json.loads(output)
            return output
        except json.JSONDecodeError:
            pass
        fenced_start = output.find("```")
        if fenced_start >= 0:
            body_start = output.find("\n", fenced_start)
            fenced_end = output.find("```", body_start + 1 if body_start >= 0 else fenced_start + 3)
            if body_start >= 0 and fenced_end > body_start:
                candidate = output[body_start + 1 : fenced_end].strip()
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    pass
        object_start = output.find("{")
        object_end = output.rfind("}")
        if 0 <= object_start < object_end:
            candidate = output[object_start : object_end + 1].strip()
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
        return None

    def _validation_flags(
        self, evaluation_case: AdapterEvaluationCase, output: str
    ) -> tuple[bool, bool]:
        if not self._expects_json(evaluation_case):
            return False, False
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return False, False
        tool_valid = False
        if evaluation_case.expected_tool_schema_json is not None and isinstance(parsed, dict):
            tool_valid = any(key in parsed for key in ("tool_name", "tool_call", "tool_calls"))
        return True, tool_valid
