from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class GatePreflightRequest(BaseModel):
    deployment_configuration_id: UUID
    evaluation_suite_id: UUID
    acceptance_policy_id: UUID
    baseline_gate_evaluation_id: UUID | None = None


class GatePreflightConfigurationSummary(BaseModel):
    id: UUID
    name: str
    artifact_name: str
    runtime_name: str
    hardware_name: str
    context_length: int
    prompt_version: str | None


class GatePreflightSuiteSummary(BaseModel):
    id: UUID
    name: str
    version_label: str
    active_case_count: int
    critical_case_count: int


class GatePreflightPolicySummary(BaseModel):
    id: UUID
    name: str
    version_label: str
    rule_count: int
    blocking_rule_count: int
    warning_rule_count: int


class GatePreflightEvidenceSummary(BaseModel):
    completed_run_count: int
    result_count: int
    metric_count: int
    source_distribution: dict[str, int]
    score_distribution: dict[str, int]
    heuristic_only_count: int
    applied_judge_label_count: int
    human_reviewed_count: int
    applied_judge_label_rate: float
    critical_review_coverage_rate: float
    trust_status: str
    production_readiness: str


class GatePreflightBaselineSummary(BaseModel):
    source: Literal["explicit", "active_scope_baseline"]
    gate_evaluation_id: UUID
    verdict: str


class GatePreflightResponse(BaseModel):
    configuration: GatePreflightConfigurationSummary
    suite: GatePreflightSuiteSummary
    policy: GatePreflightPolicySummary
    evidence: GatePreflightEvidenceSummary
    baseline: GatePreflightBaselineSummary | None
    expected_outcome_constraints: list[str]
    blocking_preconditions: list[str]
    warnings: list[str]
    can_evaluate: bool
