"""Deterministic validation against user-confirmed structured task fields."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import (
    LOGICAL_ROOT,
    CalendarCreate,
    FileMove,
    FileTrash,
    GuardError,
    Intent,
    TodoComplete,
    TodoCreate,
)


def local_instant(value: str | None, timezone: str) -> datetime:
    if not value:
        raise GuardError("time_needs_clarification")
    try:
        if "T" not in value:
            raise ValueError("date_without_time")
        naive = datetime.fromisoformat(value)
        if naive.tzinfo is not None:
            raise ValueError("local_time_must_not_include_offset")
        zone = ZoneInfo(timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise GuardError("invalid_local_time_or_timezone") from exc
    candidates = {
        aware.astimezone(UTC)
        for fold in (0, 1)
        if (aware := naive.replace(tzinfo=zone, fold=fold))
        .astimezone(UTC)
        .astimezone(zone)
        .replace(tzinfo=None)
        == naive
    }
    if len(candidates) != 1:
        raise GuardError("nonexistent_or_ambiguous_local_time")
    return candidates.pop()


def output_time(instant: datetime) -> str:
    return instant.astimezone(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")


def compile_action(intent: Intent, state: dict, sandbox) -> dict:
    """Never reads an evaluation oracle or silently repairs a model response."""
    arguments = {}
    if isinstance(intent, CalendarCreate):
        start = local_instant(intent.local_start, intent.source_timezone)
        if intent.duration_minutes is None:
            raise GuardError("duration_needs_clarification")
        end = start + timedelta(minutes=intent.duration_minutes)
        for event in state["events"]:
            existing_start = datetime.fromisoformat(event["start_at"])
            existing_end = datetime.fromisoformat(event["end_at"])
            if event["title"] == intent.title and existing_start == start and existing_end == end:
                raise GuardError("duplicate_event")
            if start < existing_end and end > existing_start:
                raise GuardError("calendar_conflict")
        arguments = {
            "title": intent.title,
            "start_at": output_time(start),
            "end_at": output_time(end),
        }
    elif isinstance(intent, TodoCreate):
        if any(t["title"] == intent.title and t["status"] == "open" for t in state["tasks"]):
            raise GuardError("duplicate_task")
        arguments = {"title": intent.title}
        if intent.local_due is not None:
            arguments["due_at"] = output_time(
                local_instant(intent.local_due, intent.source_timezone)
            )
        if intent.priority is not None:
            arguments["priority"] = intent.priority
    elif isinstance(intent, TodoComplete):
        if not intent.task_id and not intent.title:
            raise GuardError("task_target_required")
        matches = [
            t
            for t in state["tasks"]
            if (not intent.task_id or t["task_id"] == intent.task_id)
            and (not intent.title or t["title"] == intent.title)
        ]
        if len(matches) != 1:
            raise GuardError("task_target_not_unique")
        if matches[0]["status"] != "open":
            raise GuardError("task_already_complete")
        arguments = {"task_id": matches[0]["task_id"]}
    elif isinstance(intent, FileMove):
        sandbox.check_move(intent.source, intent.destination)
        arguments = {
            "source": f"{LOGICAL_ROOT}/{intent.source}",
            "destination": f"{LOGICAL_ROOT}/{intent.destination}",
        }
    elif isinstance(intent, FileTrash):
        sandbox.file_path(intent.path, must_exist=True)
        arguments = {"path": f"{LOGICAL_ROOT}/{intent.path}"}
    else:
        raise GuardError("unsupported_intent")
    return {"tool": intent.operation, "arguments": arguments}
