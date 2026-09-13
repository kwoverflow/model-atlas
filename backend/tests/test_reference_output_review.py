from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
from uuid import uuid4

from app.schemas import ReferenceCriticalFailureRead
from app.services.judge_label_review import _needs_review
from app.services.reference_output_review import build_output_review_plan


def test_heuristic_only_result_requires_review() -> None:
    assert _needs_review(
        result=SimpleNamespace(quality_score=0.9, human_label="heuristic-pass"),
        score_source="heuristic",
        candidate_labels=None,
        quality_delta=None,
    )


def test_output_review_plan_clusters_and_balances_deterministically() -> None:
    failures = [
        _failure(
            external_case_id="KO-AGENT-001",
            failure_reason="agent_execution_failed",
            entry_name=entry_name,
            sample_id=f"KO-AGENT-001::trial-{trial:02d}",
            quality_score=0.1 + (entry_index * 0.05),
        )
        for entry_index, entry_name in enumerate(
            ("small-baseline", "medium-candidate", "prompt-variant")
        )
        for trial in (1, 2)
    ]
    failures.extend(
        [
            _failure(
                external_case_id="KO-TOOL-001",
                failure_reason="tool_execution_failed",
                entry_name="small-baseline",
                sample_id="KO-TOOL-001::trial-01",
                quality_score=0.45,
            ),
            _failure(
                external_case_id="KO-TOOL-001",
                failure_reason="tool_execution_failed",
                entry_name="medium-candidate",
                sample_id="KO-TOOL-001::trial-01",
                quality_score=0.45,
            ),
        ]
    )

    plan = build_output_review_plan(
        failures=failures,
        comparison_hash="comparison-hash",
        configuration_count=3,
        target_count=5,
        currently_human_reviewed_count=0,
        remaining_human_review_target=30,
    )
    repeated = build_output_review_plan(
        failures=failures,
        comparison_hash="comparison-hash",
        configuration_count=3,
        target_count=5,
        currently_human_reviewed_count=0,
        remaining_human_review_target=30,
    )

    assert plan.plan_hash == repeated.plan_hash
    assert plan.total_failure_count == 8
    assert plan.cluster_count == 2
    assert plan.selected_result_count == 5
    assert plan.selected_unique_case_count == 2
    assert plan.selected_configuration_count == 3
    selected_by_configuration = Counter(
        item.failure.entry_name for item in plan.selected_items
    )
    assert max(selected_by_configuration.values()) - min(
        selected_by_configuration.values()
    ) <= 1
    assert plan.status == "ready_for_human_review"
    agent_cluster = next(
        item for item in plan.clusters if item.external_case_id == "KO-AGENT-001"
    )
    tool_cluster = next(
        item for item in plan.clusters if item.external_case_id == "KO-TOOL-001"
    )
    assert agent_cluster.priority == "P0"
    assert agent_cluster.occurrence_count == 6
    assert agent_cluster.configuration_count == 3
    assert tool_cluster.priority == "P1"
    assert tool_cluster.occurrence_count == 2
    assert all(not item.candidate_assessment.applied for item in plan.selected_items)
    assert all(not item.candidate_assessment.human_reviewed for item in plan.selected_items)
    assert all(
        "benchmark_result_id=" in item.failure.judge_review_href
        for item in plan.selected_items
    )


def _failure(
    *,
    external_case_id: str,
    failure_reason: str,
    entry_name: str,
    sample_id: str,
    quality_score: float,
) -> ReferenceCriticalFailureRead:
    result_id = uuid4()
    run_id = uuid4()
    return ReferenceCriticalFailureRead(
        benchmark_result_id=result_id,
        benchmark_run_id=run_id,
        deployment_configuration_id=uuid4(),
        entry_name=entry_name,
        evaluation_case_id=uuid4(),
        external_case_id=external_case_id,
        title=external_case_id,
        category=(
            "agent_multi_step" if failure_reason.startswith("agent") else "tool_single_step"
        ),
        criticality="critical",
        sample_id=sample_id,
        failure_reason=failure_reason,
        expected_contract_summary="expected",
        observed_output_summary="observed",
        quality_score=quality_score,
        groundedness_score=quality_score,
        faithfulness_score=quality_score,
        evidence_source="local_actual_runtime",
        review_status="unreviewed",
        benchmark_execution_href=f"/benchmark-executions/{run_id}",
        judge_review_href=(
            f"/judge-labels?benchmark_run_id={run_id}&benchmark_result_id={result_id}"
        ),
    )
