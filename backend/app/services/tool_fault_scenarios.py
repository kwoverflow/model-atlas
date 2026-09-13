"""Versioned test-environment faults, independent of generated Tool arguments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

TOOL_FAULT_SCENARIO_VERSION = "tool-fault-scenario-v1"
TOOL_FAULT_DATA_SOURCE = "tool_fault_fixture_diagnostic"
TOOL_FAULT_TRACE_VERSION = "tool-execution-trace-v2"
TOOL_FAULT_REGISTRY_VERSION = "local-tool-fault-fixture-registry-v1"


@dataclass(frozen=True)
class ToolFaultScenario:
    mode: str
    max_attempts: int = 2
    schema_version: str = TOOL_FAULT_SCENARIO_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != TOOL_FAULT_SCENARIO_VERSION:
            raise ValueError("unsupported Tool fault scenario version")
        if self.mode not in ("normal", "transient_once", "permanent"):
            raise ValueError("Tool fault mode must be normal, transient_once, or permanent")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 3:
            raise ValueError("Tool fault max_attempts must be an integer from 1 to 3")
        if self.mode == "transient_once" and self.max_attempts < 2:
            raise ValueError("transient_once requires a retry budget of at least two attempts")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def scenario_hash(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    def fault_at(self, attempt: int) -> str | None:
        if self.mode == "permanent" or (self.mode == "transient_once" and attempt == 1):
            return self.mode
        return None

    def audit_record(self, trace: dict[str, Any]) -> dict[str, Any]:
        steps = trace.get("steps", [])
        exercised = (
            trace.get("call_valid") is True and len(steps) == 1 and bool(steps[0]["attempts"])
        )
        attempts = steps[0]["attempts"] if exercised else []
        signatures = [
            (a["status"], a["retryable"], a["fault_injected"], a["handler_invoked"])
            for a in attempts
        ]
        expected = {
            "normal": [("success", False, False, True)],
            "transient_once": [("failed", True, True, False), ("success", False, False, True)],
            "permanent": [("failed", False, True, False)],
        }[self.mode]
        passed = exercised and signatures == expected
        return {
            **self.to_dict(),
            "scenario_hash": self.scenario_hash,
            "authority": "test_environment",
            "gate_evidence": False,
            "injection_point": "before_handler",
            "model_arguments_modified": False,
            "status": "passed" if passed else "failed" if exercised else "not_exercised",
            "passed": passed,
            "injected_failure_count": sum(a["fault_injected"] for a in attempts),
            "handler_invocation_count": sum(a["handler_invoked"] for a in attempts),
            "measurement": "executor_fixture_behavior_not_model_recovery_ability",
        }


def parse_tool_fault_scenario(value: Any) -> ToolFaultScenario | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"schema_version", "mode", "max_attempts"}:
        raise ValueError("Tool fault scenario requires only schema_version, mode, and max_attempts")
    return ToolFaultScenario(**value)


def validate_fault_case(evaluation_case: Any) -> None:
    payload = evaluation_case.input_payload_json or {}
    schema = evaluation_case.expected_tool_schema_json
    if (
        evaluation_case.category not in ("tool_single_step", "tool_failure_recovery")
        or not isinstance(schema, dict)
        or not schema.get("tool_name")
        or "expected_sequence" in schema
        or isinstance(payload.get("agent_context"), dict)
        or isinstance(payload.get("rag_context"), dict)
    ):
        raise ValueError("Tool fault scenarios support standalone, single-call Tool cases only")
    if _contains_legacy_failure_contract(schema):
        raise ValueError(
            "legacy simulate_failure evaluation contract is incompatible with environment faults; "
            "create a separate versioned case instead of rewriting historical labels"
        )


def _contains_legacy_failure_contract(value: Any) -> bool:
    if isinstance(value, dict):
        return "simulate_failure" in value or any(
            (
                key in ("required", "required_arguments")
                and isinstance(child, list)
                and "simulate_failure" in child
            )
            or _contains_legacy_failure_contract(child)
            for key, child in value.items()
        )
    return isinstance(value, list) and any(_contains_legacy_failure_contract(v) for v in value)
