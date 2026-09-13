from __future__ import annotations

import json

from pytest import MonkeyPatch

from app.models import DeploymentConfiguration, EvaluationCase
from app.services.agent_execution import (
    DEFAULT_OPERATIONAL_MEMORY_REGISTRY,
    AgentLiveReplanRequest,
    _semantic_projection,
    _semantic_signature,
    attach_agent_execution,
    build_agent_live_replan_callback,
    execute_agent_plan,
    prepare_agent_execution,
    summarize_agent_traces,
)
from app.services.inference_adapters.base import AdapterCaseResult
from app.services.tool_execution import attach_tool_execution


def _configuration() -> DeploymentConfiguration:
    return DeploymentConfiguration(
        retrieval_config_json={
            "corpus_id": "model-atlas-ops-handbook",
            "top_k": 3,
            "min_score": 0.05,
        }
    )


def _case(*, max_steps: int = 4) -> EvaluationCase:
    plan = {
        "steps": [
            {"action": "memory_read", "memory_id": "memory-release-guardrails"},
            {
                "action": "retrieve",
                "query": "approved deployment gate verified evidence release",
            },
            {
                "action": "tool",
                "tool_name": "lookup_policy",
                "arguments": {"query": "release approval policy"},
            },
            {
                "action": "respond",
                "content": "Release requires an approved deployment gate and verified evidence.",
                "citations": ["ops-release-001"],
            },
        ]
    }
    return EvaluationCase(
        external_case_id="agent-001",
        category="bounded_agent_task",
        title="Verify a release request",
        input_payload_json={
            "request": "Verify whether this release can proceed.",
            "mock_agent_plan": plan,
        },
        reference_context_json={
            "agent": {
                "max_steps": max_steps,
                "allowed_actions": ["memory_read", "retrieve", "tool", "respond"],
                "allowed_memory_ids": ["memory-release-guardrails"],
                "allowed_tools": ["lookup_policy"],
                "expected_steps": [
                    {
                        "action": "memory_read",
                        "memory_id": "memory-release-guardrails",
                    },
                    {
                        "action": "retrieve",
                        "relevant_chunk_ids": ["ops-release-001"],
                    },
                    {
                        "action": "tool",
                        "tool_name": "lookup_policy",
                        "arguments": {
                            "type": "object",
                            "required": ["query"],
                            "properties": {"query": {"type": "string"}},
                        },
                    },
                    {
                        "action": "respond",
                        "required_terms": ["approved deployment gate", "verified evidence"],
                    },
                ],
            }
        },
        tags_json=["agent", "bounded"],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="local_authored",
    )


def _result(output: dict) -> AdapterCaseResult:
    normalized = json.dumps(output)
    return AdapterCaseResult(
        raw_output=normalized,
        normalized_output=normalized,
        quality_score=None,
        exact_match=None,
        json_valid=True,
        tool_call_valid=False,
        groundedness_score=None,
        faithfulness_score=None,
        human_label="captured-needs-scoring",
        error_type=None,
        ttft_ms=100.0,
        end_to_end_latency_ms=700.0,
        prompt_tokens=300,
        completion_tokens=120,
        tokens_per_second=170.0,
        gpu_vram_used_mb=8_000.0,
        gpu_utilization_pct=50.0,
        cpu_utilization_pct=20.0,
        peak_memory_mb=18_000.0,
        oom_occurred=False,
        retry_count=0,
        metadata={},
    )


def test_agent_preparation_sanitizes_ground_truth_and_real_adapter_fixture() -> None:
    evaluation_case = _case()

    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=False,
    )

    assert preparation is not None
    assert "mock_agent_plan" not in preparation.adapter_input_payload
    assert "expected_steps" not in json.dumps(preparation.adapter_reference_context)
    assert preparation.agent_context["step_limit"] == 4
    assert preparation.agent_context["memory_registry_version"] == (
        "operational-memory-registry-v1"
    )


def test_agent_executes_memory_retrieval_tool_and_response() -> None:
    evaluation_case = _case()
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None
    plan = evaluation_case.input_payload_json["mock_agent_plan"]

    trace = execute_agent_plan(
        evaluation_case,
        json.dumps(plan),
        preparation,
    )

    assert trace.schema_version == "agent-execution-trace-v2"
    assert trace.status == "success"
    assert trace.successful is True
    assert trace.sequence_match is True
    assert trace.step_success_rate == 1.0
    assert trace.memory_provenance_count == 1
    assert trace.steps[1]["output"]["retrieval"]["schema_version"] == (
        "rag-retrieval-trace-v3"
    )
    assert trace.steps[1]["output"]["retrieval"]["retrieval_recall"] == 1.0
    assert trace.steps[2]["output"]["tool_execution"]["execution_status"] == "success"
    assert _semantic_signature(_semantic_projection(trace.to_dict())) == (
        "64870e22a23982b670389f2c29fdba2dacc30d6ffc1910172b978f8eb5a979bb"
    )


def test_agent_limit_violation_prevents_step_execution() -> None:
    evaluation_case = _case(max_steps=3)
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None

    trace = execute_agent_plan(
        evaluation_case,
        json.dumps(evaluation_case.input_payload_json["mock_agent_plan"]),
        preparation,
    )

    assert trace.status == "limit_exceeded"
    assert trace.successful is False
    assert trace.policy_violation_count == 1
    assert trace.steps == []


def test_agent_tool_retry_recovery_is_preserved() -> None:
    evaluation_case = _case()
    evaluation_case.reference_context_json = {
        "agent": {
            "max_steps": 2,
            "allowed_actions": ["tool", "respond"],
            "allowed_tools": ["search_incidents"],
            "expected_steps": [
                {
                    "action": "tool",
                    "tool_name": "search_incidents",
                    "arguments": {
                        "type": "object",
                        "required": ["query", "simulate_failure"],
                        "properties": {
                            "query": {"type": "string"},
                            "simulate_failure": {
                                "type": "string",
                                "enum": ["transient_once"],
                            },
                        },
                    },
                    "max_attempts": 2,
                },
                {"action": "respond", "required_terms": ["recovered"]},
            ],
        }
    }
    plan = {
        "steps": [
            {
                "action": "tool",
                "tool_name": "search_incidents",
                "arguments": {
                    "query": "runtime timeout",
                    "simulate_failure": "transient_once",
                },
            },
            {"action": "respond", "content": "The incident search recovered."},
        ]
    }
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None

    trace = execute_agent_plan(evaluation_case, json.dumps(plan), preparation)

    assert trace.successful is True
    assert trace.retried_tool_count == 1
    assert trace.recovered_tool_count == 1
    assert trace.steps[0]["retry_count"] == 1
    assert trace.steps[0]["recovered"] is True


def test_agent_attachment_and_summary_preserve_evidence() -> None:
    evaluation_case = _case()
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None
    plan = evaluation_case.input_payload_json["mock_agent_plan"]

    attached = attach_agent_execution(
        evaluation_case,
        _result(plan),
        preparation,
    )
    trace = attached.metadata["agent_execution"]
    summary = summarize_agent_traces([trace])

    assert attached.exact_match is True
    assert attached.error_type is None
    assert summary["agent_case_count"] == 1
    assert summary["task_success_rate"] == 1.0
    assert summary["plan_validity_rate"] == 1.0
    assert summary["memory_provenance_rate"] == 1.0
    assert summary["trace_versions"] == ["agent-execution-trace-v2"]
    registry = DEFAULT_OPERATIONAL_MEMORY_REGISTRY.descriptor()
    assert registry["record_count"] == 4
    assert all(record["content_hash"] for record in registry["records"])


def test_agent_tool_plan_is_not_reexecuted_as_standalone_tool_output() -> None:
    evaluation_case = _case()
    evaluation_case.category = "rag_tool_combined"
    evaluation_case.expected_tool_schema_json = {
        "tool_name": "lookup_policy",
        "arguments": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
    }
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None
    attached = attach_agent_execution(
        evaluation_case,
        _result(evaluation_case.input_payload_json["mock_agent_plan"]),
        preparation,
    )

    after_tool_stage = attach_tool_execution(evaluation_case, attached)

    assert after_tool_stage is attached
    assert after_tool_stage.error_type is None
    assert after_tool_stage.exact_match is True
    assert "tool_execution" not in after_tool_stage.metadata


def test_simple_agent_contract_compiles_allowed_tool_intent_with_audit_record() -> None:
    evaluation_case = EvaluationCase(
        external_case_id="agent-compiler-001",
        category="rag_tool_combined",
        title="Compile a bounded release lookup",
        input_payload_json={
            "request": "Check the release evidence.",
        },
        reference_context_json={
            "agent": {
                "max_steps": 3,
                "max_retrievals": 1,
                "max_tool_calls": 1,
                "allowed_actions": ["retrieve", "tool", "respond"],
                "allowed_tools": ["lookup_policy"],
                "expected_steps": [
                    {"action": "retrieve", "relevant_chunk_ids": ["ops-release-001"]},
                    {
                        "action": "tool",
                        "tool_name": "lookup_policy",
                        "arguments": {
                            "type": "object",
                            "required": ["query"],
                            "properties": {"query": {"type": "string"}},
                            "additionalProperties": False,
                        },
                    },
                    {
                        "action": "respond",
                        "required_terms": ["retrieve 후 lookup_policy"],
                    },
                ],
            },
            "rag": {
                "query": "approved deployment gate verified evidence release",
                "query_strategy": "reviewed-bilingual-retrieval-query-v1",
                "relevant_chunk_ids": ["ops-release-001"],
            },
        },
        expected_tool_schema_json={
            "tool_name": "lookup_policy",
            "arguments": {
                "type": "object",
                "required": ["query"],
                "properties": {"query": {"type": "string"}},
                "additionalProperties": False,
            },
        },
        tags_json=["agent", "compiler"],
        criticality="critical",
        weight=1.0,
        is_active=True,
        data_source="local_authored",
    )
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=False,
    )
    assert preparation is not None
    assert preparation.agent_context["retrieval_query"] == (
        "approved deployment gate verified evidence release"
    )
    assert "relevant_chunk_ids" not in json.dumps(preparation.agent_context)
    source_plan = {
        "steps": [
            {
                "action": "tool",
                "tool_name": "lookup_policy",
                "arguments": {
                    "query": "approved deployment gate verified evidence release",
                    "simulate_failure": "permanent",
                },
            },
            {"action": "respond", "content": "retrieve 후 lookup_policy 실행"},
        ]
    }

    attached = attach_agent_execution(
        evaluation_case,
        _result(source_plan),
        preparation,
    )
    compiled = json.loads(attached.normalized_output)
    compilation = attached.metadata["agent_plan_compilation"]

    assert attached.raw_output == json.dumps(source_plan)
    assert attached.exact_match is True
    assert attached.error_type is None
    assert [step["action"] for step in compiled["steps"]] == [
        "retrieve",
        "tool",
        "respond",
    ]
    assert compiled["steps"][1]["arguments"] == {
        "query": "approved deployment gate verified evidence release"
    }
    assert compiled["steps"][0]["query"] == ("approved deployment gate verified evidence release")
    assert compilation["applied"] is True
    assert compilation["inserted_actions"] == ["retrieve"]
    assert compilation["reordered"] is True
    assert compilation["retrieval_query_source"] == "public_contract"
    assert compilation["uses_expected_steps"] is False
    assert attached.logs[0]["event_type"] == "agent_plan_compiled"


def _approval_case() -> EvaluationCase:
    evaluation_case = _case(max_steps=3)
    evaluation_case.external_case_id = "agent-approval-001"
    evaluation_case.reference_context_json = {
        "agent": {
            "max_steps": 3,
            "max_approval_checkpoints": 1,
            "allowed_actions": ["approval_checkpoint", "tool", "respond"],
            "allowed_checkpoint_ids": ["release-change"],
            "allowed_tools": ["lookup_policy"],
            "expected_steps": [
                {
                    "action": "approval_checkpoint",
                    "checkpoint_id": "release-change",
                },
                {
                    "action": "tool",
                    "tool_name": "lookup_policy",
                    "requires_approval": "release-change",
                    "arguments": {
                        "type": "object",
                        "required": ["query"],
                        "properties": {"query": {"type": "string"}},
                    },
                },
                {"action": "respond", "required_terms": ["approved"]},
            ],
        }
    }
    evaluation_case.input_payload_json = {
        "request": "Apply a release policy change.",
        "mock_agent_plan": {
            "steps": [
                {
                    "action": "approval_checkpoint",
                    "checkpoint_id": "release-change",
                    "reason": "Production policy mutation",
                },
                {
                    "action": "tool",
                    "tool_name": "lookup_policy",
                    "arguments": {"query": "release approval policy"},
                    "requires_approval": "release-change",
                },
                {"action": "respond", "content": "The change was approved."},
            ]
        },
    }
    return evaluation_case


def test_agent_approval_checkpoint_enforces_guarded_action() -> None:
    evaluation_case = _approval_case()
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
        approval_decisions={
            "release-change": {
                "decision": "approved",
                "decided_by": "release-manager",
                "reason": "Change ticket CAB-204 is approved.",
            }
        },
    )
    assert preparation is not None

    trace = execute_agent_plan(
        evaluation_case,
        json.dumps(evaluation_case.input_payload_json["mock_agent_plan"]),
        preparation,
    )

    assert trace.successful is True
    assert trace.approval_checkpoint_count == 1
    assert trace.approved_checkpoint_count == 1
    assert trace.approval_provenance_count == 1
    approval_output = trace.steps[0]["output"]
    assert approval_output["decided_by"] == "release-manager"
    assert len(approval_output["decision_hash"]) == 64
    assert trace.steps[1]["observation"]["schema_version"] == "agent-observation-v1"


def test_agent_contract_rejects_omitted_guard_reference() -> None:
    evaluation_case = _approval_case()
    plan = json.loads(json.dumps(evaluation_case.input_payload_json["mock_agent_plan"]))
    del plan["steps"][1]["requires_approval"]
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
        approval_decisions={
            "release-change": {
                "decision": "approved",
                "decided_by": "release-manager",
                "reason": "The contract still requires an explicit guard reference.",
            }
        },
    )
    assert preparation is not None

    trace = execute_agent_plan(evaluation_case, json.dumps(plan), preparation)

    assert trace.successful is False
    assert trace.halt_reason == "policy_violation"
    assert trace.approved_checkpoint_count == 1
    assert trace.steps[1]["status"] == "policy_violation"
    assert "must declare checkpoint" in trace.steps[1]["error_message"]


def test_agent_pending_and_denied_approval_halt_before_guarded_action() -> None:
    evaluation_case = _approval_case()
    plan = json.dumps(evaluation_case.input_payload_json["mock_agent_plan"])
    pending_preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert pending_preparation is not None

    pending = execute_agent_plan(evaluation_case, plan, pending_preparation)

    assert pending.status == "pending_approval"
    assert pending.halt_reason == "approval_pending"
    assert pending.pending_checkpoint_count == 1
    assert pending.step_count == 1

    denied_preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
        approval_decisions={
            "release-change": {
                "decision": "denied",
                "decided_by": "release-manager",
                "reason": "The maintenance window is closed.",
            }
        },
    )
    assert denied_preparation is not None

    denied = execute_agent_plan(evaluation_case, plan, denied_preparation)

    assert denied.status == "approval_denied"
    assert denied.halt_reason == "approval_denied"
    assert denied.denied_checkpoint_count == 1
    assert denied.step_count == 1
    assert denied.approval_provenance_count == 1


def test_agent_cannot_bypass_required_approval() -> None:
    evaluation_case = _approval_case()
    plan = {
        "steps": [
            {
                "action": "tool",
                "tool_name": "lookup_policy",
                "arguments": {"query": "release approval policy"},
                "requires_approval": "release-change",
            },
            {"action": "respond", "content": "The change was approved."},
        ]
    }
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
        approval_decisions={
            "release-change": {
                "decision": "approved",
                "decided_by": "release-manager",
                "reason": "This decision cannot replace the checkpoint step.",
            }
        },
    )
    assert preparation is not None

    trace = execute_agent_plan(evaluation_case, json.dumps(plan), preparation)

    assert trace.successful is False
    assert trace.halt_reason == "policy_violation"
    assert trace.policy_violation_count >= 1
    assert trace.step_count == 1
    assert trace.steps[0]["status"] == "policy_violation"


def test_agent_observation_driven_replan_recovers_permanent_failure() -> None:
    evaluation_case = _case(max_steps=2)
    evaluation_case.external_case_id = "agent-replan-001"
    evaluation_case.reference_context_json = {
        "agent": {
            "max_steps": 2,
            "allow_replanning": True,
            "max_replans": 1,
            "max_recovery_steps": 1,
            "max_tool_calls": 2,
            "allowed_actions": ["tool", "respond"],
            "allowed_tools": ["search_incidents", "lookup_policy"],
            "expected_steps": [
                {
                    "action": "tool",
                    "tool_name": "search_incidents",
                    "arguments": {
                        "type": "object",
                        "required": ["query", "simulate_failure"],
                        "properties": {
                            "query": {"type": "string"},
                            "simulate_failure": {
                                "type": "string",
                                "enum": ["permanent"],
                            },
                        },
                    },
                    "max_attempts": 1,
                },
                {"action": "respond", "required_terms": ["recovered"]},
            ],
            "expected_recovery_plans": [
                {
                    "trigger_step_index": 0,
                    "steps": [
                        {
                            "action": "tool",
                            "tool_name": "lookup_policy",
                            "arguments": {
                                "type": "object",
                                "required": ["query"],
                                "properties": {"query": {"type": "string"}},
                            },
                        }
                    ],
                }
            ],
        }
    }
    plan = {
        "steps": [
            {
                "action": "tool",
                "tool_name": "search_incidents",
                "arguments": {
                    "query": "release timeout",
                    "simulate_failure": "permanent",
                },
            },
            {"action": "respond", "content": "The fallback recovered the request."},
        ],
        "recovery_plans": [
            {
                "trigger_step_index": 0,
                "on_error_types": ["permanent_tool_error"],
                "strategy": "fallback_tool",
                "steps": [
                    {
                        "action": "tool",
                        "tool_name": "lookup_policy",
                        "arguments": {"query": "release timeout fallback policy"},
                    }
                ],
            }
        ],
    }
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None

    trace = execute_agent_plan(evaluation_case, json.dumps(plan), preparation)

    assert trace.successful is True
    assert trace.replan_count == 1
    assert trace.successful_replan_count == 1
    assert trace.recovery_step_count == 1
    assert trace.successful_recovery_step_count == 1
    assert trace.unrecovered_failure_count == 0
    assert trace.steps[0]["recovered_by_replan"] is True
    assert trace.steps[1]["phase"] == "recovery"
    assert trace.replans[0]["observation"]["error_type"] == "permanent_tool_error"


def test_agent_recovery_branch_cannot_exceed_recovery_step_limit() -> None:
    evaluation_case = _case(max_steps=2)
    evaluation_case.reference_context_json = {
        "agent": {
            "max_steps": 2,
            "allow_replanning": True,
            "max_replans": 1,
            "max_recovery_steps": 1,
            "allowed_actions": ["tool", "respond"],
            "allowed_tools": ["search_incidents", "lookup_policy"],
            "expected_steps": [
                {"action": "tool"},
                {"action": "respond"},
            ],
        }
    }
    plan = {
        "steps": [
            {
                "action": "tool",
                "tool_name": "search_incidents",
                "arguments": {"query": "failure", "simulate_failure": "permanent"},
            },
            {"action": "respond", "content": "done"},
        ],
        "recovery_plans": [
            {
                "trigger_step_index": 0,
                "steps": [
                    {
                        "action": "tool",
                        "tool_name": "lookup_policy",
                        "arguments": {"query": "fallback"},
                    },
                    {"action": "respond", "content": "fallback response"},
                ],
            }
        ],
    }
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None

    trace = execute_agent_plan(evaluation_case, json.dumps(plan), preparation)

    assert trace.status == "limit_exceeded"
    assert trace.successful is False
    assert trace.step_count == 0
    assert trace.halt_reason == "policy_violation"


def test_agent_rejects_ambiguous_recovery_triggers() -> None:
    evaluation_case = _case(max_steps=2)
    evaluation_case.reference_context_json = {
        "agent": {
            "max_steps": 2,
            "allow_replanning": True,
            "max_replans": 1,
            "max_recovery_steps": 1,
            "allowed_actions": ["tool", "respond"],
            "allowed_tools": ["search_incidents", "lookup_policy"],
            "expected_steps": [
                {"action": "tool"},
                {"action": "respond"},
            ],
        }
    }
    recovery_step = {
        "action": "tool",
        "tool_name": "lookup_policy",
        "arguments": {"query": "fallback"},
    }
    plan = {
        "steps": [
            {
                "action": "tool",
                "tool_name": "search_incidents",
                "arguments": {"query": "failure", "simulate_failure": "permanent"},
            },
            {"action": "respond", "content": "done"},
        ],
        "recovery_plans": [
            {
                "trigger_step_index": 0,
                "on_error_types": ["permanent_tool_error"],
                "steps": [recovery_step],
            },
            {
                "trigger_step_index": 0,
                "on_error_types": ["permanent_tool_error"],
                "steps": [recovery_step],
            },
        ],
    }
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    assert preparation is not None

    trace = execute_agent_plan(evaluation_case, json.dumps(plan), preparation)

    assert trace.successful is False
    assert trace.status == "failed"
    assert trace.step_count == 0
    assert trace.parse_error == "recovery plans contain overlapping triggers"


def test_agent_live_replan_callback_is_one_shot_bounded_and_metered() -> None:
    evaluation_case = _case(max_steps=2)
    evaluation_case.reference_context_json = {
        "agent": {
            "max_steps": 2,
            "allow_replanning": True,
            "allow_live_replanning": True,
            "max_replans": 1,
            "max_recovery_steps": 1,
            "allowed_actions": ["tool", "respond"],
            "allowed_tools": ["search_incidents", "lookup_policy"],
            "expected_steps": [
                {"action": "tool"},
                {"action": "respond", "required_terms": ["recovered"]},
            ],
            "expected_recovery_plans": [
                {
                    "trigger_step_index": 0,
                    "steps": [
                        {
                            "action": "tool",
                            "tool_name": "lookup_policy",
                            "arguments": {
                                "type": "object",
                                "required": ["query"],
                                "properties": {"query": {"type": "string"}},
                            },
                        }
                    ],
                }
            ],
        }
    }
    evaluation_case.input_payload_json = {
        "request": "Recover a failed incident lookup.",
        "mock_agent_live_replan": {
            "trigger_step_index": 0,
            "trigger_error_type": "permanent_tool_error",
            "steps": [
                {
                    "action": "tool",
                    "tool_name": "lookup_policy",
                    "arguments": {"query": "incident fallback policy"},
                }
            ],
            "provider_id": "fixture-replanner",
            "provider_version": "fixture-replanner-v1",
            "model_name": "fixture-model-1",
            "prompt_tokens": 120,
            "completion_tokens": 24,
            "model_call_latency_ms": 321.5,
            "estimated_cost_usd": 0.00125,
        },
    }
    plan = {
        "steps": [
            {
                "action": "tool",
                "tool_name": "search_incidents",
                "arguments": {
                    "query": "incident 500",
                    "simulate_failure": "permanent",
                },
            },
            {"action": "respond", "content": "The live fallback recovered the request."},
        ]
    }
    preparation = prepare_agent_execution(
        _configuration(),
        evaluation_case,
        include_mock_plan=True,
    )
    callback = build_agent_live_replan_callback(
        evaluation_case,
        mode="mock_fixture",
    )
    assert preparation is not None
    assert callback is not None

    trace = execute_agent_plan(
        evaluation_case,
        json.dumps(plan),
        preparation,
        live_replan_callback=callback,
    )

    assert trace.successful is True
    assert trace.replan_count == 1
    assert trace.live_replan_count == 1
    assert trace.live_replan_model_call_count == 1
    assert trace.live_replan_prompt_tokens == 120
    assert trace.live_replan_completion_tokens == 24
    assert trace.live_replan_latency_ms == 321.5
    assert trace.live_replan_estimated_cost_usd == 0.00125
    assert trace.total_duration_ms >= 321.5
    assert trace.replans[0]["source"] == "live_callback"
    assert trace.replans[0]["model_call"]["model_name"] == "fixture-model-1"
    assert len(trace.replans[0]["model_call"]["response_hash"]) == 64
    assert trace.steps[0]["recovered_by_replan"] is True

    summary = summarize_agent_traces([trace.to_dict()])
    assert summary["live_replan_model_call_count"] == 1
    assert summary["live_replan_prompt_tokens"] == 120
    assert summary["live_replan_estimated_cost_usd"] == 0.00125


def test_openai_compatible_live_replan_provider_is_strict_metered_and_one_shot(
    monkeypatch: MonkeyPatch,
) -> None:
    payload = {
        "model": "replan-model-v1",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "steps": [
                                {
                                    "action": "tool",
                                    "tool_name": "lookup_policy",
                                    "arguments": {"query": "fallback policy"},
                                }
                            ]
                        }
                    )
                }
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 40},
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(request, timeout):
        assert request.full_url == "http://replanner.pytest/v1/chat/completions"
        assert timeout == 9.0
        return FakeResponse()

    monkeypatch.setattr(
        "app.services.agent_live_replan_provider.urlopen",
        fake_urlopen,
    )
    callback = build_agent_live_replan_callback(
        _case(max_steps=2),
        mode="openai_compatible",
        provider_config={
            "agent_replan_base_url": "http://replanner.pytest",
            "agent_replan_model": "replan-model-v1",
            "agent_replan_timeout_seconds": 9,
            "agent_replan_input_cost_per_million": 2.0,
            "agent_replan_output_cost_per_million": 8.0,
        },
    )
    assert callback is not None
    request = AgentLiveReplanRequest(
        schema_version="agent-live-replan-callback-v1",
        external_case_id="agent-provider-001",
        trigger_step_index=0,
        trigger_error_type="permanent_tool_error",
        observation=None,
        expected_recovery_steps=[{"action": "tool"}],
        prior_outputs=[],
        recovery_step_limit=1,
    )
    response = callback(request)
    assert response is not None
    assert response.provider_id == "openai_compatible"
    assert response.provider_version == "openai-compatible-live-replan-v1"
    assert response.prompt_tokens == 200
    assert response.completion_tokens == 40
    assert response.estimated_cost_usd == 0.00072
    assert response.steps[0]["tool_name"] == "lookup_policy"
    assert callback(request) is None
