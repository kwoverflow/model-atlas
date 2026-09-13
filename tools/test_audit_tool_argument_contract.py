import copy

import pytest

from audit_tool_argument_contract import audit_saved_outputs


def saved_result():
    return {
        "schema_version": "tool-selection-challenge-result-v1",
        "entries": [
            {
                "name": "test",
                "runtime": {"digest": "test-only"},
                "rows": [
                    {
                        "id": "test",
                        "trial": 1,
                        "group": "fixture",
                        "request": "policy",
                        "expected_tool": "lookup_policy",
                        "raw_output": '{"tool_name":"lookup_policy","arguments":{}}',
                        "normalized_output": '{"tool_name":"lookup_policy","arguments":{"query":"policy"}}',
                        "raw_selection_correct": True,
                        "raw_arguments_valid": False,
                        "normalized_arguments_valid": True,
                        "normalized_execution_success": True,
                        "metadata": {
                            "tool_call_contract": {
                                "compiler_version": "bounded-tool-call-contract-v1",
                                "changed": True,
                                "filled_arguments": ["query"],
                            }
                        },
                    }
                ],
            }
        ],
    }


def test_saved_success_is_not_treated_as_new_execution_and_input_is_unchanged():
    source = saved_result()
    before = copy.deepcopy(source)
    result = audit_saved_outputs(source, document_context={})
    assert result["observation_count"] == 1
    assert result["summary"]["previous_success_now_blocked"] == 1
    assert result["summary"]["v2_execution_allowed"] == 0
    assert result["rows"][0]["v2_preserved_arguments"] == {}
    assert source == before


def test_duplicate_grain_is_rejected_instead_of_double_counted():
    source = saved_result()
    source["entries"][0]["rows"] *= 2
    with pytest.raises(ValueError, match="duplicate observation"):
        audit_saved_outputs(source, document_context={})


@pytest.mark.parametrize("mutation", ["missing_metric", "wrong_compiler"])
def test_missing_measurement_or_wrong_contract_does_not_become_zero(mutation):
    source = saved_result()
    row = source["entries"][0]["rows"][0]
    if mutation == "missing_metric":
        del row["raw_arguments_valid"]
    else:
        row["metadata"]["tool_call_contract"]["compiler_version"] = "unknown"
    with pytest.raises(ValueError):
        audit_saved_outputs(source, document_context={})
