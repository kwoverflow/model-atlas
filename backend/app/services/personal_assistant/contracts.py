"""Trusted form inputs are separate from untrusted model proposals."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

LOGICAL_ROOT = "C:/AssistantSandbox"
VERSION = "personal-assistant-sandbox-v1"


class GuardError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class CalendarCreate(StrictModel):
    operation: Literal["calendar.create"]
    title: str = Field(min_length=1, max_length=200)
    local_start: str | None = None
    source_timezone: str = "Asia/Tokyo"
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)


class TodoCreate(StrictModel):
    operation: Literal["todo.create"]
    title: str = Field(min_length=1, max_length=200)
    local_due: str | None = None
    source_timezone: str = "Asia/Tokyo"
    priority: Literal["low", "normal", "high"] | None = None


class TodoComplete(StrictModel):
    operation: Literal["todo.complete"]
    task_id: str | None = None
    title: str | None = None


class FileMove(StrictModel):
    operation: Literal["files.move"]
    source: str
    destination: str


class FileTrash(StrictModel):
    operation: Literal["files.trash"]
    path: str


Intent = Annotated[
    CalendarCreate | TodoCreate | TodoComplete | FileMove | FileTrash,
    Field(discriminator="operation"),
]
INTENT = TypeAdapter(Intent)


class Action(StrictModel):
    tool: Literal["calendar.create", "todo.create", "todo.complete", "files.move", "files.trash"]
    arguments: dict[str, str]


class Plan(StrictModel):
    decision: Literal["propose", "clarify", "refuse", "no_change"]
    requires_confirmation: bool
    actions: list[Action] = Field(max_length=1)
    reason: str = Field(min_length=1, max_length=2000)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def parse_plan(raw: str) -> Plan:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise GuardError("duplicate_json_key")
            result[key] = value
        return result

    def reject(value):
        raise GuardError("non_finite_json")

    try:
        if len(raw) > 16000:
            raise GuardError("response_too_large")
        plan = Plan.model_validate(json.loads(raw, object_pairs_hook=unique, parse_constant=reject))
    except ValueError as exc:
        raise GuardError(f"invalid_plan: {exc}") from exc
    if plan.decision != "propose" or len(plan.actions) != 1:
        raise GuardError("model_did_not_propose_single_action")
    if not plan.requires_confirmation:
        raise GuardError("approval_required")
    return plan
