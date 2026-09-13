from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AcceptancePolicy, BenchmarkResult, EvaluationCase, GateEvaluation
from app.reference_workload.bootstrap import REFERENCE_POLICY_NAME
from app.schemas import GateEvaluationCreate, GatePreflightRequest
from app.schemas.reference_workload import (
    ReferenceArtifactWriteSummaryRead,
    ReferenceCategoryMetricRead,
    ReferenceGateReportOutcomeRead,
    ReferenceGateRuleResultRead,
    ReferenceGateRunEntryRead,
    ReferenceGateRunSummaryRead,
    ReferenceLinkedEvidenceRead,
    ReferenceReproductionArtifactRead,
    ReferenceReproductionManifestRead,
    ReferenceWorkloadReportRead,
)
from app.services.deployment_gate.evaluator import create_gate_evaluation
from app.services.deployment_gate.preflight import build_gate_preflight
from app.services.deployment_gate.staleness import reconcile_all_gate_staleness
from app.services.evidence_trust import classify_score_tier
from app.services.reference_workload_read_model import build_reference_workload_overview
from app.services.release_readiness import build_release_readiness_snapshot
from app.validators import DomainValidationError

REPORT_JSON_NAME = "reference-workload-report.json"
REPORT_MARKDOWN_NAME = "reference-workload-report.md"
COMPARISON_CSV_NAME = "configuration-comparison.csv"
CRITICAL_FAILURES_NAME = "critical-failures.json"
REPRODUCTION_MANIFEST_NAME = "reproduction-manifest.json"


def run_reference_workload_gates(db: Session) -> ReferenceGateRunSummaryRead:
    overview = build_reference_workload_overview(db)
    workload_id = overview.workload.id
    suite_id = overview.workload.evaluation_suite_id
    if workload_id is None or suite_id is None:
        raise DomainValidationError(
            "reference workload must be bootstrapped before Gate evaluation"
        )
    policy = _reference_policy(db, workload_id)
    reconciliation = reconcile_all_gate_staleness(db)
    if reconciliation.stale_count:
        db.commit()

    entries: list[ReferenceGateRunEntryRead] = []
    for configuration in overview.configuration_matrix:
        if configuration.status != "completed" or configuration.deployment_configuration_id is None:
            entries.append(
                ReferenceGateRunEntryRead(
                    entry_name=configuration.entry_name,
                    status="not_run",
                    deployment_configuration_id=configuration.deployment_configuration_id,
                    preflight_can_evaluate=False,
                    blocking_preconditions=[
                        "No completed current runtime-matrix run is available."
                    ],
                    warnings=[],
                )
            )
            continue

        payload = GatePreflightRequest(
            deployment_configuration_id=configuration.deployment_configuration_id,
            evaluation_suite_id=suite_id,
            acceptance_policy_id=policy.id,
        )
        preflight = build_gate_preflight(db, payload)
        if not preflight.can_evaluate:
            entries.append(
                ReferenceGateRunEntryRead(
                    entry_name=configuration.entry_name,
                    status="blocked",
                    deployment_configuration_id=configuration.deployment_configuration_id,
                    preflight_can_evaluate=False,
                    blocking_preconditions=preflight.blocking_preconditions,
                    warnings=preflight.warnings,
                )
            )
            continue

        existing = _latest_current_gate(
            db,
            configuration_id=configuration.deployment_configuration_id,
            suite_id=suite_id,
            policy_id=policy.id,
        )
        if existing is not None:
            entries.append(
                ReferenceGateRunEntryRead(
                    entry_name=configuration.entry_name,
                    status="reused",
                    deployment_configuration_id=configuration.deployment_configuration_id,
                    gate_evaluation_id=existing.id,
                    verdict=existing.verdict,
                    preflight_can_evaluate=True,
                    blocking_preconditions=[],
                    warnings=preflight.warnings,
                )
            )
            continue

        gate = create_gate_evaluation(
            db,
            GateEvaluationCreate(
                deployment_configuration_id=configuration.deployment_configuration_id,
                evaluation_suite_id=suite_id,
                acceptance_policy_id=policy.id,
            ),
        )
        entries.append(
            ReferenceGateRunEntryRead(
                entry_name=configuration.entry_name,
                status="created",
                deployment_configuration_id=configuration.deployment_configuration_id,
                gate_evaluation_id=gate.id,
                verdict=gate.verdict,
                preflight_can_evaluate=True,
                blocking_preconditions=[],
                warnings=preflight.warnings,
            )
        )

    return ReferenceGateRunSummaryRead(
        generated_at=_utcnow(),
        workload_profile_id=workload_id,
        evaluation_suite_id=suite_id,
        acceptance_policy_id=policy.id,
        created_count=sum(entry.status == "created" for entry in entries),
        reused_count=sum(entry.status == "reused" for entry in entries),
        blocked_count=sum(entry.status == "blocked" for entry in entries),
        entries=entries,
    )


def build_reference_workload_report(db: Session) -> ReferenceWorkloadReportRead:
    overview = build_reference_workload_overview(db)
    gate_outcomes = _gate_report_outcomes(db, overview)
    run_entry_names = {run.id: run.entry_name for run in overview.latest_runs}
    result_rows, cases_by_id = _selected_results(db, set(run_entry_names))
    linked = ReferenceLinkedEvidenceRead(
        workload_profile_id=overview.workload.id,
        evaluation_suite_id=overview.workload.evaluation_suite_id,
        deployment_configuration_ids=_unique_ids(
            item.deployment_configuration_id for item in overview.configuration_matrix
        ),
        model_artifact_ids=_unique_ids(
            item.model_artifact_id for item in overview.configuration_matrix
        ),
        benchmark_run_ids=list(run_entry_names),
        benchmark_result_ids=[result.id for result in result_rows],
        critical_result_ids=[failure.benchmark_result_id for failure in overview.critical_failures],
        gate_evaluation_ids=[outcome.gate_evaluation_id for outcome in gate_outcomes],
    )
    return ReferenceWorkloadReportRead(
        generated_at=_utcnow(),
        workload=overview.workload,
        manifest=overview.manifest,
        corpus=overview.corpus,
        case_coverage=overview.case_coverage,
        review_coverage=overview.review_coverage,
        evaluation_status=overview.evaluation_status,
        configuration_matrix=overview.configuration_matrix,
        metric_comparison=overview.metric_comparison,
        comparison_hash=overview.comparison_hash,
        category_metrics=_category_metrics(
            result_rows=result_rows,
            cases_by_id=cases_by_id,
            run_entry_names=run_entry_names,
        ),
        critical_failures=overview.critical_failures,
        gate_outcomes=gate_outcomes,
        gate_verdict=overview.gate_verdict,
        evidence_trust=overview.evidence_trust,
        release_readiness=_overall_release_readiness(gate_outcomes),
        production_readiness=overview.production_readiness,
        portfolio_completion=overview.portfolio_completion,
        incomplete_matrix_entries=[
            item.entry_name for item in overview.configuration_matrix if item.status != "completed"
        ],
        reproduction_commands=[
            *overview.reproduction_commands,
            "make reference-gate",
            "make reference-report",
        ],
        limitations=overview.limitations,
        linked_evidence_ids=linked,
    )


def render_reference_workload_markdown(report: ReferenceWorkloadReportRead) -> str:
    reviewed_output_count = (
        report.review_coverage.human_reviewed_count
        + report.review_coverage.applied_judge_label_count
    )
    lines = [
        "# Model Atlas Reference Workload Report",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        f"Schema: `{report.schema_version}`",
        "",
        "## Decision Summary",
        "",
        f"- Evaluation: `{report.evaluation_status}`",
        f"- Gate: `{report.gate_verdict}`",
        f"- Evidence Trust: `{report.evidence_trust.trust_status}`",
        f"- Release Readiness: `{report.release_readiness}`",
        f"- Production Readiness: `{report.production_readiness}`",
        f"- Portfolio Completion: `{report.portfolio_completion.status}`",
        "",
        "Local actual-runtime evidence does not establish production readiness.",
        "",
        "## Workload and Evidence",
        "",
        f"- Workload: `{report.workload.slug}` v{report.workload.version}",
        f"- Corpus: `{report.corpus.corpus_id}` v{report.corpus.corpus_version}",
        f"- Source cases: {report.case_coverage.approved_case_count} approved, "
        f"{report.case_coverage.approved_critical_case_count} critical",
        f"- Actual-runtime Results: {report.review_coverage.result_count}",
        f"- Heuristic-only Results: {report.evidence_trust.heuristic_only_count}",
        f"- Candidate judge labels: {report.evidence_trust.candidate_judge_label_count}",
        f"- Applied judge labels: {report.evidence_trust.applied_judge_label_count}",
        f"- Explicitly human-reviewed Results: {report.evidence_trust.human_reviewed_count}",
        f"- Total applied or human-reviewed Results: {reviewed_output_count}",
        f"- Production-captured Results: {report.evidence_trust.production_captured_count}",
        f"- Critical failures: {len(report.critical_failures)}",
        "",
        "## Configuration Identity",
        "",
    ]
    for item in report.configuration_matrix:
        lines.extend(
            [
                f"### {item.entry_name}",
                "",
                f"- Configuration ID: `{item.deployment_configuration_id or 'not run'}`",
                f"- Configuration hash: `{item.configuration_hash or 'not observed'}`",
                f"- Model artifact ID: `{item.model_artifact_id or 'not observed'}`",
                f"- Model: `{item.model_name or 'not observed'}`",
                f"- Model digest: `{item.model_digest or 'not observed'}`",
                f"- Runtime: `{item.runtime_name or 'not observed'}` "
                f"`{item.runtime_version or 'version unavailable'}`",
                f"- Context length: {item.context_length}",
                f"- Prompt bundle: `{item.prompt_bundle}`",
                f"- Generation config: `{json.dumps(item.generation_config, sort_keys=True)}`",
                "",
            ]
        )
    lines.extend(
        [
        "## Configuration Comparison",
        "",
        "| Configuration | Model | Prompt | Cases | Quality | Groundedness | Tool success | "
        "Task completion | P95 ms | Critical failures | Gate |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    gates = {item.entry_name: item.verdict for item in report.gate_outcomes}
    for item in report.configuration_matrix:
        metrics = item.metrics
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(item.entry_name),
                    _cell(item.model_name or "not observed"),
                    _cell(item.prompt_bundle),
                    str(item.completed_case_count),
                    _number(metrics.mean_quality_score),
                    _number(metrics.rag_groundedness_score),
                    _number(metrics.tool_execution_success_rate),
                    _number(metrics.task_completion_rate),
                    _number(metrics.p95_end_to_end_latency_ms, digits=1),
                    str(item.critical_failure_count),
                    gates.get(item.entry_name, "NOT_EVALUATED"),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Category Metrics",
            "",
            "| Configuration | Category | Results | Failed | Reviewed | Mean quality | "
            "Groundedness | Errors |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report.category_metrics:
        lines.append(
            f"| {_cell(item.entry_name)} | {_cell(item.category)} | {item.result_count} | "
            f"{item.failed_result_count} | {item.reviewed_result_count} | "
            f"{_number(item.mean_quality_score)} | {_number(item.mean_groundedness_score)} | "
            f"{item.error_count} |"
        )

    lines.extend(["", "## Gate Outcomes", ""])
    if not report.gate_outcomes:
        lines.append("- No stored Gate outcomes.")
    for gate in report.gate_outcomes:
        lines.extend(
            [
                f"### {gate.entry_name}",
                "",
                f"- Verdict: `{gate.verdict}`",
                f"- Release readiness: `{gate.release_readiness}`",
                f"- Production readiness: `{gate.production_readiness}`",
                f"- Gate ID: `{gate.gate_evaluation_id}`",
                f"- Decision hash: `{gate.decision_hash}`",
                f"- Summary: {gate.decision_summary}",
                "",
                "| Rule | Metric | Value | Samples | Status | Severity |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for rule in gate.rule_results:
            lines.append(
                f"| {_cell(rule.rule_name)} | `{_cell(rule.metric_key)}` | "
                f"{_number(rule.metric_value)} | {rule.sample_size} | {rule.status} | "
                f"{rule.severity} |"
            )

    lines.extend(["", "## Critical Failures", ""])
    if not report.critical_failures:
        lines.append("- No critical failures in the selected runs.")
    for failure in report.critical_failures:
        lines.append(
            f"- `{failure.external_case_id}` / `{failure.entry_name}` / "
            f"`{failure.failure_reason}` / review `{failure.review_status}` / "
            f"run `{failure.benchmark_run_id}`"
        )

    lines.extend(["", "## Reproduction", "", "```text"])
    lines.extend(report.reproduction_commands)
    lines.extend(["```", "", "## Linked Evidence", ""])
    linked = report.linked_evidence_ids
    configuration_ids = _markdown_ids(linked.deployment_configuration_ids)
    benchmark_run_ids = _markdown_ids(linked.benchmark_run_ids)
    gate_evaluation_ids = _markdown_ids(linked.gate_evaluation_ids)
    lines.extend(
        [
            f"- Workload profile: `{linked.workload_profile_id or 'none'}`",
            f"- Evaluation suite: `{linked.evaluation_suite_id or 'none'}`",
            f"- Deployment configurations: {configuration_ids}",
            f"- Benchmark runs: {benchmark_run_ids}",
            f"- Gate evaluations: {gate_evaluation_ids}",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in report.limitations],
        ]
    )
    return "\n".join(lines) + "\n"


def write_reference_workload_artifacts(
    report: ReferenceWorkloadReportRead,
    output_directory: Path,
) -> ReferenceArtifactWriteSummaryRead:
    output_directory.mkdir(parents=True, exist_ok=True)
    report_bytes = _json_bytes(report.model_dump(mode="json"))
    markdown_bytes = render_reference_workload_markdown(report).encode("utf-8")
    comparison_bytes = _comparison_csv(report).encode("utf-8-sig")
    failures_bytes = _json_bytes(
        {
            "schema_version": "model-atlas-reference-critical-failures-v1",
            "generated_at": report.generated_at.isoformat(),
            "gate_verdict": report.gate_verdict,
            "production_readiness": report.production_readiness,
            "items": [item.model_dump(mode="json") for item in report.critical_failures],
        }
    )
    payloads = {
        REPORT_JSON_NAME: report_bytes,
        REPORT_MARKDOWN_NAME: markdown_bytes,
        COMPARISON_CSV_NAME: comparison_bytes,
        CRITICAL_FAILURES_NAME: failures_bytes,
    }
    for name, content in payloads.items():
        _atomic_write(output_directory / name, content)
    artifacts = [_artifact(output_directory / name, content) for name, content in payloads.items()]
    report_sha256 = _sha256(report_bytes)
    reproduction = ReferenceReproductionManifestRead(
        generated_at=report.generated_at,
        report_schema_version=report.schema_version,
        report_sha256=report_sha256,
        workload_slug=report.workload.slug,
        workload_version=report.workload.version,
        manifest_hash=report.manifest.manifest_hash,
        corpus_hash=report.corpus.corpus_hash,
        evaluation_suite_hash=report.workload.evaluation_suite_hash,
        comparison_hash=report.comparison_hash,
        production_readiness=report.production_readiness,
        linked_evidence_ids=report.linked_evidence_ids,
        commands=report.reproduction_commands,
        artifacts=artifacts,
    )
    reproduction_bytes = _json_bytes(reproduction.model_dump(mode="json"))
    reproduction_path = output_directory / REPRODUCTION_MANIFEST_NAME
    _atomic_write(reproduction_path, reproduction_bytes)
    all_artifacts = [*artifacts, _artifact(reproduction_path, reproduction_bytes)]
    return ReferenceArtifactWriteSummaryRead(
        output_directory=str(output_directory),
        report_sha256=report_sha256,
        artifacts=all_artifacts,
        production_readiness=report.production_readiness,
    )


def _reference_policy(db: Session, workload_id: UUID) -> AcceptancePolicy:
    policy = db.scalar(
        select(AcceptancePolicy)
        .where(AcceptancePolicy.workload_profile_id == workload_id)
        .where(AcceptancePolicy.name == REFERENCE_POLICY_NAME)
        .order_by(AcceptancePolicy.created_at.desc())
    )
    if policy is None:
        raise DomainValidationError("reference workload acceptance policy was not found")
    return policy


def _latest_current_gate(
    db: Session,
    *,
    configuration_id: UUID,
    suite_id: UUID,
    policy_id: UUID,
) -> GateEvaluation | None:
    return db.scalar(
        select(GateEvaluation)
        .where(GateEvaluation.deployment_configuration_id == configuration_id)
        .where(GateEvaluation.evaluation_suite_id == suite_id)
        .where(GateEvaluation.acceptance_policy_id == policy_id)
        .where(GateEvaluation.status == "completed")
        .where(GateEvaluation.stale_at.is_(None))
        .order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.created_at.desc())
    )


def _gate_report_outcomes(db: Session, overview: Any) -> list[ReferenceGateReportOutcomeRead]:
    if overview.workload.id is None or overview.workload.evaluation_suite_id is None:
        return []
    policy = _reference_policy(db, overview.workload.id)
    output: list[ReferenceGateReportOutcomeRead] = []
    for configuration in overview.configuration_matrix:
        if configuration.deployment_configuration_id is None:
            continue
        gate = db.scalar(
            select(GateEvaluation)
            .where(
                GateEvaluation.deployment_configuration_id
                == configuration.deployment_configuration_id
            )
            .where(GateEvaluation.evaluation_suite_id == overview.workload.evaluation_suite_id)
            .where(GateEvaluation.acceptance_policy_id == policy.id)
            .order_by(GateEvaluation.evaluated_at.desc(), GateEvaluation.created_at.desc())
        )
        if gate is None:
            continue
        release_status = "NOT_EVALUATED"
        release_summary = "No release-readiness snapshot is available."
        production_readiness = "not_production_ready"
        try:
            readiness = build_release_readiness_snapshot(db, gate_evaluation_id=gate.id)
            release_status = readiness.status
            release_summary = readiness.release_summary
            production_readiness = readiness.production_readiness
        except DomainValidationError:
            pass
        rule_results = (gate.scorecard_json or {}).get("rule_results") or []
        output.append(
            ReferenceGateReportOutcomeRead(
                entry_name=configuration.entry_name,
                deployment_configuration_id=configuration.deployment_configuration_id,
                gate_evaluation_id=gate.id,
                acceptance_policy_id=gate.acceptance_policy_id,
                status=gate.status,
                verdict=gate.verdict,
                decision_summary=gate.decision_summary,
                decision_hash=gate.decision_hash,
                evidence_revision_hash=gate.evidence_revision_hash,
                evaluated_at=gate.evaluated_at,
                stale=gate.stale_at is not None or gate.status == "stale",
                rule_results=[
                    ReferenceGateRuleResultRead(
                        rule_name=str(rule.get("rule_name") or "Unnamed rule"),
                        metric_key=str(rule.get("metric_key") or "unknown"),
                        metric_value=rule.get("metric_value"),
                        sample_size=int(rule.get("sample_size") or 0),
                        status=str(rule.get("status") or "unknown"),
                        severity=str(rule.get("severity") or "unknown"),
                        details=dict(rule.get("details") or {}),
                    )
                    for rule in rule_results
                    if isinstance(rule, dict)
                ],
                release_readiness=release_status,
                release_summary=release_summary,
                production_readiness=production_readiness,
                gate_detail_href=f"/deployment-gates/{gate.id}",
                release_readiness_href=(f"/release-readiness?gate_evaluation_id={gate.id}"),
            )
        )
    return output


def _selected_results(
    db: Session,
    run_ids: set[UUID],
) -> tuple[list[BenchmarkResult], dict[UUID, EvaluationCase]]:
    if not run_ids:
        return [], {}
    results = list(
        db.scalars(select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id.in_(run_ids)))
    )
    case_ids = {
        result.evaluation_case_id for result in results if result.evaluation_case_id is not None
    }
    cases = (
        list(db.scalars(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))))
        if case_ids
        else []
    )
    return results, {case.id: case for case in cases}


def _category_metrics(
    *,
    result_rows: list[BenchmarkResult],
    cases_by_id: dict[UUID, EvaluationCase],
    run_entry_names: dict[UUID, str],
) -> list[ReferenceCategoryMetricRead]:
    grouped: dict[tuple[str, str], list[tuple[BenchmarkResult, EvaluationCase]]] = defaultdict(list)
    for result in result_rows:
        case = cases_by_id.get(result.evaluation_case_id)
        entry_name = run_entry_names.get(result.benchmark_run_id)
        if case is not None and entry_name is not None:
            grouped[(entry_name, case.category)].append((result, case))
    output: list[ReferenceCategoryMetricRead] = []
    for (entry_name, category), rows in sorted(grouped.items()):
        results = [row[0] for row in rows]
        quality = [item.quality_score for item in results if item.quality_score is not None]
        exact = [item.exact_match for item in results if item.exact_match is not None]
        groundedness = [
            item.groundedness_score for item in results if item.groundedness_score is not None
        ]
        json_rows = [
            result
            for result, case in rows
            if case.expected_output_json is not None or "json" in case.category.lower()
        ]
        tool_rows = [
            result
            for result, case in rows
            if case.expected_tool_schema_json is not None or "tool" in case.category.lower()
        ]
        output.append(
            ReferenceCategoryMetricRead(
                entry_name=entry_name,
                category=category,
                result_count=len(results),
                critical_result_count=sum(case.criticality == "critical" for _, case in rows),
                failed_result_count=sum(_result_failed(result) for result in results),
                reviewed_result_count=sum(
                    classify_score_tier(result, case).value
                    in {"human_reviewed", "applied_judge_label"}
                    for result, case in rows
                ),
                mean_quality_score=_mean(quality),
                exact_match_rate=_rate(exact),
                json_validity_rate=_rate([item.json_valid for item in json_rows]),
                tool_call_validity_rate=_rate([item.tool_call_valid for item in tool_rows]),
                mean_groundedness_score=_mean(groundedness),
                error_count=sum(item.error_type is not None for item in results),
            )
        )
    return output


def _result_failed(result: BenchmarkResult) -> bool:
    if result.error_type or result.exact_match is False:
        return True
    if result.quality_score is not None and result.quality_score < 0.8:
        return True
    metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
    reliability = metadata.get("runtime_reliability")
    return isinstance(reliability, dict) and reliability.get("status") != "success"


def _overall_release_readiness(outcomes: list[ReferenceGateReportOutcomeRead]) -> str:
    statuses = {item.release_readiness for item in outcomes}
    for status in ("BLOCKED", "INSUFFICIENT_EVIDENCE", "NEEDS_REVIEW"):
        if status in statuses:
            return status
    if not statuses:
        return "NOT_EVALUATED"
    if "READY_TO_PROMOTE" in statuses:
        return "READY_TO_PROMOTE"
    return "READY" if statuses == {"READY"} else sorted(statuses)[0]


def _comparison_csv(report: ReferenceWorkloadReportRead) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "entry_name",
            "model_name",
            "model_digest",
            "runtime_name",
            "context_length",
            "prompt_bundle",
            "completed_case_count",
            "result_count",
            "mean_quality_score",
            "rag_groundedness_score",
            "tool_execution_success_rate",
            "task_completion_rate",
            "p95_end_to_end_latency_ms",
            "critical_failure_count",
            "human_reviewed_count",
            "gate_verdict",
        ],
    )
    writer.writeheader()
    gates = {item.entry_name: item.verdict for item in report.gate_outcomes}
    for item in report.configuration_matrix:
        writer.writerow(
            {
                "entry_name": item.entry_name,
                "model_name": item.model_name,
                "model_digest": item.model_digest,
                "runtime_name": item.runtime_name,
                "context_length": item.context_length,
                "prompt_bundle": item.prompt_bundle,
                "completed_case_count": item.completed_case_count,
                "result_count": item.result_count,
                "mean_quality_score": item.metrics.mean_quality_score,
                "rag_groundedness_score": item.metrics.rag_groundedness_score,
                "tool_execution_success_rate": item.metrics.tool_execution_success_rate,
                "task_completion_rate": item.metrics.task_completion_rate,
                "p95_end_to_end_latency_ms": item.metrics.p95_end_to_end_latency_ms,
                "critical_failure_count": item.critical_failure_count,
                "human_reviewed_count": item.human_reviewed_count,
                "gate_verdict": gates.get(item.entry_name, "NOT_EVALUATED"),
            }
        )
    return output.getvalue()


def _artifact(path: Path, content: bytes) -> ReferenceReproductionArtifactRead:
    return ReferenceReproductionArtifactRead(
        path=path.name,
        sha256=_sha256(content),
        size_bytes=len(content),
    )


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _unique_ids(values: Any) -> list[UUID]:
    return list(dict.fromkeys(value for value in values if value is not None))


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None


def _rate(values: list[bool]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _number(value: float | None, *, digits: int = 6) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _markdown_ids(values: list[UUID]) -> str:
    return ", ".join(f"`{item}`" for item in values) or "none"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(microsecond=0)
