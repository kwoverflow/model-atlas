import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from .faults import run_faults  # noqa: E402
from .protocol import CASES, PERSONAS, VARIANTS, protocol  # noqa: E402
from .run import summarize  # noqa: E402
from .workflow import corrections, make_service, raw_score, run_case  # noqa: E402


def generator(case, mode="correct"):
    def generate(request, state):
        if mode == "invalid":
            return {"raw_output": "not JSON", "model": "test-fixture"}
        fields = dict(case.fields)
        if case.id == "M02":
            fields["task_id"] = state["tasks"][0]["task_id"]
        if mode == "quotes" and "title" in fields:
            fields["title"] = "'" + fields["title"] + "'"
        decision = case.accepted_decisions[0] if case.accepted_decisions else "propose"
        return {
            "raw_output": json.dumps(
                {
                    "decision": decision,
                    "intent": None if case.accepted_decisions else fields,
                    "reason": "Fixture",
                }
            ),
            "model": "test-fixture",
        }

    return generate


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_correct_drafts_complete_all_frozen_flows(tmp_path, case):
    row = run_case(make_service(tmp_path / "workspace"), case, PERSONAS[0], generator(case))
    assert row["raw_score"]["correct"] and row["completed_without_correction"]
    assert row["completed"] and not row["edit_keys"]


@pytest.mark.parametrize("persona", PERSONAS, ids=lambda p: p.name)
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_invalid_drafts_never_become_original_model_success(tmp_path, case, persona):
    row = run_case(make_service(tmp_path / "workspace"), case, persona, generator(case, "invalid"))
    assert not row["raw_score"]["correct"] and not row["completed_without_correction"]
    if case.flow == "duplicate":
        assert not row["completed"]
    else:
        assert row["completed"] == (len(case.fields) <= persona.edit_budget)


@pytest.mark.parametrize("case", VARIANTS, ids=lambda c: c.id)
def test_behavior_variants_use_conservative_fixed_goals(tmp_path, case):
    row = run_case(make_service(tmp_path / "workspace"), case, PERSONAS[0], generator(case))
    assert row["completed_without_correction"]


def test_one_field_correction_does_not_inflate_original_score(tmp_path):
    case = CASES[0]
    row = run_case(
        make_service(tmp_path / "workspace"), case, PERSONAS[1], generator(case, "quotes")
    )
    assert row["edit_keys"] == ["title"] and row["completed"]
    metrics = summarize([row])["groups"][PERSONAS[1].name]
    assert metrics["original_model_correct"] == metrics["completed_without_correction"] == 0
    assert metrics["completed_after_correction"] == 1


def test_optional_null_defaults_are_not_silent_string_repairs():
    assert (
        corrections(
            {"operation": "todo.create", "title": "x", "priority": None},
            {"operation": "todo.create", "title": "x"},
        )
        == []
    )
    assert corrections(
        {"operation": "todo.create", "title": "'x'"}, {"operation": "todo.create", "title": "x"}
    ) == ["title"]
    assert not raw_score('{"decision":"propose","intent":null,"reason":"wrong"}', CASES[0])[
        "strict_valid"
    ]
    assert protocol()["retries"] == 0


def test_real_killed_processes_and_concurrent_approvals(tmp_path):
    observations = run_faults(tmp_path / "faults")
    assert len(observations) == 6
    assert sum(o.get("process_terminated", False) for o in observations) == 5
    assert observations[-1]["executions"] == 1
