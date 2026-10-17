import copy
import json

import pytest
from app.services.personal_assistant.contracts import INTENT
from app.services.personal_assistant.release_generation import (
    NEUTRAL_REASONS,
    release_schema,
)
from app.services.personal_assistant.stable_inference import public_payload
from jsonschema import validate

from .run import (
    NOW,
    DraftAssistantService,
    assess_meaning,
    assess_policy,
    setup,
    splits,
    summary,
)


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    root = tmp_path_factory.mktemp("release-fixtures")
    records = []
    for split, cases in splits():
        for case in cases:
            service = DraftAssistantService(setup(case, root / case.case_id).sandbox)
            hints, *_, evidence, policy = release_schema(
                public_payload(case.request, service.state(), now=NOW)
            )
            decision = (
                evidence["action_evidence"]["decision"]
                or case.expected.get(
                    "decisions", ["clarify" if case.outcome == "block" else "propose"]
                )[0]
            )
            reason = (
                NEUTRAL_REASONS[decision]
                if policy["policy"] == "neutral_decision_only"
                else evidence["explanation_evidence"]["reason"]
            )
            draft = {
                "decision": decision,
                "intent": INTENT.validate_python(case.fields).model_dump(
                    exclude_none=True
                )
                if decision == "propose"
                else None,
                "reason": reason,
            }
            validate(draft, hints)
            generated = {"semantic_evidence": evidence, "release_explanation": policy}
            raw = json.dumps(draft)
            assert assess_policy(generated, raw)
            for seed in (42, 1729):
                records.append(
                    {
                        "split": split,
                        "case_id": case.case_id,
                        "seed": seed,
                        "outcome": case.outcome,
                        "generated": generated,
                        "extraction": {
                            "valid": True,
                            "matches_confirmation": case.outcome != "block",
                        },
                        "decision_correct": True
                        if "decisions" in case.expected
                        else None,
                        "passed": True,
                        "unchanged_before_approval": True,
                        "sentinel_unchanged": True,
                        "meaning_assessment": assess_meaning(case, generated, raw),
                        "explanation_policy_correct": True,
                    }
                )
    return records


def test_all_known_inputs_keep_compatible_intents_and_honest_explanation_contract(rows):
    result = summary(rows)
    assert result["regression_gate"] == "PASS_PENDING_APP_RELEASE"
    assert (
        result["neutral_decision_only"] == result["source_semantics_unverified"] == 68
    )
    assert result["supported_interpretations"] == 24
    assert result["autonomous_release"] == "BLOCKED_UNCHANGED"


@pytest.mark.parametrize(
    "field",
    [
        "passed",
        "unchanged_before_approval",
        "sentinel_unchanged",
        "explanation_policy_correct",
    ],
)
def test_any_gate_failure_blocks_release(rows, field):
    changed = copy.deepcopy(rows)
    changed[0][field] = False
    assert summary(changed)["regression_gate"] == "BLOCKED"


def test_missing_duplicate_and_false_source_upgrade_do_not_pass(rows):
    assert summary(rows[:-1])["regression_gate"] == "BLOCKED"
    assert summary([*rows, rows[0]])["regression_gate"] == "BLOCKED"
    case = next(
        r
        for r in rows
        if r["generated"]["release_explanation"]["policy"] == "neutral_decision_only"
    )
    generated = copy.deepcopy(case["generated"])
    generated["release_explanation"]["source_semantics_upgraded"] = True
    raw = json.dumps(
        {"decision": "clarify", "intent": None, "reason": NEUTRAL_REASONS["clarify"]}
    )
    assert not assess_policy(generated, raw)
