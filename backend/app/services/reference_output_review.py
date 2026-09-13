from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas import (
    ReferenceCriticalFailureRead,
    ReferenceFailureClusterRead,
    ReferenceOutputReviewItemRead,
    ReferenceOutputReviewPlanRead,
    ReferenceReviewCandidateAssessmentRead,
)
from app.services.deployment_gate.evidence import stable_hash
from app.services.reference_workload_read_model import build_reference_workload_overview

DEFAULT_REVIEW_TARGET = 30
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}


@dataclass(frozen=True)
class _FailureCluster:
    key: str
    failures: tuple[ReferenceCriticalFailureRead, ...]
    priority: str
    priority_reasons: tuple[str, ...]


def build_reference_output_review_plan(
    db: Session,
    *,
    target_count: int = DEFAULT_REVIEW_TARGET,
) -> ReferenceOutputReviewPlanRead:
    overview = build_reference_workload_overview(db)
    return build_output_review_plan(
        failures=overview.critical_failures,
        comparison_hash=overview.comparison_hash,
        configuration_count=sum(
            item.status == "completed" for item in overview.configuration_matrix
        ),
        target_count=target_count,
        currently_human_reviewed_count=overview.review_coverage.human_reviewed_count,
        remaining_human_review_target=overview.review_coverage.remaining_to_target,
    )


def build_output_review_plan(
    *,
    failures: list[ReferenceCriticalFailureRead],
    comparison_hash: str,
    configuration_count: int,
    target_count: int,
    currently_human_reviewed_count: int,
    remaining_human_review_target: int,
) -> ReferenceOutputReviewPlanRead:
    clusters = _build_clusters(failures, configuration_count=configuration_count)
    selected = _select_review_items(clusters, target_count=min(target_count, len(failures)))
    selected.sort(key=_selected_sort_key)

    cluster_reads = [_cluster_read(cluster) for cluster in clusters]
    selected_items = [
        ReferenceOutputReviewItemRead(
            rank=index,
            cluster_key=cluster.key,
            priority=cluster.priority,
            priority_reasons=list(cluster.priority_reasons),
            failure=failure,
            candidate_assessment=_candidate_assessment(failure, cluster=cluster),
        )
        for index, (cluster, failure) in enumerate(selected, start=1)
    ]
    plan_payload = {
        "schema_version": "model-atlas-reference-output-review-plan-v1",
        "comparison_hash": comparison_hash,
        "target_review_count": target_count,
        "critical_result_ids": sorted(str(item.benchmark_result_id) for item in failures),
        "clusters": [item.model_dump(mode="json") for item in cluster_reads],
        "selected_result_ids": [
            str(item.failure.benchmark_result_id) for item in selected_items
        ],
    }
    selected_priorities = Counter(item.priority for item in selected_items)
    return ReferenceOutputReviewPlanRead(
        generated_at=dt.datetime.now(dt.UTC),
        plan_hash=stable_hash(plan_payload),
        comparison_hash=comparison_hash,
        status="ready_for_human_review" if selected_items else "empty",
        total_failure_count=len(failures),
        cluster_count=len(clusters),
        target_review_count=target_count,
        selected_result_count=len(selected_items),
        selected_unique_case_count=len(
            {item.failure.external_case_id for item in selected_items}
        ),
        selected_category_count=len({item.failure.category for item in selected_items}),
        selected_configuration_count=len(
            {item.failure.entry_name for item in selected_items}
        ),
        currently_human_reviewed_count=currently_human_reviewed_count,
        remaining_human_review_target=remaining_human_review_target,
        priority_counts={
            priority: selected_priorities.get(priority, 0)
            for priority in ("P0", "P1", "P2")
        },
        clusters=cluster_reads,
        selected_items=selected_items,
        limitations=[
            "Candidate assessments are deterministic triage suggestions, not judge labels.",
            "Generating this plan does not apply scores or increase human-review coverage.",
            "A verified reviewer must inspect each selected output and explicitly "
            "confirm, override, or reject it.",
            "Local actual-runtime evidence does not establish production readiness.",
        ],
    )


def _build_clusters(
    failures: list[ReferenceCriticalFailureRead],
    *,
    configuration_count: int,
) -> list[_FailureCluster]:
    grouped: dict[tuple[str, str], list[ReferenceCriticalFailureRead]] = defaultdict(list)
    for failure in failures:
        grouped[(failure.external_case_id, failure.failure_reason)].append(failure)

    clusters: list[_FailureCluster] = []
    for (external_case_id, failure_reason), items in grouped.items():
        ordered = tuple(sorted(items, key=_failure_sort_key))
        affected_configurations = {item.entry_name for item in ordered}
        repeated_everywhere = (
            configuration_count > 0
            and len(affected_configurations) >= configuration_count
        )
        if repeated_everywhere:
            priority = "P0"
        elif len(affected_configurations) >= 2 or len(ordered) >= 2:
            priority = "P1"
        else:
            priority = "P2"
        reasons = []
        if repeated_everywhere:
            reasons.append(f"Failed in all {configuration_count} portfolio configurations")
        elif len(affected_configurations) > 1:
            reasons.append(
                f"Failed in {len(affected_configurations)} portfolio configurations"
            )
        if len(ordered) > 1:
            reasons.append(f"Repeated across {len(ordered)} result rows")
        reasons.append(f"Critical {ordered[0].category} contract")
        unreviewed_count = sum(item.review_status == "unreviewed" for item in ordered)
        if unreviewed_count:
            reasons.append(f"{unreviewed_count} result rows still require human review")
        key = stable_hash(
            {
                "version": "model-atlas-reference-failure-cluster-v1",
                "external_case_id": external_case_id,
                "failure_reason": failure_reason,
                "result_ids": sorted(str(item.benchmark_result_id) for item in ordered),
            }
        )
        clusters.append(
            _FailureCluster(
                key=key,
                failures=ordered,
                priority=priority,
                priority_reasons=tuple(reasons),
            )
        )
    clusters.sort(key=_cluster_sort_key)
    return clusters


def _select_review_items(
    clusters: list[_FailureCluster],
    *,
    target_count: int,
) -> list[tuple[_FailureCluster, ReferenceCriticalFailureRead]]:
    selected: list[tuple[_FailureCluster, ReferenceCriticalFailureRead]] = []
    selected_ids: set[UUID] = set()
    entry_counts: Counter[str] = Counter()
    cluster_counts: Counter[str] = Counter()

    for cluster in clusters:
        if len(selected) >= target_count:
            break
        representative = min(
            cluster.failures,
            key=lambda failure: (
                entry_counts[failure.entry_name],
                _quality_sort_value(failure.quality_score),
                failure.entry_name,
                failure.sample_id,
            ),
        )
        selected.append((cluster, representative))
        selected_ids.add(representative.benchmark_result_id)
        entry_counts[representative.entry_name] += 1
        cluster_counts[cluster.key] += 1

    while len(selected) < target_count:
        candidates = [
            (cluster, failure)
            for cluster in clusters
            for failure in cluster.failures
            if failure.benchmark_result_id not in selected_ids
        ]
        if not candidates:
            break
        cluster, failure = min(
            candidates,
            key=lambda item: (
                entry_counts[item[1].entry_name],
                cluster_counts[item[0].key],
                PRIORITY_ORDER[item[0].priority],
                _quality_sort_value(item[1].quality_score),
                item[1].entry_name,
                item[1].external_case_id,
                item[1].sample_id,
            ),
        )
        selected.append((cluster, failure))
        selected_ids.add(failure.benchmark_result_id)
        entry_counts[failure.entry_name] += 1
        cluster_counts[cluster.key] += 1
    return selected


def _cluster_read(cluster: _FailureCluster) -> ReferenceFailureClusterRead:
    qualities = [
        item.quality_score for item in cluster.failures if item.quality_score is not None
    ]
    representative = cluster.failures[0]
    return ReferenceFailureClusterRead(
        cluster_key=cluster.key,
        external_case_id=representative.external_case_id,
        title=representative.title,
        category=representative.category,
        failure_reason=representative.failure_reason,
        priority=cluster.priority,
        priority_reasons=list(cluster.priority_reasons),
        occurrence_count=len(cluster.failures),
        configuration_count=len({item.entry_name for item in cluster.failures}),
        configuration_names=sorted({item.entry_name for item in cluster.failures}),
        unreviewed_count=sum(
            item.review_status == "unreviewed" for item in cluster.failures
        ),
        mean_quality_score=round(mean(qualities), 6) if qualities else None,
        minimum_quality_score=min(qualities) if qualities else None,
        representative_result_id=representative.benchmark_result_id,
        representative_review_href=representative.judge_review_href,
    )


def _candidate_assessment(
    failure: ReferenceCriticalFailureRead,
    *,
    cluster: _FailureCluster,
) -> ReferenceReviewCandidateAssessmentRead:
    basis = [
        f"Stored critical outcome: {failure.failure_reason}",
        f"Observed in {len({item.entry_name for item in cluster.failures})} configuration(s)",
        f"Cluster contains {len(cluster.failures)} result row(s)",
    ]
    if failure.quality_score is not None:
        basis.append(f"Heuristic quality score: {failure.quality_score:.3f}")
    payload = {
        "schema_version": "model-atlas-reference-review-candidate-v1",
        "source": "deterministic_failure_triage",
        "benchmark_result_id": str(failure.benchmark_result_id),
        "candidate_label": f"critical_failure:{failure.failure_reason}",
        "quality_score": failure.quality_score,
        "groundedness_score": failure.groundedness_score,
        "faithfulness_score": failure.faithfulness_score,
        "confidence": "high" if cluster.priority == "P0" else "medium",
        "basis": basis,
        "applied": False,
        "human_reviewed": False,
    }
    return ReferenceReviewCandidateAssessmentRead(
        candidate_label=payload["candidate_label"],
        quality_score=failure.quality_score,
        groundedness_score=failure.groundedness_score,
        faithfulness_score=failure.faithfulness_score,
        confidence=payload["confidence"],
        basis=basis,
        assessment_hash=stable_hash(payload),
    )


def _cluster_sort_key(cluster: _FailureCluster) -> tuple[object, ...]:
    representative = cluster.failures[0]
    return (
        PRIORITY_ORDER[cluster.priority],
        -len({item.entry_name for item in cluster.failures}),
        -len(cluster.failures),
        representative.category,
        representative.external_case_id,
        representative.failure_reason,
    )


def _selected_sort_key(
    item: tuple[_FailureCluster, ReferenceCriticalFailureRead],
) -> tuple[object, ...]:
    cluster, failure = item
    return (
        PRIORITY_ORDER[cluster.priority],
        -len({candidate.entry_name for candidate in cluster.failures}),
        -len(cluster.failures),
        failure.category,
        failure.external_case_id,
        _quality_sort_value(failure.quality_score),
        failure.entry_name,
        failure.sample_id,
    )


def _failure_sort_key(failure: ReferenceCriticalFailureRead) -> tuple[object, ...]:
    return (
        failure.review_status != "unreviewed",
        _quality_sort_value(failure.quality_score),
        failure.entry_name,
        failure.sample_id,
        str(failure.benchmark_result_id),
    )


def _quality_sort_value(value: float | None) -> float:
    return value if value is not None else -1.0
