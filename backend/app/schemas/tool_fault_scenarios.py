from typing import Literal

from pydantic import BaseModel


class ToolFaultScenarioRead(BaseModel):
    schema_version: str
    mode: Literal["normal", "transient_once", "permanent"]
    max_attempts: int
    scenario_hash: str
    authority: Literal["test_environment"]
    gate_evidence: Literal[False]
    injection_point: Literal["before_handler"]
    model_arguments_modified: Literal[False]
    status: Literal["passed", "failed", "not_exercised"]
    passed: bool
    injected_failure_count: int
    handler_invocation_count: int
    measurement: Literal["executor_fixture_behavior_not_model_recovery_ability"]


class ToolFaultScenarioSummaryRead(BaseModel):
    schema_version: str
    case_count: int
    passed_count: int
    not_exercised_count: int
    injected_failure_count: int
    handler_invocation_count: int
    gate_evidence: Literal[False]
