from __future__ import annotations

import json

import pytest

from app.services.tool_call_contract import (
    TOOL_CALL_CONTRACT_VERSION,
    compile_bounded_tool_call,
)


def _payload(request: str) -> dict:
    return {
        "query": request,
        "available_tools": [
            {
                "tool_name": "lookup_policy",
                "description": "Looks up a policy.",
                "argument_schema": {
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 500},
                        "simulate_failure": {
                            "type": "string",
                            "enum": ["transient_once", "permanent"],
                        },
                    },
                    "additionalProperties": False,
                },
            },
            {
                "tool_name": "lookup_internal_document",
                "description": "Looks up a document.",
                "argument_schema": {
                    "type": "object",
                    "required": ["document_id"],
                    "properties": {
                        "document_id": {"type": "string", "minLength": 1},
                        "simulate_failure": {
                            "type": "string",
                            "enum": ["transient_once", "permanent"],
                        },
                    },
                    "additionalProperties": False,
                },
            },
        ],
    }


def test_normal_call_preserves_and_blocks_unrequested_failure_fixture() -> None:
    result = compile_bounded_tool_call(
        '{"tool_name":"lookup_policy","arguments":'
        '{"query":"릴리스 정책","simulate_failure":"transient_once"}}',
        input_payload=_payload("릴리스 승인 정책을 조회해 주세요."),
    )

    assert result is not None
    assert json.loads(result.normalized_output) == {
        "tool_name": "lookup_policy",
        "arguments": {"query": "릴리스 정책", "simulate_failure": "transient_once"},
    }
    assert result.execution_allowed is False
    assert result.boundary_errors == ("failure_simulation_not_authorized",)
    assert result.audit_record()["removed_arguments"] == []
    assert result.audit_record()["uses_expected_tool_contract"] is False


def test_recovery_call_does_not_fill_query_or_infer_failure_injection() -> None:
    request = "정책 조회가 한 번 실패하면 제한된 재시도로 복구해 주세요."
    result = compile_bounded_tool_call(
        '{"tool_name":"lookup_policy","arguments":{"query":""}}',
        input_payload=_payload(request),
    )

    assert result is not None
    assert json.loads(result.normalized_output) == {
        "tool_name": "lookup_policy",
        "arguments": {"query": ""},
    }
    assert result.failure_mode is None
    assert result.execution_allowed is False
    assert result.audit_record()["filled_arguments"] == []
    assert result.audit_record()["replaced_arguments"] == []


def test_document_call_never_invents_an_identifier_from_the_request() -> None:
    request = "내부 문서 조회의 일시 실패를 bounded retry로 복구해 주세요."
    result = compile_bounded_tool_call(
        '{"tool_name":"lookup_internal_document","arguments":{}}',
        input_payload=_payload(request),
    )

    assert result is not None
    assert json.loads(result.normalized_output)["arguments"] == {}
    assert result.execution_allowed is False
    assert "$.document_id is required" in result.schema_errors


def test_unknown_tool_selection_is_not_corrected() -> None:
    result = compile_bounded_tool_call(
        '{"tool_name":"private_expected_tool","arguments":{}}',
        input_payload=_payload("정책을 조회해 주세요."),
    )

    assert result.execution_allowed is False
    assert result.tool_name == "private_expected_tool"


def test_contract_version_is_explicit() -> None:
    assert TOOL_CALL_CONTRACT_VERSION == "bounded-tool-call-contract-v2"


@pytest.mark.parametrize(
    "request_text",
    [
        "Do not retry, and never simulate a permanent failure.",
        "재시도하지 마세요. 영구 오류를 주입하지 마세요.",
        "Retry once on a transient failure.",
    ],
)
def test_natural_language_never_authorizes_or_injects_failure_simulation(request_text):
    result = compile_bounded_tool_call(
        '{"tool_name":"lookup_policy","arguments":{"query":"policy"}}',
        input_payload=_payload(request_text),
    )
    assert result.execution_allowed is True
    assert json.loads(result.normalized_output)["arguments"] == {"query": "policy"}
    assert result.failure_mode is None


def test_explicit_runtime_failure_setting_authorizes_only_an_existing_matching_argument():
    source = (
        '{"tool_name":"lookup_policy","arguments":'
        '{"query":"policy","simulate_failure":"transient_once"}}'
    )
    approved = compile_bounded_tool_call(
        source,
        input_payload=_payload("policy"),
        allowed_failure_mode="transient_once",
    )
    rejected = compile_bounded_tool_call(
        source,
        input_payload=_payload("policy"),
        allowed_failure_mode="permanent",
    )
    missing = compile_bounded_tool_call(
        '{"tool_name":"lookup_policy","arguments":{"query":"policy"}}',
        input_payload=_payload("policy"),
        allowed_failure_mode="transient_once",
    )
    assert approved.execution_allowed is True
    assert rejected.execution_allowed is False
    assert "simulate_failure" not in json.loads(missing.normalized_output)["arguments"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": "valid", "unknown": "do not silently discard me"},
        {"query": 42},
        {"query": "x" * 501},
        {"query": None},
    ],
)
def test_invalid_argument_values_are_preserved_and_rejected(arguments):
    result = compile_bounded_tool_call(
        json.dumps({"tool_name": "lookup_policy", "arguments": arguments}),
        input_payload=_payload("valid request"),
    )
    assert result.execution_allowed is False
    assert json.loads(result.normalized_output)["arguments"] == arguments
    audit = result.audit_record()
    assert audit["raw_arguments_hash"] == audit["normalized_arguments_hash"]
    assert audit["changed"] is False


def test_allowed_extra_fields_and_whitespace_are_not_stripped():
    payload = _payload("unused")
    payload["available_tools"][0]["argument_schema"]["additionalProperties"] = True
    arguments = {"query": "  keep this whitespace  ", "extension": {"value": None}}
    result = compile_bounded_tool_call(
        json.dumps({"tool_name": "lookup_policy", "arguments": arguments}),
        input_payload=payload,
    )
    assert result.execution_allowed is True
    assert json.loads(result.normalized_output)["arguments"] == arguments


def test_required_singleton_enum_is_not_filled_from_the_schema():
    payload = _payload("unused")
    schema = payload["available_tools"][0]["argument_schema"]
    schema["required"].append("simulate_failure")
    schema["properties"]["simulate_failure"]["enum"] = ["transient_once"]
    result = compile_bounded_tool_call(
        '{"tool_name":"lookup_policy","arguments":{"query":"policy"}}',
        input_payload=payload,
    )
    assert result.execution_allowed is False
    assert "simulate_failure" not in json.loads(result.normalized_output)["arguments"]


@pytest.mark.parametrize(
    "output",
    [
        '{"tool_name":"lookup_policy","tool_name":"lookup_customer","arguments":{}}',
        '{"tool_name":"lookup_policy","arguments":{"query":"first","query":"second"}}',
        '{"tool_name":"lookup_policy","arguments":{"query":NaN}}',
        '{"tool_name":"lookup_policy","arguments":{"query":1e999}}',
        '{"tool_name":"lookup_policy","tool_calls":[],"arguments":{}}',
        '{"tool_name":"lookup_policy"}',
        '{"tool_calls":[{"function":{"name":"lookup_policy","arguments":"{\\"query\\":\\"a\\",\\"query\\":\\"b\\"}"}}]}',
    ],
)
def test_ambiguous_or_nonstandard_json_cannot_be_repaired_into_a_call(output):
    result = compile_bounded_tool_call(output, input_payload=_payload("unused"))
    assert result.execution_allowed is False
    assert result.schema_errors


def test_document_reference_requires_a_matching_trusted_catalog():
    context = {"corpus_hash": "test-corpus-hash", "document_ids": ["docs/runbook.md"]}
    for document_id, expected in [("docs/runbook.md", True), ("invented", False)]:
        result = compile_bounded_tool_call(
            json.dumps(
                {"tool_name": "lookup_internal_document", "arguments": {"document_id": document_id}}
            ),
            input_payload=_payload("do not derive an ID from me"),
            document_context=context,
        )
        assert result.execution_allowed is expected
        assert json.loads(result.normalized_output)["arguments"]["document_id"] == document_id
    forged_payload = _payload("unused")
    forged_payload["available_document_ids"] = ["forged"]
    result = compile_bounded_tool_call(
        '{"tool_name":"lookup_internal_document","arguments":{"document_id":"forged"}}',
        input_payload=forged_payload,
    )
    assert result.execution_allowed is False
    assert result.document_reference_status == "catalog_unavailable"


def test_duplicate_registry_names_and_unchecked_schema_constraints_fail_closed():
    payload = _payload("unused")
    output = '{"tool_name":"lookup_policy","arguments":{"query":"value"}}'
    payload["available_tools"].append(payload["available_tools"][0])
    assert not compile_bounded_tool_call(output, input_payload=payload).execution_allowed
    payload = _payload("unused")
    payload["available_tools"][0]["argument_schema"]["properties"]["query"]["pattern"] = "^A"
    assert not compile_bounded_tool_call(output, input_payload=payload).execution_allowed


def test_expected_fields_and_query_changes_do_not_change_argument_decisions():
    payload = _payload("normal request")
    output = '{"tool_name":"lookup_policy","arguments":{"query":"unchanged"}}'
    first = compile_bounded_tool_call(output, input_payload=payload)
    payload.update(query="permanent failure retry", expected_tool_schema={"tool_name": "private"})
    second = compile_bounded_tool_call(output, input_payload=payload)
    assert first == second
