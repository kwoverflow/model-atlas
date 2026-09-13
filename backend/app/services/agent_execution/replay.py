from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import BenchmarkResult
from app.validators import DomainValidationError

from .approval import _approval_decisions_from_trace
from .callbacks import (
    _recorded_live_replan_callback,
    build_agent_live_replan_callback,
)
from .execution import execute_agent_plan
from .planning import prepare_agent_execution
from .semantics import (
    _diff_paths,
    _semantic_projection,
    _semantic_signature,
)


def replay_agent_result(
    db: Session,
    *,
    benchmark_result_id: UUID,
) -> dict[str, Any]:
    result = db.get(BenchmarkResult, benchmark_result_id)
    if result is None:
        raise DomainValidationError("benchmark_result was not found")
    evaluation_case = result.evaluation_case
    benchmark_run = result.benchmark_run
    configuration = benchmark_run.deployment_configuration
    if evaluation_case is None or configuration is None:
        raise DomainValidationError(
            "agent replay requires an evaluation case and deployment configuration"
        )
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    original_trace = metadata.get("agent_execution")
    if not isinstance(original_trace, dict):
        raise DomainValidationError("benchmark result does not contain an agent trace")
    if not result.normalized_output:
        raise DomainValidationError("benchmark result does not contain a replayable plan")
    run_runtime_config = (
        benchmark_run.runtime_config_json
        if isinstance(benchmark_run.runtime_config_json, dict)
        else {}
    )
    approval_decisions = _approval_decisions_from_trace(original_trace)
    if not approval_decisions:
        approval_decisions = run_runtime_config.get("agent_approval_decisions")
    preparation = prepare_agent_execution(
        configuration,
        evaluation_case,
        include_mock_plan=False,
        approval_decisions=(approval_decisions if isinstance(approval_decisions, dict) else None),
    )
    if preparation is None:
        raise DomainValidationError("evaluation case is not an agent case")
    replay_trace = execute_agent_plan(
        evaluation_case,
        result.normalized_output,
        preparation,
        live_replan_callback=(
            _recorded_live_replan_callback(original_trace)
            or build_agent_live_replan_callback(
                evaluation_case,
                mode=str(run_runtime_config.get("agent_live_replan_mode") or "disabled"),
            )
        ),
    ).to_dict()
    original_projection = _semantic_projection(original_trace)
    replay_projection = _semantic_projection(replay_trace)
    original_signature = _semantic_signature(original_projection)
    replay_signature = _semantic_signature(replay_projection)
    version_keys = [
        "schema_version",
        "context_version",
        "runtime_version",
        "observation_schema_version",
        "recovery_policy_version",
        "approval_policy_version",
        "memory_registry_version",
        "tool_registry_version",
        "corpus_version",
        "retriever_version",
    ]
    version_compatible = all(
        original_trace.get(key) == replay_trace.get(key) for key in version_keys
    )
    return {
        "benchmark_result_id": result.id,
        "benchmark_run_id": benchmark_run.id,
        "evaluation_case_id": evaluation_case.id,
        "version_compatible": version_compatible,
        "deterministic_match": (version_compatible and original_signature == replay_signature),
        "original_signature": original_signature,
        "replay_signature": replay_signature,
        "changed_paths": _diff_paths(original_projection, replay_projection),
        "original_trace": original_trace,
        "replay_trace": replay_trace,
    }
