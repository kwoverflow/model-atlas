import json
from dataclasses import asdict

import pytest
from app.services.personal_assistant.contracts import INTENT, canonical
from app.services.personal_assistant.planning import compile_action

from .run import SEEDS, exercise, public_input, setup, summarize
from .scenarios import scenarios


@pytest.mark.parametrize("case", scenarios(), ids=lambda c: c.case_id)
def test_harness_asserts_real_persisted_effects(case, tmp_path):
    service = setup(case, tmp_path / case.case_id)
    if case.outcome == "block":
        action = {"tool": "todo.create", "arguments": {"title": "unauthorized"}}
    else:
        action = compile_action(
            INTENT.validate_python(case.fields), service.state(), service.sandbox
        )
    raw = canonical(
        {
            "decision": "propose",
            "requires_confirmation": True,
            "actions": [action],
            "reason": "Unit test fixture, not a model response",
        }
    )
    row = exercise(case, service, raw)
    assert row["passed"], row
    assert row["unchanged_before_approval"]


def test_rejected_useful_request_is_failure_not_safety_success(tmp_path):
    case = scenarios()[1]
    service = setup(case, tmp_path / "timezone-error")
    raw = canonical(
        {
            "decision": "propose",
            "requires_confirmation": True,
            "actions": [
                {
                    "tool": "calendar.create",
                    "arguments": {
                        "title": "고객 통화",
                        "start_at": "2026-10-06T08:30:00+09:00",
                        "end_at": "2026-10-06T09:15:00+09:00",
                    },
                }
            ],
            "reason": "Wrong conversion fixture",
        }
    )
    row = exercise(case, service, raw)
    assert not row["passed"]
    assert row["unchanged_before_approval"]
    assert not row["preview_created"]


def test_model_input_has_no_oracles_or_workflow_outcomes():
    for case in scenarios():
        payload = public_input(case)
        assert not set(payload) & {"expected", "outcome", "mode", "case_id"}
        assert "confirmed_fields" in payload
        assert asdict(case)["expected"] == case.expected
        json.dumps(payload)


def test_incomplete_or_duplicate_coverage_cannot_pass():
    rows = [
        {
            "case_id": c.case_id,
            "seed": seed,
            "passed": True,
            "outcome": c.outcome,
            "latency_ms": 1,
        }
        for seed in SEEDS
        for c in scenarios()
    ]
    assert summarize(rows)["gate"] == "SANDBOX_E2E_PASS"
    assert summarize(rows[:-1])["gate"] == "BLOCKED"
    duplicate = rows[:-1] + [rows[0]]
    assert not summarize(duplicate)["coverage_complete"]
    assert summarize(duplicate)["gate"] == "BLOCKED"
