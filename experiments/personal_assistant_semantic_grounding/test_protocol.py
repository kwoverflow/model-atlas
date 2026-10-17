import json

import pytest
from app.services.personal_assistant.contracts import INTENT
from app.services.personal_assistant.semantic_grounded_inference import semantic_schema
from app.services.personal_assistant.stable_inference import public_payload
from jsonschema import validate

from .run import (
    ARMS,
    BASELINE,
    NOW,
    STRATEGY,
    DraftAssistantService,
    assess_meaning,
    exercise,
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
            "extraction": {
                "valid": True,
                "matches_confirmation": case.outcome != "block",
            },
            "decision_correct": True if "decisions" in case.expected else None,
            "passed": True,
            "unchanged_before_approval": True,
            "sentinel_unchanged": True,
            "generated": {},
            "meaning_assessment": {
                "faithful_explanation": arm == STRATEGY,
                "evidence_correct": True if arm == STRATEGY else None,
                "interpretation_success": arm == STRATEGY
                and int(case.case_id[1:]) <= 12,
            }
            if split == "holdout"
            else None,
            **(
                {"baseline_origin": {}}
                if arm == BASELINE and split == "regression"
                else {}
            ),
        }
        for arm in ARMS
        for split, cases in splits()
        for case in cases
        for seed in (42, 1729)
    ]


def test_gate_separates_interpretation_from_abstention_and_does_not_deploy():
    rows = complete_rows()
    result = summary(rows)
    assert len(rows) == 656 and result["coverage_complete"]
    assert result["candidate_gate"] == "PASS_PENDING_INTEGRATION"
    assert result["autonomous_release"] == "BLOCKED_UNCHANGED"
    fresh = result["arms"][STRATEGY]["holdout"]
    assert fresh["supported_interpretations"] == 24 and fresh["safe_abstentions"] == 8
    assert result["arms"][BASELINE]["regression"]["new_model_calls"] == 0


@pytest.mark.parametrize(
    "fault",
    [
        "schema",
        "positive",
        "decision",
        "workflow",
        "mutation",
        "sentinel",
        "evidence",
        "meaning",
        "false_success",
        "runtime",
        "grounding",
    ],
)
def test_failures_cannot_be_hidden_by_aggregate_score(fault):
    rows = complete_rows()
    row = next(
        r
        for r in rows
        if r["arm"] == STRATEGY
        and (
            r["outcome"] != "block" if fault == "positive" else r["split"] == "holdout"
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
    elif fault == "sentinel":
        row["sentinel_unchanged"] = False
    elif fault in {"evidence", "meaning", "false_success"}:
        key = {
            "evidence": "evidence_correct",
            "meaning": "faithful_explanation",
            "false_success": "interpretation_success",
        }[fault]
        row["meaning_assessment"][key] = False
    elif fault == "runtime":
        row["runtime_error"] = fault
    else:
        row["generated"]["grounding_error"] = fault
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_duplicate_missing_and_no_improvement_block():
    rows = complete_rows()
    assert not summary(rows[:-1])["coverage_complete"]
    assert not summary([*rows, rows[0]])["coverage_complete"]
    for row in rows:
        if row.get("meaning_assessment"):
            row["meaning_assessment"]["faithful_explanation"] = True
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_abstention_cannot_be_counted_as_interpretation():
    rows = complete_rows()
    row = next(r for r in rows if r["arm"] == STRATEGY and r["case_id"] == "K13")
    row["meaning_assessment"]["interpretation_success"] = True
    assert summary(rows)["candidate_gate"] == "BLOCKED_KEEP_LEGACY"


def test_predeclared_goals_and_labels_are_compatible_without_model_calls(tmp_path):
    assert [len(cases) for _, cases in splits()] == [148, 16]
    for split, cases in splits():
        for case in cases:
            service = DraftAssistantService(
                setup(case, tmp_path / case.case_id).sandbox
            )
            hints, *_, proof = semantic_schema(
                public_payload(case.request, service.state(), now=NOW)
            )
            action = proof["action_evidence"]
            decision = (
                action["decision"]
                or case.expected.get(
                    "decisions", ["clarify" if case.outcome == "block" else "propose"]
                )[0]
            )
            draft = {
                "decision": decision,
                "intent": INTENT.validate_python(case.fields).model_dump(
                    exclude_none=True
                )
                if decision == "propose"
                else None,
                "reason": proof["explanation_evidence"]["reason"]
                or "unverified fixture",
            }
            validate(draft, hints)
            if split == "holdout":
                raw = json.dumps(draft)
                assessment = assess_meaning(case, {"semantic_evidence": proof}, raw)
                assert (
                    assessment["faithful_explanation"]
                    and assessment["evidence_correct"]
                ), case.case_id
                assert assessment["interpretation_success"] == (
                    int(case.case_id[1:]) <= 12
                )
                assert exercise(case, service, raw)["passed"]


def test_evidence_agreement_cannot_replace_faithful_explanation(tmp_path):
    case = splits()[1][1][0]
    service = DraftAssistantService(setup(case, tmp_path / "wrong").sandbox)
    proof = semantic_schema(public_payload(case.request, service.state(), now=NOW))[-1]
    wrong = json.dumps(
        {"decision": "no_change", "intent": None, "reason": "할 일 추가 요청입니다."}
    )
    result = assess_meaning(case, {"semantic_evidence": proof}, wrong)
    assert result["evidence_correct"] and not result["faithful_explanation"]


def test_run_and_replay_select_actual_arm(monkeypatch):
    from . import run
    from .verify import decoding

    calls = []

    def fake(name):
        def generate(*args, **kwargs):
            calls.append((name, kwargs))
            return {"strategy": name}

        return generate

    monkeypatch.setattr(run, "generate_decision_grounded_draft", fake(BASELINE))
    monkeypatch.setattr(run, "generate_semantic_grounded_draft", fake(STRATEGY))
    case = splits()[1][1][0]
    public = public_payload(
        case.request, {"events": [], "tasks": [], "files": {}}, now=NOW
    )
    for arm in ARMS:
        assert run.generate(case, {}, arm, 42, [])["strategy"] == arm
    assert [call[0] for call in calls] == list(ARMS)
    assert decoding(public, STRATEGY, 42)[0] == semantic_schema(public)
    assert decoding(public, BASELINE, 42)[0][0] != semantic_schema(public)[0]
