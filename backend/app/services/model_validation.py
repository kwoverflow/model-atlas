from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.models import (
    AgentExecutionJob,
    BenchmarkResult,
    BenchmarkRun,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    InferenceMetric,
)
from app.schemas import (
    ModelValidationCampaignCreate,
    ModelValidationCohortRead,
    ModelValidationComparisonRead,
    ModelValidationJudgeCalibrationRead,
    ModelValidationReportRead,
)
from app.services.benchmark_execution import run_benchmark_execution
from app.services.deployment_gate.evidence import (
    collect_evidence,
    evidence_revision_hash,
    stable_hash,
)
from app.services.evidence_trust import (
    EvidenceScoreTrustTier,
    classify_score_tier,
    summarize_evidence_trust,
)
from app.services.model_artifact_attestation import latest_verified_attestation
from app.services.operator_identity import SignerIdentity
from app.services.supply_chain import (
    supply_chain_assurance_for_model_artifact,
    verified_production_run_ids,
)
from app.validators import DomainValidationError

MODEL_VALIDATION_SCHEMA_VERSION = "model-validation-report-v4"
MODEL_VALIDATION_JOB_VERSION = "model-validation-campaign-v1"
MODEL_VALIDATION_CALIBRATION_TOLERANCE = 0.10
ALLOWED_API_KEY_ENV = "OPENAI_COMPATIBLE_API_KEY"
SYNTHETIC_SOURCE = "synthetic_demo"
_FORBIDDEN_SECRET_KEYS = frozenset(
    {
        "api_key",
        "access_token",
        "authorization",
        "bearer_token",
        "client_secret",
        "headers",
        "password",
        "secret",
        "token",
    }
)


def validate_model_validation_campaign(
    payload: ModelValidationCampaignCreate,
) -> None:
    _assert_no_persisted_secrets(payload.adapter_config_json)
    api_key_env = payload.adapter_config_json.get("api_key_env")
    if api_key_env is not None and api_key_env != ALLOWED_API_KEY_ENV:
        raise DomainValidationError(
            f"api_key_env must be {ALLOWED_API_KEY_ENV}"
        )
    base_url = payload.adapter_config_json.get("base_url")
    if base_url is not None:
        parsed = urlparse(str(base_url))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise DomainValidationError(
                "model validation base_url must be an HTTP(S) URL"
            )
        if parsed.username or parsed.password:
            raise DomainValidationError(
                "model validation base_url cannot contain credentials"
            )
    if payload.adapter_name == "mock" and api_key_env is not None:
        raise DomainValidationError("mock validation does not use api_key_env")


def execute_model_validation_job(
    db: Session,
    *,
    job: AgentExecutionJob,
    requester_identity: SignerIdentity,
) -> dict[str, Any]:
    if job.payload_json.get("schema_version") != MODEL_VALIDATION_JOB_VERSION:
        raise DomainValidationError(
            "model validation job schema version is unsupported"
        )
    execution_payload = job.payload_json.get("execution")
    if not isinstance(execution_payload, dict):
        raise DomainValidationError("model validation execution payload is invalid")
    try:
        payload = ModelValidationCampaignCreate.model_validate(
            {
                **execution_payload,
                "campaign_key": job.payload_json.get("campaign_key"),
            }
        )
    except ValidationError as exc:
        raise DomainValidationError(
            "model validation execution payload is invalid"
        ) from exc
    validate_model_validation_campaign(payload)
    outcome = run_benchmark_execution(
        db,
        payload,
        requester_identity=requester_identity,
    )
    job.benchmark_run_id = outcome.run.id
    report = build_model_validation_report(
        db,
        deployment_configuration_id=payload.deployment_configuration_id,
        evaluation_suite_id=payload.evaluation_suite_id,
        focus_benchmark_run_id=outcome.run.id,
    )
    return {
        "schema_version": MODEL_VALIDATION_JOB_VERSION,
        "campaign_key": payload.campaign_key,
        "benchmark_run_id": str(outcome.run.id),
        "result_count": outcome.result_count,
        "metric_count": outcome.metric_count,
        "report": report.model_dump(mode="json"),
    }


def build_model_validation_report(
    db: Session,
    *,
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
    focus_benchmark_run_id: UUID | None = None,
) -> ModelValidationReportRead:
    deployment = db.get(DeploymentConfiguration, deployment_configuration_id)
    if deployment is None:
        raise DomainValidationError("deployment_configuration was not found")
    suite = db.get(EvaluationSuite, evaluation_suite_id)
    if suite is None:
        raise DomainValidationError("evaluation_suite was not found")
    if suite.workload_profile_id != deployment.workload_profile_id:
        raise DomainValidationError(
            "evaluation suite workload does not match configuration"
        )
    focus_run = _validate_focus_run(
        db,
        focus_benchmark_run_id=focus_benchmark_run_id,
        deployment_configuration_id=deployment.id,
        evaluation_suite_id=suite.id,
    )
    bundle = collect_evidence(
        db,
        deployment_configuration=deployment,
        evaluation_suite=suite,
    )
    runs_by_id = {run.id: run for run in bundle.runs}
    verified_production_ids = verified_production_run_ids(
        db,
        set(runs_by_id),
    )
    result_groups: dict[str, list[BenchmarkResult]] = defaultdict(list)
    for result in bundle.results:
        result_groups[result.data_source].append(result)
    metric_groups = _metrics_by_source(bundle.metrics, bundle.results)
    cohorts = [
        _cohort(
            data_source=source,
            results=results,
            metrics=metric_groups.get(source, []),
            runs_by_id=runs_by_id,
            result_case_map=bundle.result_case_map,
            verified_production_run_ids=verified_production_ids,
        )
        for source, results in sorted(
            result_groups.items(),
            key=lambda item: (_source_order(item[0]), item[0]),
        )
    ]
    trust = summarize_evidence_trust(
        bundle.results,
        bundle.result_case_map,
        verified_production_run_ids=verified_production_ids,
    )
    calibration = _judge_calibration(
        bundle.results,
        bundle.result_case_map,
    )
    observed_model_names = sorted(
        {
            model_name
            for cohort in cohorts
            for model_name in cohort.model_names
            if model_name
        }
    )
    observed_model_digests = sorted(
        {
            digest
            for run in bundle.runs
            if (digest := _run_model_digest(run)) is not None
        }
    )
    configured_model_artifact_name = deployment.model_artifact.artifact_name
    configuration_model_match = _model_identity_match(
        configured_model_artifact_name,
        observed_model_names,
    )
    attestation = latest_verified_attestation(
        db,
        model_artifact_id=deployment.model_artifact_id,
    )
    configured_artifact_digest = _sha256_digest(
        deployment.model_artifact.checksum
    )
    artifact_attestation_status = _artifact_attestation_status(
        attestation=attestation,
        configured_artifact_digest=configured_artifact_digest,
        observed_model_names=observed_model_names,
        observed_model_digests=observed_model_digests,
    )
    (
        supply_chain_status,
        supply_chain_attestation_id,
        supply_chain_trust_tier,
        transparency_status,
        supply_chain_production_eligible,
    ) = supply_chain_assurance_for_model_artifact(
        db,
        model_artifact_id=deployment.model_artifact_id,
    )
    production_run_ids = {
        run.id for run in bundle.runs if run.data_source == "production_captured"
    }
    production_capture_status = (
        "not_applicable"
        if not production_run_ids
        else "verified"
        if production_run_ids <= verified_production_ids
        else "unverified"
    )
    verified_production_result_count = sum(
        1
        for result in bundle.results
        if result.data_source == "production_captured"
        and result.benchmark_run_id in verified_production_ids
    )
    actual_runtime_validated = any(
        cohort.actual_runtime_result_count > 0 for cohort in cohorts
    )
    status = _validation_status(
        cohorts=cohorts,
        trust_status=trust.trust_status,
        calibration=calibration,
        focus_run=focus_run,
        actual_runtime_validated=actual_runtime_validated,
        configuration_model_match=configuration_model_match,
        artifact_attestation_status=artifact_attestation_status,
    )
    comparisons = _comparisons(cohorts)
    recommendations, limitations = _recommendations(
        status=status,
        cohorts=cohorts,
        trust_status=trust.trust_status,
        calibration=calibration,
        actual_runtime_validated=actual_runtime_validated,
        configuration_model_match=configuration_model_match,
        artifact_attestation_status=artifact_attestation_status,
        supply_chain_status=supply_chain_status,
        supply_chain_trust_tier=supply_chain_trust_tier,
        transparency_status=transparency_status,
        supply_chain_production_eligible=supply_chain_production_eligible,
        production_capture_status=production_capture_status,
    )
    generated_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    report_payload: dict[str, Any] = {
        "schema_version": MODEL_VALIDATION_SCHEMA_VERSION,
        "generated_at": generated_at,
        "deployment_configuration_id": deployment.id,
        "deployment_configuration_name": deployment.name,
        "configured_model_artifact_name": configured_model_artifact_name,
        "observed_model_names": observed_model_names,
        "observed_model_digests": observed_model_digests,
        "configuration_model_match": configuration_model_match,
        "artifact_attestation_status": artifact_attestation_status,
        "artifact_attestation_id": attestation.id if attestation else None,
        "configured_artifact_digest": configured_artifact_digest,
        "supply_chain_status": supply_chain_status,
        "supply_chain_attestation_id": supply_chain_attestation_id,
        "supply_chain_trust_tier": supply_chain_trust_tier,
        "transparency_status": transparency_status,
        "supply_chain_production_eligible": supply_chain_production_eligible,
        "production_capture_status": production_capture_status,
        "verified_production_run_count": len(
            production_run_ids & verified_production_ids
        ),
        "verified_production_result_count": verified_production_result_count,
        "evaluation_suite_id": suite.id,
        "evaluation_suite_name": suite.name,
        "focus_benchmark_run_id": focus_benchmark_run_id,
        "status": status,
        "actual_runtime_validated": actual_runtime_validated,
        "release_authorized": False,
        "evidence_revision_hash": evidence_revision_hash(bundle),
        "selected_run_count": len(bundle.runs),
        "result_count": len(bundle.results),
        "metric_count": len(bundle.metrics),
        "cohorts": cohorts,
        "comparisons": comparisons,
        "judge_calibration": calibration,
        "evidence_trust": trust.to_dict(),
        "recommendations": recommendations,
        "limitations": limitations,
    }
    report_payload["report_hash"] = stable_hash(
        {
            key: value
            for key, value in report_payload.items()
            if key != "generated_at"
        }
    )
    return ModelValidationReportRead.model_validate(report_payload)


def render_model_validation_markdown(
    report: ModelValidationReportRead,
) -> str:
    lines = [
        "# Model Atlas Local Model Validation Report",
        "",
        f"- Status: `{report.status}`",
        f"- Deployment: `{report.deployment_configuration_name}`",
        f"- Configured model artifact: `{report.configured_model_artifact_name}`",
        f"- Observed runtime models: `{', '.join(report.observed_model_names) or 'unknown'}`",
        f"- Observed model digests: `{', '.join(report.observed_model_digests) or 'unknown'}`",
        "- Configuration model match: "
        f"`{_markdown_boolean(report.configuration_model_match)}`",
        f"- Artifact attestation: `{report.artifact_attestation_status}`",
        f"- Configured artifact digest: `{report.configured_artifact_digest or 'unknown'}`",
        f"- Supply-chain attestation: `{report.supply_chain_status}`",
        f"- Supply-chain trust tier: `{report.supply_chain_trust_tier}`",
        f"- Transparency evidence: `{report.transparency_status}`",
        "- Supply-chain production eligible: "
        f"`{'yes' if report.supply_chain_production_eligible else 'no'}`",
        f"- Production capture: `{report.production_capture_status}`",
        "- Verified production runs / results: "
        f"`{report.verified_production_run_count}` / "
        f"`{report.verified_production_result_count}`",
        f"- Evaluation suite: `{report.evaluation_suite_name}`",
        f"- Actual runtime evidence: `{'yes' if report.actual_runtime_validated else 'no'}`",
        f"- Release authorized: `{'yes' if report.release_authorized else 'no'}`",
        f"- Runs / results / metrics: `{report.selected_run_count}` / "
        f"`{report.result_count}` / `{report.metric_count}`",
        f"- Evidence revision: `{report.evidence_revision_hash}`",
        f"- Report hash: `{report.report_hash}`",
        "",
        "## Evidence Cohorts",
        "",
        "| Source | Results | Adapter | Quality | P95 latency | P50 throughput | Error | OOM |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cohort in report.cohorts:
        lines.append(
            "| "
            f"{cohort.data_source} | {cohort.result_count} | "
            f"{', '.join(cohort.adapter_names) or 'unknown'} | "
            f"{_markdown_number(cohort.average_quality_score)} | "
            f"{_markdown_number(cohort.p95_end_to_end_latency_ms)} | "
            f"{_markdown_number(cohort.p50_tokens_per_second)} | "
            f"{cohort.error_rate:.4f} | "
            f"{_markdown_number(cohort.oom_rate)} |"
        )
    lines.extend(
        [
            "",
            "## Judge Calibration",
            "",
            f"- Status: `{report.judge_calibration.status}`",
            f"- Candidate labels: `{report.judge_calibration.candidate_label_count}`",
            f"- Reviewed labels: `{report.judge_calibration.reviewed_label_count}`",
            "- Critical reviewed labels: "
            f"`{report.judge_calibration.critical_reviewed_count}`",
            f"- Distinct reviewers: `{report.judge_calibration.reviewer_count}`",
            "- Mean absolute quality delta: "
            f"`{_markdown_number(report.judge_calibration.mean_abs_quality_delta)}`",
            "",
            "## Recommendations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in report.recommendations)
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report.limitations)
    return "\n".join(lines).rstrip() + "\n"


def _validate_focus_run(
    db: Session,
    *,
    focus_benchmark_run_id: UUID | None,
    deployment_configuration_id: UUID,
    evaluation_suite_id: UUID,
) -> BenchmarkRun | None:
    if focus_benchmark_run_id is None:
        return None
    run = db.get(BenchmarkRun, focus_benchmark_run_id)
    if run is None:
        raise DomainValidationError("focus benchmark run was not found")
    if (
        run.deployment_configuration_id != deployment_configuration_id
        or run.evaluation_suite_id != evaluation_suite_id
    ):
        raise DomainValidationError(
            "focus benchmark run does not belong to the validation scope"
        )
    return run


def _cohort(
    *,
    data_source: str,
    results: list[BenchmarkResult],
    metrics: list[InferenceMetric],
    runs_by_id: Mapping[UUID, BenchmarkRun],
    result_case_map: Mapping[UUID, EvaluationCase],
    verified_production_run_ids: set[UUID],
) -> ModelValidationCohortRead:
    run_ids = sorted({result.benchmark_run_id for result in results}, key=str)
    runs = [runs_by_id[run_id] for run_id in run_ids if run_id in runs_by_id]
    adapters = sorted({_adapter_name(run) for run in runs})
    model_names = sorted({_model_name(run) for run in runs})
    exact_values = [
        result.exact_match
        for result in results
        if result.exact_match is not None
    ]
    json_results = [
        result
        for result in results
        if _is_json_case(result_case_map.get(result.id))
    ]
    tool_results = [
        result
        for result in results
        if _is_tool_case(result_case_map.get(result.id))
    ]
    reviewed_count = sum(
        1
        for result in results
        if classify_score_tier(result, result_case_map.get(result.id))
        in {
            EvidenceScoreTrustTier.APPLIED_JUDGE_LABEL,
            EvidenceScoreTrustTier.HUMAN_REVIEWED,
        }
    )
    trust = summarize_evidence_trust(
        results,
        result_case_map,
        verified_production_run_ids=verified_production_run_ids,
    )
    actual_run_ids = {
        run.id for run in runs if _adapter_name(run) == "openai_compatible"
    }
    return ModelValidationCohortRead(
        data_source=data_source,
        benchmark_run_ids=run_ids,
        result_count=len(results),
        metric_count=len(metrics),
        adapter_names=adapters,
        model_names=model_names,
        actual_runtime_result_count=sum(
            1
            for result in results
            if result.benchmark_run_id in actual_run_ids
            and result.data_source != SYNTHETIC_SOURCE
        ),
        average_quality_score=_mean(
            [result.quality_score for result in results]
        ),
        exact_match_rate=_boolean_rate(exact_values),
        json_validity_rate=_boolean_rate(
            [result.json_valid for result in json_results]
        ),
        tool_call_validity_rate=_boolean_rate(
            [result.tool_call_valid for result in tool_results]
        ),
        average_groundedness_score=_mean(
            [result.groundedness_score for result in results]
        ),
        average_faithfulness_score=_mean(
            [result.faithfulness_score for result in results]
        ),
        error_rate=_rate(
            sum(1 for result in results if result.error_type),
            len(results),
        ),
        p50_end_to_end_latency_ms=_percentile(
            [metric.end_to_end_latency_ms for metric in metrics],
            0.50,
        ),
        p95_end_to_end_latency_ms=_percentile(
            [metric.end_to_end_latency_ms for metric in metrics],
            0.95,
        ),
        p50_tokens_per_second=_percentile(
            [metric.tokens_per_second for metric in metrics],
            0.50,
        ),
        oom_rate=(
            _rate(sum(1 for metric in metrics if metric.oom_occurred), len(metrics))
            if metrics
            else None
        ),
        reviewed_result_count=reviewed_count,
        review_coverage_rate=_rate(reviewed_count, len(results)),
        trust_status=trust.trust_status,
    )


def _metrics_by_source(
    metrics: Sequence[InferenceMetric],
    results: Sequence[BenchmarkResult],
) -> dict[str, list[InferenceMetric]]:
    source_by_sample = {
        (result.benchmark_run_id, result.sample_id): result.data_source
        for result in results
    }
    groups: dict[str, list[InferenceMetric]] = defaultdict(list)
    for metric in metrics:
        source = source_by_sample.get(
            (metric.benchmark_run_id, metric.sample_id),
            metric.data_source,
        )
        groups[source].append(metric)
    return groups


def _judge_calibration(
    results: Sequence[BenchmarkResult],
    result_case_map: Mapping[UUID, EvaluationCase],
) -> ModelValidationJudgeCalibrationRead:
    deltas: list[float] = []
    reviewed_label_count = 0
    critical_reviewed_count = 0
    reviewer_subjects: set[str] = set()
    for result in results:
        evaluation_case = result_case_map.get(result.id)
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        judge_metadata = metadata.get("judge_label")
        if isinstance(judge_metadata, dict) and (
            judge_metadata.get("applied") is True
            and judge_metadata.get("human_reviewed") is True
        ):
            reviewed_label_count += 1
            if evaluation_case is not None and evaluation_case.criticality == "critical":
                critical_reviewed_count += 1
            reviewer_identity = judge_metadata.get("reviewer_identity")
            if isinstance(reviewer_identity, dict) and reviewer_identity.get("subject_id"):
                reviewer_subjects.add(str(reviewer_identity["subject_id"]))
        if (
            result.quality_score is None
            or evaluation_case is None
            or not isinstance(evaluation_case.reference_context_json, dict)
        ):
            continue
        labels = evaluation_case.reference_context_json.get("judge_labels")
        if not isinstance(labels, dict) or labels.get("quality_score") is None:
            continue
        try:
            candidate_score = float(labels["quality_score"])
        except (TypeError, ValueError):
            continue
        deltas.append(abs(candidate_score - result.quality_score))
    if not deltas:
        return ModelValidationJudgeCalibrationRead(
            status="not_available",
            candidate_label_count=0,
            tolerance=MODEL_VALIDATION_CALIBRATION_TOLERANCE,
            reviewed_label_count=reviewed_label_count,
            critical_reviewed_count=critical_reviewed_count,
            reviewer_count=len(reviewer_subjects),
        )
    mean_delta = sum(deltas) / len(deltas)
    return ModelValidationJudgeCalibrationRead(
        status=(
            "calibrated"
            if mean_delta <= MODEL_VALIDATION_CALIBRATION_TOLERANCE
            else "needs_review"
        ),
        candidate_label_count=len(deltas),
        mean_abs_quality_delta=round(mean_delta, 4),
        max_abs_quality_delta=round(max(deltas), 4),
        within_tolerance_rate=_rate(
            sum(
                1
                for delta in deltas
                if delta <= MODEL_VALIDATION_CALIBRATION_TOLERANCE
            ),
            len(deltas),
        ),
        tolerance=MODEL_VALIDATION_CALIBRATION_TOLERANCE,
        reviewed_label_count=reviewed_label_count,
        critical_reviewed_count=critical_reviewed_count,
        reviewer_count=len(reviewer_subjects),
    )


def _validation_status(
    *,
    cohorts: Sequence[ModelValidationCohortRead],
    trust_status: str,
    calibration: ModelValidationJudgeCalibrationRead,
    focus_run: BenchmarkRun | None,
    actual_runtime_validated: bool,
    configuration_model_match: bool | None,
    artifact_attestation_status: str,
) -> str:
    if not cohorts:
        return "no_evidence"
    if (
        (focus_run is not None and _adapter_name(focus_run) == "mock")
        or all(cohort.data_source == SYNTHETIC_SOURCE for cohort in cohorts)
    ):
        return "fixture_only"
    if not actual_runtime_validated:
        return "insufficient_real_evidence"
    if configuration_model_match is False:
        return "needs_attention"
    if artifact_attestation_status != "verified":
        return "needs_attention"
    if calibration.status == "needs_review":
        return "needs_calibration"
    if (
        trust_status in {"unknown", "needs_judge_review"}
        or any(cohort.error_rate > 0 for cohort in cohorts)
        or any((cohort.oom_rate or 0) > 0 for cohort in cohorts)
    ):
        return "needs_attention"
    return "validated"


def _comparisons(
    cohorts: Sequence[ModelValidationCohortRead],
) -> list[ModelValidationComparisonRead]:
    if len(cohorts) < 2:
        return []
    baseline = next(
        (cohort for cohort in cohorts if cohort.data_source == SYNTHETIC_SOURCE),
        cohorts[0],
    )
    return [
        ModelValidationComparisonRead(
            baseline_source=baseline.data_source,
            candidate_source=candidate.data_source,
            quality_delta=_delta(
                candidate.average_quality_score,
                baseline.average_quality_score,
            ),
            p95_latency_delta_ms=_delta(
                candidate.p95_end_to_end_latency_ms,
                baseline.p95_end_to_end_latency_ms,
            ),
            p50_throughput_delta=_delta(
                candidate.p50_tokens_per_second,
                baseline.p50_tokens_per_second,
            ),
            error_rate_delta=round(
                candidate.error_rate - baseline.error_rate,
                4,
            ),
            oom_rate_delta=_delta(candidate.oom_rate, baseline.oom_rate),
        )
        for candidate in cohorts
        if candidate.data_source != baseline.data_source
    ]


def _recommendations(
    *,
    status: str,
    cohorts: Sequence[ModelValidationCohortRead],
    trust_status: str,
    calibration: ModelValidationJudgeCalibrationRead,
    actual_runtime_validated: bool,
    configuration_model_match: bool | None,
    artifact_attestation_status: str,
    supply_chain_status: str,
    supply_chain_trust_tier: str,
    transparency_status: str,
    supply_chain_production_eligible: bool,
    production_capture_status: str,
) -> tuple[list[str], list[str]]:
    recommendations: list[str] = []
    limitations: list[str] = [
        "This report validates runtime evidence; it does not authorize a release.",
        "Hardware telemetry reflects only metrics captured by the configured runtime adapter.",
    ]
    if not actual_runtime_validated:
        recommendations.append(
            "Run an openai_compatible campaign against the target local runtime."
        )
    if configuration_model_match is False:
        recommendations.append(
            "Run the campaign with the model artifact named by the deployment configuration "
            "or create a separate deployment configuration for the observed runtime model."
        )
        limitations.append(
            "The observed runtime model size does not match the configured model artifact."
        )
    if artifact_attestation_status == "missing":
        recommendations.append(
            "Inspect the target runtime manifest and bind its SHA-256 digest to a draft "
            "deployment configuration."
        )
        limitations.append("The configured model artifact has no verified manifest attestation.")
    elif artifact_attestation_status in {"digest_mismatch", "model_mismatch"}:
        recommendations.append(
            "Resolve the runtime model or digest mismatch and rerun the validation campaign."
        )
        limitations.append(
            "The runtime evidence does not match the verified model artifact attestation."
        )
    if supply_chain_status == "missing":
        recommendations.append(
            "Attach a publisher-signed in-toto statement and CycloneDX SBOM "
            "to the runtime attestation."
        )
        limitations.append(
            "Publisher signature and SBOM provenance are not verified for this artifact."
        )
    elif supply_chain_status == "revoked":
        recommendations.append(
            "Replace the revoked supply-chain attestation before evaluating production readiness."
        )
        limitations.append("The latest supply-chain attestation is revoked.")
    elif not supply_chain_production_eligible:
        if supply_chain_trust_tier in {"unmanaged", "development"}:
            recommendations.append(
                "Register an internal-CA or external publisher key before production use."
            )
            limitations.append(
                "The publisher signature is development-scoped and cannot establish "
                "production trust."
            )
        if transparency_status != "verified":
            recommendations.append(
                "Attach a signed transparency-log checkpoint and verified inclusion proof."
            )
            limitations.append(
                "The supply-chain statement lacks active production-tier transparency evidence."
            )
    if production_capture_status == "unverified":
        recommendations.append(
            "Attach a signed production-capture receipt to every production-labeled run."
        )
        limitations.append(
            "Production-labeled runs without active signed receipts are excluded "
            "from production trust."
        )
    if calibration.status == "not_available":
        recommendations.append(
            "Add candidate judge labels or import reviewed labels for calibration."
        )
        limitations.append("No candidate judge labels were available for calibration.")
    elif calibration.status == "needs_review":
        recommendations.append(
            "Review score deltas and apply judge labels before relying on quality scores."
        )
    if trust_status in {"unknown", "needs_judge_review"}:
        recommendations.append(
            "Increase applied or human-reviewed label coverage, especially for critical cases."
        )
    if any(cohort.error_rate > 0 for cohort in cohorts):
        recommendations.append(
            "Inspect failed cases and execution logs before evaluating the Deployment Gate."
        )
    if any((cohort.oom_rate or 0) > 0 for cohort in cohorts):
        recommendations.append(
            "Reduce context, batch size, or model footprint and rerun reliability trials."
        )
    if status == "validated":
        recommendations.append(
            "Evaluate the acceptance policy in Deployment Gates and review release readiness."
        )
    if not recommendations:
        recommendations.append("Collect additional non-synthetic runtime evidence.")
    if not any(
        cohort.data_source == "production_captured" for cohort in cohorts
    ):
        limitations.append("Production-captured evidence is not present in this scope.")
    return recommendations, limitations


def _assert_no_persisted_secrets(value: Any, *, path: str = "adapter_config_json") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized != "api_key_env" and (
                normalized in _FORBIDDEN_SECRET_KEYS
                or normalized.endswith("_secret")
                or normalized.endswith("_password")
                or normalized.endswith("_token")
            ):
                raise DomainValidationError(
                    f"{path}.{key} cannot persist credentials; use api_key_env"
                )
            _assert_no_persisted_secrets(item, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_persisted_secrets(item, path=f"{path}[{index}]")


def _adapter_name(run: BenchmarkRun) -> str:
    config = run.runtime_config_json if isinstance(run.runtime_config_json, dict) else {}
    return str(config.get("adapter_name") or "unknown")


def _model_name(run: BenchmarkRun) -> str:
    config = run.runtime_config_json if isinstance(run.runtime_config_json, dict) else {}
    configured = config.get("model") or config.get("model_name")
    if configured:
        return str(configured)
    return run.model_artifact.artifact_name


def _run_model_digest(run: BenchmarkRun) -> str | None:
    config = run.runtime_config_json if isinstance(run.runtime_config_json, dict) else {}
    return _sha256_digest(config.get("model_digest"))


def _sha256_digest(value: Any) -> str | None:
    match = re.fullmatch(
        r"(?:sha256:)?([0-9a-fA-F]{64})",
        str(value or "").strip(),
    )
    return f"sha256:{match.group(1).lower()}" if match else None


def _artifact_attestation_status(
    *,
    attestation: Any | None,
    configured_artifact_digest: str | None,
    observed_model_names: Sequence[str],
    observed_model_digests: Sequence[str],
) -> str:
    if attestation is None:
        return "missing"
    attested_digest = _sha256_digest(attestation.digest_value)
    if (
        attested_digest is None
        or configured_artifact_digest != attested_digest
        or any(digest != attested_digest for digest in observed_model_digests)
    ):
        return "digest_mismatch"
    normalized_attested_name = str(attestation.runtime_model_name).strip().lower()
    if observed_model_names and normalized_attested_name not in {
        model_name.strip().lower() for model_name in observed_model_names
    }:
        return "model_mismatch"
    return "verified"


def _is_json_case(evaluation_case: EvaluationCase | None) -> bool:
    if evaluation_case is None:
        return False
    return (
        evaluation_case.expected_output_json is not None
        or "json" in evaluation_case.category.lower()
    )


def _is_tool_case(evaluation_case: EvaluationCase | None) -> bool:
    if evaluation_case is None:
        return False
    return (
        evaluation_case.expected_tool_schema_json is not None
        or "tool" in evaluation_case.category.lower()
    )


def _source_order(source: str) -> int:
    return {
        SYNTHETIC_SOURCE: 0,
        "local_authored": 1,
        "external_benchmark": 2,
        "production_captured": 3,
    }.get(source, 4)


def _model_identity_match(
    configured_artifact_name: str,
    observed_model_names: Sequence[str],
) -> bool | None:
    configured_sizes = _parameter_sizes(configured_artifact_name)
    observed_sizes = {
        size
        for model_name in observed_model_names
        for size in _parameter_sizes(model_name)
    }
    if configured_sizes and observed_sizes:
        return configured_sizes == observed_sizes
    return None


def _parameter_sizes(value: str) -> set[float]:
    return {
        float(match)
        for match in re.findall(
            r"(?<![0-9])([0-9]+(?:\.[0-9]+)?)\s*b\b",
            value.lower(),
        )
    }


def _mean(values: Sequence[float | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return round(sum(present) / len(present), 4)


def _boolean_rate(values: Sequence[bool]) -> float | None:
    if not values:
        return None
    return _rate(sum(1 for value in values if value), len(values))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: Sequence[float | None], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values if value is not None)
    if not ordered:
        return None
    position = (len(ordered) - 1) * quantile
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    value = ordered[lower_index] + (
        ordered[upper_index] - ordered[lower_index]
    ) * fraction
    return round(value, 3)


def _delta(candidate: float | None, baseline: float | None) -> float | None:
    if candidate is None or baseline is None:
        return None
    return round(candidate - baseline, 4)


def _markdown_number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _markdown_boolean(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return "yes" if value else "no"
