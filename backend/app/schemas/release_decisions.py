from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.release_readiness import ReleaseReadinessStatus

ReleaseDecisionType = Literal["APPROVE_RELEASE", "REJECT_RELEASE", "REQUEST_CHANGES"]
ReleaseDecisionActionType = Literal[
    "stale_detected",
    "review_requested",
    "acknowledged",
    "revoked",
    "replaced",
]
ReleaseDecisionOperationalStatus = Literal[
    "active",
    "needs_review",
    "revoked",
    "replaced",
    "recorded",
]
SnapshotDiffStatus = Literal["added", "removed", "changed"]


class ReleaseDecisionCreate(BaseModel):
    gate_evaluation_id: UUID
    decision: ReleaseDecisionType
    decided_by: str = Field(min_length=1, max_length=120)
    signer_id: str | None = Field(default=None, max_length=120)
    signer_role: str | None = Field(default=None, max_length=120)
    identity_provider: str | None = Field(default="local-ui", max_length=120)
    ticket_reference: str | None = Field(default=None, max_length=200)
    signature_statement: str | None = None
    decision_reason: str = Field(min_length=1)
    notes: str | None = None
    replaces_release_decision_id: UUID | None = None


class ReleaseDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    gate_evaluation_id: UUID
    deployment_configuration_id: UUID
    evaluation_suite_id: UUID
    acceptance_policy_id: UUID
    decision: ReleaseDecisionType
    release_readiness_status: ReleaseReadinessStatus
    decided_at: datetime
    decided_by: str
    signer_identity_json: dict[str, Any]
    identity_verified: bool
    signature_hash: str | None
    signature_statement: str | None
    approval_policy_json: dict[str, Any]
    decision_reason: str
    notes: str | None
    snapshot_hash: str
    snapshot_json: dict[str, Any]
    decision_hash: str
    replaces_release_decision_id: UUID | None = None
    operational_status: ReleaseDecisionOperationalStatus = "recorded"
    stale_warning: bool = False
    action_count: int = 0
    latest_action_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ReleaseDecisionActionCreate(BaseModel):
    action_type: Literal["review_requested", "acknowledged", "revoked"]
    reason: str = Field(min_length=1, max_length=2000)


class ReleaseDecisionActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    release_decision_id: UUID
    action_type: ReleaseDecisionActionType
    dedupe_key: str
    actor_identity_json: dict[str, Any]
    reason: str
    source_gate_evaluation_id: UUID | None = None
    replacement_release_decision_id: UUID | None = None
    metadata_json: dict[str, Any]
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime


class ReleaseSnapshotDiffItem(BaseModel):
    path: str
    status: SnapshotDiffStatus
    frozen_present: bool
    current_present: bool
    frozen_value: Any | None = None
    current_value: Any | None = None


class ReleaseSnapshotDiffRead(BaseModel):
    release_decision_id: UUID
    gate_evaluation_id: UUID
    frozen_snapshot_hash: str
    current_snapshot_hash: str
    changed: bool
    diff_count: int
    truncated: bool
    ignored_paths: list[str]
    diffs: list[ReleaseSnapshotDiffItem]
