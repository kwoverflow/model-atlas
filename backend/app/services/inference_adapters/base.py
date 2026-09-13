from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


class AdapterModelArtifact(Protocol):
    artifact_name: str


class AdapterConfiguration(Protocol):
    runtime_name: str
    runtime_config_json: dict[str, Any]
    generation_config_json: dict[str, Any]
    configuration_hash: str
    context_length: int
    model_artifact: AdapterModelArtifact


class AdapterEvaluationCase(Protocol):
    external_case_id: str
    category: str
    title: str
    input_payload_json: dict[str, Any]
    expected_output_json: dict[str, Any] | None
    reference_context_json: dict[str, Any] | None
    expected_tool_schema_json: dict[str, Any] | None


@dataclass(frozen=True)
class AdapterDescriptor:
    adapter_id: str
    adapter_version: str
    display_name: str
    capabilities: frozenset[str]
    input_schema_version: str
    output_schema_version: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capabilities"] = sorted(self.capabilities)
        return payload


@dataclass(frozen=True)
class AdapterHealth:
    adapter_name: str
    healthy: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterCaseResult:
    raw_output: str
    normalized_output: str
    quality_score: float | None
    exact_match: bool | None
    json_valid: bool
    tool_call_valid: bool
    groundedness_score: float | None
    faithfulness_score: float | None
    human_label: str | None
    error_type: str | None
    ttft_ms: float
    end_to_end_latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    tokens_per_second: float
    gpu_vram_used_mb: float | None
    gpu_utilization_pct: float | None
    cpu_utilization_pct: float | None
    peak_memory_mb: float | None
    oom_occurred: bool
    retry_count: int
    logs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class InferenceAdapter(Protocol):
    name: str
    descriptor: AdapterDescriptor

    def health_check(self, configuration: AdapterConfiguration) -> AdapterHealth:
        """Return local runtime readiness for this configuration."""

    def run_case(
        self,
        *,
        configuration: AdapterConfiguration,
        evaluation_case: AdapterEvaluationCase,
        seed: int | None = None,
    ) -> AdapterCaseResult:
        """Execute one evaluation case and return result plus metric evidence."""
