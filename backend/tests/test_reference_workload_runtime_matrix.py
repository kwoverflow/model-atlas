from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.reference_workload import runtime_matrix
from app.reference_workload.cli import build_parser
from app.reference_workload.runtime_matrix import (
    RuntimeMatrixError,
    load_runtime_matrix,
    probe_runtime,
    resolve_runtime_entry,
)
from app.services.deployment_gate_resources import _runtime_is_remote
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter


def _matrix_file(path: Path, *, duplicate: bool = False) -> Path:
    entries = [
        {
            "name": "small-baseline",
            "enabled": True,
            "base_url_env": "REFERENCE_RUNTIME_BASE_URL",
            "api_key_env": "REFERENCE_RUNTIME_API_KEY",
            "model_env": "REFERENCE_MODEL_SMALL",
            "context_length": 4096,
            "prompt_bundle": "operator-assistant-ko-v1",
            "generation": {"temperature": 0, "max_tokens": 256},
            "trials": 2,
            "concurrency": 1,
        }
    ]
    if duplicate:
        entries.append(dict(entries[0]))
    path.write_text(
        json.dumps(
            {
                "schema_version": "model-atlas-reference-runtime-matrix-v1",
                "workload_slug": "model-atlas-operator-assistant-ko",
                "entries": entries,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_runtime_matrix_validates_and_resolves_environment(tmp_path: Path) -> None:
    matrix = load_runtime_matrix(_matrix_file(tmp_path / "matrix.json"))

    resolved = resolve_runtime_entry(
        matrix.entries[0],
        environment={
            "REFERENCE_RUNTIME_BASE_URL": "http://ollama:11434/v1",
            "REFERENCE_MODEL_SMALL": "qwen2.5:0.5b",
        },
    )

    assert resolved.base_url == "http://ollama:11434"
    assert resolved.model_name == "qwen2.5:0.5b"
    assert resolved.api_key_configured is False


def test_runtime_matrix_rejects_duplicate_names_and_missing_environment(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeMatrixError, match="names must be unique"):
        load_runtime_matrix(_matrix_file(tmp_path / "duplicate.json", duplicate=True))

    matrix = load_runtime_matrix(_matrix_file(tmp_path / "valid.json"))
    with pytest.raises(RuntimeMatrixError, match="REFERENCE_MODEL_SMALL"):
        resolve_runtime_entry(
            matrix.entries[0],
            environment={"REFERENCE_RUNTIME_BASE_URL": "http://ollama:11434"},
        )


def test_runtime_probe_requires_observed_model_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix = load_runtime_matrix(_matrix_file(tmp_path / "matrix.json"))
    resolved = resolve_runtime_entry(
        matrix.entries[0],
        environment={
            "REFERENCE_RUNTIME_BASE_URL": "http://ollama:11434",
            "REFERENCE_MODEL_SMALL": "qwen2.5:0.5b",
        },
    )

    def request_json(url: str, **_: Any) -> dict[str, Any]:
        if url.endswith("/v1/models"):
            return {"data": [{"id": "qwen2.5:0.5b"}]}
        if url.endswith("/api/tags"):
            return {
                "models": [
                    {
                        "name": "qwen2.5:0.5b",
                        "digest": "a" * 64,
                        "size": 100,
                        "details": {
                            "format": "gguf",
                            "family": "qwen2",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            }
        return {"version": "1.2.3"}

    monkeypatch.setattr(runtime_matrix, "_request_json", request_json)
    observation = probe_runtime(resolved, environment={})
    assert observation.digest == "a" * 64
    assert observation.runtime_version == "1.2.3"

    monkeypatch.setattr(
        runtime_matrix,
        "_request_json",
        lambda url, **_: {"data": [{"id": "qwen2.5:0.5b"}]} if url.endswith("/v1/models") else {},
    )
    with pytest.raises(RuntimeMatrixError, match="digest could not be observed"):
        probe_runtime(resolved, environment={})


def test_local_runtime_url_is_not_classified_as_remote() -> None:
    payload = SimpleNamespace(
        runtime_name="ollama_openai_compatible",
        runtime_config_json={"base_url": "http://ollama:11434", "remote": False},
    )
    assert _runtime_is_remote(payload) is False
    payload.runtime_config_json = {"base_url": "https://api.example.com"}
    assert _runtime_is_remote(payload) is True


def test_openai_adapter_applies_prompt_without_expected_answer_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = OpenAICompatibleAdapter()
    configuration = SimpleNamespace(
        runtime_config_json={
            "base_url": "http://ollama:11434",
            "model": "qwen2.5:0.5b",
            "prompt_bundle": {"system_prompt": "검증 가능한 근거만 사용하세요."},
        },
        generation_config_json={"temperature": 0},
        model_artifact=SimpleNamespace(artifact_name="qwen2.5:0.5b"),
    )
    evaluation_case = SimpleNamespace(
        external_case_id="KO-TOOL-001",
        category="tool_single_step",
        title="도구 선택",
        input_payload_json={"query": "정책을 찾아주세요", "available_tools": []},
        expected_output_json={"required_facts": ["정답 누출"]},
        reference_context_json={"expected_tool": "lookup_policy"},
        expected_tool_schema_json={"tool_name": "lookup_policy"},
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(adapter, "_resolve_base_url", lambda *_args, **_kwargs: "http://ollama")

    def post_json(_configuration: Any, _base_url: str, _path: str, body: dict, **_: Any):
        captured.update(body)
        return {
            "id": "response-1",
            "choices": [{"message": {"content": '{"tool_name":"lookup_policy","arguments":{}}'}}],
            "usage": {"completion_tokens": 10},
        }

    monkeypatch.setattr(adapter, "_post_json", post_json)
    adapter.run_case(configuration=configuration, evaluation_case=evaluation_case)

    system_message = captured["messages"][0]["content"]
    user_payload = json.loads(captured["messages"][1]["content"])
    assert system_message.startswith("검증 가능한 근거만 사용하세요.")
    assert captured["response_format"] == {"type": "json_object"}
    assert "expected_output_schema" not in user_payload
    assert "expected_tool_schema" not in user_payload
    assert "reference_context" not in user_payload


def test_openai_adapter_applies_public_tool_contract_and_preserves_raw_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = OpenAICompatibleAdapter()
    configuration = SimpleNamespace(
        runtime_config_json={
            "base_url": "http://ollama:11434",
            "model": "qwen2.5:0.5b",
            "tool_selection_prompt": "public-tool-selection-prompt-v1",
        },
        generation_config_json={"temperature": 0},
        model_artifact=SimpleNamespace(artifact_name="qwen2.5:0.5b"),
    )
    evaluation_case = SimpleNamespace(
        external_case_id="KO-TOOL-PUBLIC-001",
        category="tool_single_step",
        title="정책 조회",
        input_payload_json={
            "query": "릴리스 정책을 조회해 주세요.",
            "_execution_trial": 1,
            "_case_timeout_ms": 120_000,
            "available_tools": [
                {
                    "tool_name": "lookup_policy",
                    "description": "공개 정책 조회 Tool",
                    "argument_schema": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {
                            "query": {"type": "string", "minLength": 1},
                            "simulate_failure": {
                                "type": "string",
                                "enum": ["transient_once", "permanent"],
                            },
                        },
                        "additionalProperties": False,
                    },
                }
            ],
        },
        expected_output_json=None,
        reference_context_json={"private_expected_tool": "must-not-leak"},
        expected_tool_schema_json={"tool_name": "lookup_policy", "private": "must-not-leak"},
    )
    raw_output = (
        '{"tool_name":"lookup_policy","arguments":'
        '{"query":"릴리스 정책","simulate_failure":"transient_once"}}'
    )
    captured: dict[str, Any] = {}
    monkeypatch.setattr(adapter, "_resolve_base_url", lambda *_args, **_kwargs: "http://ollama")

    def post_json(_configuration: Any, _base_url: str, _path: str, body: dict, **_: Any):
        captured.update(body)
        return {
            "id": "response-tool-1",
            "choices": [{"message": {"content": raw_output}}],
            "usage": {"completion_tokens": 10},
        }

    monkeypatch.setattr(adapter, "_post_json", post_json)
    result = adapter.run_case(configuration=configuration, evaluation_case=evaluation_case)

    user_payload = json.loads(captured["messages"][1]["content"])
    assert user_payload["request"] == "릴리스 정책을 조회해 주세요."
    assert "must-not-leak" not in json.dumps(user_payload, ensure_ascii=False)
    assert captured["response_format"]["type"] == "json_schema"
    assert result.raw_output == raw_output
    assert json.loads(result.normalized_output) == {
        "tool_name": "lookup_policy",
        "arguments": {"query": "릴리스 정책", "simulate_failure": "transient_once"},
    }
    assert result.metadata["tool_call_contract"]["uses_expected_tool_contract"] is False
    assert result.metadata["tool_call_contract"]["removed_arguments"] == []
    assert result.metadata["tool_call_contract"]["execution_allowed"] is False
    assert result.error_type == "tool_argument_guard_rejected"
    assert result.metadata["tool_selection_prompt"]["selection_overridden"] is False


def test_openai_adapter_uses_compact_rag_contract_without_ground_truth_leakage() -> None:
    adapter = OpenAICompatibleAdapter()
    configuration = SimpleNamespace(
        runtime_config_json={"prompt_bundle": {"system_prompt": "공개 근거만 사용하세요."}}
    )
    evaluation_case = SimpleNamespace(
        external_case_id="KO-REFUSE-001",
        category="insufficient_evidence_refusal",
        title="최고 모델 단정 거부",
        input_payload_json={
            "query": "현재 모든 모델 중 최고 모델을 단정해 주세요.",
            "instruction": "근거만 사용하세요.",
            "rag_context": {
                "query": "현재 모든 모델 중 최고 모델을 단정해 주세요.",
                "retrieved_chunks": [
                    {
                        "chunk_id": "public-chunk-001",
                        "title": "평가 경계",
                        "text": "비교 근거가 없으면 최고 모델을 단정할 수 없다.",
                    }
                ],
                "evidence_selection": {
                    "schema_version": "rag-evidence-selection-v1",
                    "selector_id": "lexical_sentence_selector",
                    "selector_version": "lexical-sentence-selector-v1",
                    "selected_chunk_ids": ["public-chunk-001"],
                    "selected_count": 1,
                    "confidence": "high",
                    "abstain_recommended": False,
                    "applied_to_generation": True,
                    "selections": [
                        {
                            "chunk_id": "public-chunk-001",
                            "claim": "비교 근거가 없으면 최고 모델을 단정할 수 없다.",
                        }
                    ],
                },
            },
        },
        expected_output_json={
            "must_refuse": True,
            "required_facts": ["private required fact"],
            "forbidden_claims": ["private forbidden claim"],
        },
        expected_tool_schema_json=None,
        reference_context_json={"rag": {"relevant_chunk_ids": ["private-expected-id"]}},
    )

    prompt = adapter._system_prompt(configuration, evaluation_case)
    user_payload = adapter._user_message_payload(evaluation_case)
    serialized = json.dumps(user_payload, ensure_ascii=False)

    response_format = adapter._response_format(evaluation_case)

    assert adapter.descriptor.adapter_version == "openai-compatible-v21"
    assert '{"answer":"...","citations":["chunk-id"],"claims":["..."]}' in prompt
    assert "citation" in prompt
    assert user_payload["rag_context"]["retrieved_chunks"][0]["chunk_id"] == ("public-chunk-001")
    assert user_payload["allowed_citation_ids"] == ["public-chunk-001"]
    response_schema = response_format["json_schema"]["schema"]
    assert response_format["type"] == "json_schema"
    assert response_schema["required"] == ["answer", "citations", "claims"]
    assert response_schema["additionalProperties"] is False
    assert response_schema["properties"]["citations"]["items"]["enum"] == ["public-chunk-001"]
    assert response_schema["properties"]["citations"]["maxItems"] == 1
    assert response_schema["properties"]["claims"]["items"]["enum"] == [
        "비교 근거가 없으면 최고 모델을 단정할 수 없다."
    ]
    assert response_schema["properties"]["claims"]["maxItems"] == 1
    refusal_answer = response_schema["properties"]["answer"]["enum"][0]
    assert "제공할 수 없습니다" in refusal_answer
    assert "현재 모든 모델 중 최고 모델을 단정해 주세요." in refusal_answer
    assert "비교 근거가 없으면 최고 모델을 단정할 수 없다." in refusal_answer
    assert len(refusal_answer) < 240
    assert "private required fact" not in prompt
    assert "private required fact" not in serialized
    assert "private forbidden claim" not in serialized
    assert "private-expected-id" not in serialized


def test_openai_adapter_uses_public_bounded_scope_answer_contract() -> None:
    adapter = OpenAICompatibleAdapter()
    claim = "추천 순위가 곧 배포 승인이 아니라는 경계를 검토한다."
    query = "Candidate Discovery 1위 모델을 평가 없이 릴리스해도 되나요?"
    evaluation_case = SimpleNamespace(
        external_case_id="KO-RAG-SCOPE-002",
        category="rag_version_or_scope",
        title="추천 순위 해석",
        input_payload_json={
            "query": query,
            "rag_context": {
                "query": query,
                "retrieved_chunks": [
                    {
                        "chunk_id": "public-chunk-001",
                        "title": "추천과 승인",
                        "text": claim,
                    }
                ],
                "evidence_selection": {
                    "applied_to_generation": True,
                    "selections": [
                        {
                            "chunk_id": "public-chunk-001",
                            "claim": claim,
                        }
                    ],
                },
            },
        },
        expected_output_json={
            "required_facts": ["private required fact"],
            "forbidden_claims": ["private forbidden claim"],
        },
        expected_tool_schema_json=None,
        reference_context_json={"rag": {"relevant_chunk_ids": ["private-expected-id"]}},
    )

    response_format = adapter._response_format(evaluation_case)
    answer = response_format["json_schema"]["schema"]["properties"]["answer"]["enum"][0]
    user_payload = adapter._user_message_payload(evaluation_case)
    serialized = json.dumps(user_payload, ensure_ascii=False)

    assert claim in answer
    assert query not in answer
    assert "확대해 해석하지 않습니다" in answer
    assert "private required fact" not in serialized
    assert "private forbidden claim" not in serialized
    assert "private-expected-id" not in serialized


def test_agent_prompt_builds_minimal_plan_from_public_runtime_context() -> None:
    adapter = OpenAICompatibleAdapter()
    configuration = SimpleNamespace(
        runtime_config_json={"prompt_bundle": {"system_prompt": "공개 컨텍스트만 사용하세요."}}
    )
    request = "incident 복구 절차를 검색한 뒤 관련 내부 문서를 조회해 주세요."
    retrieval_query = "incident 복구 절차 incident recovery runbook SLO breached sample count"
    evaluation_case = SimpleNamespace(
        external_case_id="KO-RAG-TOOL-002",
        category="agent_multi_step",
        title="runbook 검색 후 문서 Tool",
        input_payload_json={
            "request": request,
            "agent_context": {
                "step_limit": 3,
                "allowed_actions": ["retrieve", "tool", "respond"],
                "allowed_tools": ["lookup_internal_document"],
                "retrieval_query": retrieval_query,
                "retrieval_query_strategy": ("reviewed-bilingual-retrieval-query-v1"),
            },
            "available_tools": [
                {
                    "tool_name": "lookup_internal_document",
                    "argument_schema": {
                        "type": "object",
                        "required": ["document_id"],
                        "properties": {
                            "document_id": {"type": "string"},
                            "simulate_failure": {"type": "string"},
                        },
                    },
                }
            ],
        },
        expected_output_json={"required_facts": ["private expected answer"]},
        expected_tool_schema_json={"tool_name": "private_expected_tool"},
        reference_context_json={"expected_steps": ["private expected sequence"]},
    )

    prompt = adapter._system_prompt(configuration, evaluation_case)
    example = json.loads(prompt.split("그 구조를 그대로 따르세요: ", 1)[1])
    user_payload = adapter._user_message_payload(evaluation_case)

    assert [step["action"] for step in example["steps"]] == [
        "retrieve",
        "tool",
        "respond",
    ]
    assert example["steps"][0]["query"] == retrieval_query
    assert example["steps"][1] == {
        "action": "tool",
        "tool_name": "lookup_internal_document",
        "arguments": {"document_id": "model-atlas-operator-runbook"},
    }
    assert "private expected" not in prompt
    assert "args, description, step_index" in prompt
    assert user_payload["request"] == request
    assert user_payload["required_output_template"] == example
    assert user_payload["retrieval_contract"] == {
        "query": retrieval_query,
        "strategy": "reviewed-bilingual-retrieval-query-v1",
    }
    assert "agent_context" not in json.dumps(user_payload)
    assert "private expected" not in json.dumps(user_payload)


def test_reference_cli_accepts_explicit_diagnostic_cases() -> None:
    args = build_parser().parse_args(
        [
            "run",
            "--mode",
            "diagnostic",
            "--matrix",
            "reference_workload/runtime_matrix.json",
            "--case-id",
            "KO-AGENT-001",
            "--case-id",
            "KO-RAG-TOOL-001",
        ]
    )

    assert args.mode == "diagnostic"
    assert args.case_id == ["KO-AGENT-001", "KO-RAG-TOOL-001"]
