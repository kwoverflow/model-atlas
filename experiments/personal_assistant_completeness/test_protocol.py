import json

import pytest
from jsonschema import ValidationError, validate

from app.services.personal_assistant.complete_grounded_inference import complete_schema
from app.services.personal_assistant.contracts import INTENT
from app.services.personal_assistant.stable_inference import public_payload

from .run import (
    ARMS,
    BASELINE,
    NOW,
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
            "extraction": {
                "valid": True,
                "matches_confirmation": case.outcome != "block",
            },
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
        if row["arm"] == BASELINE and row["case_id"] == "D03":
            row["extraction"]["matches_confirmation"] = False
    return rows


def test_complete_gate_does_not_automatically_deploy():
    rows = complete_rows()
    result = summary(rows)
    assert len(rows) == 512 and result["coverage_complete"]
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
        and (
            r["decision_correct"] is not None
            if fault == "decision"
            else r["outcome"] != "block"
        )
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
        row["generated"][
            "completion_error" if fault == "length" else "grounding_error"
        ] = fault
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_missing_duplicate_and_no_gain_do_not_pass():
    rows = complete_rows()
    assert not summary(rows[:-1])["coverage_complete"]
    assert not summary([*rows, rows[0]])["coverage_complete"]
    for row in rows:
        if row["arm"] == BASELINE and row["outcome"] != "block":
            row["extraction"]["matches_confirmation"] = True
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_paired_regression_is_not_hidden_by_aggregate_improvement():
    rows = complete_rows()
    row = next(r for r in rows if r["arm"] == STRATEGY and r["case_id"] == "C04")
    row["extraction"]["matches_confirmation"] = False
    result = summary(rows)
    assert result["candidate_gate"] == "BLOCKED_KEEP_LEGACY"
    assert result["paired_regressions"] == [
        {"split": "holdout", "case_id": "C04", "seed": 42}
    ]


def test_goals_are_compatible_with_public_evidence_and_independent_executor(tmp_path):
    assert len(splits()[0][1]) == 108 and len(splits()[1][1]) == 20
    for split, cases in splits():
        assert len(cases) == len({case.case_id for case in cases})
        for case in cases:
            service = DraftAssistantService(
                setup(case, tmp_path / f"{split}-{case.case_id}").sandbox
            )
            public = public_payload(case.request, service.state(), now=NOW)
            hints, _, _, _, fields = complete_schema(public)
            decision = case.expected.get(
                "decisions", ["clarify" if case.outcome == "block" else "propose"]
            )[0]
            draft = {
                "decision": decision,
                "intent": INTENT.validate_python(case.fields).model_dump(
                    exclude_none=True
                )
                if decision == "propose"
                else None,
                "reason": "fixture, never sent to a model",
            }
            validate(draft, hints)
            if decision == "propose" and case.fields["operation"] in {
                "todo.create",
                "calendar.create",
            }:
                assert fields["operation"] == case.fields["operation"], case.case_id
            if split == "holdout":
                raw = json.dumps(draft)
                result = exercise(case, service, raw)
                assert result["passed"] and result["unchanged_before_approval"], (
                    case.case_id
                )
                extraction, correct = score(case, raw, {})
                assert extraction["valid"]
                assert (
                    correct is True
                    if "decisions" in case.expected
                    else extraction["matches_confirmation"]
                )


def test_every_bound_positive_rejects_missing_and_wrong_provable_fields(tmp_path):
    checked = 0
    for split, cases in splits():
        for case in cases:
            if case.outcome == "block":
                continue
            service = DraftAssistantService(
                setup(case, tmp_path / case.case_id).sandbox
            )
            hints, _, _, _, fields = complete_schema(
                public_payload(case.request, service.state(), now=NOW)
            )
            if not fields["operation"]:
                continue
            intent = INTENT.validate_python(case.fields).model_dump(exclude_none=True)
            name = (
                "TodoCreate"
                if fields["operation"] == "todo.create"
                else "CalendarCreate"
            )
            schema = hints["$defs"][name]
            for key in schema["required"]:
                if key == "operation":
                    continue
                missing = {k: v for k, v in intent.items() if k != key}
                with pytest.raises(ValidationError):
                    validate(
                        {"decision": "propose", "intent": missing, "reason": "missing"},
                        hints,
                    )
                if "const" in schema["properties"][key]:
                    wrong = {**intent, key: None}
                    with pytest.raises(ValidationError):
                        validate(
                            {"decision": "propose", "intent": wrong, "reason": "wrong"},
                            hints,
                        )
            checked += 1
    assert checked >= 35


def test_guarded_calendar_proposals_are_not_field_evidence_errors(tmp_path):
    for case in splits()[0][1]:
        if case.case_id not in {"D08", "D20"}:
            continue
        service = DraftAssistantService(setup(case, tmp_path / case.case_id).sandbox)
        hints, _, _, _, fields = complete_schema(
            public_payload(case.request, service.state(), now=NOW)
        )
        assert fields["operation"] == "calendar.create"
        validate(
            {
                "decision": "propose",
                "intent": INTENT.validate_python(case.fields).model_dump(
                    exclude_none=True
                ),
                "reason": "executor still owns conflict/DST rejection",
            },
            hints,
        )


def test_runner_uses_the_selected_frozen_arm_without_a_model(monkeypatch):
    from . import run

    calls = []

    def fake(name):
        def generate(*args, **kwargs):
            calls.append((name, kwargs))
            return {"strategy": name}

        return generate

    monkeypatch.setattr(run, "generate_field_grounded_draft", fake(BASELINE))
    monkeypatch.setattr(run, "generate_complete_grounded_draft", fake(STRATEGY))
    for arm in ARMS:
        assert run.generate(holdout_case := splits()[1][1][0], {}, arm, 42, []) == {
            "strategy": arm
        }
        assert holdout_case.case_id == "C01"
    assert [name for name, _ in calls] == list(ARMS)
    assert all(options == {"seed": 42, "now": NOW} for _, options in calls)
