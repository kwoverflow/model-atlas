from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class PromptRegressionMetric(BaseModel):
    value: float | None
    sample_size: int
    delta_vs_baseline: float | None = None


class PromptRegressionRow(BaseModel):
    prompt_version_id: UUID
    prompt_name: str
    version_label: str
    prompt_hash: str
    benchmark_run_ids: list[UUID]
    run_count: int
    result_count: int
    metric_count: int
    data_sources: list[str]
    is_baseline_prompt: bool
    mean_quality_score: PromptRegressionMetric
    groundedness_score: PromptRegressionMetric
    faithfulness_score: PromptRegressionMetric
    json_validity_rate: PromptRegressionMetric
    tool_call_validity_rate: PromptRegressionMetric
    critical_case_failure_rate: PromptRegressionMetric
    p95_end_to_end_latency_ms: PromptRegressionMetric
    p95_ttft_ms: PromptRegressionMetric
    mean_tokens_per_second: PromptRegressionMetric
    oom_rate: PromptRegressionMetric
    risk_flags: list[str]


class PromptRegressionReport(BaseModel):
    deployment_configuration_id: UUID | None
    evaluation_suite_id: UUID | None
    acceptance_policy_id: UUID | None
    baseline_gate_evaluation_id: UUID | None
    baseline_prompt_version_id: UUID | None
    row_count: int
    rows: list[PromptRegressionRow]
