import pytest
from app.services.personal_assistant.contracts import canonical
from app.services.personal_assistant.drafts import DraftAssistantService

from experiments.personal_assistant_e2e.run import exercise, setup

from .run import SEEDS, extraction_score, public_input, summarize
from .scenarios import scenarios


@pytest.mark.parametrize("case", scenarios(), ids=lambda c: c.case_id)
def test_workflow_retains_independent_effect_assertions(case, tmp_path):
    service = DraftAssistantService(setup(case, tmp_path / case.case_id).sandbox)
    raw = canonical(
        {"decision": "propose", "intent": case.fields, "reason": "Unit fixture"}
    )
    row = exercise(case, service, raw)
    assert row["passed"], row


def test_positive_wrong_extraction_is_failure_not_success(tmp_path):
    case = scenarios()[1]
    service = DraftAssistantService(setup(case, tmp_path / "wrong-zone").sandbox)
    wrong = {**case.fields, "source_timezone": "Asia/Tokyo"}
    raw = canonical(
        {"decision": "propose", "intent": wrong, "reason": "Wrong timezone fixture"}
    )
    row = exercise(case, service, raw)
    assert not row["passed"] and row["unchanged_before_approval"]
    assert not extraction_score(case, raw)["matches_confirmation"]


def test_confirmed_fields_and_outcomes_are_hidden_from_model():
    for case in scenarios():
        payload = public_input(case)
        assert not set(payload) & {
            "confirmed_fields",
            "fields",
            "expected",
            "outcome",
            "mode",
        }
        assert "intent_contract" in payload


def test_gate_requires_all_schema_checks_and_unique_complete_coverage():
    rows = [
        {
            "case_id": c.case_id,
            "seed": seed,
            "outcome": c.outcome,
            "passed": True,
            "latency_ms": 1,
            "extraction": {"valid": True, "matches_confirmation": True},
        }
        for seed in SEEDS
        for c in scenarios()
    ]
    assert summarize(rows)["gate"] == "SANDBOX_DRAFT_E2E_PASS"
    assert summarize(rows[:-1])["gate"] == "BLOCKED"
    assert summarize(rows[:-1] + [rows[0]])["gate"] == "BLOCKED"
    rows[-1]["extraction"]["valid"] = False
    assert summarize(rows)["gate"] == "BLOCKED"
