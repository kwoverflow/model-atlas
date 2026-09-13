from __future__ import annotations

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    InferenceMetric,
    Model,
    ModelArtifact,
)
from app.schemas.analytics import DataQualityWarning, ModelComparisonRow, OverviewResponse

SYNTHETIC_DATA_SOURCE = "synthetic_demo"


def get_overview(db: Session) -> OverviewResponse:
    latest_run = db.scalar(select(func.max(BenchmarkRun.started_at)))
    synthetic_count = sum(
        int(value or 0)
        for value in (
            db.scalar(
                select(func.count()).select_from(BenchmarkRun).where(
                    BenchmarkRun.data_source == SYNTHETIC_DATA_SOURCE
                )
            ),
            db.scalar(
                select(func.count()).select_from(BenchmarkResult).where(
                    BenchmarkResult.data_source == SYNTHETIC_DATA_SOURCE
                )
            ),
            db.scalar(
                select(func.count()).select_from(InferenceMetric).where(
                    InferenceMetric.data_source == SYNTHETIC_DATA_SOURCE
                )
            ),
        )
    )

    warnings: list[DataQualityWarning] = []
    failed_runs = int(
        db.scalar(
            select(func.count()).select_from(BenchmarkRun).where(BenchmarkRun.status == "failed")
        )
        or 0
    )
    if failed_runs:
        warnings.append(
            DataQualityWarning(
                code="failed_runs",
                message="Benchmark runs with failed status exist",
                count=failed_runs,
            )
        )

    oom_metrics = int(
        db.scalar(
            select(func.count())
            .select_from(InferenceMetric)
            .where(InferenceMetric.oom_occurred.is_(True))
        )
        or 0
    )
    if oom_metrics:
        warnings.append(
            DataQualityWarning(
                code="oom_metrics",
                message="Inference metrics include out-of-memory events",
                count=oom_metrics,
            )
        )

    errored_results = int(
        db.scalar(
            select(func.count())
            .select_from(BenchmarkResult)
            .where(BenchmarkResult.error_type.is_not(None))
        )
        or 0
    )
    if errored_results:
        warnings.append(
            DataQualityWarning(
                code="result_errors",
                message="Benchmark results include error labels",
                count=errored_results,
            )
        )

    return OverviewResponse(
        model_count=int(db.scalar(select(func.count()).select_from(Model)) or 0),
        model_artifact_count=int(db.scalar(select(func.count()).select_from(ModelArtifact)) or 0),
        benchmark_task_count=int(db.scalar(select(func.count()).select_from(BenchmarkTask)) or 0),
        benchmark_run_count=int(db.scalar(select(func.count()).select_from(BenchmarkRun)) or 0),
        benchmark_result_count=int(
            db.scalar(select(func.count()).select_from(BenchmarkResult)) or 0
        ),
        latest_benchmark_run_timestamp=latest_run,
        synthetic_record_count=synthetic_count,
        latest_data_quality_warnings=warnings,
    )


def get_model_comparison(db: Session) -> list[ModelComparisonRow]:
    json_valid = case((BenchmarkResult.json_valid.is_(True), 1.0), else_=0.0)
    tool_valid = case((BenchmarkResult.tool_call_valid.is_(True), 1.0), else_=0.0)
    statement = (
        select(
            ModelArtifact.id.label("model_artifact_id"),
            Model.display_name.label("model_name"),
            ModelArtifact.artifact_name.label("artifact_name"),
            BenchmarkTask.id.label("benchmark_task_id"),
            BenchmarkTask.name.label("benchmark_task_name"),
            func.avg(BenchmarkResult.quality_score).label("average_quality_score"),
            func.avg(InferenceMetric.ttft_ms).label("average_ttft_ms"),
            func.avg(InferenceMetric.end_to_end_latency_ms).label("average_end_to_end_latency_ms"),
            func.avg(InferenceMetric.tokens_per_second).label("average_tokens_per_second"),
            func.avg(InferenceMetric.gpu_vram_used_mb).label("average_vram_usage_mb"),
            func.avg(json_valid).label("json_validity_rate"),
            func.avg(tool_valid).label("tool_call_validity_rate"),
            func.count(distinct(BenchmarkRun.id)).label("benchmark_coverage_count"),
        )
        .select_from(BenchmarkRun)
        .join(ModelArtifact, BenchmarkRun.model_artifact_id == ModelArtifact.id)
        .join(Model, ModelArtifact.model_id == Model.id)
        .join(BenchmarkTask, BenchmarkRun.benchmark_task_id == BenchmarkTask.id)
        .join(BenchmarkResult, BenchmarkResult.benchmark_run_id == BenchmarkRun.id)
        .outerjoin(
            InferenceMetric,
            (InferenceMetric.benchmark_run_id == BenchmarkRun.id)
            & (InferenceMetric.sample_id == BenchmarkResult.sample_id),
        )
        .group_by(
            ModelArtifact.id,
            Model.display_name,
            ModelArtifact.artifact_name,
            BenchmarkTask.id,
            BenchmarkTask.name,
        )
        .order_by(Model.display_name, ModelArtifact.artifact_name, BenchmarkTask.name)
    )
    return [
        ModelComparisonRow(
            model_artifact_id=str(row.model_artifact_id),
            model_name=row.model_name,
            artifact_name=row.artifact_name,
            benchmark_task_id=str(row.benchmark_task_id),
            benchmark_task_name=row.benchmark_task_name,
            average_quality_score=row.average_quality_score,
            average_ttft_ms=row.average_ttft_ms,
            average_end_to_end_latency_ms=row.average_end_to_end_latency_ms,
            average_tokens_per_second=row.average_tokens_per_second,
            average_vram_usage_mb=row.average_vram_usage_mb,
            json_validity_rate=row.json_validity_rate,
            tool_call_validity_rate=row.tool_call_validity_rate,
            benchmark_coverage_count=row.benchmark_coverage_count,
        )
        for row in db.execute(statement)
    ]
