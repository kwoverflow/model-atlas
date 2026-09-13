from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OperationalMetricSampleRead(BaseModel):
    name: str
    value: float
    metric_type: Literal["gauge"] = "gauge"
    help: str
    labels: dict[str, str] = Field(default_factory=dict)


class OperationalAlertRead(BaseModel):
    key: str
    severity: Literal["warning", "critical"]
    metric_name: str
    current_value: float
    threshold: float
    summary: str
    route: str


class OperationalMetricsRead(BaseModel):
    schema_version: str
    generated_at: datetime
    health: Literal["healthy", "degraded", "critical"]
    samples: list[OperationalMetricSampleRead]
    alerts: list[OperationalAlertRead]
