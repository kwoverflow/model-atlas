from __future__ import annotations

from typing import Any

from .utils import _string_list


def _select_recovery_plan(
    recovery_plans: list[dict[str, Any]],
    *,
    trigger_step_index: int,
    error_type: str,
) -> dict[str, Any] | None:
    for branch in recovery_plans:
        if branch.get("trigger_step_index") != trigger_step_index:
            continue
        error_types = _string_list(branch.get("on_error_types"))
        if error_types and error_type not in error_types:
            continue
        return branch
    return None


def _has_ambiguous_recovery_plans(
    recovery_plans: list[dict[str, Any]],
) -> bool:
    for index, left in enumerate(recovery_plans):
        left_trigger = left.get("trigger_step_index")
        left_errors = set(_string_list(left.get("on_error_types")))
        for right in recovery_plans[index + 1 :]:
            if right.get("trigger_step_index") != left_trigger:
                continue
            right_errors = set(_string_list(right.get("on_error_types")))
            if not left_errors or not right_errors or left_errors & right_errors:
                return True
    return False
