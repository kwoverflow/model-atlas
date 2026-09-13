from __future__ import annotations

from collections import Counter
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    DeploymentBaseline,
    DeploymentConfiguration,
    GateEvaluation,
    ReleaseDecision,
    WorkloadProfile,
)
from app.schemas.analytics import (
    ControlPlaneLatestGate,
    ControlPlaneNextAction,
    ControlPlaneOverviewResponse,
    ControlPlaneRecentRun,
    ControlPlaneWorkflowStep,
)
from app.schemas.release_readiness import ReleaseReadinessSnapshot
from app.services.analytics import get_overview
from app.services.evidence_trust import normalize_source_tier
from app.services.release_readiness import build_release_readiness_snapshot
from app.services.supply_chain import verified_production_run_ids
from app.validators import DomainValidationError

Priority = Literal["high", "medium", "low"]
WorkflowStatus = Literal["complete", "attention", "not_started"]
OverviewMode = Literal["empty", "demo", "production_evidence"]
PRIORITY_ORDER: dict[Priority, int] = {"high": 0, "medium": 1, "low": 2}


def build_control_plane_overview(db: Session) -> ControlPlaneOverviewResponse:
    inventory = get_overview(db)
    gates = list(
        db.scalars(
            select(GateEvaluation).order_by(
                GateEvaluation.evaluated_at.desc(),
                GateEvaluation.created_at.desc(),
            )
        )
    )
    latest_by_configuration: dict[UUID, GateEvaluation] = {}
    for gate in gates:
        latest_by_configuration.setdefault(gate.deployment_configuration_id, gate)

    readiness_by_gate: dict[UUID, ReleaseReadinessSnapshot] = {}
    for gate in latest_by_configuration.values():
        try:
            readiness_by_gate[gate.id] = build_release_readiness_snapshot(
                db,
                gate_evaluation_id=gate.id,
            )
        except DomainValidationError:
            continue

    release_ready_count = sum(
        1
        for snapshot in readiness_by_gate.values()
        if snapshot.status in {"READY", "READY_TO_PROMOTE"}
    )
    needs_review_count = sum(
        1 for snapshot in readiness_by_gate.values() if snapshot.status == "NEEDS_REVIEW"
    )

    results = list(db.scalars(select(BenchmarkResult)))
    verified_production_ids = verified_production_run_ids(
        db,
        {result.benchmark_run_id for result in results},
    )
    source_counts: Counter[str] = Counter()
    for result in results:
        source = normalize_source_tier(result.data_source).value
        if (
            source == "production_captured"
            and result.benchmark_run_id not in verified_production_ids
        ):
            source = "production_captured_unverified"
        source_counts[source] += 1
    failed_critical_case_count = sum(
        1
        for gate in latest_by_configuration.values()
        for outcome in (gate.scorecard_json or {}).get("critical_case_outcomes", [])
        if outcome.get("status") == "fail"
    )
    active_baseline_count = _count(
        db,
        select(func.count())
        .select_from(DeploymentBaseline)
        .where(DeploymentBaseline.status == "active"),
    )
    latest_gate = gates[0] if gates else None
    latest_readiness = readiness_by_gate.get(latest_gate.id) if latest_gate else None

    workload_count = _count(db, select(func.count()).select_from(WorkloadProfile))
    configuration_count = _count(
        db,
        select(func.count()).select_from(DeploymentConfiguration),
    )
    completed_run_count = _count(
        db,
        select(func.count())
        .select_from(BenchmarkRun)
        .where(BenchmarkRun.status == "completed"),
    )
    release_decision_count = _count(db, select(func.count()).select_from(ReleaseDecision))

    recent_runs = list(
        db.scalars(select(BenchmarkRun).order_by(BenchmarkRun.started_at.desc()).limit(5))
    )
    return ControlPlaneOverviewResponse(
        mode=_mode(source_counts, len(results)),
        latest_gate=_latest_gate_summary(latest_gate, latest_readiness),
        release_ready_configuration_count=release_ready_count,
        needs_review_count=needs_review_count,
        production_evidence_result_count=source_counts["production_captured"],
        local_authored_result_count=source_counts["local_authored"],
        synthetic_evidence_result_count=source_counts["synthetic_demo"],
        unknown_evidence_result_count=(
            source_counts["unknown"]
            + source_counts["production_captured_unverified"]
        ),
        failed_critical_case_count=failed_critical_case_count,
        active_baseline_count=active_baseline_count,
        next_actions=_next_actions(
            workload_count=workload_count,
            configuration_count=configuration_count,
            completed_run_count=completed_run_count,
            latest_gate=latest_gate,
            latest_readiness=latest_readiness,
            failed_critical_case_count=failed_critical_case_count,
            needs_review_count=needs_review_count,
            active_baseline_count=active_baseline_count,
            production_evidence_count=source_counts["production_captured"],
        ),
        workflow_steps=_workflow_steps(
            workload_count=workload_count,
            configuration_count=configuration_count,
            completed_run_count=completed_run_count,
            latest_gate=latest_gate,
            latest_readiness=latest_readiness,
            release_decision_count=release_decision_count,
            result_count=len(results),
        ),
        inventory=inventory,
        recent_runs=[
            ControlPlaneRecentRun(
                id=run.id,
                status=run.status,
                runtime_name=run.runtime_name,
                data_source=run.data_source,
                started_at=run.started_at,
            )
            for run in recent_runs
        ],
    )


def _latest_gate_summary(
    gate: GateEvaluation | None,
    readiness: ReleaseReadinessSnapshot | None,
) -> ControlPlaneLatestGate | None:
    if gate is None:
        return None
    scorecard = gate.scorecard_json if isinstance(gate.scorecard_json, dict) else {}
    trust = (
        scorecard.get("evidence_trust")
        if isinstance(scorecard.get("evidence_trust"), dict)
        else {}
    )
    trust_status = readiness.evidence_trust.trust_status if readiness else None
    production_readiness = readiness.production_readiness if readiness else None
    return ControlPlaneLatestGate(
        id=gate.id,
        verdict=gate.verdict,
        evidence_trust_status=str(trust_status or trust.get("trust_status") or "unknown"),
        production_readiness=str(
            production_readiness or trust.get("production_readiness") or "unknown"
        ),
        decision_summary=gate.decision_summary,
        created_at=gate.evaluated_at,
    )


def _next_actions(
    *,
    workload_count: int,
    configuration_count: int,
    completed_run_count: int,
    latest_gate: GateEvaluation | None,
    latest_readiness: ReleaseReadinessSnapshot | None,
    failed_critical_case_count: int,
    needs_review_count: int,
    active_baseline_count: int,
    production_evidence_count: int,
) -> list[ControlPlaneNextAction]:
    actions: list[ControlPlaneNextAction] = []
    if workload_count == 0:
        actions.append(
            _action(
                "high",
                "workload",
                "Define a workload",
                "Create the first versioned workload and evaluation suite.",
                "/workloads",
            )
        )
    if configuration_count == 0:
        actions.append(
            _action(
                "high",
                "configuration",
                "Configure a deployment",
                "Bind a model artifact, runtime, hardware, prompt, and workload.",
                "/deployments",
            )
        )
    if completed_run_count == 0:
        actions.append(
            _action(
                "high",
                "benchmark",
                "Execute evaluation evidence",
                "Run the selected configuration against an active evaluation suite.",
                "/benchmark-executions/new",
            )
        )
    if latest_gate is None:
        actions.append(
            _action(
                "high",
                "gate",
                "Evaluate a deployment gate",
                "Review evidence against a versioned acceptance policy.",
                "/deployment-gates/new",
            )
        )
    if failed_critical_case_count:
        actions.append(
            _action(
                "high",
                "judge_review",
                f"Review {failed_critical_case_count} critical failure outcome(s)",
                "This count sums the latest Gate for every configuration; review is required "
                "before release sign-off.",
                "/judge-labels",
            )
        )
    if latest_gate is not None and latest_gate.verdict in {
        "BLOCKED",
        "INSUFFICIENT_EVIDENCE",
    }:
        actions.append(
            _action(
                "high",
                "gate_blocker",
                f"Resolve the latest {latest_gate.verdict.lower()} gate",
                latest_gate.decision_summary,
                f"/deployment-gates/{latest_gate.id}",
            )
        )
    if needs_review_count:
        actions.append(
            _action(
                "medium",
                "release_review",
                f"Resolve {needs_review_count} release readiness review item(s)",
                "Evidence trust, labels, or regressions still require review.",
                "/release-readiness",
            )
        )
    if (
        latest_gate is not None
        and latest_gate.verdict == "APPROVED"
        and active_baseline_count == 0
    ):
        actions.append(
            _action(
                "medium",
                "baseline",
                "Promote an approved baseline",
                "An approved gate is available but no active baseline exists.",
                "/deployment-baselines",
            )
        )
    if production_evidence_count == 0 and completed_run_count:
        actions.append(
            _action(
                "low",
                "production_evidence",
                "Capture production evidence",
                "Current local or synthetic evidence does not establish production readiness.",
                "/benchmark-executions/new",
            )
        )
    if latest_readiness and latest_readiness.status == "NEEDS_REVIEW" and not needs_review_count:
        actions.append(
            _action(
                "medium",
                "readiness",
                "Review release readiness",
                latest_readiness.release_summary,
                "/release-readiness",
            )
        )
    actions.sort(key=lambda item: PRIORITY_ORDER[item.priority])
    return actions[:5]


def _workflow_steps(
    *,
    workload_count: int,
    configuration_count: int,
    completed_run_count: int,
    latest_gate: GateEvaluation | None,
    latest_readiness: ReleaseReadinessSnapshot | None,
    release_decision_count: int,
    result_count: int,
) -> list[ControlPlaneWorkflowStep]:
    gate_status: WorkflowStatus = "not_started"
    if latest_gate is not None:
        gate_status = "complete" if latest_gate.verdict == "APPROVED" else "attention"
    review_status: WorkflowStatus = "not_started"
    trust_status = latest_readiness.evidence_trust.trust_status if latest_readiness else None
    if result_count:
        review_status = (
            "complete"
            if trust_status in {"local_demo_ready", "production_evidence_ready"}
            else "attention"
        )
    decision_status: WorkflowStatus = "complete" if release_decision_count else "not_started"
    if not release_decision_count and latest_readiness and latest_readiness.status in {
        "READY",
        "READY_TO_PROMOTE",
    }:
        decision_status = "attention"
    return [
        _step("define_workload", "Define Workload", _binary_status(workload_count), "/workloads"),
        _step(
            "configure_deployment",
            "Configure Deployment",
            _binary_status(configuration_count),
            "/deployments",
        ),
        _step(
            "execute_evaluation",
            "Execute Evaluation",
            _binary_status(completed_run_count),
            "/benchmark-executions/new",
        ),
        _step("evaluate_gate", "Evaluate Gate", gate_status, "/deployment-gates/new"),
        _step("review_evidence", "Review Evidence", review_status, "/judge-labels"),
        _step(
            "sign_release",
            "Sign Release Decision",
            decision_status,
            "/release-decisions",
        ),
    ]


def _action(
    priority: Priority,
    kind: str,
    title: str,
    description: str,
    href: str,
) -> ControlPlaneNextAction:
    return ControlPlaneNextAction(
        priority=priority,
        kind=kind,
        title=title,
        description=description,
        href=href,
    )


def _step(
    key: str,
    label: str,
    status: WorkflowStatus,
    href: str,
) -> ControlPlaneWorkflowStep:
    return ControlPlaneWorkflowStep(key=key, label=label, status=status, href=href)


def _binary_status(count: int) -> WorkflowStatus:
    return "complete" if count else "not_started"


def _mode(source_counts: Counter[str], result_count: int) -> OverviewMode:
    if result_count == 0:
        return "empty"
    if source_counts["production_captured"]:
        return "production_evidence"
    return "demo"


def _count(db: Session, statement: Any) -> int:
    return int(db.scalar(statement) or 0)
