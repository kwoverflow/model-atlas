from __future__ import annotations

import hashlib
import json
from collections import Counter
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
    InferenceMetric,
)
from app.services.evidence_trust import (
    EVIDENCE_TRUST_VERSION,
    EvidenceTrustSummary,
    summarize_evidence_trust,
)
from app.services.tool_fault_scenarios import TOOL_FAULT_DATA_SOURCE

CALCULATION_VERSION = "deployment-gate-sprint-5d-v1"
GATE_EVIDENCE_SCHEMA_VERSION = "gate-evidence-snapshot-v8"
SYNTHETIC_SOURCE = "synthetic_demo"
KNOWN_ADAPTER_VERSIONS = {
    "mock": "mock-adapter-v6",
    "openai_compatible": "openai-compatible-v7",
}


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def deployment_configuration_hash(payload: dict[str, Any]) -> str:
    relevant_fields = {
        "workload_profile_id": str(payload["workload_profile_id"]),
        "hardware_profile_id": str(payload["hardware_profile_id"]),
        "model_artifact_id": str(payload["model_artifact_id"]),
        "runtime_name": payload["runtime_name"],
        "runtime_version": payload.get("runtime_version"),
        "runtime_config_json": payload.get("runtime_config_json") or {},
        "context_length": payload["context_length"],
        "generation_config_json": payload.get("generation_config_json") or {},
        "prompt_bundle_json": payload.get("prompt_bundle_json") or {},
        "output_schema_version": payload.get("output_schema_version"),
        "tool_schema_version": payload.get("tool_schema_version"),
        "retrieval_config_json": payload.get("retrieval_config_json"),
        "concurrency_target": payload["concurrency_target"],
    }
    return stable_hash(relevant_fields)


@dataclass(frozen=True)
class EvidenceBundle:
    deployment_configuration: DeploymentConfiguration
    evaluation_suite: EvaluationSuite
    active_cases: list[EvaluationCase]
    runs: list[BenchmarkRun]
    results: list[BenchmarkResult]
    metrics: list[InferenceMetric]
    source_distribution: dict[str, int]
    result_case_map: dict[UUID, EvaluationCase]

    @property
    def benchmark_run_ids(self) -> list[str]:
        return [str(run.id) for run in self.runs]

    @property
    def active_case_count(self) -> int:
        return len(self.active_cases)

    @property
    def result_count(self) -> int:
        return len(self.results)

    @property
    def metric_count(self) -> int:
        return len(self.metrics)

    @property
    def has_real_evidence(self) -> bool:
        for result in self.results:
            case = self.result_case_map.get(result.id)
            if (
                case
                and case.data_source != SYNTHETIC_SOURCE
                and result.data_source != SYNTHETIC_SOURCE
            ):
                return True
        return False

    @property
    def only_synthetic_evidence(self) -> bool:
        return self.result_count > 0 and not self.has_real_evidence

    @property
    def mandatory_evidence_missing(self) -> bool:
        return self.active_case_count == 0 or len(self.runs) == 0 or self.result_count == 0


def collect_evidence(
    db: Session,
    *,
    deployment_configuration: DeploymentConfiguration,
    evaluation_suite: EvaluationSuite,
) -> EvidenceBundle:
    active_cases = list(
        db.scalars(
            select(EvaluationCase)
            .where(EvaluationCase.evaluation_suite_id == evaluation_suite.id)
            .where(EvaluationCase.is_active.is_(True))
        ).all()
    )
    active_case_ids = {case.id for case in active_cases}
    cases_by_id = {case.id: case for case in active_cases}

    candidate_runs = list(
        db.scalars(
            select(BenchmarkRun)
            .where(BenchmarkRun.deployment_configuration_id == deployment_configuration.id)
            .where(BenchmarkRun.evaluation_suite_id == evaluation_suite.id)
            .where(BenchmarkRun.status == "completed")
            .where(BenchmarkRun.data_source != TOOL_FAULT_DATA_SOURCE)
        ).all()
    )
    candidate_run_ids = {run.id for run in candidate_runs}

    candidate_results: list[BenchmarkResult] = []
    if candidate_run_ids and active_case_ids:
        candidate_results = list(
            db.scalars(
                select(BenchmarkResult)
                .where(BenchmarkResult.benchmark_run_id.in_(candidate_run_ids))
                .where(BenchmarkResult.evaluation_case_id.in_(active_case_ids))
            ).all()
        )
    results = _latest_result_revisions(candidate_results)
    selected_run_ids = {result.benchmark_run_id for result in results}
    runs = [run for run in candidate_runs if run.id in selected_run_ids]

    evaluated_sample_keys = {(result.benchmark_run_id, result.sample_id) for result in results}
    metrics: list[InferenceMetric] = []
    if evaluated_sample_keys:
        candidate_metrics = db.scalars(
            select(InferenceMetric).where(InferenceMetric.benchmark_run_id.in_(selected_run_ids))
        ).all()
        metrics = [
            metric
            for metric in candidate_metrics
            if (metric.benchmark_run_id, metric.sample_id) in evaluated_sample_keys
        ]

    source_counter: Counter[str] = Counter()
    for case in active_cases:
        source_counter[f"case:{case.data_source}"] += 1
    for run in runs:
        source_counter[f"run:{run.data_source}"] += 1
    for result in results:
        source_counter[f"result:{result.data_source}"] += 1
    for metric in metrics:
        source_counter[f"metric:{metric.data_source}"] += 1

    return EvidenceBundle(
        deployment_configuration=deployment_configuration,
        evaluation_suite=evaluation_suite,
        active_cases=active_cases,
        runs=runs,
        results=results,
        metrics=metrics,
        source_distribution=dict(source_counter),
        result_case_map={
            result.id: cases_by_id[result.evaluation_case_id]
            for result in results
            if result.evaluation_case_id in cases_by_id
        },
    )


def evidence_snapshot(
    bundle: EvidenceBundle,
    trust_summary: EvidenceTrustSummary | None = None,
) -> dict[str, Any]:
    resolved_trust = trust_summary or summarize_evidence_trust(
        bundle.results,
        bundle.result_case_map,
    )
    scorer_registry_versions, scorer_versions = _scorer_versions(bundle)
    tool_registry_versions, tool_execution_versions = _tool_execution_versions(bundle)
    rag_corpus_versions, retriever_versions, rag_evaluation_versions = _rag_execution_versions(
        bundle
    )
    runtime_reliability_versions = _runtime_reliability_versions(bundle)
    (
        agent_runtime_versions,
        agent_execution_versions,
        operational_memory_registry_versions,
        agent_observation_versions,
        agent_recovery_policy_versions,
        agent_approval_policy_versions,
    ) = _agent_execution_versions(bundle)
    revision_manifest = _evidence_revision_manifest(bundle)
    return {
        "schema_version": GATE_EVIDENCE_SCHEMA_VERSION,
        "benchmark_run_ids": bundle.benchmark_run_ids,
        "evidence_revision_hash": stable_hash(revision_manifest),
        "evidence_revision_manifest": revision_manifest,
        "result_count": bundle.result_count,
        "metric_count": bundle.metric_count,
        "active_case_count": bundle.active_case_count,
        "metric_calculation_version": CALCULATION_VERSION,
        "evidence_trust_version": EVIDENCE_TRUST_VERSION,
        "scorer_registry_versions": scorer_registry_versions,
        "scorer_versions": scorer_versions,
        "adapter_versions": _adapter_versions(bundle),
        "tool_registry_versions": tool_registry_versions,
        "tool_execution_versions": tool_execution_versions,
        "rag_corpus_versions": rag_corpus_versions,
        "retriever_versions": retriever_versions,
        "rag_evaluation_versions": rag_evaluation_versions,
        "runtime_reliability_versions": runtime_reliability_versions,
        "agent_runtime_versions": agent_runtime_versions,
        "agent_execution_versions": agent_execution_versions,
        "operational_memory_registry_versions": (operational_memory_registry_versions),
        "agent_observation_versions": agent_observation_versions,
        "agent_recovery_policy_versions": agent_recovery_policy_versions,
        "agent_approval_policy_versions": agent_approval_policy_versions,
        "evidence_trust": resolved_trust.to_dict(),
        "source_data_source_distribution": bundle.source_distribution,
        "configuration_hash": bundle.deployment_configuration.configuration_hash,
        "suite_hash": bundle.evaluation_suite.suite_hash,
    }


def evidence_revision_hash(bundle: EvidenceBundle) -> str:
    return stable_hash(_evidence_revision_manifest(bundle))


def _latest_result_revisions(
    results: list[BenchmarkResult],
) -> list[BenchmarkResult]:
    latest: dict[UUID, BenchmarkResult] = {}
    for result in results:
        root_id = result.root_benchmark_result_id or result.id
        current = latest.get(root_id)
        if current is None or _revision_sort_key(result) > _revision_sort_key(current):
            latest[root_id] = result
    return sorted(
        latest.values(),
        key=lambda result: (result.sample_id, str(result.id)),
    )


def _revision_sort_key(result: BenchmarkResult) -> tuple[int, str, str]:
    return (
        max(1, int(result.revision_number or 1)),
        result.created_at.isoformat() if result.created_at else "",
        str(result.id),
    )


def _evidence_revision_manifest(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    return [
        {
            "benchmark_result_id": str(result.id),
            "benchmark_run_id": str(result.benchmark_run_id),
            "root_benchmark_result_id": str(result.root_benchmark_result_id or result.id),
            "parent_benchmark_result_id": (
                str(result.parent_benchmark_result_id)
                if result.parent_benchmark_result_id
                else None
            ),
            "revision_number": max(1, int(result.revision_number or 1)),
            "sample_id": result.sample_id,
            "evidence_revision_hash": (
                result.evidence_revision_hash or _result_revision_hash(result)
            ),
        }
        for result in bundle.results
    ]


def _result_revision_hash(result: BenchmarkResult) -> str:
    return stable_hash(
        {
            "benchmark_result_id": str(result.id),
            "benchmark_run_id": str(result.benchmark_run_id),
            "evaluation_case_id": (
                str(result.evaluation_case_id) if result.evaluation_case_id else None
            ),
            "sample_id": result.sample_id,
            "scores": {
                "quality_score": result.quality_score,
                "exact_match": result.exact_match,
                "json_valid": result.json_valid,
                "tool_call_valid": result.tool_call_valid,
                "groundedness_score": result.groundedness_score,
                "faithfulness_score": result.faithfulness_score,
                "error_type": result.error_type,
            },
            "normalized_output": result.normalized_output,
            "metadata": result.metadata_json or {},
            "data_source": result.data_source,
        }
    )


def _scorer_versions(bundle: EvidenceBundle) -> tuple[list[str], list[str]]:
    registry_versions: set[str] = set()
    scorer_versions: set[str] = set()
    for result in bundle.results:
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        scorer = metadata.get("scorer") if isinstance(metadata.get("scorer"), dict) else {}
        registry_version = scorer.get("registry_version")
        scorer_version = scorer.get("scorer_version") or scorer.get("version")
        if registry_version:
            registry_versions.add(str(registry_version))
        elif scorer.get("version"):
            registry_versions.add(str(scorer["version"]))
        if scorer_version:
            scorer_versions.add(str(scorer_version))
    return sorted(registry_versions), sorted(scorer_versions)


def _adapter_versions(bundle: EvidenceBundle) -> list[str]:
    versions: set[str] = set()
    for run in bundle.runs:
        runtime_config = (
            run.runtime_config_json if isinstance(run.runtime_config_json, dict) else {}
        )
        descriptor = (
            runtime_config.get("adapter_descriptor")
            if isinstance(runtime_config.get("adapter_descriptor"), dict)
            else {}
        )
        _add_adapter_version(versions, descriptor, runtime_config.get("adapter_name"))
    for result in bundle.results:
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        descriptor = (
            metadata.get("adapter_descriptor")
            if isinstance(metadata.get("adapter_descriptor"), dict)
            else {}
        )
        adapter_name = metadata.get("adapter_name") or metadata.get("adapter")
        _add_adapter_version(versions, descriptor, adapter_name)
    return sorted(versions)


def _tool_execution_versions(bundle: EvidenceBundle) -> tuple[list[str], list[str]]:
    registry_versions: set[str] = set()
    execution_versions: set[str] = set()
    for result in bundle.results:
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        trace = (
            metadata.get("tool_execution")
            if isinstance(metadata.get("tool_execution"), dict)
            else {}
        )
        registry_version = trace.get("registry_version")
        execution_version = trace.get("schema_version")
        if registry_version:
            registry_versions.add(str(registry_version))
        if execution_version:
            execution_versions.add(str(execution_version))
    return sorted(registry_versions), sorted(execution_versions)


def _rag_execution_versions(
    bundle: EvidenceBundle,
) -> tuple[list[str], list[str], list[str]]:
    corpus_versions: set[str] = set()
    retriever_versions: set[str] = set()
    evaluation_versions: set[str] = set()
    for result in bundle.results:
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        trace = (
            metadata.get("rag_evaluation")
            if isinstance(metadata.get("rag_evaluation"), dict)
            else {}
        )
        retrieval = trace.get("retrieval") if isinstance(trace.get("retrieval"), dict) else {}
        corpus_version = retrieval.get("corpus_version")
        retriever_version = retrieval.get("retriever_version")
        evaluation_version = trace.get("schema_version")
        if corpus_version:
            corpus_versions.add(str(corpus_version))
        if retriever_version:
            retriever_versions.add(str(retriever_version))
        if evaluation_version:
            evaluation_versions.add(str(evaluation_version))
    return (
        sorted(corpus_versions),
        sorted(retriever_versions),
        sorted(evaluation_versions),
    )


def _runtime_reliability_versions(bundle: EvidenceBundle) -> list[str]:
    versions: set[str] = set()
    for result in bundle.results:
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        trace = (
            metadata.get("runtime_reliability")
            if isinstance(metadata.get("runtime_reliability"), dict)
            else {}
        )
        version = trace.get("schema_version")
        if version:
            versions.add(str(version))
    return sorted(versions)


def _agent_execution_versions(
    bundle: EvidenceBundle,
) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    runtime_versions: set[str] = set()
    execution_versions: set[str] = set()
    memory_registry_versions: set[str] = set()
    observation_versions: set[str] = set()
    recovery_policy_versions: set[str] = set()
    approval_policy_versions: set[str] = set()
    for run in bundle.runs:
        runtime_config = (
            run.runtime_config_json if isinstance(run.runtime_config_json, dict) else {}
        )
        descriptor = runtime_config.get("agent_runtime_descriptor")
        if isinstance(descriptor, dict) and descriptor.get("runtime_version"):
            runtime_versions.add(str(descriptor["runtime_version"]))
    for result in bundle.results:
        metadata = result.metadata_json if isinstance(result.metadata_json, dict) else {}
        trace = (
            metadata.get("agent_execution")
            if isinstance(metadata.get("agent_execution"), dict)
            else {}
        )
        if trace.get("schema_version"):
            execution_versions.add(str(trace["schema_version"]))
        if trace.get("memory_registry_version"):
            memory_registry_versions.add(str(trace["memory_registry_version"]))
        if trace.get("observation_schema_version"):
            observation_versions.add(str(trace["observation_schema_version"]))
        if trace.get("recovery_policy_version"):
            recovery_policy_versions.add(str(trace["recovery_policy_version"]))
        if trace.get("approval_policy_version"):
            approval_policy_versions.add(str(trace["approval_policy_version"]))
    return (
        sorted(runtime_versions),
        sorted(execution_versions),
        sorted(memory_registry_versions),
        sorted(observation_versions),
        sorted(recovery_policy_versions),
        sorted(approval_policy_versions),
    )


def _add_adapter_version(
    versions: set[str],
    descriptor: dict[str, Any],
    adapter_name: Any,
) -> None:
    adapter_version = descriptor.get("adapter_version")
    if adapter_version:
        versions.add(str(adapter_version))
        return
    known_version = KNOWN_ADAPTER_VERSIONS.get(str(adapter_name))
    if known_version:
        versions.add(known_version)
