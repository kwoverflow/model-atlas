from __future__ import annotations

from dataclasses import dataclass

from app.models import HardwareProfile, Model, ModelArtifact
from app.schemas.analytics import ModelComparisonRow
from app.schemas.recommendations import RecommendationCandidate, RecommendationRequest
from app.services.recommendation_evidence import EvidenceMetrics

CONFIDENCE_TARGET_RUNS = 3


@dataclass(frozen=True)
class EligibleArtifactEvidence:
    artifact: ModelArtifact
    model: Model
    rows: list[ModelComparisonRow]
    metrics: EvidenceMetrics


def normalize_higher(value: float | None, values: list[float]) -> float:
    if value is None or not values:
        return 0.0
    low = min(values)
    high = max(values)
    if high == low:
        return 1.0
    return (value - low) / (high - low)


def normalize_lower(value: float | None, values: list[float]) -> float:
    if value is None:
        return 0.0
    return 1.0 - normalize_higher(value, values)


def bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


def evidence_confidence(
    benchmark_coverage_count: int,
    target_runs: int = CONFIDENCE_TARGET_RUNS,
) -> float:
    if benchmark_coverage_count <= 0 or target_runs <= 0:
        return 0.0
    return bounded((benchmark_coverage_count / target_runs) ** 0.5)


def _score_ranges(
    eligible: list[EligibleArtifactEvidence],
) -> tuple[list[float], list[float], list[float]]:
    quality_values = [
        item.metrics.quality for item in eligible if item.metrics.quality is not None
    ]
    latency_values = [
        item.metrics.latency for item in eligible if item.metrics.latency is not None
    ]
    throughput_values = [
        item.metrics.throughput for item in eligible if item.metrics.throughput is not None
    ]
    return quality_values, latency_values, throughput_values


def _total_weight(request: RecommendationRequest) -> float:
    return (
        request.weights.quality
        + request.weights.latency
        + request.weights.throughput
        + request.weights.vram_efficiency
    )


def _candidate_from_evidence(
    item: EligibleArtifactEvidence,
    hardware: HardwareProfile,
    request: RecommendationRequest,
    quality_values: list[float],
    latency_values: list[float],
    throughput_values: list[float],
) -> RecommendationCandidate:
    artifact = item.artifact
    model = item.model
    metrics = item.metrics
    quality_component = normalize_higher(metrics.quality, quality_values)
    latency_component = normalize_lower(metrics.latency, latency_values)
    throughput_component = normalize_higher(metrics.throughput, throughput_values)
    vram_source = artifact.recommended_vram_gb or artifact.minimum_vram_gb or 0
    vram_efficiency_component = bounded(1.0 - (vram_source / max(hardware.gpu_vram_gb, 1)))
    raw_score = 100 * (
        request.weights.quality * quality_component
        + request.weights.latency * latency_component
        + request.weights.throughput * throughput_component
        + request.weights.vram_efficiency * vram_efficiency_component
    ) / _total_weight(request)
    confidence = evidence_confidence(metrics.coverage)
    confidence_penalty = 1.0 - confidence
    score = raw_score * confidence

    rationale = [
        f"Quality component {quality_component:.2f}",
        f"Latency component {latency_component:.2f}",
        f"Throughput component {throughput_component:.2f}",
        f"VRAM efficiency component {vram_efficiency_component:.2f}",
        f"Evidence confidence {confidence:.2f} from {metrics.coverage} benchmark run(s)",
    ]
    if request.benchmark_task_id is not None:
        rationale.append(f"Uses benchmark evidence from {item.rows[0].benchmark_task_name}.")
    else:
        rationale.append(f"Uses benchmark evidence from {len(item.rows)} task group(s).")

    return RecommendationCandidate(
        rank=0,
        model_id=str(model.id),
        model_name=model.display_name,
        provider=model.provider,
        family=model.family,
        artifact_id=str(artifact.id),
        artifact_name=artifact.artifact_name,
        format=artifact.format,
        quantization=artifact.quantization,
        precision=artifact.precision,
        recommended_vram_gb=artifact.recommended_vram_gb,
        context_limit=artifact.context_limit,
        runtime_compatibility=artifact.runtime_compatibility,
        average_quality_score=metrics.quality,
        average_ttft_ms=metrics.ttft,
        average_end_to_end_latency_ms=metrics.latency,
        average_tokens_per_second=metrics.throughput,
        average_vram_usage_mb=metrics.vram,
        json_validity_rate=metrics.json_rate,
        tool_call_validity_rate=metrics.tool_rate,
        benchmark_coverage_count=metrics.coverage,
        quality_component=round(quality_component, 4),
        latency_component=round(latency_component, 4),
        throughput_component=round(throughput_component, 4),
        vram_efficiency_component=round(vram_efficiency_component, 4),
        raw_recommendation_score=round(raw_score, 2),
        evidence_confidence=round(confidence, 4),
        confidence_penalty=round(confidence_penalty, 4),
        recommendation_score=round(score, 2),
        pareto_optimal=False,
        rationale=rationale,
    )


def is_dominated(
    candidate: RecommendationCandidate,
    other: RecommendationCandidate,
) -> bool:
    dimensions = [
        (
            other.average_quality_score or 0,
            candidate.average_quality_score or 0,
            "higher",
        ),
        (
            other.average_tokens_per_second or 0,
            candidate.average_tokens_per_second or 0,
            "higher",
        ),
        (
            other.average_end_to_end_latency_ms or float("inf"),
            candidate.average_end_to_end_latency_ms or float("inf"),
            "lower",
        ),
        (
            other.average_vram_usage_mb or float("inf"),
            candidate.average_vram_usage_mb or float("inf"),
            "lower",
        ),
    ]
    at_least_as_good = all(
        other_value >= candidate_value if direction == "higher" else other_value <= candidate_value
        for other_value, candidate_value, direction in dimensions
    )
    strictly_better = any(
        other_value > candidate_value if direction == "higher" else other_value < candidate_value
        for other_value, candidate_value, direction in dimensions
    )
    return at_least_as_good and strictly_better


def with_pareto_flags(
    candidates: list[RecommendationCandidate],
) -> list[RecommendationCandidate]:
    flagged: list[RecommendationCandidate] = []
    for candidate in candidates:
        pareto_optimal = not any(
            is_dominated(candidate, other)
            for other in candidates
            if other.artifact_id != candidate.artifact_id
        )
        flagged.append(candidate.model_copy(update={"pareto_optimal": pareto_optimal}))
    return flagged


def rank_candidates(
    eligible: list[EligibleArtifactEvidence],
    hardware: HardwareProfile,
    request: RecommendationRequest,
) -> list[RecommendationCandidate]:
    quality_values, latency_values, throughput_values = _score_ranges(eligible)
    candidates = [
        _candidate_from_evidence(
            item,
            hardware,
            request,
            quality_values,
            latency_values,
            throughput_values,
        )
        for item in eligible
    ]
    candidates = with_pareto_flags(candidates)
    candidates = sorted(
        candidates,
        key=lambda candidate: (
            candidate.recommendation_score,
            candidate.average_quality_score or 0,
            candidate.average_tokens_per_second or 0,
        ),
        reverse=True,
    )
    return [
        candidate.model_copy(update={"rank": index + 1})
        for index, candidate in enumerate(candidates)
    ]
