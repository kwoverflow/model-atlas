from __future__ import annotations

from typing import Any


def _bounded_int(value: Any, default: int, maximum: int) -> int:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return default
    return max(1, min(int(value), maximum))


def _non_negative_int(value: Any) -> int:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0
    return max(0, int(value))


def _non_negative_float(value: Any) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0.0
    return max(0.0, float(value))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None
