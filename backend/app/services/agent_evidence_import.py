from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkExecutionLog,
    BenchmarkResult,
    BenchmarkRun,
    EvaluationCase,
    InferenceMetric,
)
from app.schemas import AgentEvidenceImportCreate
from app.services.agent_approval_policy import assert_agent_evidence_import_allowed
from app.services.agent_execution import (
    MAX_AGENT_LIVE_REPLAN_CALLS,
    MAX_AGENT_REPLANS,
    SUPPORTED_AGENT_TRACE_VERSIONS,
)
from app.services.deployment_gate.staleness import mark_scope_gates_stale
from app.services.inference_adapters import AdapterCaseResult
from app.services.operator_identity import SignerIdentity
from app.services.result_scoring import score_case_result
from app.validators import DomainValidationError

AGENT_EVIDENCE_IMPORT_CONTRACT_VERSION = "production-agent-evidence-import-v1"
AGENT_EVIDENCE_IMPORT_POLICY_VERSION = "agent-evidence-import-rbac-v1"
PRODUCTION_CAPTURED_SOURCE = "production_captured"


def agent_trace_hash(trace: dict[str, Any]) -> str:
    return _hash_payload(trace)


def import_production_agent_evidence(
    db: Session,
    *,
    payload: AgentEvidenceImportCreate,
    signer_identity: SignerIdentity,
    commit: bool = True,
) -> dict[str, Any]:
    assert_agent_evidence_import_allowed(signer_identity)
    benchmark_run = db.get(BenchmarkRun, payload.benchmark_run_id)
    if benchmark_run is None:
        raise DomainValidationError("benchmark_run was not found")
    evaluation_case = db.get(EvaluationCase, payload.evaluation_case_id)
    if evaluation_case is None:
        raise DomainValidationError("evaluation_case was not found")
    if benchmark_run.data_source != PRODUCTION_CAPTURED_SOURCE:
        raise DomainValidationError(
            "production Agent evidence requires a production_captured benchmark run"
        )
    if benchmark_run.evaluation_suite_id != evaluation_case.evaluation_suite_id:
        raise DomainValidationError(
            "Agent evidence evaluation case does not belong to the benchmark run suite"
        )
    trace = payload.trace.model_dump(mode="json")
    _validate_trace(evaluation_case, trace)
    supplied_hash = payload.provenance.source_trace_hash.lower()
    calculated_hash = agent_trace_hash(trace)
    if supplied_hash != calculated_hash:
        raise DomainValidationError(
            "Agent evidence source_trace_hash does not match the normalized trace"
        )
    _validate_plan_output(payload.normalized_output)
    _assert_not_duplicate(
        db,
        benchmark_run_id=benchmark_run.id,
        sample_id=payload.sample_id,
        source_event_id=payload.provenance.source_event_id,
    )

    metric_payload = payload.metric
    adapter_result = AdapterCaseResult(
        raw_output=payload.raw_output,
        normalized_output=payload.normalized_output,
        quality_score=None,
        exact_match=trace.get("successful") is True,
        json_valid=trace.get("parse_valid") is True,
        tool_call_valid=False,
        groundedness_score=None,
        faithfulness_score=None,
        human_label=payload.human_label or "captured-needs-scoring",
        error_type=None if trace.get("successful") else "agent_execution_failed",
        ttft_ms=metric_payload.ttft_ms,
        end_to_end_latency_ms=metric_payload.end_to_end_latency_ms,
        prompt_tokens=metric_payload.prompt_tokens,
        completion_tokens=metric_payload.completion_tokens,
        tokens_per_second=metric_payload.tokens_per_second,
        gpu_vram_used_mb=metric_payload.gpu_vram_used_mb,
        gpu_utilization_pct=metric_payload.gpu_utilization_pct,
        cpu_utilization_pct=metric_payload.cpu_utilization_pct,
        peak_memory_mb=metric_payload.peak_memory_mb,
        oom_occurred=metric_payload.oom_occurred,
        retry_count=metric_payload.retry_count,
        metadata={"agent_execution": trace},
    )
    scored = score_case_result(evaluation_case, adapter_result)
    provenance = {
        **payload.provenance.model_dump(mode="json"),
        "source_trace_hash": calculated_hash,
        "imported_by": signer_identity.to_json(),
        "identity_verified": signer_identity.identity_verified,
        "import_contract_version": AGENT_EVIDENCE_IMPORT_CONTRACT_VERSION,
        "import_policy_version": AGENT_EVIDENCE_IMPORT_POLICY_VERSION,
    }
    evidence_hash = _hash_payload(
        {
            "benchmark_run_id": str(benchmark_run.id),
            "evaluation_case_id": str(evaluation_case.id),
            "sample_id": payload.sample_id,
            "trace_hash": calculated_hash,
            "provenance": provenance,
            "metric": metric_payload.model_dump(mode="json"),
        }
    )
    result = BenchmarkResult(
        benchmark_run_id=benchmark_run.id,
        evaluation_case_id=evaluation_case.id,
        sample_id=payload.sample_id,
        quality_score=scored.quality_score,
        exact_match=scored.exact_match,
        json_valid=scored.json_valid,
        tool_call_valid=scored.tool_call_valid,
        groundedness_score=scored.groundedness_score,
        faithfulness_score=scored.faithfulness_score,
        human_label=scored.human_label,
        error_type=scored.error_type,
        raw_output=scored.raw_output,
        normalized_output=scored.normalized_output,
        metadata_json={
            **scored.metadata,
            "adapter_name": "production_agent_evidence_import",
            "agent_evidence_import": {
                **provenance,
                "evidence_hash": evidence_hash,
            },
        },
        evidence_revision_hash=evidence_hash,
        data_source=PRODUCTION_CAPTURED_SOURCE,
    )
    db.add(result)
    db.flush()
    metric = InferenceMetric(
        benchmark_run_id=benchmark_run.id,
        sample_id=payload.sample_id,
        ttft_ms=metric_payload.ttft_ms,
        end_to_end_latency_ms=metric_payload.end_to_end_latency_ms,
        prompt_tokens=metric_payload.prompt_tokens,
        completion_tokens=metric_payload.completion_tokens,
        tokens_per_second=metric_payload.tokens_per_second,
        gpu_vram_used_mb=metric_payload.gpu_vram_used_mb,
        gpu_utilization_pct=metric_payload.gpu_utilization_pct,
        cpu_utilization_pct=metric_payload.cpu_utilization_pct,
        peak_memory_mb=metric_payload.peak_memory_mb,
        oom_occurred=metric_payload.oom_occurred,
        retry_count=metric_payload.retry_count,
        data_source=PRODUCTION_CAPTURED_SOURCE,
    )
    db.add(metric)
    db.flush()
    db.add(
        BenchmarkExecutionLog(
            benchmark_run_id=benchmark_run.id,
            event_type="production_agent_evidence_imported",
            level="info",
            message=(
                f"Imported production Agent evidence {payload.provenance.source_event_id}."
            ),
            payload_json={
                "benchmark_result_id": str(result.id),
                "evaluation_case_id": str(evaluation_case.id),
                "source_event_id": payload.provenance.source_event_id,
                "source_trace_hash": calculated_hash,
                "evidence_hash": evidence_hash,
                "import_contract_version": AGENT_EVIDENCE_IMPORT_CONTRACT_VERSION,
                "import_policy_version": AGENT_EVIDENCE_IMPORT_POLICY_VERSION,
            },
            occurred_at=payload.provenance.captured_at,
            data_source=PRODUCTION_CAPTURED_SOURCE,
        )
    )
    if benchmark_run.deployment_configuration_id and benchmark_run.evaluation_suite_id:
        db.flush()
        mark_scope_gates_stale(
            db,
            deployment_configuration_id=benchmark_run.deployment_configuration_id,
            evaluation_suite_id=benchmark_run.evaluation_suite_id,
            reason=(
                "New production Agent evidence was imported after this Gate evaluation. "
                "Run the Deployment Gate again."
            ),
            now=payload.provenance.captured_at,
        )
    if commit:
        db.commit()
    return {
        "import_contract_version": AGENT_EVIDENCE_IMPORT_CONTRACT_VERSION,
        "import_policy_version": AGENT_EVIDENCE_IMPORT_POLICY_VERSION,
        "benchmark_run_id": benchmark_run.id,
        "benchmark_result_id": result.id,
        "inference_metric_id": metric.id,
        "evaluation_case_id": evaluation_case.id,
        "sample_id": payload.sample_id,
        "source_event_id": payload.provenance.source_event_id,
        "source_trace_hash": calculated_hash,
        "evidence_hash": evidence_hash,
        "trace_status": str(trace.get("status")),
        "quality_score": scored.quality_score,
        "data_source": PRODUCTION_CAPTURED_SOURCE,
    }


def _validate_trace(
    evaluation_case: EvaluationCase,
    trace: dict[str, Any],
) -> None:
    if trace.get("schema_version") not in SUPPORTED_AGENT_TRACE_VERSIONS:
        raise DomainValidationError("Agent evidence trace version is not supported")
    if trace.get("external_case_id") != evaluation_case.external_case_id:
        raise DomainValidationError(
            "Agent evidence external_case_id does not match the evaluation case"
        )
    steps = trace.get("steps")
    if not isinstance(steps, list) or int(trace.get("step_count") or 0) != len(steps):
        raise DomainValidationError("Agent evidence step_count does not match trace steps")
    if int(trace.get("replan_count") or 0) > MAX_AGENT_REPLANS:
        raise DomainValidationError("Agent evidence exceeds the replan limit")
    if int(trace.get("live_replan_model_call_count") or 0) > MAX_AGENT_LIVE_REPLAN_CALLS:
        raise DomainValidationError("Agent evidence exceeds the live replan model-call limit")
    if int(trace.get("pending_checkpoint_count") or 0) > 0:
        raise DomainValidationError(
            "Pending Agent checkpoints must be imported through resumable checkpoint state"
        )
    for step in steps:
        if not isinstance(step, dict) or step.get("action") != "approval_checkpoint":
            continue
        if step.get("status") != "approved":
            continue
        output = step.get("output")
        output = output if isinstance(output, dict) else {}
        if output.get("identity_verified") is not True:
            raise DomainValidationError(
                "Production Agent approval evidence requires verified approver provenance"
            )
        if not output.get("decision_hash") or not output.get("checkpoint_record_id"):
            raise DomainValidationError(
                "Production Agent approval evidence is missing persisted decision provenance"
            )
    replans = trace.get("replans")
    replans = replans if isinstance(replans, list) else []
    for replan in replans:
        if not isinstance(replan, dict) or replan.get("source") != "live_callback":
            continue
        model_call = replan.get("model_call")
        model_call = model_call if isinstance(model_call, dict) else {}
        provider = str(model_call.get("provider_id") or "").lower()
        if not provider or "mock" in provider or "fixture" in provider:
            raise DomainValidationError(
                "Production Agent live replan evidence requires a non-fixture provider"
            )
        response_hash = str(model_call.get("response_hash") or "")
        if len(response_hash) != 64:
            raise DomainValidationError(
                "Production Agent live replan evidence is missing response_hash"
            )


def _validate_plan_output(normalized_output: str) -> None:
    try:
        plan = json.loads(normalized_output)
    except json.JSONDecodeError as exc:
        raise DomainValidationError("Agent evidence normalized_output is not valid JSON") from exc
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        raise DomainValidationError("Agent evidence normalized_output must contain steps")


def _assert_not_duplicate(
    db: Session,
    *,
    benchmark_run_id: Any,
    sample_id: str,
    source_event_id: str,
) -> None:
    existing_results = db.scalars(
        select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id == benchmark_run_id)
    ).all()
    for result in existing_results:
        if result.sample_id == sample_id:
            raise DomainValidationError("Agent evidence sample_id already exists in the run")
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        imported = metadata.get("agent_evidence_import")
        if isinstance(imported, dict) and imported.get("source_event_id") == source_event_id:
            raise DomainValidationError("Agent evidence source_event_id was already imported")


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
