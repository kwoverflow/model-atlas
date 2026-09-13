from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.tool_selection_prompt import build_tool_selection_prompt


def _configuration():
    return SimpleNamespace(
        runtime_config_json={
            "tool_selection_prompt": "public-tool-selection-prompt-v1",
        }
    )


def _payload():
    return {
        "query": "Find the incident response document, not the incident history.",
        "instruction": "Read only. Do not create a ticket.",
        "available_tools": [
            {
                "tool_name": name,
                "description": description,
                "argument_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "maxLength": 100}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            }
            for name, description in [
                ("new_document_reader", "Reads documents from an isolated test store."),
                ("new_incident_search", "Reads incident history; never writes."),
            ]
        ],
        "_execution_trial": 3,
        "_case_timeout_ms": 1000,
        "expected_tool_schema": {"tool_name": "PRIVATE_EXPECTED_TOOL"},
    }


def _case(payload):
    return SimpleNamespace(
        category="tool_single_step",
        external_case_id="PRIVATE_CASE_ID",
        title="PRIVATE_TITLE",
        expected_tool_schema_json={"tool_name": "PRIVATE_EXPECTED_TOOL"},
        expected_output_json={"answer": "PRIVATE_ANSWER"},
        reference_context_json={"expected": "PRIVATE_CONTEXT"},
        input_payload_json=payload,
    )


def test_public_projection_preserves_instructions_and_new_tools_without_private_fields():
    payload = _payload()
    original = copy.deepcopy(payload)
    contract = build_tool_selection_prompt(payload)
    assert contract is not None
    assert payload == original
    assert contract.user_payload["instruction"] == payload["instruction"]
    assert contract.user_payload["request"] == payload["query"]
    assert contract.tool_names == ("new_document_reader", "new_incident_search")
    encoded = json.dumps(contract.user_payload)
    assert "PRIVATE" not in encoded
    assert "_execution_trial" not in encoded
    assert "_case_timeout_ms" not in encoded
    assert contract.user_payload["available_tools"][1]["description"].endswith("never writes.")
    contract.user_payload["available_tools"][0]["arguments"]["query"]["maxLength"] = 1
    assert payload == original


def test_contract_preserves_candidate_order_and_does_not_select_from_query_keywords():
    payload = _payload()
    first = build_tool_selection_prompt(payload)
    payload["available_tools"].reverse()
    second = build_tool_selection_prompt(payload)
    assert first is not None and second is not None
    assert second.tool_names == tuple(reversed(first.tool_names))
    assert first.source_hash != second.source_hash
    schema = second.response_format()["json_schema"]["schema"]
    assert schema["properties"]["tool_name"]["enum"] == list(second.tool_names)
    assert schema["required"] == ["tool_name", "arguments"]
    assert second.audit_record()["selection_overridden"] is False


def test_private_labels_do_not_affect_prompts_or_hashes():
    adapter = OpenAICompatibleAdapter()
    case = _case(_payload())
    configuration = _configuration()
    configuration.runtime_config_json["prompt_bundle"] = {
        "system_prompt": "KEEP THIS OPERATOR INSTRUCTION",
    }
    before = (
        adapter._system_prompt(configuration, case),
        adapter._user_message_payload(case, configuration=configuration),
        adapter._response_format(case, configuration=configuration),
        adapter._tool_selection_prompt(case, configuration).source_hash,
    )
    case.external_case_id = "OTHER_ID"
    case.title = "OTHER_TITLE"
    case.expected_tool_schema_json = {"tool_name": "OTHER_TOOL", "example_arguments": {"secret": 1}}
    case.expected_output_json = {"answer": "OTHER_ANSWER"}
    case.reference_context_json = {"private": "OTHER_CONTEXT"}
    case.input_payload_json["expected_tool_schema"] = {"tool_name": "OTHER_TOOL"}
    after = (
        adapter._system_prompt(configuration, case),
        adapter._user_message_payload(case, configuration=configuration),
        adapter._response_format(case, configuration=configuration),
        adapter._tool_selection_prompt(case, configuration).source_hash,
    )
    assert before == after
    assert before[0].startswith("KEEP THIS OPERATOR INSTRUCTION\n\n")
    assert "PRIVATE" not in json.dumps(before)


@pytest.mark.parametrize("mutation", ["empty", "duplicate", "bad_required", "reference", "complex"])
def test_unsupported_descriptors_retain_legacy_presentation(mutation):
    payload = _payload()
    if mutation == "empty":
        payload["available_tools"] = []
    elif mutation == "duplicate":
        payload["available_tools"].append(copy.deepcopy(payload["available_tools"][0]))
    else:
        schema = payload["available_tools"][0]["argument_schema"]
        if mutation == "bad_required":
            schema["required"] = ["missing"]
        elif mutation == "reference":
            schema["properties"]["query"] = {"$ref": "#/$defs/query"}
        else:
            schema["oneOf"] = [{"required": ["query"]}]
    assert build_tool_selection_prompt(payload) is None
    assert OpenAICompatibleAdapter()._response_format(
        _case(payload), configuration=_configuration()
    ) == {"type": "json_object"}


@pytest.mark.parametrize("context", ["agent", "rag", "multi_step", "legacy", "text"])
def test_contract_does_not_change_other_execution_paths(context):
    case = _case(_payload())
    if context in {"agent", "rag"}:
        case.input_payload_json[f"{context}_context"] = {}
    elif context == "multi_step":
        case.expected_tool_schema_json["expected_sequence"] = [
            {"tool_name": "a"},
            {"tool_name": "b"},
        ]
    elif context == "legacy":
        case.category = "legacy_tool_call"
    else:
        case.expected_tool_schema_json = None
    assert OpenAICompatibleAdapter()._tool_selection_prompt(case, _configuration()) is None


@pytest.mark.parametrize("mode", [None, "legacy"])
def test_experimental_selection_is_opt_in_and_default_stays_legacy(mode):
    case = _case(_payload())
    configuration = SimpleNamespace(runtime_config_json={"tool_selection_prompt": mode})
    adapter = OpenAICompatibleAdapter()
    assert adapter._tool_selection_prompt(case, configuration) is None
    assert adapter._response_format(case, configuration=configuration) == {"type": "json_object"}
    assert (
        adapter._user_message_payload(case, configuration=configuration)["input"]
        == case.input_payload_json
    )


def test_unknown_prompt_mode_is_rejected():
    configuration = SimpleNamespace(runtime_config_json={"tool_selection_prompt": "typo"})
    with pytest.raises(ValueError, match="unsupported tool_selection_prompt"):
        OpenAICompatibleAdapter()._tool_selection_prompt(_case(_payload()), configuration)


def test_custom_description_is_never_replaced_just_because_tool_name_matches():
    payload = _payload()
    payload["available_tools"][0]["tool_name"] = "lookup_customer"
    payload["available_tools"][0]["description"] = "Returns redacted data only. No contract access."
    contract = build_tool_selection_prompt(payload)
    assert contract is not None
    assert contract.user_payload["available_tools"][0]["description"].endswith(
        "No contract access."
    )
