from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any

TOOL_SELECTION_PROMPT_VERSION = "public-tool-selection-prompt-v1"
SYSTEM_PROMPT = (
    "요청의 동작과 대상을 기준으로 도구 하나를 선택하세요. "
    "부수적인 주제 단어보다 요청한 작업을 우선하세요. 재시도 조건은 도구 종류를 바꾸지 않습니다. "
    "tool_name과 arguments를 포함한 JSON 객체 하나만 출력하세요. "
    "선택한 도구의 required_arguments를 채우세요."
)

# Exact source-description matching avoids replacing a custom tool's execution boundaries.
_DESCRIPTIONS_KO = {
    "Returns a deterministic local policy record.": "정책 및 승인 규칙 조회",
    "Returns a deterministic in-memory document fixture.": "내부 문서 및 운영 매뉴얼 조회",
    "Searches an in-memory incident fixture.": "장애 및 사고 이력 검색",
    "Creates a deterministic simulated ticket without external side effects.": (
        "모의 작업 티켓 생성"
    ),
    "Returns a deterministic local customer fixture.": "고객 정보 및 계약 상태 조회",
    "Summarizes local text and can consume prior tool outputs.": "대화 및 이전 도구 결과 요약",
}


@dataclass(frozen=True)
class ToolSelectionPrompt:
    user_payload: dict[str, Any]
    tool_names: tuple[str, ...]
    source_hash: str

    def response_format(self) -> dict[str, Any]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "tool_call",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string", "enum": list(self.tool_names)},
                        "arguments": {"type": "object"},
                    },
                    "required": ["tool_name", "arguments"],
                    "additionalProperties": False,
                },
            },
        }

    def audit_record(self) -> dict[str, Any]:
        return {
            "version": TOOL_SELECTION_PROMPT_VERSION,
            "source": "public_request_and_tool_registry",
            "source_hash": self.source_hash,
            "available_tool_names": list(self.tool_names),
            "uses_expected_tool_contract": False,
            "selection_overridden": False,
            "argument_validation": "tool_registry_at_execution",
        }


def build_tool_selection_prompt(input_payload: dict[str, Any]) -> ToolSelectionPrompt | None:
    request = next(
        (
            value.strip()
            for key in ("request", "query", "question")
            if isinstance(value := input_payload.get(key), str) and value.strip()
        ),
        "",
    )
    descriptors = input_payload.get("available_tools")
    if not request or not isinstance(descriptors, list) or not descriptors:
        return None
    tools = []
    names = []
    for descriptor in descriptors:
        if not isinstance(descriptor, dict):
            return None
        name = descriptor.get("tool_name")
        description = descriptor.get("description")
        schema = descriptor.get("argument_schema")
        if (
            not isinstance(name, str)
            or not name.strip()
            or name in names
            or not isinstance(description, str)
            or not isinstance(schema, dict)
            or schema.get("type") != "object"
        ):
            return None
        # Complex schemas retain the legacy presentation instead of losing schema constraints.
        if set(schema) - {"type", "required", "properties", "additionalProperties"}:
            return None
        properties = schema.get("properties")
        required = schema.get("required", [])
        if (
            not isinstance(properties, dict)
            or not all(isinstance(value, dict) for value in properties.values())
            or not isinstance(required, list)
            or any(not isinstance(key, str) or key not in properties for key in required)
            or _contains_reference(properties)
        ):
            return None
        names.append(name)
        tools.append(
            {
                "tool_name": name,
                "description": _DESCRIPTIONS_KO.get(description, description),
                "required_arguments": list(required),
                "arguments": copy.deepcopy(properties),
            }
        )
    payload: dict[str, Any] = {"request": request, "available_tools": tools}
    instruction = input_payload.get("instruction")
    if isinstance(instruction, str) and instruction.strip():
        payload["instruction"] = instruction
    source = {"request": request, "instruction": instruction, "available_tools": descriptors}
    document_ids = input_payload.get("available_document_ids")
    if isinstance(document_ids, list) and all(isinstance(value, str) for value in document_ids):
        payload["available_document_ids"] = list(document_ids)
        source["available_document_ids"] = list(document_ids)
        provenance = input_payload.get("document_catalog_provenance")
        if isinstance(provenance, dict):
            payload["document_catalog_provenance"] = copy.deepcopy(provenance)
            source["document_catalog_provenance"] = copy.deepcopy(provenance)
    digest = hashlib.sha256(
        json.dumps(source, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return ToolSelectionPrompt(payload, tuple(names), digest)


def _contains_reference(value: Any) -> bool:
    if isinstance(value, dict):
        return any(key in {"$ref", "$dynamicRef"} for key in value) or any(
            _contains_reference(item) for item in value.values()
        )
    return isinstance(value, list) and any(_contains_reference(item) for item in value)
