from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from uuid import UUID

from app.schemas.analytics import ModelComparisonRow


@dataclass(frozen=True)
class EvidenceMetrics:
    quality: float | None
    ttft: float | None
    latency: float | None
    throughput: float | None
    vram: float | None
    json_rate: float | None
    tool_rate: float | None
    coverage: int


def average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(mean(present))


def comparison_by_artifact(
    rows: list[ModelComparisonRow],
    benchmark_task_id: UUID | None,
) -> dict[str, list[ModelComparisonRow]]:
    grouped: dict[str, list[ModelComparisonRow]] = defaultdict(list)
    for row in rows:
        if benchmark_task_id is not None and row.benchmark_task_id != str(benchmark_task_id):
            continue
        grouped[row.model_artifact_id].append(row)
    return grouped


def aggregate_evidence(rows: list[ModelComparisonRow]) -> EvidenceMetrics:
    return EvidenceMetrics(
        quality=average([row.average_quality_score for row in rows]),
        ttft=average([row.average_ttft_ms for row in rows]),
        latency=average([row.average_end_to_end_latency_ms for row in rows]),
        throughput=average([row.average_tokens_per_second for row in rows]),
        vram=average([row.average_vram_usage_mb for row in rows]),
        json_rate=average([row.json_validity_rate for row in rows]),
        tool_rate=average([row.tool_call_validity_rate for row in rows]),
        coverage=sum(row.benchmark_coverage_count for row in rows),
    )
