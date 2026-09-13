from __future__ import annotations

import copy
import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkExecutionLog,
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    InferenceMetric,
    PromptVersion,
)
from app.schemas import BenchmarkExecutionCreate
from app.services.agent_control_plane import (
    AGENT_CONTROL_LINK_VERSION,
    materialize_pending_agent_checkpoints,
)
from app.services.agent_execution import (
    AGENT_EXECUTION_TRACE_VERSION,
    DEFAULT_OPERATIONAL_MEMORY_REGISTRY,
    AgentPreparation,
    agent_runtime_descriptor,
    attach_agent_execution,
    build_agent_live_replan_callback,
    is_agent_case,
    prepare_agent_execution,
    summarize_agent_traces,
)
from app.services.deployment_gate.staleness import mark_scope_gates_stale
from app.services.experiment_lineage import record_benchmark_run_event
from app.services.inference_adapters import (
    AdapterCaseResult,
    AdapterHealth,
    InferenceAdapter,
    get_inference_adapter,
)
from app.services.operator_identity import SignerIdentity, local_operator_identity
from app.services.rag_answer_contract import rag_answer_contract_descriptor
from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS_REGISTRY,
    DEFAULT_RETRIEVER_DESCRIPTOR,
    RAG_EVALUATION_TRACE_VERSION,
    RagCorpusRegistry,
    RagPreparation,
    attach_rag_evaluation,
    is_rag_case,
    prepare_rag_execution,
    summarize_rag_traces,
)
from app.services.rag_evidence_contract import rag_evidence_contract_descriptor
from app.services.rag_evidence_selection import selector_descriptor
from app.services.rag_semantic_contract import rag_semantic_contract_descriptor
from app.services.result_scoring import score_case_result
from app.services.runtime_reliability import (
    RUNTIME_RELIABILITY_TRACE_VERSION,
    attach_runtime_reliability,
    reliability_trace,
    summarize_reliability_traces,
)
from app.services.tool_execution import (
    DEFAULT_TOOL_REGISTRY,
    TOOL_EXECUTION_SCHEMA_VERSION,
    ToolRegistry,
    attach_tool_execution,
    build_fault_tool_registry,
    summarize_tool_traces,
)
from app.services.tool_fault_scenarios import (
    TOOL_FAULT_DATA_SOURCE,
    TOOL_FAULT_TRACE_VERSION,
    ToolFaultScenario,
    parse_tool_fault_scenario,
    validate_fault_case,
)
from app.services.workload_isolation import (
    execution_isolation_preflights,
    expected_tools_from_cases,
)
from app.validators import DomainValidationError


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


@dataclass(frozen=True)
class BenchmarkExecutionOutcome:
    run: BenchmarkRun
    result_count: int
    metric_count: int
    log_count: int
    tool_execution_summary: dict[str, Any]
    rag_evaluation_summary: dict[str, Any]
    runtime_reliability_summary: dict[str, Any]
    agent_execution_summary: dict[str, Any]


@dataclass(frozen=True)
class _AdapterModelArtifactSnapshot:
    artifact_name: str


@dataclass(frozen=True)
class _AdapterConfigurationSnapshot:
    runtime_name: str
    runtime_config_json: dict[str, Any]
    generation_config_json: dict[str, Any]
    configuration_hash: str
    context_length: int
    model_artifact: _AdapterModelArtifactSnapshot


@dataclass(frozen=True)
class _AdapterEvaluationCaseSnapshot:
    external_case_id: str
    category: str
    title: str
    input_payload_json: dict[str, Any]
    expected_output_json: dict[str, Any] | None
    reference_context_json: dict[str, Any] | None
    expected_tool_schema_json: dict[str, Any] | None


@dataclass(frozen=True)
class _PreparedTrial:
    evaluation_case: EvaluationCase
    configuration: _AdapterConfigurationSnapshot
    adapter_case: _AdapterEvaluationCaseSnapshot
    rag_preparation: RagPreparation | None
    agent_preparation: AgentPreparation | None
    trial_index: int
    sample_id: str
    fault_scenario: ToolFaultScenario | None = None


def _get_required(db: Session, model: type, entity_id: UUID, label: str):
    entity = db.get(model, entity_id)
    if entity is None:
        raise DomainValidationError(f"{label} was not found")
    return entity


def check_runtime_health(
    db: Session,
    *,
    deployment_configuration_id: UUID,
    adapter_name: str,
    adapter_config_json: dict | None = None,
) -> AdapterHealth:
    configuration = _get_required(
        db,
        DeploymentConfiguration,
        deployment_configuration_id,
        "deployment_configuration",
    )
    adapter = get_inference_adapter(adapter_name)
    runtime_config = {
        **dict(configuration.runtime_config_json or {}),
        **(adapter_config_json or {}),
    }
    return adapter.health_check(
        _adapter_configuration_snapshot(
            configuration,
            runtime_config=runtime_config,
            case_timeout_ms=120_000,
        )
    )


def run_benchmark_execution(
    db: Session,
    payload: BenchmarkExecutionCreate,
    *,
    requester_identity: SignerIdentity | None = None,
    rag_corpus_registry: RagCorpusRegistry | None = None,
) -> BenchmarkExecutionOutcome:
    requester_identity = requester_identity or local_operator_identity()
    configuration = _get_required(
        db,
        DeploymentConfiguration,
        payload.deployment_configuration_id,
        "deployment_configuration",
    )
    suite = _get_required(db, EvaluationSuite, payload.evaluation_suite_id, "evaluation_suite")
    task = _get_required(db, BenchmarkTask, payload.benchmark_task_id, "benchmark_task")
    prompt = _get_required(db, PromptVersion, payload.prompt_version_id, "prompt_version")
    if suite.workload_profile_id != configuration.workload_profile_id:
        raise DomainValidationError("evaluation suite workload does not match configuration")
    if prompt.benchmark_task_id != task.id:
        raise DomainValidationError("prompt version must belong to the benchmark task")

    cases_statement = (
        select(EvaluationCase)
        .where(EvaluationCase.evaluation_suite_id == suite.id)
        .where(EvaluationCase.is_active.is_(True))
        .order_by(EvaluationCase.external_case_id)
    )
    if payload.evaluation_case_external_ids:
        cases_statement = cases_statement.where(
            EvaluationCase.external_case_id.in_(payload.evaluation_case_external_ids)
        )
    active_cases = list(db.scalars(cases_statement).all())
    if payload.evaluation_case_external_ids:
        case_order = {
            case_id: index for index, case_id in enumerate(payload.evaluation_case_external_ids)
        }
        active_cases.sort(key=lambda case: case_order[case.external_case_id])
        missing_case_ids = sorted(
            set(payload.evaluation_case_external_ids)
            - {case.external_case_id for case in active_cases}
        )
        if missing_case_ids:
            raise DomainValidationError(
                "requested active evaluation cases were not found in the suite: "
                + ", ".join(missing_case_ids)
            )
    if payload.max_cases is not None:
        active_cases = active_cases[: payload.max_cases]
    if not active_cases:
        raise DomainValidationError("evaluation suite has no active cases to execute")
    total_trial_count = len(active_cases) * payload.trials_per_case
    if total_trial_count > 5_000:
        raise DomainValidationError("benchmark execution is limited to 5000 total trials")

    adapter = get_inference_adapter(payload.adapter_name)
    adapter_descriptor = adapter.descriptor.to_dict()
    has_tool_cases = any(
        evaluation_case.expected_tool_schema_json is not None
        or "tool" in (evaluation_case.category or "").lower()
        for evaluation_case in active_cases
    )
    has_rag_cases = any(is_rag_case(evaluation_case) for evaluation_case in active_cases)
    has_agent_cases = any(is_agent_case(evaluation_case) for evaluation_case in active_cases)
    agent_approval_decisions = {
        checkpoint_id: decision.model_dump()
        for checkpoint_id, decision in payload.agent_approval_decisions.items()
    }
    has_reliability_trials = payload.reliability_mode
    original_runtime_config = dict(configuration.runtime_config_json or {})
    runtime_config = {
        **original_runtime_config,
        **payload.adapter_config_json,
        "prompt_bundle": {
            "name": prompt.name,
            "version_label": prompt.version_label,
            "prompt_hash": prompt.prompt_hash,
            "system_prompt": prompt.system_prompt,
            "user_template": prompt.user_template,
        },
    }
    if "tool_fault_scenario" in payload.adapter_config_json:
        raise DomainValidationError(
            "persist tool_fault_scenario in a separate Deployment Configuration; "
            "per-run adapter overrides are not supported"
        )
    try:
        fault_scenario = parse_tool_fault_scenario(runtime_config.get("tool_fault_scenario"))
        if fault_scenario is not None:
            if payload.data_source != TOOL_FAULT_DATA_SOURCE:
                raise ValueError(
                    f"Tool fault scenarios require data_source={TOOL_FAULT_DATA_SOURCE}"
                )
            if runtime_config.get("tool_failure_simulation") is not None:
                raise ValueError(
                    "environment faults cannot be combined with legacy failure authorization"
                )
            for evaluation_case in active_cases:
                validate_fault_case(evaluation_case)
    except ValueError as exc:
        raise DomainValidationError(str(exc)) from exc
    tool_registry = (
        build_fault_tool_registry() if fault_scenario is not None else DEFAULT_TOOL_REGISTRY
    )
    resolved_rag_registry = rag_corpus_registry or DEFAULT_RAG_CORPUS_REGISTRY
    isolation_preflights = (
        execution_isolation_preflights(
            policy_id=payload.isolation_policy_id,
            has_tool_cases=has_tool_cases,
            has_rag_cases=has_rag_cases,
            requested_tools=expected_tools_from_cases(active_cases),
            runtime_config=runtime_config,
        )
        if payload.isolation_policy_id
        else []
    )
    health = adapter.health_check(
        _adapter_configuration_snapshot(
            configuration,
            runtime_config=runtime_config,
            case_timeout_ms=payload.case_timeout_ms,
        )
    )
    if not health.healthy:
        raise DomainValidationError(health.message)

    started_at = _utcnow()
    run = BenchmarkRun(
        hardware_profile_id=configuration.hardware_profile_id,
        model_artifact_id=configuration.model_artifact_id,
        benchmark_task_id=task.id,
        prompt_version_id=prompt.id,
        deployment_configuration_id=configuration.id,
        evaluation_suite_id=suite.id,
        runtime_name=configuration.runtime_name,
        runtime_version=configuration.runtime_version,
        runtime_config_json={
            **runtime_config,
            "adapter_name": payload.adapter_name,
            "adapter_descriptor": adapter_descriptor,
            "configuration_hash": configuration.configuration_hash,
            "resolved_base_url": health.details.get("base_url"),
            **(
                {
                    "isolation_preflights": [
                        preflight.model_dump(mode="json") for preflight in isolation_preflights
                    ]
                }
                if isolation_preflights
                else {}
            ),
            **(
                {
                    "tool_execution_schema_version": (
                        TOOL_FAULT_TRACE_VERSION
                        if fault_scenario is not None
                        else TOOL_EXECUTION_SCHEMA_VERSION
                    ),
                    "tool_registry_descriptor": tool_registry.descriptor(),
                    **(
                        {"tool_fault_scenario_hash": fault_scenario.scenario_hash}
                        if fault_scenario is not None
                        else {}
                    ),
                }
                if has_tool_cases
                else {}
            ),
            **(
                {
                    "rag_evaluation_schema_version": RAG_EVALUATION_TRACE_VERSION,
                    "rag_corpus_registry_descriptor": (resolved_rag_registry.descriptor()),
                    "retriever_descriptor": DEFAULT_RETRIEVER_DESCRIPTOR.to_dict(),
                    "evidence_selector_descriptor": selector_descriptor(),
                    "rag_evidence_contract_descriptor": (rag_evidence_contract_descriptor()),
                    "rag_semantic_contract_descriptor": (rag_semantic_contract_descriptor()),
                    "rag_answer_contract_descriptor": rag_answer_contract_descriptor(),
                }
                if has_rag_cases
                else {}
            ),
            **(
                {
                    "runtime_reliability_schema_version": (RUNTIME_RELIABILITY_TRACE_VERSION),
                    "runtime_reliability_execution": {
                        "trials_per_case": payload.trials_per_case,
                        "concurrency": payload.concurrency,
                        "case_timeout_ms": payload.case_timeout_ms,
                    },
                }
                if has_reliability_trials
                else {}
            ),
            **(
                {
                    "agent_execution_schema_version": AGENT_EXECUTION_TRACE_VERSION,
                    "agent_control_plane_schema_version": AGENT_CONTROL_LINK_VERSION,
                    "agent_live_replan_mode": payload.agent_live_replan_mode,
                    "agent_runtime_descriptor": agent_runtime_descriptor(),
                    "operational_memory_registry_descriptor": (
                        DEFAULT_OPERATIONAL_MEMORY_REGISTRY.descriptor()
                    ),
                    "agent_approval_decisions": agent_approval_decisions,
                }
                if has_agent_cases
                else {}
            ),
        },
        dataset_version=f"{suite.name}:{suite.version_label}",
        seed=payload.seed,
        started_at=started_at,
        status="running",
        data_source=payload.data_source,
    )
    db.add(run)
    db.flush()
    db.add(
        BenchmarkExecutionLog(
            benchmark_run_id=run.id,
            event_type="run_started",
            level="info",
            message=(
                f"Started {payload.adapter_name} execution for {len(active_cases)} cases "
                f"and {total_trial_count} trials."
            ),
            payload_json={
                "adapter_name": payload.adapter_name,
                "adapter_version": adapter.descriptor.adapter_version,
                "evaluation_suite_id": str(suite.id),
                "configuration_hash": configuration.configuration_hash,
                "case_count": len(active_cases),
                "trial_count": total_trial_count,
                "concurrency": payload.concurrency,
            },
            occurred_at=started_at,
            data_source=payload.data_source,
        )
    )

    result_count = 0
    metric_count = 0
    log_count = 1
    tool_traces: list[dict[str, Any]] = []
    rag_traces: list[dict[str, Any]] = []
    reliability_traces: list[dict[str, Any]] = []
    agent_traces: list[dict[str, Any]] = []
    agent_checkpoint_count = 0
    try:
        prepared_trials = _prepare_trials(
            configuration,
            active_cases,
            runtime_config=runtime_config,
            trials_per_case=payload.trials_per_case,
            case_timeout_ms=payload.case_timeout_ms,
            include_mock_agent_plan=payload.adapter_name == "mock",
            agent_approval_decisions=agent_approval_decisions,
            rag_corpus_registry=resolved_rag_registry,
        )
        case_results = _execute_trials(
            adapter,
            prepared_trials,
            seed=payload.seed,
            concurrency=payload.concurrency,
            capture_failures=payload.reliability_mode,
            case_timeout_ms=payload.case_timeout_ms,
        )
        for prepared, case_result in zip(prepared_trials, case_results, strict=True):
            evaluation_case = prepared.evaluation_case
            case_result = attach_agent_execution(
                evaluation_case,
                case_result,
                prepared.agent_preparation,
                live_replan_callback=build_agent_live_replan_callback(
                    evaluation_case,
                    mode=payload.agent_live_replan_mode,
                    provider_config=runtime_config,
                ),
            )
            case_result = attach_rag_evaluation(
                evaluation_case,
                case_result,
                prepared.rag_preparation,
            )
            case_result = attach_tool_execution(
                evaluation_case,
                case_result,
                tool_registry,
                fault_scenario=prepared.fault_scenario,
            )
            trace = case_result.metadata.get("tool_execution")
            if isinstance(trace, dict):
                tool_traces.append(trace)
            rag_trace = case_result.metadata.get("rag_evaluation")
            if isinstance(rag_trace, dict):
                rag_traces.append(rag_trace)
            agent_trace = case_result.metadata.get("agent_execution")
            if isinstance(agent_trace, dict):
                agent_traces.append(agent_trace)
            case_result = score_case_result(evaluation_case, case_result)
            if has_reliability_trials:
                case_result = attach_runtime_reliability(
                    evaluation_case,
                    case_result,
                    trial_index=prepared.trial_index,
                    total_trials=payload.trials_per_case,
                    concurrency=payload.concurrency,
                    case_timeout_ms=payload.case_timeout_ms,
                    context_window_tokens=configuration.context_length,
                    seed=payload.seed,
                    benchmark_run_id=str(run.id),
                )
                trial_trace = reliability_trace(case_result.metadata)
                if trial_trace is not None:
                    reliability_traces.append(trial_trace)
            benchmark_result = BenchmarkResult(
                benchmark_run_id=run.id,
                evaluation_case_id=evaluation_case.id,
                sample_id=prepared.sample_id,
                quality_score=case_result.quality_score,
                exact_match=case_result.exact_match,
                json_valid=case_result.json_valid,
                tool_call_valid=case_result.tool_call_valid,
                groundedness_score=case_result.groundedness_score,
                faithfulness_score=case_result.faithfulness_score,
                human_label=case_result.human_label,
                error_type=case_result.error_type,
                raw_output=case_result.raw_output,
                normalized_output=case_result.normalized_output,
                metadata_json={
                    **case_result.metadata,
                    "adapter_name": payload.adapter_name,
                    "adapter_descriptor": adapter_descriptor,
                    "evaluation_case_id": str(evaluation_case.id),
                },
                data_source=payload.data_source,
            )
            db.add(benchmark_result)
            db.flush()
            if isinstance(agent_trace, dict) and prepared.agent_preparation is not None:
                checkpoints = materialize_pending_agent_checkpoints(
                    db,
                    benchmark_result=benchmark_result,
                    trace=agent_trace,
                    contract=prepared.agent_preparation.contract,
                    requester_identity=requester_identity,
                )
                agent_checkpoint_count += len(checkpoints)
                log_count += len(checkpoints)
            result_count += 1
            db.add(
                InferenceMetric(
                    benchmark_run_id=run.id,
                    sample_id=prepared.sample_id,
                    ttft_ms=case_result.ttft_ms,
                    end_to_end_latency_ms=case_result.end_to_end_latency_ms,
                    prompt_tokens=case_result.prompt_tokens,
                    completion_tokens=case_result.completion_tokens,
                    tokens_per_second=case_result.tokens_per_second,
                    gpu_vram_used_mb=case_result.gpu_vram_used_mb,
                    gpu_utilization_pct=case_result.gpu_utilization_pct,
                    cpu_utilization_pct=case_result.cpu_utilization_pct,
                    peak_memory_mb=case_result.peak_memory_mb,
                    oom_occurred=case_result.oom_occurred,
                    retry_count=case_result.retry_count,
                    data_source=payload.data_source,
                )
            )
            metric_count += 1
            for log in case_result.logs:
                db.add(
                    BenchmarkExecutionLog(
                        benchmark_run_id=run.id,
                        event_type=str(log.get("event_type", "case_event")),
                        level=str(log.get("level", "info")),
                        message=str(log.get("message", "adapter event")),
                        payload_json=log.get("payload_json"),
                        occurred_at=_utcnow(),
                        data_source=payload.data_source,
                    )
                )
                log_count += 1
        run.status = "completed"
        run.completed_at = _utcnow()
        db.flush()
        mark_scope_gates_stale(
            db,
            deployment_configuration_id=configuration.id,
            evaluation_suite_id=suite.id,
            reason=(
                "New benchmark evidence was captured after this Gate evaluation. "
                "Run the Deployment Gate again."
            ),
            now=run.completed_at,
        )
        db.add(
            BenchmarkExecutionLog(
                benchmark_run_id=run.id,
                event_type="run_completed",
                level="info",
                message="Benchmark execution completed.",
                payload_json={
                    "result_count": result_count,
                    "metric_count": metric_count,
                    "tool_execution_summary": summarize_tool_traces(tool_traces),
                    "rag_evaluation_summary": summarize_rag_traces(rag_traces),
                    "runtime_reliability_summary": summarize_reliability_traces(reliability_traces),
                    "agent_execution_summary": summarize_agent_traces(agent_traces),
                    "agent_approval_checkpoint_count": agent_checkpoint_count,
                },
                occurred_at=run.completed_at,
                data_source=payload.data_source,
            )
        )
        log_count += 1
        record_benchmark_run_event(db, run)
    except Exception as exc:
        run.status = "failed"
        run.completed_at = _utcnow()
        run.failure_reason = str(exc)
        record_benchmark_run_event(db, run)
        db.add(
            BenchmarkExecutionLog(
                benchmark_run_id=run.id,
                event_type="run_failed",
                level="error",
                message=str(exc),
                payload_json={"adapter_name": payload.adapter_name},
                occurred_at=run.completed_at,
                data_source=payload.data_source,
            )
        )
        db.commit()
        raise

    db.commit()
    db.refresh(run)
    return BenchmarkExecutionOutcome(
        run=run,
        result_count=result_count,
        metric_count=metric_count,
        log_count=log_count,
        tool_execution_summary=summarize_tool_traces(tool_traces),
        rag_evaluation_summary=summarize_rag_traces(rag_traces),
        runtime_reliability_summary=summarize_reliability_traces(reliability_traces),
        agent_execution_summary=summarize_agent_traces(agent_traces),
    )


def get_benchmark_execution_detail(
    db: Session,
    *,
    benchmark_run_id: UUID,
) -> dict[str, Any]:
    run = _get_required(db, BenchmarkRun, benchmark_run_id, "benchmark_run")
    results = list(
        db.scalars(
            select(BenchmarkResult)
            .where(BenchmarkResult.benchmark_run_id == benchmark_run_id)
            .order_by(BenchmarkResult.sample_id)
        ).all()
    )
    metrics = list(
        db.scalars(
            select(InferenceMetric).where(InferenceMetric.benchmark_run_id == benchmark_run_id)
        ).all()
    )
    logs = list(
        db.scalars(
            select(BenchmarkExecutionLog).where(
                BenchmarkExecutionLog.benchmark_run_id == benchmark_run_id
            )
        ).all()
    )
    trace_records: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    rag_trace_records: list[dict[str, Any]] = []
    rag_traces: list[dict[str, Any]] = []
    reliability_trace_records: list[dict[str, Any]] = []
    reliability_traces: list[dict[str, Any]] = []
    agent_trace_records: list[dict[str, Any]] = []
    agent_traces: list[dict[str, Any]] = []
    for result in results:
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        evaluation_case = result.evaluation_case
        trace = metadata.get("tool_execution")
        if isinstance(trace, dict):
            traces.append(trace)
            trace_records.append(
                {
                    "benchmark_result_id": result.id,
                    "evaluation_case_id": result.evaluation_case_id,
                    "sample_id": result.sample_id,
                    "case_title": evaluation_case.title if evaluation_case else None,
                    "criticality": evaluation_case.criticality if evaluation_case else None,
                    "trace": trace,
                }
            )
        rag_trace = metadata.get("rag_evaluation")
        if isinstance(rag_trace, dict):
            rag_traces.append(rag_trace)
            rag_trace_records.append(
                {
                    "benchmark_result_id": result.id,
                    "evaluation_case_id": result.evaluation_case_id,
                    "sample_id": result.sample_id,
                    "case_title": evaluation_case.title if evaluation_case else None,
                    "criticality": evaluation_case.criticality if evaluation_case else None,
                    "trace": rag_trace,
                }
            )
        trial_trace = reliability_trace(metadata)
        if trial_trace is not None:
            reliability_traces.append(trial_trace)
            reliability_trace_records.append(
                {
                    "benchmark_result_id": result.id,
                    "evaluation_case_id": result.evaluation_case_id,
                    "sample_id": result.sample_id,
                    "case_title": evaluation_case.title if evaluation_case else None,
                    "criticality": evaluation_case.criticality if evaluation_case else None,
                    "trace": trial_trace,
                }
            )
        agent_trace = metadata.get("agent_execution")
        if isinstance(agent_trace, dict):
            agent_traces.append(agent_trace)
            agent_trace_records.append(
                {
                    "benchmark_result_id": result.id,
                    "evaluation_case_id": result.evaluation_case_id,
                    "sample_id": result.sample_id,
                    "case_title": evaluation_case.title if evaluation_case else None,
                    "criticality": evaluation_case.criticality if evaluation_case else None,
                    "trace": agent_trace,
                }
            )
    return {
        "benchmark_run": run,
        "result_count": len(results),
        "metric_count": len(metrics),
        "log_count": len(logs),
        "tool_execution_summary": summarize_tool_traces(traces),
        "tool_traces": trace_records,
        "rag_evaluation_summary": summarize_rag_traces(rag_traces),
        "rag_traces": rag_trace_records,
        "runtime_reliability_summary": summarize_reliability_traces(reliability_traces),
        "reliability_traces": reliability_trace_records,
        "agent_execution_summary": summarize_agent_traces(agent_traces),
        "agent_traces": agent_trace_records,
    }


def _prepare_trials(
    configuration: DeploymentConfiguration,
    evaluation_cases: list[EvaluationCase],
    *,
    runtime_config: dict[str, Any],
    trials_per_case: int,
    case_timeout_ms: int,
    include_mock_agent_plan: bool,
    agent_approval_decisions: dict[str, Any],
    rag_corpus_registry: RagCorpusRegistry | None = None,
) -> list[_PreparedTrial]:
    prepared: list[_PreparedTrial] = []
    fault_scenario = parse_tool_fault_scenario(runtime_config.get("tool_fault_scenario"))
    tool_registry = (
        build_fault_tool_registry() if fault_scenario is not None else DEFAULT_TOOL_REGISTRY
    )
    if fault_scenario is not None:
        if runtime_config.get("tool_failure_simulation") is not None:
            raise ValueError(
                "environment faults cannot be combined with legacy failure authorization"
            )
        for evaluation_case in evaluation_cases:
            validate_fault_case(evaluation_case)
    document_context = _tool_document_context(configuration, rag_corpus_registry)
    configuration_snapshot = _adapter_configuration_snapshot(
        configuration,
        runtime_config={
            **{key: value for key, value in runtime_config.items() if key != "tool_fault_scenario"},
            "_tool_document_context": document_context,
        },
        case_timeout_ms=case_timeout_ms,
    )
    for evaluation_case in evaluation_cases:
        agent_preparation = prepare_agent_execution(
            configuration,
            evaluation_case,
            include_mock_plan=include_mock_agent_plan,
            approval_decisions=agent_approval_decisions,
            rag_corpus_registry=rag_corpus_registry,
        )
        rag_preparation = (
            None
            if agent_preparation is not None
            else prepare_rag_execution(
                configuration,
                evaluation_case,
                registry=rag_corpus_registry,
            )
        )
        base_input = (
            agent_preparation.adapter_input_payload
            if agent_preparation is not None
            else (
                rag_preparation.adapter_input_payload
                if rag_preparation is not None
                else evaluation_case.input_payload_json
            )
        )
        base_reference = (
            agent_preparation.adapter_reference_context
            if agent_preparation is not None
            else (
                rag_preparation.adapter_reference_context
                if rag_preparation is not None
                else evaluation_case.reference_context_json
            )
        )
        for trial_index in range(1, trials_per_case + 1):
            adapter_input = copy.deepcopy(base_input or {})
            tool_descriptors = _available_tool_descriptors(evaluation_case, tool_registry)
            if tool_descriptors:
                adapter_input["available_tools"] = tool_descriptors
                if (
                    document_context is not None
                    and agent_preparation is None
                    and rag_preparation is None
                ):
                    adapter_input["available_document_ids"] = document_context["document_ids"]
                    adapter_input["document_catalog_provenance"] = {
                        key: value
                        for key, value in document_context.items()
                        if key != "document_ids"
                    }
            adapter_input["_execution_trial"] = trial_index
            adapter_input["_case_timeout_ms"] = case_timeout_ms
            adapter_case = _AdapterEvaluationCaseSnapshot(
                external_case_id=evaluation_case.external_case_id,
                category=evaluation_case.category,
                title=evaluation_case.title,
                input_payload_json=adapter_input,
                expected_output_json=copy.deepcopy(evaluation_case.expected_output_json),
                reference_context_json=copy.deepcopy(base_reference),
                expected_tool_schema_json=copy.deepcopy(evaluation_case.expected_tool_schema_json),
            )
            prepared.append(
                _PreparedTrial(
                    evaluation_case=evaluation_case,
                    configuration=configuration_snapshot,
                    adapter_case=adapter_case,
                    rag_preparation=rag_preparation,
                    agent_preparation=agent_preparation,
                    trial_index=trial_index,
                    sample_id=_trial_sample_id(
                        evaluation_case.external_case_id,
                        trial_index,
                        trials_per_case,
                    ),
                    fault_scenario=fault_scenario,
                )
            )
    return prepared


def _tool_document_context(
    configuration: DeploymentConfiguration,
    registry: RagCorpusRegistry | None,
) -> dict[str, Any] | None:
    retrieval = configuration.retrieval_config_json or {}
    corpus_id = retrieval.get("corpus_id")
    corpus = (
        registry.get(corpus_id) if registry is not None and isinstance(corpus_id, str) else None
    )
    if corpus is None:
        return None
    if any(
        retrieval.get(key) is not None and retrieval[key] != getattr(corpus, key)
        for key in ("corpus_version", "corpus_hash")
    ):
        return None
    return {
        "corpus_id": corpus.corpus_id,
        "corpus_version": corpus.corpus_version,
        "corpus_hash": corpus.corpus_hash,
        "document_ids": sorted({chunk.document_id for chunk in corpus.chunks}),
    }


def _available_tool_descriptors(
    evaluation_case: EvaluationCase,
    registry: ToolRegistry | None = None,
) -> list[dict[str, Any]]:
    if evaluation_case.expected_tool_schema_json is None and not is_agent_case(evaluation_case):
        return []
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    agent_contract = reference.get("agent")
    allowed = (
        set(str(value) for value in agent_contract.get("allowed_tools", []))
        if isinstance(agent_contract, dict)
        else None
    )
    descriptors = (registry or DEFAULT_TOOL_REGISTRY).descriptor()["tools"]
    return [
        {
            "tool_name": descriptor["tool_id"],
            "description": descriptor["description"],
            "argument_schema": descriptor["argument_schema"],
        }
        for descriptor in descriptors
        if allowed is None or descriptor["tool_id"] in allowed
    ]


def _adapter_configuration_snapshot(
    configuration: DeploymentConfiguration,
    *,
    runtime_config: dict[str, Any],
    case_timeout_ms: int,
) -> _AdapterConfigurationSnapshot:
    return _AdapterConfigurationSnapshot(
        runtime_name=configuration.runtime_name,
        runtime_config_json={
            **copy.deepcopy(runtime_config),
            "_case_timeout_ms": case_timeout_ms,
        },
        generation_config_json=copy.deepcopy(configuration.generation_config_json or {}),
        configuration_hash=configuration.configuration_hash,
        context_length=configuration.context_length,
        model_artifact=_AdapterModelArtifactSnapshot(
            artifact_name=configuration.model_artifact.artifact_name
        ),
    )


def _execute_trials(
    adapter: InferenceAdapter,
    prepared_trials: list[_PreparedTrial],
    *,
    seed: int | None,
    concurrency: int,
    capture_failures: bool,
    case_timeout_ms: int,
) -> list[AdapterCaseResult]:
    def execute(trial: _PreparedTrial) -> AdapterCaseResult:
        started = time.perf_counter()
        try:
            return adapter.run_case(
                configuration=trial.configuration,
                evaluation_case=trial.adapter_case,
                seed=seed,
            )
        except Exception as exc:
            if not capture_failures:
                raise
            elapsed_ms = max(1.0, (time.perf_counter() - started) * 1000)
            return _failed_case_result(exc, elapsed_ms, case_timeout_ms)

    if concurrency == 1:
        return [execute(trial) for trial in prepared_trials]
    with ThreadPoolExecutor(
        max_workers=concurrency,
        thread_name_prefix="model-atlas-benchmark",
    ) as executor:
        return list(executor.map(execute, prepared_trials))


def _failed_case_result(
    exc: Exception,
    elapsed_ms: float,
    case_timeout_ms: int,
) -> AdapterCaseResult:
    message = str(exc) or type(exc).__name__
    normalized_message = message.lower().replace(" ", "_")
    if (
        isinstance(exc, TimeoutError)
        or "timed_out" in normalized_message
        or "timeout" in normalized_message
    ):
        error_type = "timeout"
        elapsed_ms = max(elapsed_ms, float(case_timeout_ms))
    elif isinstance(exc, MemoryError) or "out_of_memory" in normalized_message:
        error_type = "out_of_memory"
    else:
        error_type = type(exc).__name__.lower()
    return AdapterCaseResult(
        raw_output="",
        normalized_output="",
        quality_score=None,
        exact_match=None,
        json_valid=False,
        tool_call_valid=False,
        groundedness_score=None,
        faithfulness_score=None,
        human_label="runtime-fail",
        error_type=error_type,
        ttft_ms=round(elapsed_ms, 3),
        end_to_end_latency_ms=round(elapsed_ms, 3),
        prompt_tokens=0,
        completion_tokens=0,
        tokens_per_second=0.0,
        gpu_vram_used_mb=None,
        gpu_utilization_pct=None,
        cpu_utilization_pct=None,
        peak_memory_mb=None,
        oom_occurred=error_type == "out_of_memory",
        retry_count=0,
        logs=[
            {
                "event_type": "case_execution_failed",
                "level": "error",
                "message": message,
                "payload_json": {"error_type": error_type},
            }
        ],
        metadata={"reliability_error_message": message},
    )


def _trial_sample_id(external_case_id: str, trial_index: int, total_trials: int) -> str:
    if total_trials == 1:
        return external_case_id
    suffix = f"::trial-{trial_index:02d}"
    return f"{external_case_id[: 120 - len(suffix)]}{suffix}"


def get_tool_registry_descriptor() -> dict[str, Any]:
    return DEFAULT_TOOL_REGISTRY.descriptor()


def list_execution_logs(
    db: Session,
    *,
    benchmark_run_id: UUID,
    limit: int,
    offset: int,
) -> list[BenchmarkExecutionLog]:
    return list(
        db.scalars(
            select(BenchmarkExecutionLog)
            .where(BenchmarkExecutionLog.benchmark_run_id == benchmark_run_id)
            .order_by(BenchmarkExecutionLog.occurred_at, BenchmarkExecutionLog.created_at)
            .offset(offset)
            .limit(limit)
        ).all()
    )
