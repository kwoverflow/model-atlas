import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from .cases import holdout  # noqa: E402
from .run import ARMS, SEEDS, scenarios, summary  # noqa: E402


def complete_rows():
    rows = []
    for arm in ARMS:
        for split, cases in (("regression", scenarios()), ("holdout", holdout())):
            for case in cases:
                for seed in SEEDS:
                    candidate = arm == ARMS[1]
                    rows.append(
                        {
                            "arm": arm,
                            "split": split,
                            "case_id": case.case_id,
                            "seed": seed,
                            "outcome": case.outcome,
                            "extraction": {
                                "valid": candidate,
                                "matches_confirmation": candidate and case.outcome != "block",
                            },
                            "passed": candidate,
                            "unchanged_before_approval": True,
                            "generated": {},
                            "negative_decision_correct": candidate and case.outcome == "block",
                        }
                    )
    return rows


def test_complete_exact_candidate_is_only_a_human_review_adoption():
    result = summary(complete_rows())
    assert result["coverage_complete"]
    assert result["adoption"] == "ADOPT_HUMAN_REVIEW_DRAFT_PATH"
    assert result["autonomous_release"] == "BLOCKED_UNCHANGED"
    assert len(holdout()) == 16 and len({c.case_id for c in holdout()}) == 16


def test_invalid_schema_wrong_intent_or_conservative_decision_blocks_adoption():
    for field in ("schema", "intent", "negative", "mutation", "incomplete", "workflow"):
        rows = complete_rows()
        row = next(
            r
            for r in rows
            if r["arm"] == ARMS[1]
            and r["split"] == "holdout"
            and (r["outcome"] == "block" if field == "negative" else r["outcome"] != "block")
        )
        if field == "schema":
            row["extraction"]["valid"] = False
        elif field == "intent":
            row["extraction"]["matches_confirmation"] = False
        elif field == "negative":
            row["negative_decision_correct"] = False
        elif field == "mutation":
            row["unchanged_before_approval"] = False
        elif field == "incomplete":
            row["generated"]["completion_error"] = "length"
        else:
            row["passed"] = False
        assert summary(rows)["adoption"] == "KEEP_LEGACY_DEFAULT"


def test_duplicate_or_missing_rows_do_not_count_as_complete():
    rows = complete_rows()
    assert not summary(rows[:-1])["coverage_complete"]
    assert not summary([*rows, rows[0]])["coverage_complete"]
