from __future__ import annotations

import hashlib
import json
from typing import Any


def _semantic_projection(value: Any) -> Any:
    volatile_keys = {
        "callback_duration_ms",
        "duration_ms",
        "live_replan_latency_ms",
        "model_call_latency_ms",
        "retrieval_latency_ms",
        "total_duration_ms",
    }
    if isinstance(value, dict):
        return {
            str(key): _semantic_projection(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in volatile_keys
        }
    if isinstance(value, list):
        return [_semantic_projection(item) for item in value]
    return value


def _semantic_signature(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _diff_paths(left: Any, right: Any, path: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        changed: list[str] = []
        for key in sorted(set(left) | set(right)):
            child_path = f"{path}.{key}"
            if key not in left or key not in right:
                changed.append(child_path)
            else:
                changed.extend(_diff_paths(left[key], right[key], child_path))
        return changed
    if isinstance(left, list):
        changed = []
        if len(left) != len(right):
            changed.append(f"{path}.length")
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=False)):
            changed.extend(_diff_paths(left_item, right_item, f"{path}[{index}]"))
        return changed
    return [] if left == right else [path]
