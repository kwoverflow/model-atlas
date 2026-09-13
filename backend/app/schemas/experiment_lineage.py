from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

ExperimentLineageEventType = Literal[
    "prompt_version_created",
    "benchmark_run_created",
    "benchmark_run_completed",
    "benchmark_run_failed",
    "gate_evaluation_completed",
    "baseline_promoted",
    "baseline_superseded",
    "release_decision_signed",
]

ExperimentLineageEntityType = Literal[
    "prompt_version",
    "benchmark_run",
    "gate_evaluation",
    "deployment_baseline",
    "release_decision",
]

ExperimentLineageStatus = Literal["recorded", "superseded", "failed"]


class ExperimentLineageEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: ExperimentLineageEventType
    primary_entity_type: ExperimentLineageEntityType
    primary_entity_id: UUID
    event_time: datetime
    lineage_key: str
    deployment_configuration_id: UUID | None
    evaluation_suite_id: UUID | None
    acceptance_policy_id: UUID | None
    prompt_version_id: UUID | None
    benchmark_run_id: UUID | None
    gate_evaluation_id: UUID | None
    deployment_baseline_id: UUID | None
    release_decision_id: UUID | None
    status: ExperimentLineageStatus
    summary: str
    metadata_json: dict[str, Any] | None
    data_source: str
    created_at: datetime
    updated_at: datetime


class ExperimentLineageMaterializeResponse(BaseModel):
    created_count: int
    existing_count: int
    event_count: int


class ExperimentLineageReport(BaseModel):
    event_count: int
    lineage_count: int
    benchmark_run_event_count: int
    gate_event_count: int
    baseline_event_count: int
    release_decision_event_count: int
    events: list[ExperimentLineageEventRead]
