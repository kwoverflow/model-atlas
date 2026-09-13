from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    DeploymentConfiguration,
    EvaluationSuite,
    GateEvaluation,
    GateRuleResult,
)
from app.schemas import GateEvaluationCreate
from app.services.deployment_gate.baselines import get_active_baseline_gate
from app.services.deployment_gate.evidence import (
    collect_evidence,
    evidence_snapshot,
    stable_hash,
)
from app.services.deployment_gate.metrics import (
    calculate_metrics,
    critical_case_outcomes,
    metrics_to_scorecard,
)
from app.services.deployment_gate.policy import (
    POLICY_ENGINE_VERSION,
    EvaluatedRule,
    evaluate_policy_rules,
)
from app.services.deployment_gate.regression import apply_baseline_regressions
from app.services.deployment_gate.staleness import (
    mark_scope_gates_stale,
    reconcile_all_gate_staleness,
    supersede_stale_gates,
)
from app.services.evidence_trust import EvidenceTrustSummary, summarize_evidence_trust
from app.services.experiment_lineage import record_gate_evaluation_completed
from app.services.supply_chain import verified_production_run_ids
from app.validators import DomainValidationError


def _get_required(db: Session, model: type[Any], entity_id: UUID, label: str) -> Any:
    entity = db.get(model, entity_id)
    if entity is None:
        raise DomainValidationError(f"{label} was not found")
    return entity


def _validate_baseline_scope(
    *,
    baseline: GateEvaluation,
    deployment_configuration: DeploymentConfiguration,
    evaluation_suite: EvaluationSuite,
    acceptance_policy: AcceptancePolicy,
) -> None:
    if (
        baseline.deployment_configuration_id != deployment_configuration.id
        or baseline.evaluation_suite_id != evaluation_suite.id
        or baseline.acceptance_policy_id != acceptance_policy.id
    ):
        raise DomainValidationError(
            "baseline gate evaluation scope does not match the requested gate"
        )


def _policy_rules(db: Session, policy_id: UUID) -> list[AcceptancePolicyRule]:
    return list(
        db.scalars(
            select(AcceptancePolicyRule)
            .options(selectinload(AcceptancePolicyRule.metric_definition))
            .where(AcceptancePolicyRule.acceptance_policy_id == policy_id)
            .where(AcceptancePolicyRule.enabled.is_(True))
        ).all()
    )


def _required_insufficient(evaluated_rules: list[EvaluatedRule]) -> bool:
    return any(rule.rule.required and rule.status == "insufficient" for rule in evaluated_rules)


def _resolve_verdict(
    *,
    mandatory_evidence_missing: bool,
    synthetic_only: bool,
    required_rule_insufficient: bool,
    evaluated_rules: list[EvaluatedRule],
    critical_failure_present: bool,
    allow_conditional: bool,
) -> str:
    if mandatory_evidence_missing or synthetic_only or required_rule_insufficient:
        return "INSUFFICIENT_EVIDENCE"
    blocker_failed = any(
        rule.status == "fail" and rule.severity == "blocker" for rule in evaluated_rules
    )
    if blocker_failed:
        return "BLOCKED"
    if critical_failure_present:
        return "BLOCKED"
    warning_failed = any(
        rule.status == "fail" and rule.severity == "warning" for rule in evaluated_rules
    )
    if warning_failed:
        return "CONDITIONAL" if allow_conditional else "BLOCKED"
    return "APPROVED"


def _next_actions(
    *,
    verdict: str,
    synthetic_only: bool,
    evaluated_rules: list[EvaluatedRule],
    critical_failures: list[dict[str, Any]],
    trust_summary: EvidenceTrustSummary,
) -> list[str]:
    actions: list[str] = []
    if synthetic_only:
        actions.append(
            "Replace synthetic_demo evaluation cases with real captured benchmark cases."
        )
    for rule in evaluated_rules:
        if rule.status in {"fail", "insufficient"}:
            message = rule.rule.message_on_fail
            if rule.status == "insufficient":
                message = f"Collect enough evidence for {rule.metric_key}."
            actions.append(message)
    if critical_failures:
        actions.append("Inspect and fix failed critical evaluation cases before approval.")
    if trust_summary.trust_status == "needs_judge_review":
        actions.append("Apply judge labels to meet local evidence review coverage.")
    if trust_summary.production_readiness != "production_ready":
        actions.append("Collect reviewed production-captured evidence for production readiness.")
    if verdict == "APPROVED":
        actions.append(
            "Promote this gate evaluation as the deployment baseline if operationally ready."
        )
    return list(dict.fromkeys(actions))


def _decision_explanation(
    *,
    verdict: str,
    decision_summary: str,
    evaluated_rules: list[EvaluatedRule],
    critical_failures: list[dict[str, Any]],
    trust_summary: EvidenceTrustSummary,
    next_actions: list[str],
) -> dict[str, Any]:
    blockers = [
        {
            "code": f"policy_rule_{rule.status}",
            "title": rule.rule.rule_name,
            "detail": rule.rule.message_on_fail,
            "severity": "blocking" if rule.severity == "blocker" else "warning",
            "sample_ids": [],
        }
        for rule in evaluated_rules
        if rule.status in {"fail", "insufficient"} and rule.severity == "blocker"
    ]
    blockers.extend(
        {
            "code": "critical_case_failure",
            "title": str(outcome.get("title") or "Critical case failed"),
            "detail": "A critical evaluation case failed and requires review.",
            "severity": "blocking",
            "sample_ids": [str(outcome.get("sample_id"))],
        }
        for outcome in critical_failures
    )
    warnings = [
        {
            "code": "policy_warning",
            "title": rule.rule.rule_name,
            "detail": rule.rule.message_on_fail,
            "severity": "warning",
        }
        for rule in evaluated_rules
        if rule.status == "fail" and rule.severity == "warning"
    ]
    warnings.extend(
        {
            "code": "evidence_trust_limitation",
            "title": "Evidence trust limitation",
            "detail": limitation,
            "severity": "warning",
        }
        for limitation in trust_summary.limitations
    )
    return {
        "summary": decision_summary,
        "verdict": verdict,
        "blockers": blockers,
        "warnings": warnings,
        "next_actions": [
            {
                "code": f"next_action_{index}",
                "title": action,
                "description": action,
                "href": _action_href(action),
            }
            for index, action in enumerate(next_actions, start=1)
        ],
    }


def _action_href(action: str) -> str:
    normalized = action.lower()
    if "judge" in normalized or "critical" in normalized:
        return "/judge-labels"
    if "baseline" in normalized:
        return "/deployment-baselines"
    if "production" in normalized or "evidence" in normalized:
        return "/benchmark-executions/new"
    return "/deployment-gates"


def _decision_summary(
    *,
    verdict: str,
    synthetic_only: bool,
    mandatory_evidence_missing: bool,
    evaluated_rules: list[EvaluatedRule],
    critical_failures: list[dict[str, Any]],
) -> str:
    if verdict == "APPROVED":
        return "APPROVED: all required policy rules passed with sufficient non-synthetic evidence."
    if verdict == "INSUFFICIENT_EVIDENCE":
        reasons: list[str] = []
        if synthetic_only:
            reasons.append("available evidence is not backed by non-synthetic evaluation cases")
        if mandatory_evidence_missing:
            reasons.append("mandatory benchmark evidence is missing")
        if _required_insufficient(evaluated_rules):
            reasons.append("one or more required policy metrics are insufficient")
        return "INSUFFICIENT_EVIDENCE: " + "; ".join(reasons)
    if verdict == "BLOCKED":
        blocker_count = sum(
            1 for rule in evaluated_rules if rule.status == "fail" and rule.severity == "blocker"
        )
        return (
            "BLOCKED: "
            f"{blocker_count} blocker rule(s) failed and "
            f"{len(critical_failures)} critical case failure(s) were detected."
        )
    warning_count = sum(
        1 for rule in evaluated_rules if rule.status == "fail" and rule.severity == "warning"
    )
    return f"CONDITIONAL: blocker rules passed, but {warning_count} warning rule(s) require review."


def create_gate_evaluation(db: Session, payload: GateEvaluationCreate) -> GateEvaluation:
    deployment_configuration = _get_required(
        db,
        DeploymentConfiguration,
        payload.deployment_configuration_id,
        "deployment_configuration",
    )
    if (deployment_configuration.runtime_config_json or {}).get("tool_fault_scenario") is not None:
        raise DomainValidationError(
            "Tool fault fixture configurations cannot supply release Gate evidence"
        )
    evaluation_suite = _get_required(
        db,
        EvaluationSuite,
        payload.evaluation_suite_id,
        "evaluation_suite",
    )
    acceptance_policy = _get_required(
        db,
        AcceptancePolicy,
        payload.acceptance_policy_id,
        "acceptance_policy",
    )
    if deployment_configuration.workload_profile_id != evaluation_suite.workload_profile_id:
        raise DomainValidationError(
            "deployment configuration and evaluation suite workloads differ"
        )
    if acceptance_policy.workload_profile_id != deployment_configuration.workload_profile_id:
        raise DomainValidationError("acceptance policy workload does not match the configuration")

    baseline: GateEvaluation | None = None
    if payload.baseline_gate_evaluation_id is not None:
        baseline = _get_required(
            db,
            GateEvaluation,
            payload.baseline_gate_evaluation_id,
            "baseline_gate_evaluation",
        )
    else:
        baseline = get_active_baseline_gate(
            db,
            deployment_configuration_id=deployment_configuration.id,
            evaluation_suite_id=evaluation_suite.id,
            acceptance_policy_id=acceptance_policy.id,
        )
    if baseline is not None:
        _validate_baseline_scope(
            baseline=baseline,
            deployment_configuration=deployment_configuration,
            evaluation_suite=evaluation_suite,
            acceptance_policy=acceptance_policy,
        )

    bundle = collect_evidence(
        db,
        deployment_configuration=deployment_configuration,
        evaluation_suite=evaluation_suite,
    )
    metrics = calculate_metrics(bundle)
    metrics = apply_baseline_regressions(
        metrics,
        baseline.scorecard_json.get("metrics") if baseline is not None else None,
    )
    rules = _policy_rules(db, acceptance_policy.id)
    evaluated_rules = evaluate_policy_rules(rules, metrics)
    critical_outcomes = critical_case_outcomes(bundle)
    critical_failures = [outcome for outcome in critical_outcomes if outcome["status"] == "fail"]
    trust_summary = summarize_evidence_trust(
        bundle.results,
        bundle.result_case_map,
        verified_production_run_ids=verified_production_run_ids(
            db,
            {run.id for run in bundle.runs},
        ),
    )
    verdict = _resolve_verdict(
        mandatory_evidence_missing=bundle.mandatory_evidence_missing,
        synthetic_only=bundle.only_synthetic_evidence,
        required_rule_insufficient=_required_insufficient(evaluated_rules),
        evaluated_rules=evaluated_rules,
        critical_failure_present=bool(critical_failures),
        allow_conditional=acceptance_policy.allow_conditional,
    )
    next_actions = _next_actions(
        verdict=verdict,
        synthetic_only=bundle.only_synthetic_evidence,
        evaluated_rules=evaluated_rules,
        critical_failures=critical_failures,
        trust_summary=trust_summary,
    )
    snapshot = evidence_snapshot(bundle, trust_summary)
    snapshot["policy_hash"] = acceptance_policy.policy_hash
    snapshot["policy_engine_version"] = POLICY_ENGINE_VERSION
    if baseline is not None:
        snapshot["baseline_gate_evaluation_id"] = str(baseline.id)
        snapshot["baseline_decision_hash"] = baseline.decision_hash

    decision_summary = _decision_summary(
        verdict=verdict,
        synthetic_only=bundle.only_synthetic_evidence,
        mandatory_evidence_missing=bundle.mandatory_evidence_missing,
        evaluated_rules=evaluated_rules,
        critical_failures=critical_failures,
    )
    scorecard = {
        "metrics": metrics_to_scorecard(metrics),
        "rule_results": [
            {
                "rule_id": str(rule.rule.id),
                "rule_name": rule.rule.rule_name,
                "metric_key": rule.metric_key,
                "metric_value": rule.metric_value,
                "sample_size": rule.sample_size,
                "status": rule.status,
                "severity": rule.severity,
                "details": rule.details,
            }
            for rule in evaluated_rules
        ],
        "critical_case_outcomes": critical_outcomes,
        "baseline_comparison": {
            "baseline_gate_evaluation_id": str(baseline.id) if baseline else None,
            "quality_regression_vs_baseline": metrics["quality_regression_vs_baseline"].value,
            "latency_regression_vs_baseline": metrics["latency_regression_vs_baseline"].value,
        },
        "next_actions": next_actions,
        "evidence_trust": trust_summary.to_dict(),
        "decision_explanation": _decision_explanation(
            verdict=verdict,
            decision_summary=decision_summary,
            evaluated_rules=evaluated_rules,
            critical_failures=critical_failures,
            trust_summary=trust_summary,
            next_actions=next_actions,
        ),
        "synthetic_data_warning": (
            "synthetic_demo evaluation cases may demonstrate the UI, but they cannot approve "
            "deployment."
            if bundle.only_synthetic_evidence
            else None
        ),
    }
    decision_hash = stable_hash(
        {
            "deployment_configuration_id": str(deployment_configuration.id),
            "evaluation_suite_id": str(evaluation_suite.id),
            "acceptance_policy_id": str(acceptance_policy.id),
            "baseline_gate_evaluation_id": str(baseline.id) if baseline else None,
            "evidence_snapshot": snapshot,
            "scorecard": scorecard,
            "verdict": verdict,
        }
    )

    gate = GateEvaluation(
        deployment_configuration_id=deployment_configuration.id,
        evaluation_suite_id=evaluation_suite.id,
        acceptance_policy_id=acceptance_policy.id,
        baseline_gate_evaluation_id=baseline.id if baseline else None,
        status="completed",
        verdict=verdict,
        evidence_snapshot_json=snapshot,
        scorecard_json=scorecard,
        decision_summary=decision_summary,
        decision_hash=decision_hash,
        evidence_revision_hash=str(snapshot["evidence_revision_hash"]),
    )
    mark_scope_gates_stale(
        db,
        deployment_configuration_id=deployment_configuration.id,
        evaluation_suite_id=evaluation_suite.id,
        current_revision_hash=gate.evidence_revision_hash,
        reason="A newer Gate evaluation captured a different evidence revision.",
    )
    db.add(gate)
    db.flush()
    supersede_stale_gates(db, replacement_gate=gate)
    record_gate_evaluation_completed(db, gate)
    for rule in evaluated_rules:
        db.add(
            GateRuleResult(
                gate_evaluation_id=gate.id,
                acceptance_policy_rule_id=rule.rule.id,
                metric_value=rule.metric_value,
                sample_size=rule.sample_size,
                status=rule.status,
                severity=rule.severity,
                details_json=rule.details,
            )
        )
    db.commit()
    return get_gate_evaluation(db, gate.id)


def get_gate_evaluation(db: Session, gate_evaluation_id: UUID) -> GateEvaluation:
    reconciliation = reconcile_all_gate_staleness(db)
    if reconciliation.stale_count:
        db.commit()
    gate = db.scalar(
        select(GateEvaluation)
        .options(selectinload(GateEvaluation.rule_results))
        .where(GateEvaluation.id == gate_evaluation_id)
    )
    if gate is None:
        raise DomainValidationError("gate_evaluation was not found")
    return gate


def list_gate_evaluations(db: Session, *, limit: int, offset: int) -> list[GateEvaluation]:
    reconciliation = reconcile_all_gate_staleness(db)
    if reconciliation.stale_count:
        db.commit()
    return list(
        db.scalars(
            select(GateEvaluation)
            .options(selectinload(GateEvaluation.rule_results))
            .order_by(GateEvaluation.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
    )
