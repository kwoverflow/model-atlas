from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    DeploymentConfiguration,
    EvaluationSuite,
    GateEvaluation,
)
from app.schemas.gate_preflight import (
    GatePreflightBaselineSummary,
    GatePreflightConfigurationSummary,
    GatePreflightEvidenceSummary,
    GatePreflightPolicySummary,
    GatePreflightRequest,
    GatePreflightResponse,
    GatePreflightSuiteSummary,
)
from app.services.deployment_gate.baselines import get_active_baseline_gate
from app.services.deployment_gate.evidence import collect_evidence
from app.services.evidence_trust import summarize_evidence_trust
from app.services.supply_chain import verified_production_run_ids
from app.validators import DomainValidationError


def build_gate_preflight(
    db: Session,
    payload: GatePreflightRequest,
) -> GatePreflightResponse:
    configuration = _get_required(
        db,
        DeploymentConfiguration,
        payload.deployment_configuration_id,
        "deployment_configuration",
    )
    suite = _get_required(
        db,
        EvaluationSuite,
        payload.evaluation_suite_id,
        "evaluation_suite",
    )
    policy = _get_required(
        db,
        AcceptancePolicy,
        payload.acceptance_policy_id,
        "acceptance_policy",
    )
    rules = list(
        db.scalars(
            select(AcceptancePolicyRule)
            .where(AcceptancePolicyRule.acceptance_policy_id == policy.id)
            .where(AcceptancePolicyRule.enabled.is_(True))
        )
    )
    bundle = collect_evidence(
        db,
        deployment_configuration=configuration,
        evaluation_suite=suite,
    )
    trust = summarize_evidence_trust(
        bundle.results,
        bundle.result_case_map,
        verified_production_run_ids=verified_production_run_ids(
            db,
            {run.id for run in bundle.runs},
        ),
    )
    baseline, baseline_source = _resolve_baseline(db, payload)
    blockers = _blocking_preconditions(
        configuration=configuration,
        suite=suite,
        policy=policy,
        active_case_count=bundle.active_case_count,
        completed_run_count=len(bundle.runs),
        result_count=bundle.result_count,
    )
    if baseline is not None and not _baseline_matches(
        baseline=baseline,
        configuration=configuration,
        suite=suite,
        policy=policy,
    ):
        blockers.append("The selected baseline does not match the requested gate scope.")
    warnings = list(trust.limitations)
    if not rules:
        warnings.append("The acceptance policy has no enabled rules.")
    if bundle.metric_count == 0:
        warnings.append("No inference metrics are available for policy evaluation.")
    if baseline is None:
        warnings.append("No active or explicit baseline is available for regression comparison.")

    return GatePreflightResponse(
        configuration=GatePreflightConfigurationSummary(
            id=configuration.id,
            name=configuration.name,
            artifact_name=configuration.model_artifact.artifact_name,
            runtime_name=configuration.runtime_name,
            hardware_name=configuration.hardware_profile.name,
            context_length=configuration.context_length,
            prompt_version=_prompt_version(configuration.prompt_bundle_json),
        ),
        suite=GatePreflightSuiteSummary(
            id=suite.id,
            name=suite.name,
            version_label=suite.version_label,
            active_case_count=bundle.active_case_count,
            critical_case_count=sum(
                1
                for evaluation_case in bundle.active_cases
                if evaluation_case.criticality == "critical"
            ),
        ),
        policy=GatePreflightPolicySummary(
            id=policy.id,
            name=policy.name,
            version_label=policy.version_label,
            rule_count=len(rules),
            blocking_rule_count=sum(1 for rule in rules if rule.severity == "blocker"),
            warning_rule_count=sum(1 for rule in rules if rule.severity == "warning"),
        ),
        evidence=GatePreflightEvidenceSummary(
            completed_run_count=len(bundle.runs),
            result_count=bundle.result_count,
            metric_count=bundle.metric_count,
            source_distribution=trust.source_distribution,
            score_distribution=trust.score_distribution,
            heuristic_only_count=trust.heuristic_only_count,
            applied_judge_label_count=trust.applied_judge_label_count,
            human_reviewed_count=trust.human_reviewed_count,
            applied_judge_label_rate=trust.applied_judge_label_rate,
            critical_review_coverage_rate=trust.critical_review_coverage_rate,
            trust_status=trust.trust_status,
            production_readiness=trust.production_readiness,
        ),
        baseline=(
            GatePreflightBaselineSummary(
                source=baseline_source,
                gate_evaluation_id=baseline.id,
                verdict=baseline.verdict,
            )
            if baseline is not None and baseline_source is not None
            else None
        ),
        expected_outcome_constraints=_expected_constraints(trust.trust_status, trust.limitations),
        blocking_preconditions=list(dict.fromkeys(blockers)),
        warnings=list(dict.fromkeys(warnings)),
        can_evaluate=not blockers,
    )


def _get_required(db: Session, model: type[Any], entity_id: Any, label: str) -> Any:
    entity = db.get(model, entity_id)
    if entity is None:
        raise DomainValidationError(f"{label} was not found")
    return entity


def _resolve_baseline(
    db: Session,
    payload: GatePreflightRequest,
) -> tuple[GateEvaluation | None, str | None]:
    if payload.baseline_gate_evaluation_id is not None:
        return (
            _get_required(
                db,
                GateEvaluation,
                payload.baseline_gate_evaluation_id,
                "baseline_gate_evaluation",
            ),
            "explicit",
        )
    baseline = get_active_baseline_gate(
        db,
        deployment_configuration_id=payload.deployment_configuration_id,
        evaluation_suite_id=payload.evaluation_suite_id,
        acceptance_policy_id=payload.acceptance_policy_id,
    )
    return baseline, "active_scope_baseline" if baseline is not None else None


def _baseline_matches(
    *,
    baseline: GateEvaluation,
    configuration: DeploymentConfiguration,
    suite: EvaluationSuite,
    policy: AcceptancePolicy,
) -> bool:
    return (
        baseline.deployment_configuration_id == configuration.id
        and baseline.evaluation_suite_id == suite.id
        and baseline.acceptance_policy_id == policy.id
    )


def _blocking_preconditions(
    *,
    configuration: DeploymentConfiguration,
    suite: EvaluationSuite,
    policy: AcceptancePolicy,
    active_case_count: int,
    completed_run_count: int,
    result_count: int,
) -> list[str]:
    blockers: list[str] = []
    if configuration.workload_profile_id != suite.workload_profile_id:
        blockers.append("Deployment configuration and evaluation suite workloads differ.")
    if policy.workload_profile_id != configuration.workload_profile_id:
        blockers.append("Acceptance policy workload does not match the configuration.")
    if active_case_count == 0:
        blockers.append("The evaluation suite has no active cases.")
    if completed_run_count == 0:
        blockers.append("No completed benchmark run matches this configuration and suite.")
    elif result_count == 0:
        blockers.append("Matching completed runs do not contain active-case results.")
    return blockers


def _expected_constraints(trust_status: str, limitations: list[str]) -> list[str]:
    constraints = list(limitations)
    if trust_status == "local_demo_ready":
        constraints.insert(
            0,
            "This evidence can support a local demo decision but not production readiness.",
        )
    elif trust_status == "synthetic_only":
        constraints.insert(0, "Synthetic evidence cannot authorize a deployment release.")
    elif trust_status == "needs_judge_review":
        constraints.insert(0, "Judge review coverage must improve before release sign-off.")
    elif trust_status == "unknown":
        constraints.insert(0, "Evidence provenance is insufficient for a readiness claim.")
    return list(dict.fromkeys(constraints))


def _prompt_version(prompt_bundle: Any) -> str | None:
    if not isinstance(prompt_bundle, dict):
        return None
    for key in ("version", "version_label", "prompt_version"):
        if prompt_bundle.get(key):
            return str(prompt_bundle[key])
    return None
