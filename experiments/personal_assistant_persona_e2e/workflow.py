"""Independent final-state assertions and bounded, explicitly idealized reviewers."""

import copy
import hashlib
import json
from dataclasses import replace
from unittest.mock import patch

from jsonschema import ValidationError, validate

from app.services.personal_assistant.contracts import INTENT, GuardError, canonical
from app.services.personal_assistant.drafts import parse_draft
from app.services.personal_assistant.inference import draft_schema
from app.services.personal_assistant.reviews import ReviewService
from app.services.personal_assistant.sandbox import Sandbox

from .protocol import FIXTURE, Case, Persona


def binding(record):
    return {"revision": record["revision"], "content_hash": record["content_hash"]}


def confirm(service, record):
    return service.confirm(record["id"], **binding(record))


def approve(service, record):
    return service.approve_review(
        record["id"], **binding(record), plan_hash=record["preview"]["plan_hash"]
    )


def fixture(service, fields):
    raw = canonical({"decision": "propose", "intent": fields, "reason": "Synthetic setup only"})
    return approve(
        service, confirm(service, service.create("Synthetic setup", lambda *_: {"raw_output": raw}))
    )


def make_service(root):
    sandbox = Sandbox.create(root)
    (root / "files" / "Inbox").mkdir()
    (root / "files" / "Archive").mkdir()
    (root / "files" / "Inbox" / "review-demo.txt").write_bytes(FIXTURE)
    return ReviewService(sandbox)


def prepare_case(service, case):
    if case.setup:
        fixture(
            service,
            {
                "operation": "todo.create",
                "title": "수동점검 수정 후" if case.setup == "duplicate" else "수동점검 준비",
            },
        )
        if case.setup == "target":
            target = service.state()["tasks"][0]["task_id"]
            # This ID is observable workspace state, not a hidden model answer.
            return replace(
                case,
                request=case.request.format(task_id=target),
                fields={"operation": "todo.complete", "task_id": target},
            )
    return case


def normalized(fields):
    """Treat omitted/defaulted/null optional fields equivalently; no string repair."""
    return INTENT.validate_python(fields).model_dump(exclude_none=True)


def raw_score(raw, case):
    try:
        draft = parse_draft(raw)
        validate(json.loads(raw), draft_schema())
        if case.accepted_decisions:
            return {
                "strict_valid": True,
                "correct": draft.decision in case.accepted_decisions and draft.intent is None,
                "decision": draft.decision,
            }
        return {
            "strict_valid": True,
            "correct": draft.decision == "propose"
            and draft.intent is not None
            and normalized(draft.intent.model_dump()) == normalized(case.fields),
            "decision": draft.decision,
        }
    except (ValueError, GuardError, ValidationError):
        return {"strict_valid": False, "correct": False, "decision": None}


def corrections(initial, goal):
    left, right = copy.deepcopy(initial), copy.deepcopy(goal)
    # Default timezone is not a correction when absent and irrelevant.
    try:
        if normalized(left) == normalized(right):
            return []
    except ValueError:
        pass
    missing = object()
    return sorted(
        k for k in left.keys() | right.keys() if left.get(k, missing) != right.get(k, missing)
    )


def rejected(call, message):
    try:
        call()
    except GuardError as exc:
        assert message in str(exc), str(exc)
        return str(exc)
    raise AssertionError("Expected rejection: " + message)


def assert_effect(case, before, after, fields):
    """Does not call compile_action or score only a receipt from the executor."""
    op = fields["operation"]
    if op.startswith("todo"):
        assert after["events"] == before["events"] and after["files"] == before["files"]
        if op == "todo.complete":
            expected = copy.deepcopy(before["tasks"])
            target = next(t for t in expected if t["task_id"] == fields["task_id"])
            target["status"] = "complete"
            assert after["tasks"] == expected
        else:
            old_ids = {t["task_id"] for t in before["tasks"]}
            new = [t for t in after["tasks"] if t["task_id"] not in old_ids]
            assert len(new) == 1 and len(after["tasks"]) == len(before["tasks"]) + 1
            assert [t for t in after["tasks"] if t["task_id"] in old_ids] == before["tasks"]
            expected = {"task_id": new[0]["task_id"], "title": fields["title"], "status": "open"}
            if case.id == "M01":
                expected.update(due_at="2026-12-22T09:00:00+09:00", priority="low")
            assert new[0] == expected
    elif op == "calendar.create":
        assert after["tasks"] == before["tasks"] and after["files"] == before["files"]
        new = [e for e in after["events"] if e not in before["events"]]
        assert len(new) == 1 and len(after["events"]) == len(before["events"]) + 1
        times = {
            "M03": ("2026-12-23T10:00:00+09:00", "2026-12-23T10:40:00+09:00"),
            "M04": ("2026-12-24T22:30:00+09:00", "2026-12-24T23:15:00+09:00"),
        }
        start, end = times[case.id]
        assert new[0] == {
            "event_id": new[0]["event_id"],
            "title": fields["title"],
            "start_at": start,
            "end_at": end,
        }
    else:
        assert after["events"] == before["events"] and after["tasks"] == before["tasks"]
        assert "files/Inbox/review-demo.txt" not in after["files"]
        destinations = list(after["files"])
        assert len(destinations) == 1
        if op == "files.move":
            assert destinations == ["files/Archive/review-demo.txt"]
        else:
            assert destinations[0].startswith("trash/")
        assert after["files"][destinations[0]] == before["files"]["files/Inbox/review-demo.txt"]
        assert after["files"][destinations[0]]["sha256"] == hashlib.sha256(FIXTURE).hexdigest()


def run_case(service, case: Case, persona: Persona, generator):
    case = prepare_case(service, case)
    before = service.state()
    record = service.create(case.request, generator)
    assert service.state() == before, "Generation mutated workspace"
    result = {
        "case_id": case.id,
        "persona": persona.name,
        "request": case.request,
        "raw_score": raw_score(record["raw_output"], case),
        "initial_record": record,
        "goal_fields": case.fields,
        "before": before,
        "edit_keys": [],
        "planned_user_changes": 0,
        "completed": False,
        "completed_without_correction": False,
        "preapproval_unchanged": True,
        "outcome": "abandoned",
        "expiry_mode": None,
    }
    if case.flow == "no_effect":
        result.update(
            completed=result["raw_score"]["correct"],
            completed_without_correction=result["raw_score"]["correct"],
            outcome="no_effect_decision"
            if result["raw_score"]["correct"]
            else "incorrect_decision_abandoned",
        )
    elif case.flow == "duplicate":
        if result["raw_score"]["correct"]:
            result.update(
                completed=True, completed_without_correction=True, outcome="model_no_effect"
            )
        else:
            # A deterministic guard is NOT the same as model clarification correctness.
            if not corrections(record["fields"], case.fields):
                result["rejection"] = rejected(lambda: confirm(service, record), "duplicate_task")
                result.update(
                    completed=True,
                    completed_without_correction=True,
                    outcome="code_duplicate_guard",
                )
    else:
        edits = corrections(record["fields"], case.fields)
        result["required_edit_keys"] = edits
        if len(edits) > persona.edit_budget:
            result["outcome"] = "edit_budget_exceeded"
        else:
            if edits:
                record = service.save(record["id"], **binding(record), fields=case.fields)
                result["edit_keys"] = edits
            record = confirm(service, record)
            assert service.state() == before, "Confirmation mutated workspace"
            if case.flow == "change":
                old = record
                changed = {**case.fields, "title": "수동점검 수정 후"}
                record = service.save(record["id"], **binding(record), fields=changed)
                result["rejection"] = rejected(
                    lambda: approve(service, old), "stale_review_revision"
                )
                assert service.state() == before
                record = confirm(service, record)
                result["planned_user_changes"] = 1
            if case.flow == "cancel":
                record = service.cancel_review(record["id"], **binding(record))
                assert record["status"] == "cancelled" and service.state() == before
            elif case.flow == "expire":
                # Fast service verification; actual 300s wait belongs to browser evidence.
                with patch("time.time", return_value=record["preview"]["expires_at"] + 1):
                    assert service.get(record["id"])["status"] == "expired"
                    result["rejection"] = rejected(
                        lambda: approve(service, record), "approval_expired_or_state_changed"
                    )
                result["expiry_mode"] = "controlled_clock"
                assert service.state() == before
            else:
                record = approve(service, record)
                after = service.state()
                assert_effect(case, before, after, record["fields"])
                replay = approve(service, record)
                assert (
                    replay["events"][-1]["event"] == "execution_replayed"
                    and service.state() == after
                )
                if case.flow == "restore":
                    restore = service.restore_preview(record["id"], **binding(record))
                    assert service.state() == after
                    assert restore["parent_id"] == record["id"]
                    assert approve(service, restore)["status"] == "executed"
                    assert service.state() == before
            result.update(
                completed=True, completed_without_correction=not edits, outcome="flow_passed"
            )
    result["final_record"] = service.get(record["id"])
    result["after"] = service.state()
    if not result["completed"] or case.flow in {"no_effect", "duplicate"}:
        assert result["after"] == before, "Abandoned/no-effect case mutated workspace"
    reopened = ReviewService(Sandbox(service.sandbox.root))
    assert reopened.state() == result["after"]
    assert reopened.get(record["id"])["raw_output"] == result["initial_record"]["raw_output"]
    return result
