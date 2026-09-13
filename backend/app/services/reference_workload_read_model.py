from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    GateEvaluation,
    InferenceMetric,
    JudgeLabelReviewDecision,
    WorkloadProfile,
)
from app.reference_workload.bootstrap import REFERENCE_SUITE_NAME
from app.reference_workload.cases import ReferenceCasePack, load_reference_case_pack
from app.reference_workload.corpus import ReferenceCorpusBundle, build_reference_corpus
from app.reference_workload.manifest import default_repository_root
from app.reference_workload.runtime_matrix import (
    ACTUAL_RUNTIME_DATA_SOURCE,
    RuntimeMatrix,
    RuntimeMatrixEntry,
    load_runtime_matrix,
)
from app.schemas.reference_workload import (
    ReferenceCaseCoverageRead,
    ReferenceCaseListRead,
    ReferenceCaseRead,
    ReferenceConfigurationListRead,
    ReferenceConfigurationRead,
    ReferenceCorpusRead,
    ReferenceCriticalFailureRead,
    ReferenceFailureListRead,
    ReferenceGateOutcomeRead,
    ReferenceLatestRunRead,
    ReferenceManifestRead,
    ReferenceMetricComparisonRead,
    ReferenceMetricComparisonRowRead,
    ReferenceMetricSetRead,
    ReferenceNextActionRead,
    ReferenceOutputReviewCoverageRead,
    ReferencePortfolioCheckRead,
    ReferencePortfolioCompletionRead,
    ReferenceWorkloadDefinitionRead,
    ReferenceWorkloadOverviewRead,
)
from app.services.deployment_gate.evidence import EvidenceBundle, stable_hash
from app.services.deployment_gate.metrics import (
    calculate_metrics,
    critical_case_outcomes,
    metrics_to_scorecard,
)
from app.services.evidence_trust import classify_score_tier, summarize_evidence_trust
from app.services.release_readiness import build_release_readiness_snapshot
from app.services.supply_chain import verified_production_run_ids
from app.validators import DomainValidationError

REFERENCE_WORKLOAD_SLUG = "model-atlas-operator-assistant-ko"
REFERENCE_MATRIX_RESULT_MINIMUM = 3
REFERENCE_ARTIFACT_MINIMUM = 2
REFERENCE_OUTPUT_REVIEW_TARGET = 30

COMPARISON_METRICS = (
    "mean_quality_score",
    "json_validity_rate",
    "tool_selection_accuracy",
    "tool_argument_validity_rate",
    "tool_execution_success_rate",
    "tool_sequence_success_rate",
    "rag_retrieval_recall",
    "rag_groundedness_score",
    "rag_unsupported_claim_rate",
    "agent_task_success_rate",
    "task_completion_rate",
    "critical_case_failure_rate",
    "p95_end_to_end_latency_ms",
    "oom_rate",
)


@dataclass(frozen=True)
class ConfigurationEvidence:
    entry: RuntimeMatrixEntry
    configuration: DeploymentConfiguration | None
    run: BenchmarkRun | None
    results: list[BenchmarkResult]
    metrics: list[InferenceMetric]
    cases: list[EvaluationCase]
    result_case_map: dict[UUID, EvaluationCase]
    scorecard: dict[str, dict[str, Any]]
    gate: GateEvaluation | None
    read: ReferenceConfigurationRead


@dataclass(frozen=True)
class ReferenceReadContext:
    corpus_bundle: ReferenceCorpusBundle
    case_pack: ReferenceCasePack
    matrix: RuntimeMatrix
    workload: WorkloadProfile | None
    suite: EvaluationSuite | None
    configurations: list[ConfigurationEvidence]
    selected_results: list[BenchmarkResult]
    selected_result_case_map: dict[UUID, EvaluationCase]
    review_decisions: dict[UUID, JudgeLabelReviewDecision]


def build_reference_workload_overview(db: Session) -> ReferenceWorkloadOverviewRead:
    context = _load_context(db)
    coverage = _case_coverage(context)
    comparison = _comparison(context.configurations)
    failures = _critical_failures(context)
    trust = summarize_evidence_trust(
        context.selected_results,
        context.selected_result_case_map,
        verified_production_run_ids=verified_production_run_ids(
            db,
            {result.benchmark_run_id for result in context.selected_results},
        ),
    )
    review_coverage = ReferenceOutputReviewCoverageRead(
        result_count=trust.total_result_count,
        human_reviewed_count=trust.human_reviewed_count,
        applied_judge_label_count=trust.applied_judge_label_count,
        critical_result_count=trust.critical_result_count,
        critical_reviewed_count=trust.critical_reviewed_count,
        human_review_coverage_rate=trust.applied_judge_label_rate,
        critical_review_coverage_rate=trust.critical_review_coverage_rate,
        target_review_count=REFERENCE_OUTPUT_REVIEW_TARGET,
        remaining_to_target=max(
            0,
            REFERENCE_OUTPUT_REVIEW_TARGET
            - trust.human_reviewed_count
            - trust.applied_judge_label_count,
        ),
    )
    checks = _portfolio_checks(
        context=context,
        coverage=coverage,
        review_coverage=review_coverage,
        critical_failure_count=len(failures),
    )
    gate_outcomes = [_gate_outcome(db, item, trust.trust_status) for item in context.configurations]
    evaluation_complete = _evaluation_complete(context.configurations)
    production_count = trust.production_captured_count
    return ReferenceWorkloadOverviewRead(
        generated_at=dt.datetime.now(dt.UTC).replace(microsecond=0),
        workload=_workload_definition(context),
        manifest=_manifest_summary(context.corpus_bundle),
        corpus=_corpus_summary(context.corpus_bundle),
        case_coverage=coverage,
        review_coverage=review_coverage,
        evaluation_status="COMPLETE" if evaluation_complete else "INCOMPLETE",
        configuration_matrix=[item.read for item in context.configurations],
        latest_runs=[
            ReferenceLatestRunRead(
                id=item.run.id,
                entry_name=item.entry.name,
                deployment_configuration_id=item.configuration.id,
                status=item.run.status,
                data_source=item.run.data_source,
                result_count=len(item.results),
                started_at=item.run.started_at,
                completed_at=item.run.completed_at,
                benchmark_execution_href=f"/benchmark-executions/{item.run.id}",
            )
            for item in context.configurations
            if item.run is not None and item.configuration is not None
        ],
        metric_comparison=comparison.rows,
        comparison_hash=comparison.comparison_hash,
        critical_failure_count=len(failures),
        critical_failures=failures,
        gate_outcomes=gate_outcomes,
        gate_verdict=_overall_gate_verdict(gate_outcomes),
        evidence_trust=trust.to_dict(),
        actual_runtime_result_count=sum(
            result.data_source == ACTUAL_RUNTIME_DATA_SOURCE for result in context.selected_results
        ),
        production_captured_result_count=production_count,
        production_readiness=(
            "production_ready"
            if production_count and trust.production_readiness == "production_ready"
            else "not_production_ready"
        ),
        portfolio_completion=ReferencePortfolioCompletionRead(
            status="ready" if all(check.passed for check in checks) else "incomplete",
            checks=checks,
            next_actions=_next_actions(
                review_coverage=review_coverage,
                configurations=context.configurations,
            ),
        ),
        reproduction_commands=[
            "docker compose --profile runtime up -d ollama",
            "make reference-validate",
            "make reference-bootstrap",
            (
                "make reference-run REFERENCE_MODEL_SMALL=qwen2.5:0.5b "
                "REFERENCE_MODEL_MEDIUM=qwen2.5:1.5b"
            ),
            "make reference-compare",
        ],
        limitations=_limitations(
            context=context,
            review_coverage=review_coverage,
            production_count=production_count,
        ),
    )


def list_reference_workload_cases(db: Session) -> ReferenceCaseListRead:
    context = _load_context(db)
    stored_cases = {
        case.external_case_id: case for item in context.configurations for case in item.cases
    }
    results_by_case: dict[UUID, list[BenchmarkResult]] = defaultdict(list)
    for result in context.selected_results:
        if result.evaluation_case_id is not None:
            results_by_case[result.evaluation_case_id].append(result)
    items: list[ReferenceCaseRead] = []
    for contract in context.case_pack.cases:
        stored = stored_cases.get(contract.external_case_id)
        results = results_by_case.get(stored.id, []) if stored else []
        items.append(
            ReferenceCaseRead(
                evaluation_case_id=stored.id if stored else None,
                external_case_id=contract.external_case_id,
                title=contract.title,
                category=contract.category,
                criticality=contract.criticality,
                weight=contract.weight,
                is_active=bool(stored.is_active) if stored else False,
                source_review_status=contract.review.status,
                source_reviewed_at=contract.review.reviewed_at,
                result_count=len(results),
                failed_result_count=sum(_result_failed(result) for result in results),
                human_reviewed_result_count=sum(
                    _human_reviewed(result, stored) for result in results
                ),
            )
        )
    return ReferenceCaseListRead(
        workload_profile_id=context.workload.id if context.workload else None,
        evaluation_suite_id=context.suite.id if context.suite else None,
        coverage=_case_coverage(context),
        cases=items,
    )


def list_reference_workload_configurations(db: Session) -> ReferenceConfigurationListRead:
    context = _load_context(db)
    return ReferenceConfigurationListRead(
        configurations=[item.read for item in context.configurations]
    )


def build_reference_workload_comparison(db: Session) -> ReferenceMetricComparisonRead:
    return _comparison(_load_context(db).configurations)


def list_reference_workload_failures(
    db: Session,
    *,
    limit: int,
    offset: int,
) -> ReferenceFailureListRead:
    failures = _critical_failures(_load_context(db))
    return ReferenceFailureListRead(
        total=len(failures),
        items=failures[offset : offset + limit],
        limit=limit,
        offset=offset,
    )


def _load_context(db: Session) -> ReferenceReadContext:
    root = default_repository_root()
    corpus_bundle = build_reference_corpus(repository_root=root)
    case_pack = load_reference_case_pack(corpus_bundle=corpus_bundle)
    matrix = load_runtime_matrix(root / "reference_workload" / "runtime_matrix.json")
    workload = db.scalar(
        select(WorkloadProfile).where(WorkloadProfile.slug == REFERENCE_WORKLOAD_SLUG)
    )
    suite = None
    if workload is not None:
        suite = db.scalar(
            select(EvaluationSuite)
            .where(EvaluationSuite.workload_profile_id == workload.id)
            .where(
                EvaluationSuite.version_label == corpus_bundle.manifest.contract.workload_version
            )
            .order_by(EvaluationSuite.created_at.desc())
        )
    configurations = _configuration_evidence(db, matrix=matrix, workload=workload, suite=suite)
    selected_results = [result for item in configurations for result in item.results]
    selected_result_case_map = {
        result.id: case
        for item in configurations
        for result, case in (
            (result, item.result_case_map.get(result.id)) for result in item.results
        )
        if case is not None
    }
    result_ids = {result.id for result in selected_results}
    decisions = (
        list(
            db.scalars(
                select(JudgeLabelReviewDecision)
                .where(JudgeLabelReviewDecision.benchmark_result_id.in_(result_ids))
                .order_by(JudgeLabelReviewDecision.reviewed_at.desc())
            )
        )
        if result_ids
        else []
    )
    decision_by_result: dict[UUID, JudgeLabelReviewDecision] = {}
    for decision in decisions:
        decision_by_result.setdefault(decision.benchmark_result_id, decision)
    return ReferenceReadContext(
        corpus_bundle=corpus_bundle,
        case_pack=case_pack,
        matrix=matrix,
        workload=workload,
        suite=suite,
        configurations=configurations,
        selected_results=selected_results,
        selected_result_case_map=selected_result_case_map,
        review_decisions=decision_by_result,
    )


def _configuration_evidence(
    db: Session,
    *,
    matrix: RuntimeMatrix,
    workload: WorkloadProfile | None,
    suite: EvaluationSuite | None,
) -> list[ConfigurationEvidence]:
    runs: list[BenchmarkRun] = []
    if workload is not None and suite is not None:
        runs = list(
            db.scalars(
                select(BenchmarkRun)
                .join(
                    DeploymentConfiguration,
                    BenchmarkRun.deployment_configuration_id == DeploymentConfiguration.id,
                )
                .where(DeploymentConfiguration.workload_profile_id == workload.id)
                .where(BenchmarkRun.evaluation_suite_id == suite.id)
                .where(BenchmarkRun.status == "completed")
                .where(BenchmarkRun.data_source == ACTUAL_RUNTIME_DATA_SOURCE)
                .order_by(BenchmarkRun.started_at.desc(), BenchmarkRun.created_at.desc())
            )
        )
    runs_by_entry: dict[str, list[BenchmarkRun]] = defaultdict(list)
    for run in runs:
        configuration = run.deployment_configuration
        if configuration is None:
            continue
        entry_name = _entry_name(configuration.name)
        if entry_name in {entry.name for entry in matrix.entries}:
            runs_by_entry[entry_name].append(run)

    expected_case_ids = (
        set(
            db.scalars(
                select(EvaluationCase.id)
                .where(EvaluationCase.evaluation_suite_id == suite.id)
                .where(EvaluationCase.is_active.is_(True))
            ).all()
        )
        if suite is not None
        else set()
    )
    trials_by_run: dict[UUID, Counter[UUID]] = defaultdict(Counter)
    if runs and expected_case_ids:
        rows = db.execute(
            select(
                BenchmarkResult.benchmark_run_id,
                BenchmarkResult.evaluation_case_id,
            )
            .where(BenchmarkResult.benchmark_run_id.in_([run.id for run in runs]))
            .where(BenchmarkResult.evaluation_case_id.in_(expected_case_ids))
        ).all()
        for run_id, case_id in rows:
            if case_id is not None:
                trials_by_run[run_id][case_id] += 1

    output: list[ConfigurationEvidence] = []
    for entry in matrix.entries:
        run = _select_reference_run(
            runs_by_entry.get(entry.name, []),
            entry=entry,
            expected_case_ids=expected_case_ids,
            trials_by_run=trials_by_run,
        )
        configuration = run.deployment_configuration if run is not None else None
        results = (
            list(
                db.scalars(
                    select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id == run.id)
                )
            )
            if run is not None
            else []
        )
        metrics = (
            list(
                db.scalars(
                    select(InferenceMetric).where(InferenceMetric.benchmark_run_id == run.id)
                )
            )
            if run is not None
            else []
        )
        case_ids = {
            result.evaluation_case_id for result in results if result.evaluation_case_id is not None
        }
        cases = (
            list(db.scalars(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))))
            if case_ids
            else []
        )
        cases_by_id = {case.id: case for case in cases}
        result_case_map = {
            result.id: cases_by_id[result.evaluation_case_id]
            for result in results
            if result.evaluation_case_id in cases_by_id
        }
        scorecard = _scorecard(
            configuration=configuration,
            suite=suite,
            run=run,
            results=results,
            metrics=metrics,
            cases=cases,
            result_case_map=result_case_map,
        )
        gate = _latest_gate(db, configuration=configuration, suite=suite)
        output.append(
            ConfigurationEvidence(
                entry=entry,
                configuration=configuration,
                run=run,
                results=results,
                metrics=metrics,
                cases=cases,
                result_case_map=result_case_map,
                scorecard=scorecard,
                gate=gate,
                read=_configuration_read(
                    entry=entry,
                    configuration=configuration,
                    run=run,
                    results=results,
                    metrics=metrics,
                    scorecard=scorecard,
                    gate=gate,
                    result_case_map=result_case_map,
                ),
            )
        )
    return output


def _scorecard(
    *,
    configuration: DeploymentConfiguration | None,
    suite: EvaluationSuite | None,
    run: BenchmarkRun | None,
    results: list[BenchmarkResult],
    metrics: list[InferenceMetric],
    cases: list[EvaluationCase],
    result_case_map: dict[UUID, EvaluationCase],
) -> dict[str, dict[str, Any]]:
    if configuration is None or suite is None or run is None:
        return {}
    bundle = EvidenceBundle(
        deployment_configuration=configuration,
        evaluation_suite=suite,
        active_cases=cases,
        runs=[run],
        results=results,
        metrics=metrics,
        source_distribution={ACTUAL_RUNTIME_DATA_SOURCE: len(results)},
        result_case_map=result_case_map,
    )
    return metrics_to_scorecard(calculate_metrics(bundle))


def _configuration_read(
    *,
    entry: RuntimeMatrixEntry,
    configuration: DeploymentConfiguration | None,
    run: BenchmarkRun | None,
    results: list[BenchmarkResult],
    metrics: list[InferenceMetric],
    scorecard: dict[str, dict[str, Any]],
    gate: GateEvaluation | None,
    result_case_map: dict[UUID, EvaluationCase],
) -> ReferenceConfigurationRead:
    runtime = configuration.runtime_config_json if configuration else {}
    trials = Counter(
        result.evaluation_case_id for result in results if result.evaluation_case_id is not None
    )
    critical_failures = _critical_outcomes(
        configuration=configuration,
        run=run,
        results=results,
        metrics=metrics,
        result_case_map=result_case_map,
    )
    human_reviewed_count = sum(
        _human_reviewed(result, result_case_map.get(result.id)) for result in results
    )
    digest = str(runtime.get("model_digest") or "") or None
    return ReferenceConfigurationRead(
        entry_name=entry.name,
        enabled=entry.enabled,
        status="disabled" if not entry.enabled else "completed" if run else "not_run",
        deployment_configuration_id=configuration.id if configuration else None,
        configuration_hash=configuration.configuration_hash if configuration else None,
        model_artifact_id=configuration.model_artifact_id if configuration else None,
        model_name=str(runtime.get("model") or "") or None,
        model_digest=digest,
        digest_status="observed" if digest else "missing" if run else "not_run",
        runtime_name=configuration.runtime_name if configuration else None,
        runtime_version=run.runtime_version if run else None,
        context_length=configuration.context_length if configuration else entry.context_length,
        prompt_bundle=(
            str(configuration.prompt_bundle_json.get("name") or entry.prompt_bundle)
            if configuration
            else entry.prompt_bundle
        ),
        generation_config=(
            configuration.generation_config_json if configuration else entry.generation.model_dump()
        ),
        concurrency=configuration.concurrency_target if configuration else entry.concurrency,
        latest_run_id=run.id if run else None,
        latest_run_started_at=run.started_at if run else None,
        latest_run_completed_at=run.completed_at if run else None,
        data_source=run.data_source if run else None,
        completed_case_count=len(trials),
        result_count=len(results),
        metric_count=len(metrics),
        minimum_trials_per_case=min(trials.values(), default=0),
        maximum_trials_per_case=max(trials.values(), default=0),
        error_count=sum(result.error_type is not None for result in results),
        timeout_count=sum(
            _runtime_trace_value(result, "within_timeout") is False for result in results
        ),
        oom_count=sum(metric.oom_occurred for metric in metrics),
        critical_failure_count=len(critical_failures),
        human_reviewed_count=human_reviewed_count,
        metrics=_metric_set(scorecard),
        gate_evaluation_id=gate.id if gate else None,
        gate_verdict=gate.verdict if gate else "NOT_EVALUATED",
    )


def _critical_outcomes(
    *,
    configuration: DeploymentConfiguration | None,
    run: BenchmarkRun | None,
    results: list[BenchmarkResult],
    metrics: list[InferenceMetric],
    result_case_map: dict[UUID, EvaluationCase],
) -> list[dict[str, Any]]:
    if configuration is None or run is None or run.evaluation_suite is None:
        return []
    bundle = EvidenceBundle(
        deployment_configuration=configuration,
        evaluation_suite=run.evaluation_suite,
        active_cases=list({case.id: case for case in result_case_map.values()}.values()),
        runs=[run],
        results=results,
        metrics=metrics,
        source_distribution={ACTUAL_RUNTIME_DATA_SOURCE: len(results)},
        result_case_map=result_case_map,
    )
    return [item for item in critical_case_outcomes(bundle) if item["status"] == "fail"]


def _comparison(configurations: list[ConfigurationEvidence]) -> ReferenceMetricComparisonRead:
    completed = [item for item in configurations if item.run is not None]
    baseline = completed[0] if completed else None
    rows: list[ReferenceMetricComparisonRowRead] = []
    for item in completed:
        rows.append(
            ReferenceMetricComparisonRowRead(
                entry_name=item.entry.name,
                deployment_configuration_id=item.configuration.id if item.configuration else None,
                benchmark_run_id=item.run.id,
                model_name=item.read.model_name,
                prompt_bundle=item.read.prompt_bundle,
                metrics=item.read.metrics,
                delta_from_baseline=_metric_delta(
                    baseline.read.metrics if baseline else ReferenceMetricSetRead(),
                    item.read.metrics,
                ),
            )
        )
    payload = {
        "baseline_entry_name": baseline.entry.name if baseline else None,
        "generated_from_run_ids": [str(item.run.id) for item in completed],
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    return ReferenceMetricComparisonRead(
        baseline_entry_name=payload["baseline_entry_name"],
        generated_from_run_ids=[item.run.id for item in completed],
        comparison_hash=stable_hash(payload),
        rows=rows,
    )


def _critical_failures(context: ReferenceReadContext) -> list[ReferenceCriticalFailureRead]:
    failures: list[ReferenceCriticalFailureRead] = []
    for item in context.configurations:
        if item.run is None or item.configuration is None:
            continue
        results_by_sample = {result.sample_id: result for result in item.results}
        for outcome in _critical_outcomes(
            configuration=item.configuration,
            run=item.run,
            results=item.results,
            metrics=item.metrics,
            result_case_map=item.result_case_map,
        ):
            result = results_by_sample.get(str(outcome["sample_id"]))
            if result is None:
                continue
            case = item.result_case_map.get(result.id)
            if case is None:
                continue
            decision = context.review_decisions.get(result.id)
            gate_href = f"/deployment-gates/{item.gate.id}" if item.gate else None
            failures.append(
                ReferenceCriticalFailureRead(
                    benchmark_result_id=result.id,
                    benchmark_run_id=item.run.id,
                    deployment_configuration_id=item.configuration.id,
                    entry_name=item.entry.name,
                    evaluation_case_id=case.id,
                    external_case_id=case.external_case_id,
                    title=case.title,
                    category=case.category,
                    criticality=case.criticality,
                    sample_id=result.sample_id,
                    failure_reason=_failure_reason(result),
                    expected_contract_summary=_contract_summary(
                        case.expected_output_json,
                        case.expected_tool_schema_json,
                    ),
                    observed_output_summary=_observed_summary(result.raw_output),
                    quality_score=result.quality_score,
                    groundedness_score=result.groundedness_score,
                    faithfulness_score=result.faithfulness_score,
                    evidence_source=result.data_source,
                    review_status=_review_status(result, case, decision),
                    benchmark_execution_href=f"/benchmark-executions/{item.run.id}",
                    judge_review_href=(
                        f"/judge-labels?benchmark_run_id={item.run.id}"
                        f"&benchmark_result_id={result.id}"
                    ),
                    gate_detail_href=gate_href,
                )
            )
    failures.sort(
        key=lambda failure: (
            failure.review_status != "unreviewed",
            failure.quality_score if failure.quality_score is not None else -1,
            failure.entry_name,
            failure.external_case_id,
            failure.sample_id,
        )
    )
    return failures


def _case_coverage(context: ReferenceReadContext) -> ReferenceCaseCoverageRead:
    active_count = 0
    critical_count = 0
    if context.suite is not None:
        stored = list(context.suite.cases)
        active_count = sum(case.is_active for case in stored)
        critical_count = sum(case.is_active and case.criticality == "critical" for case in stored)
    total = len(context.case_pack.cases)
    return ReferenceCaseCoverageRead(
        case_count=total,
        active_case_count=active_count,
        approved_case_count=context.case_pack.approved_case_count,
        approved_critical_case_count=context.case_pack.approved_critical_case_count,
        critical_case_count=critical_count,
        draft_case_count=context.case_pack.draft_case_count,
        rejected_case_count=context.case_pack.rejected_case_count,
        category_counts=context.case_pack.category_counts,
        critical_category_counts=context.case_pack.critical_category_counts,
        source_review_coverage_rate=(
            round(context.case_pack.approved_case_count / total, 4) if total else 0.0
        ),
    )


def _portfolio_checks(
    *,
    context: ReferenceReadContext,
    coverage: ReferenceCaseCoverageRead,
    review_coverage: ReferenceOutputReviewCoverageRead,
    critical_failure_count: int,
) -> list[ReferencePortfolioCheckRead]:
    completed = [item for item in context.configurations if item.run is not None]
    artifact_ids = {
        item.configuration.model_artifact_id for item in completed if item.configuration is not None
    }
    queued_count = critical_failure_count
    return [
        _check(
            "source_cases",
            "Approved source cases",
            coverage.approved_case_count >= 60,
            coverage.approved_case_count,
            60,
            "/reference-workload",
        ),
        _check(
            "critical_source_cases",
            "Approved critical source cases",
            coverage.approved_critical_case_count >= 20,
            coverage.approved_critical_case_count,
            20,
            "/reference-workload",
        ),
        _check(
            "runtime_configurations",
            "Completed runtime configurations",
            len(completed) >= REFERENCE_MATRIX_RESULT_MINIMUM,
            len(completed),
            REFERENCE_MATRIX_RESULT_MINIMUM,
            "/reference-workload",
        ),
        _check(
            "model_artifacts",
            "Distinct observed model artifacts",
            len(artifact_ids) >= REFERENCE_ARTIFACT_MINIMUM,
            len(artifact_ids),
            REFERENCE_ARTIFACT_MINIMUM,
            "/models",
        ),
        _check(
            "repeated_trials",
            "Minimum trials per case",
            bool(completed) and all(item.read.minimum_trials_per_case >= 2 for item in completed),
            min((item.read.minimum_trials_per_case for item in completed), default=0),
            2,
            "/reference-workload",
        ),
        _check(
            "critical_failure_queue",
            "Critical failures in review queue",
            queued_count == critical_failure_count,
            queued_count,
            critical_failure_count,
            "/judge-labels",
        ),
        _check(
            "model_output_review",
            "Human-reviewed model outputs",
            review_coverage.human_reviewed_count + review_coverage.applied_judge_label_count
            >= REFERENCE_OUTPUT_REVIEW_TARGET,
            review_coverage.human_reviewed_count + review_coverage.applied_judge_label_count,
            REFERENCE_OUTPUT_REVIEW_TARGET,
            "/judge-labels",
        ),
        _check(
            "gate_outcomes",
            "Configurations with Gate outcomes",
            bool(completed) and all(item.gate is not None for item in completed),
            sum(item.gate is not None for item in completed),
            len(completed),
            "/deployment-gates/new",
        ),
    ]


def _check(
    key: str,
    label: str,
    passed: bool,
    observed: int | str,
    required: int | str,
    href: str,
) -> ReferencePortfolioCheckRead:
    return ReferencePortfolioCheckRead(
        key=key,
        label=label,
        passed=passed,
        observed=observed,
        required=required,
        href=href,
    )


def _gate_outcome(
    db: Session,
    item: ConfigurationEvidence,
    trust_status: str,
) -> ReferenceGateOutcomeRead:
    if item.configuration is None:
        return ReferenceGateOutcomeRead(
            entry_name=item.entry.name,
            verdict="NOT_EVALUATED",
            evidence_trust_status=trust_status,
            release_readiness="NOT_EVALUATED",
            production_readiness="not_production_ready",
            decision_summary="No completed deployment configuration is available.",
        )
    if item.gate is None:
        return ReferenceGateOutcomeRead(
            entry_name=item.entry.name,
            deployment_configuration_id=item.configuration.id,
            verdict="NOT_EVALUATED",
            evidence_trust_status=trust_status,
            release_readiness="NOT_EVALUATED",
            production_readiness="not_production_ready",
            decision_summary="Stored evidence exists, but no Deployment Gate has evaluated it yet.",
        )
    release_status = "NEEDS_REVIEW"
    production_readiness = "not_production_ready"
    try:
        readiness = build_release_readiness_snapshot(
            db,
            gate_evaluation_id=item.gate.id,
        )
        release_status = readiness.status
        production_readiness = readiness.production_readiness
    except (DomainValidationError, AttributeError):
        pass
    return ReferenceGateOutcomeRead(
        entry_name=item.entry.name,
        deployment_configuration_id=item.configuration.id,
        gate_evaluation_id=item.gate.id,
        verdict=item.gate.verdict,
        evidence_trust_status=trust_status,
        release_readiness=release_status,
        production_readiness=production_readiness,
        decision_summary=item.gate.decision_summary,
        gate_detail_href=f"/deployment-gates/{item.gate.id}",
    )


def _overall_gate_verdict(outcomes: list[ReferenceGateOutcomeRead]) -> str:
    verdicts = [outcome.verdict for outcome in outcomes]
    if not verdicts or all(verdict == "NOT_EVALUATED" for verdict in verdicts):
        return "NOT_EVALUATED"
    for verdict in ("BLOCKED", "INSUFFICIENT_EVIDENCE"):
        if verdict in verdicts:
            return verdict
    if "NOT_EVALUATED" in verdicts:
        return "NOT_EVALUATED"
    for verdict in ("CONDITIONAL", "APPROVED"):
        if verdict in verdicts:
            return verdict
    return "NOT_EVALUATED"


def _next_actions(
    *,
    review_coverage: ReferenceOutputReviewCoverageRead,
    configurations: list[ConfigurationEvidence],
) -> list[ReferenceNextActionRead]:
    actions: list[ReferenceNextActionRead] = []
    if review_coverage.remaining_to_target:
        actions.append(
            ReferenceNextActionRead(
                priority="high",
                title=f"Review {review_coverage.remaining_to_target} model outputs",
                description="Apply explicit human decisions, starting with critical failures.",
                href="/judge-labels",
            )
        )
    missing_gates = sum(item.run is not None and item.gate is None for item in configurations)
    if missing_gates:
        actions.append(
            ReferenceNextActionRead(
                priority="high",
                title=f"Evaluate {missing_gates} configuration Gate outcomes",
                description="Use the existing Gate Preflight and Deployment Gate path.",
                href="/deployment-gates/new",
            )
        )
    actions.append(
        ReferenceNextActionRead(
            priority="medium",
            title="Download the evidence report",
            description=(
                "Export the stored Gate outcomes, metrics, failures, and reproduction evidence."
            ),
            href="/reference-workload",
        )
    )
    return actions


def _limitations(
    *,
    context: ReferenceReadContext,
    review_coverage: ReferenceOutputReviewCoverageRead,
    production_count: int,
) -> list[str]:
    limitations = [
        "The compared results are actual local-runtime evidence, not production-captured evidence.",
        (
            "Small local models show substantial RAG, Tool, and Agent quality "
            "failures on this workload."
        ),
    ]
    if review_coverage.remaining_to_target:
        reviewed_count = (
            review_coverage.human_reviewed_count + review_coverage.applied_judge_label_count
        )
        limitations.append(
            f"Human model-output review is {reviewed_count}/{REFERENCE_OUTPUT_REVIEW_TARGET}."
        )
    missing_gates = sum(
        item.run is not None and item.gate is None for item in context.configurations
    )
    if missing_gates:
        limitations.append(
            f"{missing_gates} completed configurations do not yet have Gate outcomes."
        )
    if production_count == 0:
        limitations.append("No signed production collector receipt is linked to the selected runs.")
    limitations.append(
        "The local lexical retriever is deterministic and is not a production "
        "vector-search service."
    )
    return limitations


def _workload_definition(context: ReferenceReadContext) -> ReferenceWorkloadDefinitionRead:
    contract = context.corpus_bundle.manifest.contract
    workload = context.workload
    suite = context.suite
    return ReferenceWorkloadDefinitionRead(
        id=workload.id if workload else None,
        name=workload.name if workload else "Model Atlas Korean Operator Assistant",
        slug=contract.workload_slug,
        version=contract.workload_version,
        description=(
            workload.description
            if workload
            else (
                "Korean operator workload for grounded guidance, bounded Tools, "
                "refusal, recovery, and Agent evaluation."
            )
        ),
        domain=workload.domain if workload else "ai_platform_operations",
        primary_language=workload.primary_language if workload else contract.language,
        local_only_required=workload.local_only_required if workload else True,
        evaluation_suite_id=suite.id if suite else None,
        evaluation_suite_name=suite.name if suite else REFERENCE_SUITE_NAME,
        evaluation_suite_status=suite.status if suite else "not_bootstrapped",
        evaluation_suite_hash=suite.suite_hash if suite else None,
    )


def _manifest_summary(bundle: ReferenceCorpusBundle) -> ReferenceManifestRead:
    return ReferenceManifestRead(
        schema_version=bundle.manifest.contract.schema_version,
        manifest_hash=bundle.manifest.manifest_hash,
        file_count=len(bundle.manifest.files),
        total_bytes=sum(item.size_bytes for item in bundle.manifest.files),
        source_paths=[item.path for item in bundle.manifest.files],
    )


def _corpus_summary(bundle: ReferenceCorpusBundle) -> ReferenceCorpusRead:
    contract = bundle.manifest.contract.corpus
    return ReferenceCorpusRead(
        corpus_id=bundle.corpus.corpus_id,
        corpus_version=bundle.corpus.corpus_version,
        corpus_hash=bundle.corpus.corpus_hash,
        chunking_version=contract.chunking_version,
        chunk_count=len(bundle.corpus.chunks),
    )


def _metric_set(scorecard: dict[str, dict[str, Any]]) -> ReferenceMetricSetRead:
    values = {key: _metric_value(scorecard, key) for key in COMPARISON_METRICS}
    values["task_completion_rate"] = _metric_value(scorecard, "reliability_success_rate")
    return ReferenceMetricSetRead(**values)


def _metric_value(scorecard: dict[str, dict[str, Any]], key: str) -> float | None:
    value = (scorecard.get(key) or {}).get("value")
    return round(float(value), 6) if value is not None else None


def _metric_delta(
    baseline: ReferenceMetricSetRead,
    candidate: ReferenceMetricSetRead,
) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    for key in COMPARISON_METRICS:
        left = getattr(baseline, key)
        right = getattr(candidate, key)
        output[key] = round(right - left, 6) if left is not None and right is not None else None
    return output


def _latest_gate(
    db: Session,
    *,
    configuration: DeploymentConfiguration | None,
    suite: EvaluationSuite | None,
) -> GateEvaluation | None:
    if configuration is None or suite is None:
        return None
    return db.scalar(
        select(GateEvaluation)
        .where(GateEvaluation.deployment_configuration_id == configuration.id)
        .where(GateEvaluation.evaluation_suite_id == suite.id)
        .order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.created_at.desc())
    )


def _select_reference_run(
    candidates: list[BenchmarkRun],
    *,
    entry: RuntimeMatrixEntry,
    expected_case_ids: set[UUID],
    trials_by_run: dict[UUID, Counter[UUID]],
) -> BenchmarkRun | None:
    if not candidates:
        return None
    if expected_case_ids:
        for run in candidates:
            trial_counts = trials_by_run.get(run.id, Counter())
            if all(trial_counts[case_id] >= entry.trials for case_id in expected_case_ids):
                return run
    return candidates[0]


def _entry_name(configuration_name: str) -> str:
    return configuration_name.removeprefix("Reference runtime: ").strip()


def _runtime_trace_value(result: BenchmarkResult, key: str) -> Any:
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    trace = metadata.get("runtime_reliability")
    return trace.get(key) if isinstance(trace, dict) else None


def _human_reviewed(result: BenchmarkResult, case: EvaluationCase | None) -> bool:
    return classify_score_tier(result, case).value in {"human_reviewed", "applied_judge_label"}


def _result_failed(result: BenchmarkResult) -> bool:
    if result.error_type:
        return True
    if result.exact_match is False:
        return True
    if result.quality_score is not None and result.quality_score < 0.8:
        return True
    return _runtime_trace_value(result, "status") == "error"


def _failure_reason(result: BenchmarkResult) -> str:
    if result.error_type:
        return result.error_type
    status = _runtime_trace_value(result, "status")
    if status and status != "success":
        return f"runtime_{status}"
    if result.quality_score is not None and result.quality_score < 0.8:
        return "quality_below_critical_threshold"
    return "critical_contract_failed"


def _review_status(
    result: BenchmarkResult,
    case: EvaluationCase,
    decision: JudgeLabelReviewDecision | None,
) -> str:
    if decision is not None:
        return "human_reviewed" if decision.identity_verified else decision.decision_type
    return "human_reviewed" if _human_reviewed(result, case) else "unreviewed"


def _contract_summary(expected: Any, tool_schema: Any) -> str:
    payload: dict[str, Any] = {}
    if isinstance(expected, dict):
        payload["expected_output"] = expected
    if isinstance(tool_schema, dict):
        payload["expected_tool"] = tool_schema
    return _truncate(json.dumps(payload, ensure_ascii=False, sort_keys=True), 320) or "No contract"


def _observed_summary(raw_output: str | None) -> str:
    if not raw_output:
        return "No model output was recorded."
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("answer", "final_response", "message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return _truncate(_normalize_text(value), 320)
    return _truncate(_normalize_text(raw_output), 320)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _truncate(value: str, limit: int) -> str:
    normalized = value.strip()
    return normalized if len(normalized) <= limit else f"{normalized[: limit - 3]}..."


def _evaluation_complete(configurations: list[ConfigurationEvidence]) -> bool:
    completed = [item for item in configurations if item.run is not None]
    artifacts = {
        item.configuration.model_artifact_id for item in completed if item.configuration is not None
    }
    return (
        len(completed) >= REFERENCE_MATRIX_RESULT_MINIMUM
        and len(artifacts) >= REFERENCE_ARTIFACT_MINIMUM
        and all(item.read.completed_case_count >= 60 for item in completed)
        and all(item.read.minimum_trials_per_case >= 2 for item in completed)
    )
