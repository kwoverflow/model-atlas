from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    AgentApprovalCheckpoint,
    BenchmarkExecutionLog,
    BenchmarkResult,
    BenchmarkRun,
    InferenceMetric,
)
from app.schemas import (
    AgentCheckpointDecisionCreate,
    AgentCheckpointRevocationCreate,
)
from app.services.agent_approval_policy import (
    assert_agent_checkpoint_operation_allowed,
    checkpoint_policy_from_json,
    resolve_agent_checkpoint_policy,
)
from app.services.agent_execution import (
    approval_decisions_from_agent_trace,
    attach_agent_execution,
    build_agent_live_replan_callback,
    prepare_agent_execution,
    summarize_agent_traces,
)
from app.services.deployment_gate.staleness import mark_scope_gates_stale
from app.services.inference_adapters import AdapterCaseResult
from app.services.operator_identity import SignerIdentity
from app.services.result_scoring import score_case_result
from app.validators import DomainValidationError

AGENT_APPROVAL_REQUEST_VERSION = "agent-approval-request-v1"
AGENT_CONTROL_LINK_VERSION = "agent-control-plane-link-v2"
AGENT_RESUME_EVENT_VERSION = "agent-resume-event-v2"
AGENT_EVIDENCE_REVISION_VERSION = "agent-evidence-revision-v1"


@dataclass(frozen=True)
class AgentCheckpointResumeOutcome:
    checkpoint: AgentApprovalCheckpoint
    benchmark_run_id: UUID
    benchmark_result_id: UUID
    parent_benchmark_run_id: UUID
    parent_benchmark_result_id: UUID
    result_revision: int
    trace: dict[str, Any]
    summary: dict[str, Any]


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def materialize_pending_agent_checkpoints(
    db: Session,
    *,
    benchmark_result: BenchmarkResult,
    trace: dict[str, Any],
    contract: dict[str, Any],
    requester_identity: SignerIdentity,
    now: dt.datetime | None = None,
) -> list[AgentApprovalCheckpoint]:
    requested_at = now or _utcnow()
    existing = {
        checkpoint.checkpoint_id: checkpoint
        for checkpoint in db.scalars(
            select(AgentApprovalCheckpoint).where(
                AgentApprovalCheckpoint.benchmark_result_id == benchmark_result.id
            )
        ).all()
    }
    created: list[AgentApprovalCheckpoint] = []
    for step in _pending_checkpoint_steps(trace):
        output = step.get("output")
        output = output if isinstance(output, dict) else {}
        checkpoint_id = str(output.get("checkpoint_id") or "").strip()
        if not checkpoint_id or checkpoint_id in existing:
            continue
        policy = resolve_agent_checkpoint_policy(
            contract,
            checkpoint_id=checkpoint_id,
        )
        request_snapshot = _checkpoint_request_snapshot(
            benchmark_result=benchmark_result,
            trace=trace,
            step=step,
            checkpoint_id=checkpoint_id,
        )
        request_hash = _hash_payload(
            {
                "request": request_snapshot,
                "policy": policy.to_json(),
                "requested_by": requester_identity.to_json(),
                "requested_at": requested_at.isoformat(),
            }
        )
        checkpoint = AgentApprovalCheckpoint(
            benchmark_run_id=benchmark_result.benchmark_run_id,
            benchmark_result_id=benchmark_result.id,
            checkpoint_id=checkpoint_id,
            status="pending",
            requested_by_subject_id=requester_identity.subject_id,
            requested_by_identity_json=requester_identity.to_json(),
            request_snapshot_json=request_snapshot,
            approval_policy_json=policy.to_json(),
            request_hash=request_hash,
            expires_at=requested_at
            + dt.timedelta(seconds=policy.expires_in_seconds),
            version=1,
        )
        db.add(checkpoint)
        db.flush()
        existing[checkpoint_id] = checkpoint
        created.append(checkpoint)
        _add_log(
            db,
            benchmark_result=benchmark_result,
            event_type="agent_approval_checkpoint_requested",
            level="warning",
            message=f"Agent checkpoint {checkpoint_id} is waiting for approval.",
            payload_json={
                "checkpoint_record_id": str(checkpoint.id),
                "checkpoint_id": checkpoint_id,
                "request_hash": request_hash,
                "expires_at": checkpoint.expires_at.isoformat(),
                "policy_version": policy.policy_version,
            },
            occurred_at=requested_at,
        )
    if created:
        metadata = _metadata(benchmark_result)
        control_link = _control_link(metadata)
        checkpoint_record_ids = list(control_link.get("checkpoint_record_ids", []))
        request_hashes = list(control_link.get("request_hashes", []))
        checkpoint_record_ids.extend(str(checkpoint.id) for checkpoint in created)
        request_hashes.extend(checkpoint.request_hash for checkpoint in created)
        metadata["agent_control_plane"] = {
            **control_link,
            "schema_version": AGENT_CONTROL_LINK_VERSION,
            "state_source": "agent_approval_checkpoints",
            "checkpoint_record_ids": list(dict.fromkeys(checkpoint_record_ids)),
            "request_hashes": list(dict.fromkeys(request_hashes)),
            "result_revision": int(control_link.get("result_revision") or 1),
        }
        benchmark_result.metadata_json = metadata
    return created


def list_agent_approval_checkpoints(
    db: Session,
    *,
    benchmark_run_id: UUID | None = None,
    benchmark_result_id: UUID | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AgentApprovalCheckpoint]:
    _expire_due_checkpoints(db)
    query = select(AgentApprovalCheckpoint)
    if benchmark_run_id is not None:
        query = query.where(
            AgentApprovalCheckpoint.benchmark_run_id == benchmark_run_id
        )
    if benchmark_result_id is not None:
        query = query.where(
            AgentApprovalCheckpoint.benchmark_result_id == benchmark_result_id
        )
    if status is not None:
        query = query.where(AgentApprovalCheckpoint.status == status)
    return list(
        db.scalars(
            query.order_by(
                AgentApprovalCheckpoint.created_at.desc(),
                AgentApprovalCheckpoint.checkpoint_id,
            )
            .offset(offset)
            .limit(limit)
        ).all()
    )


def get_agent_approval_checkpoint(
    db: Session,
    checkpoint_record_id: UUID,
) -> AgentApprovalCheckpoint:
    checkpoint = db.get(AgentApprovalCheckpoint, checkpoint_record_id)
    if checkpoint is None:
        raise DomainValidationError("agent approval checkpoint was not found")
    if _checkpoint_is_due(checkpoint):
        _mark_checkpoint_expired(db, checkpoint, now=_utcnow())
        db.commit()
        db.refresh(checkpoint)
    return checkpoint


def reconcile_agent_approval_checkpoints(
    db: Session,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    reconciled_at = now or _utcnow()
    due = list(
        db.scalars(
            select(AgentApprovalCheckpoint)
            .where(AgentApprovalCheckpoint.status.in_(["pending", "approved"]))
            .where(AgentApprovalCheckpoint.expires_at <= reconciled_at)
            .with_for_update()
        ).all()
    )
    for checkpoint in due:
        _mark_checkpoint_expired(db, checkpoint, now=reconciled_at)
    resumed_without_revision = db.scalar(
        select(func.count())
        .select_from(AgentApprovalCheckpoint)
        .where(AgentApprovalCheckpoint.status == "resumed")
        .where(
            or_(
                AgentApprovalCheckpoint.transition_benchmark_run_id.is_(None),
                AgentApprovalCheckpoint.transition_benchmark_result_id.is_(None),
            )
        )
    )
    return {
        "schema_version": "agent-checkpoint-reconciliation-v1",
        "reconciled_at": reconciled_at.isoformat(),
        "expired_count": len(due),
        "resumed_without_revision_count": int(resumed_without_revision or 0),
    }


def decide_agent_approval_checkpoint(
    db: Session,
    *,
    checkpoint_record_id: UUID,
    payload: AgentCheckpointDecisionCreate,
    signer_identity: SignerIdentity,
) -> AgentApprovalCheckpoint:
    checkpoint = _locked_checkpoint(db, checkpoint_record_id)
    now = _utcnow()
    _expire_and_reject_if_due(db, checkpoint, now=now)
    _assert_expected_version(checkpoint, payload.expected_version)
    if checkpoint.status != "pending":
        raise DomainValidationError(
            f"agent approval checkpoint cannot be decided from {checkpoint.status}"
        )
    policy = checkpoint_policy_from_json(checkpoint.approval_policy_json)
    policy_evaluation = assert_agent_checkpoint_operation_allowed(
        policy=policy,
        operation="decide",
        signer_identity=signer_identity,
        requester_subject_id=checkpoint.requested_by_subject_id,
    )
    decision_payload = {
        "checkpoint_record_id": str(checkpoint.id),
        "checkpoint_id": checkpoint.checkpoint_id,
        "request_hash": checkpoint.request_hash,
        "decision": payload.decision,
        "reason": payload.reason,
        "decided_at": now.isoformat(),
        "approver_identity": signer_identity.to_json(),
        "policy_evaluation": policy_evaluation.to_json(),
    }
    checkpoint.status = payload.decision
    checkpoint.decision = payload.decision
    checkpoint.decision_reason = payload.reason
    checkpoint.decided_at = now
    checkpoint.approver_identity_json = signer_identity.to_json()
    checkpoint.identity_verified = signer_identity.identity_verified
    checkpoint.decision_hash = _hash_payload(decision_payload)
    checkpoint.version += 1
    _add_log(
        db,
        benchmark_result=checkpoint.benchmark_result,
        event_type="agent_approval_checkpoint_decided",
        level="info" if payload.decision == "approved" else "warning",
        message=(
            f"Agent checkpoint {checkpoint.checkpoint_id} was {payload.decision}."
        ),
        payload_json={
            "checkpoint_record_id": str(checkpoint.id),
            "decision": payload.decision,
            "decision_hash": checkpoint.decision_hash,
            "policy_version": policy.policy_version,
            "identity_verified": signer_identity.identity_verified,
        },
        occurred_at=now,
    )
    if payload.decision == "denied":
        transition_result, _, _ = _apply_persisted_decisions(
            db,
            benchmark_result=checkpoint.benchmark_result,
            decision_records=[checkpoint],
            operator_identity=signer_identity,
            event_type="agent_execution_denied",
            now=now,
        )
        checkpoint.transition_benchmark_run_id = transition_result.benchmark_run_id
        checkpoint.transition_benchmark_result_id = transition_result.id
    db.commit()
    db.refresh(checkpoint)
    return checkpoint


def revoke_agent_approval_checkpoint(
    db: Session,
    *,
    checkpoint_record_id: UUID,
    payload: AgentCheckpointRevocationCreate,
    signer_identity: SignerIdentity,
) -> AgentApprovalCheckpoint:
    checkpoint = _locked_checkpoint(db, checkpoint_record_id)
    now = _utcnow()
    _expire_and_reject_if_due(db, checkpoint, now=now)
    _assert_expected_version(checkpoint, payload.expected_version)
    if checkpoint.status != "approved":
        raise DomainValidationError(
            f"agent approval checkpoint cannot be revoked from {checkpoint.status}"
        )
    policy = checkpoint_policy_from_json(checkpoint.approval_policy_json)
    policy_evaluation = assert_agent_checkpoint_operation_allowed(
        policy=policy,
        operation="revoke",
        signer_identity=signer_identity,
        requester_subject_id=checkpoint.requested_by_subject_id,
    )
    revocation_payload = {
        "checkpoint_record_id": str(checkpoint.id),
        "decision_hash": checkpoint.decision_hash,
        "reason": payload.reason,
        "revoked_at": now.isoformat(),
        "revoked_by": signer_identity.to_json(),
        "policy_evaluation": policy_evaluation.to_json(),
    }
    checkpoint.status = "revoked"
    checkpoint.revoked_at = now
    checkpoint.revocation_reason = payload.reason
    checkpoint.revoked_by_identity_json = signer_identity.to_json()
    checkpoint.revocation_hash = _hash_payload(revocation_payload)
    checkpoint.version += 1
    _add_log(
        db,
        benchmark_result=checkpoint.benchmark_result,
        event_type="agent_approval_checkpoint_revoked",
        level="warning",
        message=f"Agent checkpoint {checkpoint.checkpoint_id} approval was revoked.",
        payload_json={
            "checkpoint_record_id": str(checkpoint.id),
            "revocation_hash": checkpoint.revocation_hash,
            "policy_version": policy.policy_version,
        },
        occurred_at=now,
    )
    db.commit()
    db.refresh(checkpoint)
    return checkpoint


def resume_agent_approval_checkpoint(
    db: Session,
    *,
    checkpoint_record_id: UUID,
    expected_version: int,
    signer_identity: SignerIdentity,
) -> AgentCheckpointResumeOutcome:
    checkpoint = _locked_checkpoint(db, checkpoint_record_id)
    result = checkpoint.benchmark_result
    if checkpoint.status == "resumed":
        return _resume_outcome(checkpoint)
    now = _utcnow()
    _expire_and_reject_if_due(db, checkpoint, now=now)
    _assert_expected_version(checkpoint, expected_version)
    if checkpoint.status != "approved":
        raise DomainValidationError(
            f"agent approval checkpoint cannot resume from {checkpoint.status}"
        )
    policy = checkpoint_policy_from_json(checkpoint.approval_policy_json)
    policy_evaluation = assert_agent_checkpoint_operation_allowed(
        policy=policy,
        operation="resume",
        signer_identity=signer_identity,
        requester_subject_id=checkpoint.requested_by_subject_id,
    )
    records = list(
        db.scalars(
            select(AgentApprovalCheckpoint)
            .where(AgentApprovalCheckpoint.benchmark_result_id == result.id)
            .with_for_update()
        ).all()
    )
    blocking = next(
        (
            record
            for record in records
            if record.status in {"pending", "denied", "revoked", "expired"}
        ),
        None,
    )
    if blocking is not None:
        raise DomainValidationError(
            f"checkpoint {blocking.checkpoint_id} is {blocking.status} and blocks resume"
        )
    transition_result, trace, result_revision = _apply_persisted_decisions(
        db,
        benchmark_result=result,
        decision_records=records,
        operator_identity=signer_identity,
        event_type="agent_execution_resumed",
        now=now,
    )
    resumed_records = [record for record in records if record.status == "approved"]
    for record in resumed_records:
        resume_payload = {
            "schema_version": AGENT_RESUME_EVENT_VERSION,
            "checkpoint_record_id": str(record.id),
            "decision_hash": record.decision_hash,
            "result_revision": result_revision,
            "parent_benchmark_run_id": str(result.benchmark_run_id),
            "parent_benchmark_result_id": str(result.id),
            "benchmark_run_id": str(transition_result.benchmark_run_id),
            "benchmark_result_id": str(transition_result.id),
            "resumed_at": now.isoformat(),
            "resumed_by": signer_identity.to_json(),
            "policy_evaluation": policy_evaluation.to_json(),
        }
        record.status = "resumed"
        record.resumed_at = now
        record.resumed_by_identity_json = signer_identity.to_json()
        record.resume_hash = _hash_payload(resume_payload)
        record.transition_benchmark_run_id = transition_result.benchmark_run_id
        record.transition_benchmark_result_id = transition_result.id
        record.version += 1
    requester_identity = _identity_from_json(checkpoint.requested_by_identity_json)
    evaluation_case = result.evaluation_case
    if evaluation_case is None:
        raise DomainValidationError("agent checkpoint result has no evaluation case")
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    contract = reference.get("agent")
    contract = dict(contract) if isinstance(contract, dict) else {}
    materialize_pending_agent_checkpoints(
        db,
        benchmark_result=transition_result,
        trace=trace,
        contract=contract,
        requester_identity=requester_identity,
        now=now,
    )
    _add_log(
        db,
        benchmark_result=transition_result,
        event_type="agent_approval_checkpoint_resumed",
        level="info",
        message=f"Agent execution resumed from checkpoint {checkpoint.checkpoint_id}.",
        payload_json={
            "checkpoint_record_id": str(checkpoint.id),
            "parent_benchmark_run_id": str(result.benchmark_run_id),
            "parent_benchmark_result_id": str(result.id),
            "benchmark_run_id": str(transition_result.benchmark_run_id),
            "benchmark_result_id": str(transition_result.id),
            "result_revision": result_revision,
            "resume_hash": checkpoint.resume_hash,
            "trace_status": trace.get("status"),
        },
        occurred_at=now,
    )
    db.commit()
    db.refresh(checkpoint)
    return AgentCheckpointResumeOutcome(
        checkpoint=checkpoint,
        benchmark_run_id=transition_result.benchmark_run_id,
        benchmark_result_id=transition_result.id,
        parent_benchmark_run_id=result.benchmark_run_id,
        parent_benchmark_result_id=result.id,
        result_revision=result_revision,
        trace=trace,
        summary=summarize_agent_traces([trace]),
    )


def _apply_persisted_decisions(
    db: Session,
    *,
    benchmark_result: BenchmarkResult,
    decision_records: list[AgentApprovalCheckpoint],
    operator_identity: SignerIdentity,
    event_type: str,
    now: dt.datetime,
) -> tuple[BenchmarkResult, dict[str, Any], int]:
    evaluation_case = benchmark_result.evaluation_case
    benchmark_run = benchmark_result.benchmark_run
    configuration = benchmark_run.deployment_configuration
    if evaluation_case is None or configuration is None:
        raise DomainValidationError(
            "agent resume requires an evaluation case and deployment configuration"
        )
    metadata = _metadata(benchmark_result)
    original_trace = metadata.get("agent_execution")
    original_trace = original_trace if isinstance(original_trace, dict) else {}
    decisions = approval_decisions_from_agent_trace(original_trace)
    decisions.update({
        record.checkpoint_id: _decision_for_runtime(record)
        for record in decision_records
        if record.decision in {"approved", "denied"}
        and record.status in {"approved", "denied", "resumed"}
    })
    preparation = prepare_agent_execution(
        configuration,
        evaluation_case,
        include_mock_plan=False,
        approval_decisions=decisions,
    )
    if preparation is None:
        raise DomainValidationError("evaluation case is not an agent case")
    metric = db.scalar(
        select(InferenceMetric)
        .where(InferenceMetric.benchmark_run_id == benchmark_result.benchmark_run_id)
        .where(InferenceMetric.sample_id == benchmark_result.sample_id)
    )
    if metric is None:
        raise DomainValidationError("agent resume requires an inference metric")
    original_trace_duration = float(original_trace.get("total_duration_ms") or 0)
    original_retry_count = sum(
        int(step.get("retry_count") or 0)
        for step in original_trace.get("steps", [])
        if isinstance(step, dict)
    )
    base_metadata = {
        key: value
        for key, value in metadata.items()
        if key
        not in {
            "agent_execution",
            "agent_control_plane",
            "operational_memory_registry",
            "scorer",
        }
    }
    base_error_type = (
        None
        if benchmark_result.error_type == "agent_execution_failed"
        else benchmark_result.error_type
    )
    base_result = AdapterCaseResult(
        raw_output=benchmark_result.raw_output or "",
        normalized_output=benchmark_result.normalized_output or "",
        quality_score=None,
        exact_match=None,
        json_valid=benchmark_result.json_valid,
        tool_call_valid=benchmark_result.tool_call_valid,
        groundedness_score=None,
        faithfulness_score=None,
        human_label=benchmark_result.human_label,
        error_type=base_error_type,
        ttft_ms=metric.ttft_ms,
        end_to_end_latency_ms=max(
            0.0,
            metric.end_to_end_latency_ms - original_trace_duration,
        ),
        prompt_tokens=metric.prompt_tokens,
        completion_tokens=metric.completion_tokens,
        tokens_per_second=metric.tokens_per_second,
        gpu_vram_used_mb=metric.gpu_vram_used_mb,
        gpu_utilization_pct=metric.gpu_utilization_pct,
        cpu_utilization_pct=metric.cpu_utilization_pct,
        peak_memory_mb=metric.peak_memory_mb,
        oom_occurred=metric.oom_occurred,
        retry_count=max(0, metric.retry_count - original_retry_count),
        logs=[],
        metadata=base_metadata,
    )
    executed = attach_agent_execution(
        evaluation_case,
        base_result,
        preparation,
        live_replan_callback=build_agent_live_replan_callback(
            evaluation_case,
            mode=str(
                (benchmark_run.runtime_config_json or {}).get(
                    "agent_live_replan_mode", "disabled"
                )
            ),
            provider_config=dict(benchmark_run.runtime_config_json or {}),
        ),
    )
    scored = score_case_result(evaluation_case, executed)
    trace = scored.metadata.get("agent_execution")
    if not isinstance(trace, dict):
        raise DomainValidationError("agent resume did not produce an execution trace")

    control_link = _control_link(metadata)
    root_result_id = benchmark_result.root_benchmark_result_id or benchmark_result.id
    latest_revision = db.scalar(
        select(func.max(BenchmarkResult.revision_number)).where(
            or_(
                BenchmarkResult.id == root_result_id,
                BenchmarkResult.root_benchmark_result_id == root_result_id,
            )
        )
    )
    result_revision = max(
        int(latest_revision or 1),
        int(benchmark_result.revision_number or 1),
    ) + 1
    root_run_id = benchmark_run.root_benchmark_run_id or benchmark_run.id

    revision_run = BenchmarkRun(
        hardware_profile_id=benchmark_run.hardware_profile_id,
        model_artifact_id=benchmark_run.model_artifact_id,
        benchmark_task_id=benchmark_run.benchmark_task_id,
        prompt_version_id=benchmark_run.prompt_version_id,
        deployment_configuration_id=benchmark_run.deployment_configuration_id,
        evaluation_suite_id=benchmark_run.evaluation_suite_id,
        parent_benchmark_run_id=benchmark_run.id,
        root_benchmark_run_id=root_run_id,
        revision_number=result_revision,
        revision_reason=event_type,
        runtime_name=benchmark_run.runtime_name,
        runtime_version=benchmark_run.runtime_version,
        runtime_config_json={
            **dict(benchmark_run.runtime_config_json or {}),
            "agent_evidence_revision": {
                "schema_version": AGENT_EVIDENCE_REVISION_VERSION,
                "parent_benchmark_run_id": str(benchmark_run.id),
                "root_benchmark_run_id": str(root_run_id),
                "parent_benchmark_result_id": str(benchmark_result.id),
                "root_benchmark_result_id": str(root_result_id),
                "revision_number": result_revision,
                "transition": event_type,
            },
        },
        dataset_version=benchmark_run.dataset_version,
        seed=benchmark_run.seed,
        started_at=now,
        completed_at=now,
        status="completed",
        failure_reason=None,
        data_source=benchmark_run.data_source,
    )
    db.add(revision_run)
    db.flush()

    control_link = {
        **control_link,
        "schema_version": AGENT_CONTROL_LINK_VERSION,
        "state_source": "agent_approval_checkpoints",
        "result_revision": result_revision,
        "revision_mode": "append_only_child_run",
        "parent_benchmark_run_id": str(benchmark_run.id),
        "root_benchmark_run_id": str(root_run_id),
        "parent_benchmark_result_id": str(benchmark_result.id),
        "root_benchmark_result_id": str(root_result_id),
        "parent_evidence_revision_hash": benchmark_result.evidence_revision_hash,
        "last_transition": event_type,
        "last_transition_at": now.isoformat(),
        "last_transition_by": operator_identity.to_json(),
    }
    revision_result = BenchmarkResult(
        benchmark_run_id=revision_run.id,
        evaluation_case_id=benchmark_result.evaluation_case_id,
        parent_benchmark_result_id=benchmark_result.id,
        root_benchmark_result_id=root_result_id,
        revision_number=result_revision,
        sample_id=benchmark_result.sample_id,
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
            "agent_control_plane": control_link,
        },
        data_source=benchmark_result.data_source,
    )
    db.add(revision_result)
    db.flush()
    revision_result.evidence_revision_hash = _hash_payload(
        {
            "schema_version": AGENT_EVIDENCE_REVISION_VERSION,
            "benchmark_run_id": str(revision_run.id),
            "benchmark_result_id": str(revision_result.id),
            "parent_benchmark_result_id": str(benchmark_result.id),
            "root_benchmark_result_id": str(root_result_id),
            "revision_number": result_revision,
            "transition": event_type,
            "trace": trace,
            "scores": {
                "quality_score": scored.quality_score,
                "exact_match": scored.exact_match,
                "json_valid": scored.json_valid,
                "tool_call_valid": scored.tool_call_valid,
                "error_type": scored.error_type,
            },
        }
    )
    revision_run.evidence_revision_hash = _hash_payload(
        {
            "schema_version": AGENT_EVIDENCE_REVISION_VERSION,
            "benchmark_run_id": str(revision_run.id),
            "parent_benchmark_run_id": str(benchmark_run.id),
            "root_benchmark_run_id": str(root_run_id),
            "revision_number": result_revision,
            "result_revision_hash": revision_result.evidence_revision_hash,
        }
    )
    revision_metric = InferenceMetric(
        benchmark_run_id=revision_run.id,
        sample_id=benchmark_result.sample_id,
        ttft_ms=metric.ttft_ms,
        end_to_end_latency_ms=scored.end_to_end_latency_ms,
        prompt_tokens=scored.prompt_tokens,
        completion_tokens=scored.completion_tokens,
        tokens_per_second=scored.tokens_per_second,
        gpu_vram_used_mb=scored.gpu_vram_used_mb,
        gpu_utilization_pct=scored.gpu_utilization_pct,
        cpu_utilization_pct=scored.cpu_utilization_pct,
        peak_memory_mb=scored.peak_memory_mb,
        oom_occurred=scored.oom_occurred,
        retry_count=scored.retry_count,
        data_source=benchmark_result.data_source,
    )
    db.add(revision_metric)
    db.flush()
    for log in scored.logs:
        _add_log(
            db,
            benchmark_result=revision_result,
            event_type=str(log.get("event_type") or "agent_execution_event"),
            level=str(log.get("level") or "info"),
            message=str(log.get("message") or "Agent execution event."),
            payload_json=(
                log.get("payload_json")
                if isinstance(log.get("payload_json"), dict)
                else None
            ),
            occurred_at=now,
        )
    _add_log(
        db,
        benchmark_result=revision_result,
        event_type=event_type,
        level="info" if trace.get("successful") else "warning",
        message=f"Agent result advanced to revision {result_revision}.",
        payload_json={
            "result_revision": result_revision,
            "benchmark_run_id": str(revision_run.id),
            "benchmark_result_id": str(revision_result.id),
            "parent_benchmark_run_id": str(benchmark_run.id),
            "parent_benchmark_result_id": str(benchmark_result.id),
            "evidence_revision_hash": revision_result.evidence_revision_hash,
            "trace_status": trace.get("status"),
            "checkpoint_record_ids": [str(record.id) for record in decision_records],
        },
        occurred_at=now,
    )
    if benchmark_run.deployment_configuration_id and benchmark_run.evaluation_suite_id:
        mark_scope_gates_stale(
            db,
            deployment_configuration_id=benchmark_run.deployment_configuration_id,
            evaluation_suite_id=benchmark_run.evaluation_suite_id,
            reason=(
                "Agent evidence advanced through an append-only result revision. "
                "Run the Deployment Gate again."
            ),
            now=now,
        )
    return revision_result, trace, result_revision


def _resume_outcome(
    checkpoint: AgentApprovalCheckpoint,
) -> AgentCheckpointResumeOutcome:
    transition_result_id = checkpoint.transition_benchmark_result_id
    transition_run_id = checkpoint.transition_benchmark_run_id
    if transition_result_id is None or transition_run_id is None:
        raise DomainValidationError("resumed checkpoint is missing its result revision link")
    session = Session.object_session(checkpoint)
    if session is None:
        raise DomainValidationError("resumed checkpoint is detached from its session")
    transition_result = session.get(BenchmarkResult, transition_result_id)
    if transition_result is None:
        raise DomainValidationError("resumed checkpoint result revision was not found")
    metadata = _metadata(transition_result)
    trace = metadata.get("agent_execution")
    if not isinstance(trace, dict):
        raise DomainValidationError("resumed agent result does not contain a trace")
    control_link = _control_link(metadata)
    return AgentCheckpointResumeOutcome(
        checkpoint=checkpoint,
        benchmark_run_id=transition_run_id,
        benchmark_result_id=transition_result_id,
        parent_benchmark_run_id=checkpoint.benchmark_run_id,
        parent_benchmark_result_id=checkpoint.benchmark_result_id,
        result_revision=int(control_link.get("result_revision") or 1),
        trace=trace,
        summary=summarize_agent_traces([trace]),
    )


def _locked_checkpoint(
    db: Session,
    checkpoint_record_id: UUID,
) -> AgentApprovalCheckpoint:
    checkpoint = db.scalar(
        select(AgentApprovalCheckpoint)
        .where(AgentApprovalCheckpoint.id == checkpoint_record_id)
        .with_for_update()
    )
    if checkpoint is None:
        raise DomainValidationError("agent approval checkpoint was not found")
    return checkpoint


def _assert_expected_version(
    checkpoint: AgentApprovalCheckpoint,
    expected_version: int,
) -> None:
    if checkpoint.version != expected_version:
        raise DomainValidationError(
            "agent approval checkpoint version conflict: "
            f"expected {expected_version}, current {checkpoint.version}"
        )


def _expire_due_checkpoints(db: Session) -> None:
    outcome = reconcile_agent_approval_checkpoints(db)
    if outcome["expired_count"]:
        db.commit()


def _expire_and_reject_if_due(
    db: Session,
    checkpoint: AgentApprovalCheckpoint,
    *,
    now: dt.datetime,
) -> None:
    if not _checkpoint_is_due(checkpoint, now=now):
        return
    _mark_checkpoint_expired(db, checkpoint, now=now)
    db.commit()
    raise DomainValidationError("agent approval checkpoint has expired")


def _checkpoint_is_due(
    checkpoint: AgentApprovalCheckpoint,
    *,
    now: dt.datetime | None = None,
) -> bool:
    return checkpoint.status in {"pending", "approved"} and checkpoint.expires_at <= (
        now or _utcnow()
    )


def _mark_checkpoint_expired(
    db: Session,
    checkpoint: AgentApprovalCheckpoint,
    *,
    now: dt.datetime,
) -> None:
    previous_status = checkpoint.status
    checkpoint.status = "expired"
    checkpoint.version += 1
    _add_log(
        db,
        benchmark_result=checkpoint.benchmark_result,
        event_type="agent_approval_checkpoint_expired",
        level="warning",
        message=f"Agent checkpoint {checkpoint.checkpoint_id} expired.",
        payload_json={
            "checkpoint_record_id": str(checkpoint.id),
            "previous_status": previous_status,
            "expires_at": checkpoint.expires_at.isoformat(),
        },
        occurred_at=now,
    )


def _decision_for_runtime(checkpoint: AgentApprovalCheckpoint) -> dict[str, Any]:
    approver = checkpoint.approver_identity_json or {}
    return {
        "decision": checkpoint.decision,
        "decided_by": str(approver.get("display_name") or approver.get("subject_id") or ""),
        "reason": checkpoint.decision_reason,
        "decision_source": "persisted_agent_control_plane",
        "policy_version": str(
            checkpoint.approval_policy_json.get("policy_version") or ""
        ),
        "decision_hash": checkpoint.decision_hash,
        "identity_verified": checkpoint.identity_verified,
        "approver_identity": approver,
        "decided_at": (
            checkpoint.decided_at.isoformat() if checkpoint.decided_at else None
        ),
        "checkpoint_record_id": str(checkpoint.id),
    }


def _pending_checkpoint_steps(trace: dict[str, Any]) -> list[dict[str, Any]]:
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return []
    return [
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("action") == "approval_checkpoint"
        and step.get("status") == "pending"
    ]


def _checkpoint_request_snapshot(
    *,
    benchmark_result: BenchmarkResult,
    trace: dict[str, Any],
    step: dict[str, Any],
    checkpoint_id: str,
) -> dict[str, Any]:
    evaluation_case = benchmark_result.evaluation_case
    return {
        "schema_version": AGENT_APPROVAL_REQUEST_VERSION,
        "benchmark_run_id": str(benchmark_result.benchmark_run_id),
        "benchmark_result_id": str(benchmark_result.id),
        "evaluation_case_id": (
            str(benchmark_result.evaluation_case_id)
            if benchmark_result.evaluation_case_id
            else None
        ),
        "external_case_id": (
            evaluation_case.external_case_id if evaluation_case is not None else None
        ),
        "sample_id": benchmark_result.sample_id,
        "checkpoint_id": checkpoint_id,
        "step_index": step.get("step_index"),
        "checkpoint_input": step.get("input") if isinstance(step.get("input"), dict) else {},
        "guarded_actions": _guarded_actions(trace, checkpoint_id),
        "trace_versions": {
            key: trace.get(key)
            for key in (
                "schema_version",
                "runtime_version",
                "recovery_policy_version",
                "approval_policy_version",
            )
        },
    }


def _guarded_actions(trace: dict[str, Any], checkpoint_id: str) -> list[dict[str, Any]]:
    steps = trace.get("steps")
    if not isinstance(steps, list):
        return []
    guarded: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        input_payload = step.get("input")
        input_payload = input_payload if isinstance(input_payload, dict) else {}
        if str(input_payload.get("requires_approval") or "") != checkpoint_id:
            continue
        guarded.append(
            {
                "step_index": step.get("step_index"),
                "action": step.get("action"),
                "phase": step.get("phase"),
            }
        )
    return guarded


def _add_log(
    db: Session,
    *,
    benchmark_result: BenchmarkResult,
    event_type: str,
    level: str,
    message: str,
    payload_json: dict[str, Any] | None,
    occurred_at: dt.datetime,
) -> None:
    db.add(
        BenchmarkExecutionLog(
            benchmark_run_id=benchmark_result.benchmark_run_id,
            event_type=event_type,
            level=level,
            message=message,
            payload_json=payload_json,
            occurred_at=occurred_at,
            data_source=benchmark_result.data_source,
        )
    )


def _metadata(benchmark_result: BenchmarkResult) -> dict[str, Any]:
    return (
        dict(benchmark_result.metadata_json)
        if isinstance(benchmark_result.metadata_json, dict)
        else {}
    )


def _control_link(metadata: dict[str, Any]) -> dict[str, Any]:
    value = metadata.get("agent_control_plane")
    return dict(value) if isinstance(value, dict) else {}


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _identity_from_json(payload: dict[str, Any]) -> SignerIdentity:
    return SignerIdentity(
        subject_id=str(payload.get("subject_id") or "unknown-requester"),
        display_name=str(payload.get("display_name") or "Unknown requester"),
        role=str(payload["role"]) if payload.get("role") else None,
        identity_provider=str(payload.get("identity_provider") or "unknown"),
        auth_source=str(payload.get("auth_source") or "unknown"),
        identity_verified=bool(payload.get("identity_verified", False)),
        ticket_reference=(
            str(payload["ticket_reference"])
            if payload.get("ticket_reference")
            else None
        ),
    )
