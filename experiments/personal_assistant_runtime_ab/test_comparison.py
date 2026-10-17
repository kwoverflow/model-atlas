from experiments.personal_assistant_draft_e2e.scenarios import scenarios
from experiments.personal_assistant_runtime_ab.run import (
    ARMS,
    SEEDS,
    comparison,
    strict_score,
)


def rows():
    return [
        {
            "arm": arm,
            "case_id": c.case_id,
            "seed": seed,
            "outcome": c.outcome,
            "passed": True,
            "latency_ms": 1,
            "unchanged_before_approval": True,
            "extraction": {"valid": True, "matches_confirmation": c.outcome != "block"},
        }
        for arm in ARMS
        for seed in SEEDS
        for c in scenarios()
    ]


def test_adoption_does_not_follow_a_schema_only_improvement():
    observations = rows()
    observations[0]["extraction"]["valid"] = False
    assert comparison(observations)["adoption"] == "KEEP_EXISTING_PATH"


def test_improvement_and_complete_controls_are_required():
    observations = rows()
    observations[0]["passed"] = False
    observations[0]["extraction"]["matches_confirmation"] = False
    result = comparison(observations)
    assert result["adoption"] == "ADOPT_GENERATE_PATH"
    assert result["gate"] == "SANDBOX_DRAFT_E2E_PASS"
    target = next(
        r for r in observations if r["arm"] == "generate" and r["outcome"] == "control"
    )
    target["passed"] = False
    assert comparison(observations)["adoption"] == "KEEP_EXISTING_PATH"


def test_incomplete_or_mutated_comparison_cannot_be_adopted():
    observations = rows()
    observations[0]["passed"] = False
    observations[0]["extraction"]["matches_confirmation"] = False
    assert comparison(observations[:-1])["adoption"] == "KEEP_EXISTING_PATH"
    observations[-1]["unchanged_before_approval"] = False
    assert comparison(observations)["adoption"] == "KEEP_EXISTING_PATH"


def test_strict_scoring_rejects_unsupported_offset_even_if_pydantic_accepts():
    raw = (
        '{"decision":"propose","intent":{"operation":"calendar.create",'
        '"title":"도면 점검","local_start":"2026-11-18T11:20:00+09:00",'
        '"duration_minutes":40},"reason":"검토"}'
    )
    result = strict_score(scenarios()[0], raw)
    assert not result["valid"] and not result["matches_confirmation"]
