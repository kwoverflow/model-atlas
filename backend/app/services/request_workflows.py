"""Observe real local contracts; never supply expected arguments to generation or execution."""

import json
from uuid import UUID, uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from app.models.base import utcnow
from app.models.request_workflows import RequestWorkflowAttempt
from app.models.structured_requests import StructuredRequestCheck
from app.services import structured_requests as lab
from app.services.request_workflow_catalog import scenario
from app.services.structured_ticket_contract import digest, proposal_digest


def owned(db, attempt_id, actor, *, lock=False):
    query = (
        select(RequestWorkflowAttempt)
        .where(
            RequestWorkflowAttempt.id == attempt_id,
            RequestWorkflowAttempt.owner_key == lab.owner_key(actor),
        )
        .execution_options(populate_existing=True)
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "workflow_not_found")
    return row


def snapshot(db, row, actor, *, lock=False):
    if row.request_id is None:
        return None
    contract = lab.get_owned(db, row.request_id, actor, lock=lock)
    value = lab.read_request(db, contract)
    # Include every check, not the regular UI's latest-20 window. Expiry is derived, not evidence.
    value.pop("expired")
    value["checks"] = [
        lab.read_check(check)
        for check in db.scalars(
            select(StructuredRequestCheck)
            .where(StructuredRequestCheck.request_id == row.request_id)
            .order_by(StructuredRequestCheck.created_at.desc(), StructuredRequestCheck.id)
        )
    ]
    return jsonable_encoder(value)


def read(db, row, actor):
    current = None if row.ended_at else snapshot(db, row, actor)
    evidence = None
    if row.result_json:
        # Preserve numeric spellings through JavaScript JSON.stringify without rewriting results.
        canonical = json.dumps(
            {key: value for key, value in row.result_json.items() if key != "evidence_hash"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        evidence = {
            "canonical_json": canonical,
            "sha256": row.result_json["evidence_hash"],
            "verified": proposal_digest(canonical) == row.result_json["evidence_hash"],
            "scope": "stored_result_without_evidence_hash",
        }
    return {
        "id": str(row.id),
        "revision": row.revision,
        "source": row.source,
        "task": row.scenario_json["task"],
        "actor": row.actor_json,
        "request_id": str(row.request_id) if row.request_id else None,
        "request_state_hash": digest(current) if current is not None else None,
        "request": current,
        "help_count": row.help_count,
        "help_events": row.help_events_json,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "result": row.result_json,
        "evidence": evidence,
        "human_review_verified": False,
        "gate_evidence": False,
    }


def open_row(db, attempt_id, binding, actor):
    row = owned(db, attempt_id, actor, lock=True)
    if row.ended_at:
        raise HTTPException(409, "workflow_already_ended")
    if row.revision != binding.expected_revision:
        raise HTTPException(409, "stale_workflow_revision")
    return row


def start(db, payload, actor):
    task = scenario(payload.task_id)
    if task is None:
        raise HTTPException(404, "workflow_task_not_found")
    row = RequestWorkflowAttempt(
        id=uuid4(),
        owner_key=lab.owner_key(actor),
        source=payload.source,
        scenario_json=task,
        actor_json=actor.to_json(),
        revision=0,
        help_count=0,
        help_events_json=[],
    )
    db.add(row)
    lab.commit(db)
    return read(db, row, actor)


def create_draft(db, attempt_id, payload, actor):
    row = open_row(db, attempt_id, payload, actor)
    if row.request_id:
        raise HTTPException(409, "workflow_request_already_linked")
    if payload.draft.original_request != row.scenario_json["task"]["request"]:
        raise HTTPException(422, "workflow_original_request_changed")
    request = lab.save_draft(db, payload.draft, actor, commit_changes=False)
    row.request_id = UUID(request["id"])
    row.revision += 1
    lab.commit(db)
    return request


def record_help(db, attempt_id, payload, actor):
    row = open_row(db, attempt_id, payload, actor)
    if row.help_count >= 100:
        raise HTTPException(409, "workflow_help_limit")
    row.help_count += 1
    row.help_events_json = [
        *row.help_events_json,
        {"at": utcnow().isoformat(), "kind": "self_reported_help_request"},
    ]
    row.revision += 1
    lab.commit(db)
    return read(db, row, actor)


def assess(row, payload, request, ended_at):
    expected = row.scenario_json["expected"]
    checks = request["checks"] if request else []
    executions = [c for c in checks if c["execution"] is not None]
    current_executed = (
        next((c for c in executions if c["id"] == request["executed_check_id"]), None)
        if request
        else None
    )
    mismatches = []
    draft = request["draft"] if request else None
    if draft and draft["original_request"] != row.scenario_json["task"]["request"]:
        mismatches.append("original_request")
    if expected["decision"] == "execute":
        for key in ("query", "priority"):
            if not draft or draft[key] != expected[key]:
                mismatches.append(key)
        if payload.disposition != "finished":
            mismatches.append("decision")
        if not current_executed or not current_executed["execution"]["trace"]["successful"]:
            mismatches.append("successful_current_execution")
    elif payload.disposition != "clarification_requested" or executions:
        mismatches.append("clarification_without_execution")
    # Previous wrong executions must not disappear after editing and re-executing a contract.
    expected_arguments = {"query": expected["query"]}
    if expected["priority"]["mode"] == "set":
        expected_arguments["priority"] = expected["priority"]["value"]
    unsafe_execution_ids = [
        c["id"]
        for c in executions
        if expected["decision"] != "execute"
        or c["execution"]["verdict"]["actual_arguments"] != expected_arguments
    ]
    if unsafe_execution_ids:
        mismatches.append("execution_arguments")
    save_count = sum(e["event"] == "draft_saved" for e in request["events"]) if request else 0
    return {
        "disposition": payload.disposition,
        "assessment": "abandoned"
        if payload.disposition == "abandoned"
        else "matches_task"
        if not mismatches
        else "does_not_match_task",
        "mismatches": mismatches,
        "expected": expected,
        "feedback": {
            "assistance": payload.assistance,
            "difficulty": payload.difficulty,
            "note": payload.note,
        },
        "metrics": {
            "elapsed_seconds": max(0, round((ended_at - row.started_at).total_seconds(), 3)),
            "timing_scope": "server_wall_time_including_idle_and_reload",
            "saved_revision_count_after_first": max(0, save_count - 1),
            "revision_scope": (
                "all_draft_saves_after_first_including_identical_saves_not_keystrokes"
            ),
            "help_request_count": row.help_count,
            "proposal_count": len(checks),
            "model_proposal_count": sum(c["source"] == "local_model_proposal" for c in checks),
            "manual_proposal_count": sum(c["source"] == "manual_proposal" for c in checks),
            "blocked_proposal_count": sum(not c["verdict"]["allowed"] for c in checks),
            "execution_count": len(executions),
        },
        "unsafe_execution_ids": unsafe_execution_ids,
        "request_snapshot": request,
        "source": row.source,
        "human_review_verified": False,
        "gate_evidence": False,
        "scope": "local_authored_workflow_usability_not_model_accuracy_or_independent_review",
        "known_limitation": "incorrect_user_confirmation_can_authorize_incorrect_arguments",
    }


def finish(db, attempt_id, payload, actor):
    row = owned(db, attempt_id, actor, lock=True)
    submission_hash = digest(payload.model_dump())
    if row.ended_at:
        if submission_hash != row.submission_hash:
            raise HTTPException(409, "workflow_already_ended")
        return {**read(db, row, actor), "replayed": True}
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "stale_workflow_revision")
    if (row.source == "automated_qa") != (payload.assistance == "not_applicable"):
        raise HTTPException(422, "workflow_assistance_source_mismatch")
    if row.help_count and payload.assistance == "none_reported":
        raise HTTPException(422, "workflow_help_already_reported")
    request = snapshot(db, row, actor, lock=True)
    state_hash = digest(request) if request is not None else None
    if state_hash != payload.request_state_hash:
        raise HTTPException(409, "stale_workflow_request_state")
    if payload.disposition == "finished" and (not request or not request["checks"]):
        raise HTTPException(422, "workflow_proposal_check_required")
    row.ended_at = utcnow()
    result = assess(row, payload, request, row.ended_at)
    evidence = jsonable_encoder(
        {
            "attempt_id": str(row.id),
            "owner_key": row.owner_key,
            "actor": row.actor_json,
            "task": row.scenario_json["task"],
            "started_at": row.started_at,
            "ended_at": row.ended_at,
            "help_events": row.help_events_json,
            **result,
        }
    )
    row.result_json = {**evidence, "evidence_hash": digest(evidence)}
    row.submission_hash = submission_hash
    row.revision += 1
    lab.commit(db)
    return {**read(db, row, actor), "replayed": False}


def summary(db, actor):
    groups = {}
    for row in db.scalars(
        select(RequestWorkflowAttempt).where(
            RequestWorkflowAttempt.owner_key == lab.owner_key(actor)
        )
    ):
        result = row.result_json
        assistance = result["feedback"]["assistance"] if result else "pending"
        key = (row.scenario_json["task"]["pack_hash"], row.source, assistance)
        group = groups.setdefault(
            key,
            {
                "pack_hash": key[0],
                "source": row.source,
                "assistance": assistance,
                "total": 0,
                "open": 0,
                "matches_task": 0,
                "does_not_match_task": 0,
                "abandoned": 0,
            },
        )
        group["total"] += 1
        group[result["assessment"] if result else "open"] += 1
    return {
        "groups": list(groups.values()),
        "count_scope": "all_owned_attempts_not_people",
        "gate_evidence": False,
        "human_review_verified": False,
    }
