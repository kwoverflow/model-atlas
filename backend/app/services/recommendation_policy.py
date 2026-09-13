from __future__ import annotations

from app.models import HardwareProfile, Model, ModelArtifact
from app.schemas.analytics import ModelComparisonRow
from app.schemas.recommendations import EligibilityIssue, RecommendationRequest


def capability_issue(model: Model, request: RecommendationRequest) -> tuple[str, str] | None:
    if request.require_text and not model.supports_text:
        return "missing_text", "Model does not support text workloads."
    if request.require_vision and not model.supports_vision:
        return "missing_vision", "Model does not support vision workloads."
    if request.require_tool_calling and not model.supports_tool_calling:
        return "missing_tool_calling", "Model does not support tool calling."
    if request.require_structured_output and not model.supports_structured_output:
        return "missing_structured_output", "Model does not support structured output."
    return None


def eligibility_issue(
    artifact: ModelArtifact,
    model: Model,
    hardware: HardwareProfile,
    request: RecommendationRequest,
    rows: list[ModelComparisonRow],
) -> EligibilityIssue | None:
    if not artifact.is_active:
        return EligibilityIssue(
            artifact_name=artifact.artifact_name,
            reason_code="inactive_artifact",
            message="Artifact is inactive.",
        )

    required_vram = artifact.recommended_vram_gb or artifact.minimum_vram_gb
    if required_vram is None:
        return EligibilityIssue(
            artifact_name=artifact.artifact_name,
            reason_code="missing_vram_requirement",
            message="Artifact has no registered VRAM requirement.",
        )
    if required_vram > hardware.gpu_vram_gb:
        return EligibilityIssue(
            artifact_name=artifact.artifact_name,
            reason_code="insufficient_vram",
            message=(
                f"Requires {required_vram:g} GB VRAM, but hardware has "
                f"{hardware.gpu_vram_gb:g} GB."
            ),
        )

    if (
        request.min_context_length is not None
        and artifact.context_limit < request.min_context_length
    ):
        return EligibilityIssue(
            artifact_name=artifact.artifact_name,
            reason_code="insufficient_context",
            message=f"Context limit is below {request.min_context_length} tokens.",
        )

    if request.commercial_use_required and model.commercial_use_allowed is not True:
        return EligibilityIssue(
            artifact_name=artifact.artifact_name,
            reason_code="commercial_use_not_allowed",
            message="Model is not marked as commercially usable.",
        )

    missing_capability = capability_issue(model, request)
    if missing_capability is not None:
        reason_code, message = missing_capability
        return EligibilityIssue(
            artifact_name=artifact.artifact_name,
            reason_code=reason_code,
            message=message,
        )

    if not rows:
        return EligibilityIssue(
            artifact_name=artifact.artifact_name,
            reason_code="no_benchmark_coverage",
            message="No benchmark evidence is available for the selected scope.",
        )

    return None
