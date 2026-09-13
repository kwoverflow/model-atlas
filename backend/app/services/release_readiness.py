from __future__ import annotations

import datetime as dt
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import DeploymentBaseline, GateEvaluation
from app.schemas import (
    EvidenceTrustSummaryRead,
    ReleaseReadinessBaselineSummary,
    ReleaseReadinessGateSummary,
    ReleaseReadinessJudgeSummary,
    ReleaseReadinessLineageSummary,
    ReleaseReadinessPromptSummary,
    ReleaseReadinessSnapshot,
)
from app.services.deployment_gate.baselines import list_deployment_baselines
from app.services.evidence_trust import (
    EVIDENCE_TRUST_VERSION,
    EvidenceTrustSummary,
    summarize_gate_evidence_trust,
)
from app.services.experiment_lineage import build_experiment_lineage_report
from app.services.judge_label_review import review_judge_labels
from app.services.prompt_regressions import build_prompt_regression_report
from app.validators import DomainValidationError


def build_release_readiness_snapshot(
    db: Session,
    *,
    gate_evaluation_id: UUID | None = None,
) -> ReleaseReadinessSnapshot:
    gate = _gate_evaluation(db, gate_evaluation_id)
    gate_summary = _gate_summary(gate)
    baseline_summary = _baseline_summary(db, gate)
    trust_summary = summarize_gate_evidence_trust(db, gate)
    judge_summary = _judge_summary(db, gate_summary.benchmark_run_ids, trust_summary)
    prompt_summary = _prompt_summary(db, gate)
    lineage_summary = _lineage_summary(db, gate)
    status, readiness_reasons, review_reasons = _readiness_status(
        gate=gate,
        baseline=baseline_summary,
        judge=judge_summary,
        prompt=prompt_summary,
        trust=trust_summary,
    )
    production_readiness = _production_readiness(
        status=status,
        baseline=baseline_summary,
        judge=judge_summary,
        prompt=prompt_summary,
        trust=trust_summary,
    )
    next_actions = _next_actions(
        gate=gate,
        baseline=baseline_summary,
        judge=judge_summary,
        prompt=prompt_summary,
        status=status,
        trust=trust_summary,
    )

    return ReleaseReadinessSnapshot(
        schema_version="release-readiness-snapshot-v2",
        evidence_trust_version=EVIDENCE_TRUST_VERSION,
        generated_at=_utcnow(),
        status=status,
        production_readiness=production_readiness,
        release_summary=_release_summary(status, production_readiness, gate, trust_summary),
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        acceptance_policy_id=gate.acceptance_policy_id,
        readiness_reasons=readiness_reasons,
        review_reasons=review_reasons,
        next_actions=next_actions,
        evidence_trust=EvidenceTrustSummaryRead.model_validate(trust_summary.to_dict()),
        gate=gate_summary,
        baseline=baseline_summary,
        judge_calibration=judge_summary,
        prompt_regression=prompt_summary,
        lineage=lineage_summary,
    )


def render_release_readiness_markdown(snapshot: ReleaseReadinessSnapshot) -> str:
    lines = [
        "# Model Atlas Release Readiness Snapshot",
        "",
        f"- Status: {snapshot.status}",
        f"- Production readiness: {snapshot.production_readiness}",
        f"- Generated at: {snapshot.generated_at.isoformat()}",
        f"- Gate evaluation: {snapshot.gate.gate_evaluation_id}",
        f"- Verdict: {snapshot.gate.verdict}",
        f"- Decision hash: {snapshot.gate.decision_hash}",
        "",
        "## Summary",
        "",
        snapshot.release_summary,
        "",
        "## Readiness Reasons",
        "",
        *[f"- {reason}" for reason in snapshot.readiness_reasons],
        "",
        "## Review Reasons",
        "",
        *([f"- {reason}" for reason in snapshot.review_reasons] or ["- none"]),
        "",
        "## Next Actions",
        "",
        *([f"- {action}" for action in snapshot.next_actions] or ["- none"]),
        "",
        "## Evidence",
        "",
        f"- Benchmark runs: {len(snapshot.gate.benchmark_run_ids)}",
        f"- Results: {snapshot.gate.result_count}",
        f"- Metrics: {snapshot.gate.metric_count}",
        f"- Failed rules: {snapshot.gate.failed_rule_count}",
        f"- Insufficient rules: {snapshot.gate.insufficient_rule_count}",
        f"- Critical failures: {snapshot.gate.critical_failure_count}",
        f"- Evidence trust: {snapshot.evidence_trust.trust_status}",
        f"- Applied label coverage: {snapshot.evidence_trust.applied_judge_label_rate:.1%}",
        (
            "- Critical review coverage: "
            f"{snapshot.evidence_trust.critical_review_coverage_rate:.1%}"
        ),
        "",
        "## Baseline",
        "",
        f"- Status: {snapshot.baseline.baseline_status}",
        f"- Gate is active baseline: {snapshot.baseline.gate_is_active_baseline}",
        f"- Active baseline: {snapshot.baseline.active_baseline_id or 'none'}",
        "",
        "## Judge Calibration",
        "",
        f"- Result count: {snapshot.judge_calibration.result_count}",
        f"- Reviewed count: {snapshot.judge_calibration.reviewed_count}",
        f"- Needs review: {snapshot.judge_calibration.needs_review_count}",
        f"- Unlabeled count: {snapshot.judge_calibration.unlabeled_count}",
        "",
        "## Prompt Regression",
        "",
        f"- Prompt versions: {snapshot.prompt_regression.prompt_version_count}",
        f"- Risk rows: {snapshot.prompt_regression.risk_row_count}",
        f"- Risk flags: {', '.join(snapshot.prompt_regression.risk_flags) or 'none'}",
        "",
        "## Lineage",
        "",
        f"- Event count: {snapshot.lineage.event_count}",
        f"- Lineage count: {snapshot.lineage.lineage_count}",
    ]
    return "\n".join(lines) + "\n"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)


def _gate_evaluation(db: Session, gate_evaluation_id: UUID | None) -> GateEvaluation:
    query = select(GateEvaluation).options(selectinload(GateEvaluation.rule_results))
    if gate_evaluation_id is not None:
        query = query.where(GateEvaluation.id == gate_evaluation_id)
    else:
        query = query.order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.created_at.desc())
    gate = db.scalar(query.limit(1))
    if gate is None:
        raise DomainValidationError("gate_evaluation was not found")
    return gate


def _gate_summary(gate: GateEvaluation) -> ReleaseReadinessGateSummary:
    scorecard = gate.scorecard_json or {}
    rule_results = scorecard.get("rule_results", [])
    critical_outcomes = scorecard.get("critical_case_outcomes", [])
    snapshot = gate.evidence_snapshot_json or {}
    return ReleaseReadinessGateSummary(
        gate_evaluation_id=gate.id,
        status=gate.status,
        verdict=gate.verdict,
        decision_hash=gate.decision_hash,
        decision_summary=gate.decision_summary,
        evaluated_at=gate.evaluated_at,
        passed_rule_count=sum(1 for rule in rule_results if rule.get("status") == "pass"),
        failed_rule_count=sum(1 for rule in rule_results if rule.get("status") == "fail"),
        insufficient_rule_count=sum(
            1 for rule in rule_results if rule.get("status") == "insufficient"
        ),
        critical_failure_count=sum(
            1 for outcome in critical_outcomes if outcome.get("status") == "fail"
        ),
        benchmark_run_ids=_uuid_list(snapshot.get("benchmark_run_ids", [])),
        metric_count=int(snapshot.get("metric_count") or 0),
        result_count=int(snapshot.get("result_count") or 0),
        source_distribution={
            str(key): int(value)
            for key, value in (snapshot.get("source_data_source_distribution") or {}).items()
        },
        evidence_revision_hash=(
            gate.evidence_revision_hash
            or str(snapshot.get("evidence_revision_hash") or "")
            or None
        ),
        stale_at=gate.stale_at,
        stale_reason=gate.stale_reason,
        superseded_by_gate_evaluation_id=gate.superseded_by_gate_evaluation_id,
    )


def _baseline_summary(db: Session, gate: GateEvaluation) -> ReleaseReadinessBaselineSummary:
    active_baselines = list_deployment_baselines(
        db,
        limit=1,
        offset=0,
        active_only=True,
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        acceptance_policy_id=gate.acceptance_policy_id,
    )
    active = active_baselines[0] if active_baselines else None
    gate_is_active = active is not None and active.gate_evaluation_id == gate.id
    return ReleaseReadinessBaselineSummary(
        active_baseline_id=active.id if active else None,
        active_baseline_gate_evaluation_id=active.gate_evaluation_id if active else None,
        gate_is_active_baseline=gate_is_active,
        baseline_status=_baseline_status(active, gate),
        baseline_hash=active.baseline_hash if active else None,
        promoted_at=active.promoted_at if active else None,
    )


def _baseline_status(
    active: DeploymentBaseline | None,
    gate: GateEvaluation,
) -> str:
    if active is None:
        return "not_promoted"
    if active.gate_evaluation_id == gate.id:
        return "active_source"
    return "different_active_baseline"


def _judge_summary(
    db: Session,
    benchmark_run_ids: list[UUID],
    trust: EvidenceTrustSummary,
) -> ReleaseReadinessJudgeSummary:
    reports = [
        review_judge_labels(db, limit=1000, offset=0, benchmark_run_id=run_id)
        for run_id in benchmark_run_ids
    ]
    result_count = sum(report.result_count for report in reports)
    candidate_label_count = sum(report.candidate_label_count for report in reports)
    return ReleaseReadinessJudgeSummary(
        result_count=result_count,
        reviewed_count=sum(report.reviewed_count for report in reports),
        candidate_label_count=candidate_label_count,
        heuristic_scored_count=sum(report.heuristic_scored_count for report in reports),
        heuristic_only_count=trust.heuristic_only_count,
        applied_label_count=trust.applied_judge_label_count,
        human_reviewed_count=trust.human_reviewed_count,
        unlabeled_count=sum(report.unlabeled_count for report in reports),
        needs_review_count=sum(report.needs_review_count for report in reports),
        applied_label_coverage_rate=trust.applied_judge_label_rate,
        critical_review_coverage_rate=trust.critical_review_coverage_rate,
        average_quality_score=_weighted_average(
            [(report.average_quality_score, report.result_count) for report in reports]
        ),
        average_abs_quality_delta_vs_candidate=_weighted_average(
            [
                (
                    report.average_abs_quality_delta_vs_candidate,
                    report.candidate_label_count,
                )
                for report in reports
                if report.candidate_label_count
            ]
        ),
    )


def _prompt_summary(db: Session, gate: GateEvaluation) -> ReleaseReadinessPromptSummary:
    report = build_prompt_regression_report(
        db,
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        acceptance_policy_id=gate.acceptance_policy_id,
    )
    flags = sorted({flag for row in report.rows for flag in row.risk_flags})
    return ReleaseReadinessPromptSummary(
        prompt_version_count=report.row_count,
        baseline_prompt_version_id=report.baseline_prompt_version_id,
        risk_row_count=sum(1 for row in report.rows if row.risk_flags),
        risk_flags=flags,
    )


def _lineage_summary(db: Session, gate: GateEvaluation) -> ReleaseReadinessLineageSummary:
    report = build_experiment_lineage_report(
        db,
        limit=20,
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        acceptance_policy_id=gate.acceptance_policy_id,
    )
    return ReleaseReadinessLineageSummary(
        event_count=report.event_count,
        lineage_count=report.lineage_count,
        latest_events=[
            {
                "event_type": event.event_type,
                "event_time": event.event_time.isoformat(),
                "summary": event.summary,
                "status": event.status,
            }
            for event in report.events[:5]
        ],
    )


def _readiness_status(
    *,
    gate: GateEvaluation,
    baseline: ReleaseReadinessBaselineSummary,
    judge: ReleaseReadinessJudgeSummary,
    prompt: ReleaseReadinessPromptSummary,
    trust: EvidenceTrustSummary,
) -> tuple[str, list[str], list[str]]:
    readiness_reasons: list[str] = []
    review_reasons: list[str] = []

    if gate.status == "stale":
        review_reasons.append(
            gate.stale_reason
            or "Gate evidence is stale and requires a new evaluation."
        )
        return "BLOCKED", readiness_reasons, review_reasons
    if gate.verdict == "INSUFFICIENT_EVIDENCE":
        review_reasons.append("Gate verdict is INSUFFICIENT_EVIDENCE.")
        return "INSUFFICIENT_EVIDENCE", readiness_reasons, review_reasons
    if trust.trust_status == "synthetic_only":
        review_reasons.append("Evidence trust is SYNTHETIC_ONLY.")
        return "INSUFFICIENT_EVIDENCE", readiness_reasons, review_reasons
    if gate.verdict == "BLOCKED":
        review_reasons.append("Gate verdict is BLOCKED.")
        return "BLOCKED", readiness_reasons, review_reasons
    if gate.verdict == "CONDITIONAL":
        review_reasons.append("Gate verdict is CONDITIONAL.")

    if trust.trust_status in {"needs_judge_review", "unknown"}:
        review_reasons.extend(trust.reasons)

    if gate.verdict == "APPROVED":
        readiness_reasons.append("Gate verdict is APPROVED.")
    if baseline.gate_is_active_baseline:
        readiness_reasons.append("Gate evaluation is the active deployment baseline.")
    else:
        review_reasons.append("Gate evaluation is not the active deployment baseline.")
    if judge.needs_review_count:
        review_reasons.append(f"{judge.needs_review_count} judge-label row(s) need review.")
    else:
        readiness_reasons.append("Judge calibration has no pending review rows.")
    if prompt.risk_row_count:
        review_reasons.append(
            f"{prompt.risk_row_count} prompt regression row(s) have risk flags."
        )
    else:
        readiness_reasons.append("Prompt regression report has no risk rows.")

    if (
        gate.verdict == "CONDITIONAL"
        or trust.trust_status in {"needs_judge_review", "unknown"}
        or judge.needs_review_count
        or prompt.risk_row_count
    ):
        return "NEEDS_REVIEW", readiness_reasons, review_reasons
    if baseline.gate_is_active_baseline:
        return "READY", readiness_reasons, review_reasons
    return "READY_TO_PROMOTE", readiness_reasons, review_reasons


def _next_actions(
    *,
    gate: GateEvaluation,
    baseline: ReleaseReadinessBaselineSummary,
    judge: ReleaseReadinessJudgeSummary,
    prompt: ReleaseReadinessPromptSummary,
    status: str,
    trust: EvidenceTrustSummary,
) -> list[str]:
    actions = list((gate.scorecard_json or {}).get("next_actions") or [])
    if gate.status == "stale":
        actions.insert(0, "Run a new Deployment Gate against the latest evidence revision.")
    if status == "READY_TO_PROMOTE":
        actions.append("Promote the approved gate evaluation as the active baseline.")
    if baseline.baseline_status == "different_active_baseline":
        actions.append("Review why a different gate evaluation is currently active baseline.")
    if judge.needs_review_count:
        actions.append("Resolve pending judge-label review rows before release sign-off.")
    if prompt.risk_row_count:
        actions.append("Review prompt regression risk flags and rerun evidence if needed.")
    if trust.trust_status == "synthetic_only":
        actions.append("Replace synthetic evidence with locally authored evaluation results.")
    elif trust.trust_status == "needs_judge_review":
        actions.append("Apply judge labels to meet the configured evidence coverage threshold.")
    elif trust.trust_status == "unknown":
        actions.append("Add canonical source and score provenance to the benchmark results.")
    elif trust.trust_status == "local_demo_ready":
        actions.append("Collect reviewed production-captured evidence before production release.")
    return list(dict.fromkeys(actions))


def _release_summary(
    status: str,
    production_readiness: str,
    gate: GateEvaluation,
    trust: EvidenceTrustSummary,
) -> str:
    if status == "READY":
        if production_readiness == "production_ready":
            return "Production-ready: release controls and production evidence requirements pass."
        if trust.trust_status == "local_demo_ready":
            return (
                "Release-ready for a reproducible local demonstration, but not production-ready."
            )
        return "Release-ready: the gate is approved, promoted, and no review risks are open."
    if status == "READY_TO_PROMOTE":
        return "Approved but not yet promoted as the active deployment baseline."
    if status == "NEEDS_REVIEW":
        return "Gate evidence is usable, but review items remain before release sign-off."
    if status == "BLOCKED":
        if gate.status == "stale":
            return "Release is blocked because the Gate evidence revision is stale."
        return "Release is blocked by the Deployment Gate verdict."
    return f"Release cannot proceed because evidence is insufficient: {gate.decision_summary}"


def _production_readiness(
    *,
    status: str,
    baseline: ReleaseReadinessBaselineSummary,
    judge: ReleaseReadinessJudgeSummary,
    prompt: ReleaseReadinessPromptSummary,
    trust: EvidenceTrustSummary,
) -> str:
    if trust.trust_status == "unknown":
        return "unknown"
    if (
        status == "READY"
        and trust.trust_status == "production_evidence_ready"
        and baseline.gate_is_active_baseline
        and judge.needs_review_count == 0
        and prompt.risk_row_count == 0
    ):
        return "production_ready"
    return "not_production_ready"


def _uuid_list(values: list) -> list[UUID]:
    output: list[UUID] = []
    for value in values:
        try:
            output.append(UUID(str(value)))
        except ValueError:
            continue
    return output


def _weighted_average(values: list[tuple[float | None, int]]) -> float | None:
    numerator = 0.0
    denominator = 0
    for value, weight in values:
        if value is None or weight <= 0:
            continue
        numerator += value * weight
        denominator += weight
    return numerator / denominator if denominator else None
