import json
from dataclasses import replace
from uuid import uuid4

from app.models import EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult
from app.services.tool_call_contract import compile_bounded_tool_call
from app.services.tool_execution import (
    attach_tool_execution,
    build_default_tool_registry,
    execute_tool_calls,
    summarize_tool_traces,
)


def test_argument_guard_prevents_handler_execution_and_false_exact_match():
    registry = build_default_tool_registry()
    calls = []
    registered = registry.tools["lookup_internal_document"]
    registry.tools["lookup_internal_document"] = replace(
        registered,
        handler=lambda args, context: calls.append(args),
    )
    case = _case({"tool_name": "lookup_internal_document"})
    result = _adapter_result(
        {
            "tool_name": "lookup_internal_document",
            "arguments": {"document_id": "invented"},
        }
    )
    contract = compile_bounded_tool_call(
        result.raw_output,
        input_payload={
            "available_tools": [
                {
                    "tool_name": "lookup_internal_document",
                    "argument_schema": registered.descriptor.argument_schema,
                }
            ]
        },
        document_context={"corpus_hash": "test", "document_ids": ["actual-doc"]},
    )
    result = attach_tool_execution(
        case,
        replace(result, metadata={"tool_call_contract": contract.audit_record()}),
        registry,
    )
    assert calls == []
    assert result.raw_output == result.normalized_output
    assert result.exact_match is False
    assert result.tool_call_valid is False
    assert result.metadata["tool_execution"]["steps"][0]["attempt_count"] == 0
    assert result.metadata["tool_execution"]["steps"][0]["selection_valid"] is True


def test_authorized_failure_remains_a_real_retry_not_a_postprocessing_fill():
    registry = build_default_tool_registry()
    case = _case({"tool_name": "lookup_policy", "max_attempts": 2})
    result = _adapter_result(
        {
            "tool_name": "lookup_policy",
            "arguments": {"query": "policy", "simulate_failure": "transient_once"},
        }
    )
    contract = compile_bounded_tool_call(
        result.raw_output,
        input_payload={
            "available_tools": [
                {
                    "tool_name": "lookup_policy",
                    "argument_schema": registry.tools["lookup_policy"].descriptor.argument_schema,
                }
            ]
        },
        allowed_failure_mode="transient_once",
    )
    result = attach_tool_execution(
        case,
        replace(result, metadata={"tool_call_contract": contract.audit_record()}),
        registry,
    )
    assert result.exact_match is True
    assert result.retry_count == 1
    assert result.metadata["tool_execution"]["steps"][0]["recovered"] is True
    assert result.metadata["tool_call_contract"]["filled_arguments"] == []


def _case(expected_schema: dict, *, external_case_id: str = "tool-case-001") -> EvaluationCase:
    return EvaluationCase(
        evaluation_suite_id=uuid4(),
        external_case_id=external_case_id,
        category="tool_execution",
        title="Tool execution test",
        input_payload_json={"request": "check policy"},
        expected_output_json=None,
        reference_context_json=None,
        expected_tool_schema_json=expected_schema,
        tags_json=["tool"],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="local_authored",
    )


def _adapter_result(output: dict) -> AdapterCaseResult:
    serialized = json.dumps(output)
    return AdapterCaseResult(
        raw_output=serialized,
        normalized_output=serialized,
        quality_score=None,
        exact_match=None,
        json_valid=True,
        tool_call_valid=True,
        groundedness_score=None,
        faithfulness_score=None,
        human_label=None,
        error_type=None,
        ttft_ms=10,
        end_to_end_latency_ms=20,
        prompt_tokens=10,
        completion_tokens=10,
        tokens_per_second=500,
        gpu_vram_used_mb=None,
        gpu_utilization_pct=None,
        cpu_utilization_pct=None,
        peak_memory_mb=None,
        oom_occurred=False,
        retry_count=0,
    )


def _query_arguments() -> dict:
    return {
        "type": "object",
        "required": ["query"],
        "properties": {"query": {"type": "string"}},
    }


def test_executes_registered_tool_and_records_output() -> None:
    case = _case({"tool_name": "lookup_policy", "arguments": _query_arguments()})

    trace = execute_tool_calls(
        case,
        json.dumps({"tool_name": "lookup_policy", "arguments": {"query": "release"}}),
    )

    assert trace.status == "success"
    assert trace.call_valid is True
    assert trace.successful is True
    assert trace.steps[0].output["data"]["release_requires_gate"] is True
    assert trace.steps[0].attempt_count == 1


def test_wrong_tool_is_rejected_without_execution() -> None:
    case = _case({"tool_name": "lookup_policy", "arguments": _query_arguments()})

    trace = execute_tool_calls(
        case,
        json.dumps({"tool_name": "create_ticket", "arguments": {"query": "release"}}),
    )

    assert trace.status == "failed"
    assert trace.call_valid is False
    assert trace.steps[0].selection_valid is False
    assert trace.steps[0].execution_status == "skipped"
    assert trace.steps[0].attempt_count == 0


def test_invalid_arguments_are_rejected_without_execution() -> None:
    case = _case({"tool_name": "lookup_policy", "arguments": _query_arguments()})

    trace = execute_tool_calls(
        case,
        json.dumps({"tool_name": "lookup_policy", "arguments": {}}),
    )

    assert trace.call_valid is False
    assert trace.steps[0].arguments_valid is False
    assert trace.steps[0].execution_status == "skipped"
    assert "$.query is required" in trace.steps[0].validation_errors


def test_transient_failure_retries_and_recovers() -> None:
    case = _case(
        {
            "tool_name": "search_incidents",
            "arguments": _query_arguments(),
            "max_attempts": 2,
        }
    )

    trace = execute_tool_calls(
        case,
        json.dumps(
            {
                "tool_name": "search_incidents",
                "arguments": {
                    "query": "timeout",
                    "simulate_failure": "transient_once",
                },
            }
        ),
    )

    assert trace.status == "success"
    assert trace.retry_recovery_rate == 1.0
    assert trace.steps[0].attempt_count == 2
    assert trace.steps[0].retry_count == 1
    assert trace.steps[0].recovered is True
    assert trace.steps[0].attempts[0].error_type == "transient_tool_error"


def test_permanent_failure_is_not_retried() -> None:
    case = _case(
        {
            "tool_name": "search_incidents",
            "arguments": _query_arguments(),
            "max_attempts": 3,
        }
    )

    trace = execute_tool_calls(
        case,
        json.dumps(
            {
                "tool_name": "search_incidents",
                "arguments": {"query": "failure", "simulate_failure": "permanent"},
            }
        ),
    )

    assert trace.status == "failed"
    assert trace.call_valid is True
    assert trace.successful is False
    assert trace.steps[0].attempt_count == 1
    assert trace.steps[0].error_type == "permanent_tool_error"


def test_multi_step_sequence_executes_in_order() -> None:
    case = _case(
        {
            "expected_sequence": [
                {"tool_name": "lookup_customer", "arguments": _query_arguments()},
                {"tool_name": "summarize_thread", "arguments": _query_arguments()},
            ]
        },
        external_case_id="tool-multi-001",
    )

    trace = execute_tool_calls(
        case,
        json.dumps(
            {
                "tool_calls": [
                    {"tool_name": "lookup_customer", "arguments": {"query": "C-001"}},
                    {"tool_name": "summarize_thread", "arguments": {"query": "status"}},
                ]
            }
        ),
    )

    assert trace.status == "success"
    assert trace.sequence_match is True
    assert trace.actual_tool_sequence == ["lookup_customer", "summarize_thread"]
    assert trace.steps[1].output["data"]["source_step_count"] == 1


def test_openai_native_function_shape_is_normalized() -> None:
    case = _case({"tool_name": "lookup_policy", "arguments": _query_arguments()})

    trace = execute_tool_calls(
        case,
        json.dumps(
            {
                "tool_calls": [
                    {
                        "id": "call-native-1",
                        "type": "function",
                        "function": {
                            "name": "lookup_policy",
                            "arguments": json.dumps({"query": "release"}),
                        },
                    }
                ]
            }
        ),
    )

    assert trace.status == "success"
    assert trace.steps[0].call_id == "call-native-1"


def test_attachment_and_summary_preserve_trace_provenance() -> None:
    case = _case({"tool_name": "lookup_policy", "arguments": _query_arguments()})
    result = _adapter_result({"tool_name": "lookup_policy", "arguments": {"query": "release"}})

    attached = attach_tool_execution(case, result)
    trace = attached.metadata["tool_execution"]
    summary = summarize_tool_traces([trace])

    assert attached.exact_match is True
    assert attached.tool_call_valid is True
    assert attached.metadata["tool_registry"]["registry_version"] == "local-tool-registry-v1"
    assert attached.logs[-1]["event_type"] == "tool_execution_completed"
    assert summary["tool_case_count"] == 1
    assert summary["execution_success_rate"] == 1.0
