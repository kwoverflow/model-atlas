from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkRun,
    DeploymentBaseline,
    ExperimentLineageEvent,
    GateEvaluation,
    PromptVersion,
    ReleaseDecision,
)
from app.schemas import ExperimentLineageReport


@dataclass(frozen=True)
class LineageMaterializeSummary:
    created_count: int
    existing_count: int
    event_count: int


def _id_part(label: str, value: UUID | None) -> str:
    return f"{label}:{value}" if value is not None else f"{label}:none"


def lineage_key(
    *,
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
) -> str:
    return "|".join(
        [
            _id_part("deployment", deployment_configuration_id),
            _id_part("suite", evaluation_suite_id),
            _id_part("policy", acceptance_policy_id),
            _id_part("prompt", prompt_version_id),
        ]
    )


def _record_lineage_event(
    db: Session,
    *,
    event_type: str,
    primary_entity_type: str,
    primary_entity_id: UUID,
    event_time,
    lineage_key_value: str,
    summary: str,
    status: str = "recorded",
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    benchmark_run_id: UUID | None = None,
    gate_evaluation_id: UUID | None = None,
    deployment_baseline_id: UUID | None = None,
    release_decision_id: UUID | None = None,
    metadata_json: dict | None = None,
    data_source: str = "system",
) -> tuple[ExperimentLineageEvent, bool]:
    existing = db.scalar(
        select(ExperimentLineageEvent).where(
            ExperimentLineageEvent.event_type == event_type,
            ExperimentLineageEvent.primary_entity_id == primary_entity_id,
        )
    )
    if existing is not None:
        return existing, False

    event = ExperimentLineageEvent(
        event_type=event_type,
        primary_entity_type=primary_entity_type,
        primary_entity_id=primary_entity_id,
        event_time=event_time,
        lineage_key=lineage_key_value,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
        prompt_version_id=prompt_version_id,
        benchmark_run_id=benchmark_run_id,
        gate_evaluation_id=gate_evaluation_id,
        deployment_baseline_id=deployment_baseline_id,
        release_decision_id=release_decision_id,
        status=status,
        summary=summary,
        metadata_json=metadata_json,
        data_source=data_source,
    )
    db.add(event)
    return event, True


def record_prompt_version_created(
    db: Session,
    prompt: PromptVersion,
    *,
    commit: bool = False,
) -> ExperimentLineageEvent:
    event, _ = _record_lineage_event(
        db,
        event_type="prompt_version_created",
        primary_entity_type="prompt_version",
        primary_entity_id=prompt.id,
        event_time=prompt.created_at,
        lineage_key_value=lineage_key(prompt_version_id=prompt.id),
        prompt_version_id=prompt.id,
        summary=f"Prompt version {prompt.name} {prompt.version_label} was created.",
        metadata_json={
            "benchmark_task_id": str(prompt.benchmark_task_id),
            "prompt_hash": prompt.prompt_hash,
            "version_label": prompt.version_label,
            "is_active": prompt.is_active,
        },
    )
    if commit:
        db.commit()
        db.refresh(event)
    return event


def _benchmark_run_event_type(run: BenchmarkRun) -> str:
    if run.status == "completed":
        return "benchmark_run_completed"
    if run.status == "failed":
        return "benchmark_run_failed"
    return "benchmark_run_created"


def record_benchmark_run_event(
    db: Session,
    run: BenchmarkRun,
    *,
    commit: bool = False,
) -> ExperimentLineageEvent:
    event_type = _benchmark_run_event_type(run)
    event_time = run.completed_at or run.started_at or run.created_at
    status = "failed" if event_type == "benchmark_run_failed" else "recorded"
    event, _ = _record_lineage_event(
        db,
        event_type=event_type,
        primary_entity_type="benchmark_run",
        primary_entity_id=run.id,
        event_time=event_time,
        lineage_key_value=lineage_key(
            deployment_configuration_id=run.deployment_configuration_id,
            evaluation_suite_id=run.evaluation_suite_id,
            prompt_version_id=run.prompt_version_id,
        ),
        deployment_configuration_id=run.deployment_configuration_id,
        evaluation_suite_id=run.evaluation_suite_id,
        prompt_version_id=run.prompt_version_id,
        benchmark_run_id=run.id,
        status=status,
        summary=f"Benchmark run {str(run.id)[:8]} {run.status}.",
        metadata_json={
            "hardware_profile_id": str(run.hardware_profile_id),
            "model_artifact_id": str(run.model_artifact_id),
            "benchmark_task_id": str(run.benchmark_task_id),
            "runtime_name": run.runtime_name,
            "runtime_version": run.runtime_version,
            "dataset_version": run.dataset_version,
            "failure_reason": run.failure_reason,
        },
        data_source=run.data_source,
    )
    if commit:
        db.commit()
        db.refresh(event)
    return event


def record_gate_evaluation_completed(
    db: Session,
    gate: GateEvaluation,
    *,
    commit: bool = False,
) -> ExperimentLineageEvent:
    event, _ = _record_gate_without_commit(db, gate)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def record_baseline_promoted(
    db: Session,
    baseline: DeploymentBaseline,
    *,
    commit: bool = False,
) -> ExperimentLineageEvent:
    event, _ = _record_baseline_without_commit(db, baseline)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def record_baseline_superseded(
    db: Session,
    baseline: DeploymentBaseline,
    *,
    commit: bool = False,
) -> ExperimentLineageEvent:
    event, _ = _record_superseded_without_commit(db, baseline)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def record_release_decision_signed(
    db: Session,
    release_decision: ReleaseDecision,
    *,
    commit: bool = False,
) -> ExperimentLineageEvent:
    event, _ = _record_release_decision_without_commit(db, release_decision)
    if commit:
        db.commit()
        db.refresh(event)
    return event


def materialize_experiment_lineage(db: Session) -> LineageMaterializeSummary:
    created = 0
    existing = 0

    for prompt in db.scalars(select(PromptVersion)).all():
        _, was_created = _record_prompt_without_commit(db, prompt)
        created += int(was_created)
        existing += int(not was_created)

    for run in db.scalars(select(BenchmarkRun)).all():
        _, was_created = _record_benchmark_run_without_commit(db, run)
        created += int(was_created)
        existing += int(not was_created)

    for gate in db.scalars(select(GateEvaluation)).all():
        _, was_created = _record_gate_without_commit(db, gate)
        created += int(was_created)
        existing += int(not was_created)

    for baseline in db.scalars(select(DeploymentBaseline)).all():
        _, was_created = _record_baseline_without_commit(db, baseline)
        created += int(was_created)
        existing += int(not was_created)
        if baseline.status == "superseded":
            _, was_created = _record_superseded_without_commit(db, baseline)
            created += int(was_created)
            existing += int(not was_created)

    for release_decision in db.scalars(select(ReleaseDecision)).all():
        _, was_created = _record_release_decision_without_commit(db, release_decision)
        created += int(was_created)
        existing += int(not was_created)

    db.commit()
    event_count = int(db.scalar(select(func.count()).select_from(ExperimentLineageEvent)) or 0)
    return LineageMaterializeSummary(
        created_count=created,
        existing_count=existing,
        event_count=event_count,
    )


def list_experiment_lineage_events(
    db: Session,
    *,
    limit: int,
    offset: int,
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    event_type: str | None = None,
    sync_missing: bool = True,
) -> list[ExperimentLineageEvent]:
    if sync_missing:
        materialize_experiment_lineage(db)

    query = select(ExperimentLineageEvent)
    if deployment_configuration_id is not None:
        query = query.where(
            ExperimentLineageEvent.deployment_configuration_id == deployment_configuration_id
        )
    if evaluation_suite_id is not None:
        query = query.where(ExperimentLineageEvent.evaluation_suite_id == evaluation_suite_id)
    if acceptance_policy_id is not None:
        query = query.where(ExperimentLineageEvent.acceptance_policy_id == acceptance_policy_id)
    if prompt_version_id is not None:
        query = query.where(ExperimentLineageEvent.prompt_version_id == prompt_version_id)
    if event_type is not None:
        query = query.where(ExperimentLineageEvent.event_type == event_type)
    return list(
        db.scalars(
            query.order_by(
                ExperimentLineageEvent.event_time.desc(),
                ExperimentLineageEvent.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        ).all()
    )


def build_experiment_lineage_report(
    db: Session,
    *,
    limit: int,
    offset: int = 0,
    deployment_configuration_id: UUID | None = None,
    evaluation_suite_id: UUID | None = None,
    acceptance_policy_id: UUID | None = None,
    prompt_version_id: UUID | None = None,
    event_type: str | None = None,
) -> ExperimentLineageReport:
    events = list_experiment_lineage_events(
        db,
        limit=limit,
        offset=offset,
        deployment_configuration_id=deployment_configuration_id,
        evaluation_suite_id=evaluation_suite_id,
        acceptance_policy_id=acceptance_policy_id,
        prompt_version_id=prompt_version_id,
        event_type=event_type,
    )
    lineage_count = len({event.lineage_key for event in events})
    return ExperimentLineageReport(
        event_count=len(events),
        lineage_count=lineage_count,
        benchmark_run_event_count=sum(
            1 for event in events if event.primary_entity_type == "benchmark_run"
        ),
        gate_event_count=sum(
            1 for event in events if event.primary_entity_type == "gate_evaluation"
        ),
        baseline_event_count=sum(
            1 for event in events if event.primary_entity_type == "deployment_baseline"
        ),
        release_decision_event_count=sum(
            1 for event in events if event.primary_entity_type == "release_decision"
        ),
        events=events,
    )


def _record_prompt_without_commit(
    db: Session,
    prompt: PromptVersion,
) -> tuple[ExperimentLineageEvent, bool]:
    return _record_lineage_event(
        db,
        event_type="prompt_version_created",
        primary_entity_type="prompt_version",
        primary_entity_id=prompt.id,
        event_time=prompt.created_at,
        lineage_key_value=lineage_key(prompt_version_id=prompt.id),
        prompt_version_id=prompt.id,
        summary=f"Prompt version {prompt.name} {prompt.version_label} was created.",
        metadata_json={
            "benchmark_task_id": str(prompt.benchmark_task_id),
            "prompt_hash": prompt.prompt_hash,
            "version_label": prompt.version_label,
            "is_active": prompt.is_active,
        },
    )


def _record_benchmark_run_without_commit(
    db: Session,
    run: BenchmarkRun,
) -> tuple[ExperimentLineageEvent, bool]:
    event_type = _benchmark_run_event_type(run)
    event_time = run.completed_at or run.started_at or run.created_at
    status = "failed" if event_type == "benchmark_run_failed" else "recorded"
    return _record_lineage_event(
        db,
        event_type=event_type,
        primary_entity_type="benchmark_run",
        primary_entity_id=run.id,
        event_time=event_time,
        lineage_key_value=lineage_key(
            deployment_configuration_id=run.deployment_configuration_id,
            evaluation_suite_id=run.evaluation_suite_id,
            prompt_version_id=run.prompt_version_id,
        ),
        deployment_configuration_id=run.deployment_configuration_id,
        evaluation_suite_id=run.evaluation_suite_id,
        prompt_version_id=run.prompt_version_id,
        benchmark_run_id=run.id,
        status=status,
        summary=f"Benchmark run {str(run.id)[:8]} {run.status}.",
        metadata_json={
            "hardware_profile_id": str(run.hardware_profile_id),
            "model_artifact_id": str(run.model_artifact_id),
            "benchmark_task_id": str(run.benchmark_task_id),
            "runtime_name": run.runtime_name,
            "runtime_version": run.runtime_version,
            "dataset_version": run.dataset_version,
            "failure_reason": run.failure_reason,
        },
        data_source=run.data_source,
    )


def _record_gate_without_commit(
    db: Session,
    gate: GateEvaluation,
) -> tuple[ExperimentLineageEvent, bool]:
    prompt_ids = _prompt_ids_for_run_ids(
        db,
        (gate.evidence_snapshot_json or {}).get("benchmark_run_ids", []),
    )
    prompt_version_id = prompt_ids[0] if len(prompt_ids) == 1 else None
    return _record_lineage_event(
        db,
        event_type="gate_evaluation_completed",
        primary_entity_type="gate_evaluation",
        primary_entity_id=gate.id,
        event_time=gate.evaluated_at,
        lineage_key_value=lineage_key(
            deployment_configuration_id=gate.deployment_configuration_id,
            evaluation_suite_id=gate.evaluation_suite_id,
            acceptance_policy_id=gate.acceptance_policy_id,
            prompt_version_id=prompt_version_id,
        ),
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        acceptance_policy_id=gate.acceptance_policy_id,
        prompt_version_id=prompt_version_id,
        gate_evaluation_id=gate.id,
        summary=f"Gate evaluation {str(gate.id)[:8]} returned {gate.verdict}.",
        metadata_json={
            "verdict": gate.verdict,
            "decision_hash": gate.decision_hash,
            "baseline_gate_evaluation_id": (
                str(gate.baseline_gate_evaluation_id)
                if gate.baseline_gate_evaluation_id
                else None
            ),
            "benchmark_run_ids": (gate.evidence_snapshot_json or {}).get(
                "benchmark_run_ids",
                [],
            ),
            "prompt_version_ids": [str(prompt_id) for prompt_id in prompt_ids],
        },
    )


def _record_baseline_without_commit(
    db: Session,
    baseline: DeploymentBaseline,
) -> tuple[ExperimentLineageEvent, bool]:
    gate = db.get(GateEvaluation, baseline.gate_evaluation_id)
    prompt_ids = _prompt_ids_for_run_ids(
        db,
        (gate.evidence_snapshot_json or {}).get("benchmark_run_ids", []) if gate else [],
    )
    prompt_version_id = prompt_ids[0] if len(prompt_ids) == 1 else None
    return _record_lineage_event(
        db,
        event_type="baseline_promoted",
        primary_entity_type="deployment_baseline",
        primary_entity_id=baseline.id,
        event_time=baseline.promoted_at,
        lineage_key_value=lineage_key(
            deployment_configuration_id=baseline.deployment_configuration_id,
            evaluation_suite_id=baseline.evaluation_suite_id,
            acceptance_policy_id=baseline.acceptance_policy_id,
            prompt_version_id=prompt_version_id,
        ),
        deployment_configuration_id=baseline.deployment_configuration_id,
        evaluation_suite_id=baseline.evaluation_suite_id,
        acceptance_policy_id=baseline.acceptance_policy_id,
        prompt_version_id=prompt_version_id,
        gate_evaluation_id=baseline.gate_evaluation_id,
        deployment_baseline_id=baseline.id,
        summary=f"Gate {str(baseline.gate_evaluation_id)[:8]} was promoted as baseline.",
        metadata_json={
            "baseline_hash": baseline.baseline_hash,
            "promoted_by": baseline.promoted_by,
            "promotion_reason": baseline.promotion_reason,
            "prompt_version_ids": [str(prompt_id) for prompt_id in prompt_ids],
        },
    )


def _record_superseded_without_commit(
    db: Session,
    baseline: DeploymentBaseline,
) -> tuple[ExperimentLineageEvent, bool]:
    return _record_lineage_event(
        db,
        event_type="baseline_superseded",
        primary_entity_type="deployment_baseline",
        primary_entity_id=baseline.id,
        event_time=baseline.superseded_at or baseline.updated_at,
        lineage_key_value=lineage_key(
            deployment_configuration_id=baseline.deployment_configuration_id,
            evaluation_suite_id=baseline.evaluation_suite_id,
            acceptance_policy_id=baseline.acceptance_policy_id,
        ),
        deployment_configuration_id=baseline.deployment_configuration_id,
        evaluation_suite_id=baseline.evaluation_suite_id,
        acceptance_policy_id=baseline.acceptance_policy_id,
        gate_evaluation_id=baseline.gate_evaluation_id,
        deployment_baseline_id=baseline.id,
        status="superseded",
        summary=f"Baseline {str(baseline.id)[:8]} was superseded.",
        metadata_json={
            "baseline_hash": baseline.baseline_hash,
            "superseded_by_baseline_id": (
                str(baseline.superseded_by_baseline_id)
                if baseline.superseded_by_baseline_id
                else None
            ),
        },
    )


def _record_release_decision_without_commit(
    db: Session,
    release_decision: ReleaseDecision,
) -> tuple[ExperimentLineageEvent, bool]:
    gate = db.get(GateEvaluation, release_decision.gate_evaluation_id)
    prompt_ids = _prompt_ids_for_run_ids(
        db,
        (gate.evidence_snapshot_json or {}).get("benchmark_run_ids", []) if gate else [],
    )
    prompt_version_id = prompt_ids[0] if len(prompt_ids) == 1 else None
    return _record_lineage_event(
        db,
        event_type="release_decision_signed",
        primary_entity_type="release_decision",
        primary_entity_id=release_decision.id,
        event_time=release_decision.decided_at,
        lineage_key_value=lineage_key(
            deployment_configuration_id=release_decision.deployment_configuration_id,
            evaluation_suite_id=release_decision.evaluation_suite_id,
            acceptance_policy_id=release_decision.acceptance_policy_id,
            prompt_version_id=prompt_version_id,
        ),
        deployment_configuration_id=release_decision.deployment_configuration_id,
        evaluation_suite_id=release_decision.evaluation_suite_id,
        acceptance_policy_id=release_decision.acceptance_policy_id,
        prompt_version_id=prompt_version_id,
        gate_evaluation_id=release_decision.gate_evaluation_id,
        release_decision_id=release_decision.id,
        summary=(
            f"Release decision {str(release_decision.id)[:8]} signed "
            f"{release_decision.decision}."
        ),
        metadata_json={
            "decision": release_decision.decision,
            "release_readiness_status": release_decision.release_readiness_status,
            "decided_by": release_decision.decided_by,
            "identity_verified": release_decision.identity_verified,
            "signer_identity": release_decision.signer_identity_json,
            "approval_policy": release_decision.approval_policy_json,
            "decision_hash": release_decision.decision_hash,
            "signature_hash": release_decision.signature_hash,
            "snapshot_hash": release_decision.snapshot_hash,
            "prompt_version_ids": [str(prompt_id) for prompt_id in prompt_ids],
        },
    )


def _prompt_ids_for_run_ids(db: Session, run_ids: list[str]) -> list[UUID]:
    if not run_ids:
        return []
    runs = db.scalars(select(BenchmarkRun).where(BenchmarkRun.id.in_(run_ids))).all()
    return list(dict.fromkeys(run.prompt_version_id for run in runs))
