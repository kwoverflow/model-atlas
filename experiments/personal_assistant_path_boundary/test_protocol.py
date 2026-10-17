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
    return [
        {
            "arm": arm,
            "split": split,
            "case_id": case.case_id,
            "seed": seed,
            "outcome": case.outcome,
            "extraction": {"valid": True, "matches_confirmation": case.outcome != "block"},
            "decision_correct": (arm == STRATEGY) if "decisions" in case.expected else None,
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


def test_complete_gate_still_requires_integration_and_keeps_autonomous_blocked():
    rows = complete_rows()
    result = summary(rows)
    assert len(rows) == 224 and result["coverage_complete"]
    assert result["candidate_gate"] == "PASS_PENDING_INTEGRATION"
    assert result["autonomous_release"] == "BLOCKED_UNCHANGED"


@pytest.mark.parametrize(
    "fault", ["schema", "positive", "decision", "workflow", "mutation", "outside", "length"]
)
def test_one_failure_blocks_default_adoption(fault):
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
        row["generated"]["completion_error"] = "length"
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_missing_duplicate_and_no_improvement_do_not_pass():
    rows = complete_rows()
    assert not summary(rows[:-1])["coverage_complete"]
    assert not summary([*rows, rows[0]])["coverage_complete"]
    for row in rows:
        if row["arm"] == BASELINE and row["decision_correct"] is not None:
            row["decision_correct"] = True
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_new_cases_match_existing_executor_boundary_and_effects(tmp_path):
    import json

    _, cases = splits()[1]
    assert len(cases) == len({c.case_id for c in cases}) == 20
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
        extraction, decision_correct = score(case, raw, {})
        assert extraction["valid"]
        assert (
            decision_correct is True
            if "decisions" in case.expected
            else extraction["matches_confirmation"]
        )
