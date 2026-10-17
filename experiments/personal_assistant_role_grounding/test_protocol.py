import json

import pytest

from .run import (
    ARMS,
    BASELINE,
    STRATEGY,
    DraftAssistantService,
    exercise,
    score,
    setup,
    splits,
    summary,
)


def complete_rows():
    rows = [
        {
            "arm": arm,
            "split": split,
            "case_id": case.case_id,
            "seed": seed,
            "outcome": case.outcome,
            "extraction": {"valid": True, "matches_confirmation": case.outcome != "block"},
            "decision_correct": True if "decisions" in case.expected else None,
            "passed": True,
            "unchanged_before_approval": True,
            "sentinel_unchanged": True,
            "generated": {},
        }
        for arm in ARMS
        for split, cases in splits()
        for case in cases
        for seed in (42, 1729)
    ]
    for row in rows:
        if row["arm"] == BASELINE and row["case_id"] == "F18":
            row["extraction"]["matches_confirmation"] = False
    return rows


def test_complete_success_is_not_automatic_deployment():
    rows = complete_rows()
    assert len(rows) == 352
    result = summary(rows)
    assert result["coverage_complete"] and not result["paired_regressions"]
    assert result["candidate_gate"] == "PASS_PENDING_INTEGRATION"
    assert result["autonomous_release"] == "BLOCKED_UNCHANGED"


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "positive",
        "decision",
        "workflow",
        "mutation",
        "outside",
        "length",
        "grounding",
    ],
)
def test_any_failure_blocks_gate(fault):
    rows = complete_rows()
    row = next(
        r
        for r in rows
        if r["arm"] == STRATEGY
        and r["split"] == "holdout"
        and (r["decision_correct"] is not None if fault == "decision" else r["outcome"] != "block")
    )
    if fault == "schema":
        row["extraction"]["valid"] = False
    elif fault == "positive":
        row["extraction"]["matches_confirmation"] = False
    elif fault == "decision":
        row["decision_correct"] = False
    elif fault == "workflow":
        row["passed"] = False
    elif fault == "mutation":
        row["unchanged_before_approval"] = False
    elif fault == "outside":
        row["sentinel_unchanged"] = False
    else:
        row["generated"]["completion_error" if fault == "length" else "grounding_error"] = fault
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_incomplete_duplicate_and_no_gain_do_not_pass():
    rows = complete_rows()
    assert not summary(rows[:-1])["coverage_complete"]
    assert not summary([*rows, rows[0]])["coverage_complete"]
    for row in rows:
        if row["arm"] == BASELINE and row["outcome"] != "block":
            row["extraction"]["matches_confirmation"] = True
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_paired_regression_is_reported_even_when_aggregate_gain_remains():
    rows = complete_rows()
    row = next(r for r in rows if r["arm"] == STRATEGY and r["case_id"] == "R08")
    row["extraction"]["matches_confirmation"] = False
    result = summary(rows)
    assert result["candidate_gate"] == "BLOCKED_KEEP_LEGACY"
    assert result["paired_regressions"] == [{"split": "holdout", "case_id": "R08", "seed": 42}]


def test_all_fresh_case_goals_match_independent_executor(tmp_path):
    _, cases = splits()[1]
    assert len(cases) == len({c.case_id for c in cases}) == 16
    assert len(splits()[0][1]) == 72
    for case in cases:
        service = DraftAssistantService(setup(case, tmp_path / case.case_id).sandbox)
        decision = case.expected.get("decisions", ["propose"])[0]
        raw = json.dumps(
            {
                "decision": decision,
                "intent": case.fields if decision == "propose" else None,
                "reason": "fixture",
            }
        )
        row = exercise(case, service, raw)
        assert row["passed"] and row["unchanged_before_approval"], case.case_id
        extraction, correct = score(case, raw, {})
        assert extraction["valid"]
        assert (
            correct is True if "decisions" in case.expected else extraction["matches_confirmation"]
        )
