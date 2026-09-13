"""Self-reported input exercises. No model calls, Tool execution or official review writes."""

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.base import utcnow
from app.models.request_scenarios import RequestScenarioRun, RequestStudyAttempt
from app.services.request_scenario_catalog import pack, study_task
from app.services.request_scenario_runner import run_scenarios
from app.services.structured_requests import commit, owner_key
from app.services.structured_ticket_contract import digest


def public_catalog():
    fixed = pack()
    return {
        "version": fixed["version"],
        "hash": fixed["hash"],
        "count": len(fixed["cases"]),
        "tasks": [study_task(c, fixed["hash"]) for c in fixed["cases"] if c.study_answer],
    }


def read_run(row):
    return {"id": str(row.id), "created_at": row.created_at, "report": row.report_json}


def create_run(db, actor):
    report = run_scenarios()
    report["initiated_by"] = actor.to_json()
    row = RequestScenarioRun(owner_key=owner_key(actor), report_json=report)
    db.add(row)
    commit(db)
    return read_run(row)


def read_attempt(row):
    scenario = row.scenario_json
    return {
        "id": str(row.id),
        "source": row.source,
        "revision": row.revision,
        "task": scenario["task"],
        "answer": row.answer_json,
        "answer_hash": row.answer_hash,
        "result": row.result_json,
        "correction_count": row.correction_count,
        "started_at": row.started_at,
        "submitted_at": row.submitted_at,
        "actor": row.actor_json,
        "human_review_verified": False,
        "gate_evidence": False,
    }


def owned_attempt(db, attempt_id, actor, *, lock=False):
    query = (
        select(RequestStudyAttempt)
        .where(
            RequestStudyAttempt.id == attempt_id, RequestStudyAttempt.owner_key == owner_key(actor)
        )
        .execution_options(populate_existing=True)
    )
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None:
        raise HTTPException(404, "study_not_found")
    return row


def start_attempt(db, payload, actor):
    fixed = pack()
    case = next((c for c in fixed["cases"] if c.id == payload.scenario_id and c.study_answer), None)
    if case is None:
        raise HTTPException(404, "study_scenario_not_found")
    row = RequestStudyAttempt(
        id=uuid4(),
        owner_key=owner_key(actor),
        source=payload.source,
        scenario_json={"task": study_task(case, fixed["hash"]), "expected": case.study_answer},
        actor_json=actor.to_json(),
        revision=0,
        correction_count=0,
    )
    db.add(row)
    commit(db)
    return read_attempt(row)


def answer_hash(row):
    return digest(
        {
            "id": str(row.id),
            "revision": row.revision,
            "source": row.source,
            "owner": row.owner_key,
            "task": row.scenario_json["task"],
            "answer": row.answer_json,
        }
    )


def save_answer(db, attempt_id, payload, actor):
    row = owned_attempt(db, attempt_id, actor, lock=True)
    if row.submitted_at:
        raise HTTPException(409, "study_already_submitted")
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "stale_study_revision")
    answer = payload.answer.model_dump()
    if row.answer_json != answer:
        row.correction_count += int(row.answer_json is not None)
        row.answer_json = answer
        row.revision += 1
        row.answer_hash = answer_hash(row)
        commit(db)
    return read_attempt(row)


def submit_answer(db, attempt_id, payload, actor):
    row = owned_attempt(db, attempt_id, actor, lock=True)
    if row.revision != payload.expected_revision or row.answer_hash != payload.expected_hash:
        raise HTTPException(409, "stale_study_revision")
    if row.answer_json is None or answer_hash(row) != row.answer_hash:
        raise HTTPException(409, "study_answer_integrity_failed")
    if row.submitted_at:
        return {**read_attempt(row), "replayed": True}
    expected = row.scenario_json["expected"]
    observed = row.answer_json
    mismatches = [
        key for key in ("decision", "query", "priority") if observed[key] != expected[key]
    ]
    row.submitted_at = utcnow()
    row.result_json = {
        "matches_scenario_key": not mismatches,
        "mismatches": mismatches,
        "expected": expected,
        "elapsed_seconds": max(0, round((row.submitted_at - row.started_at).total_seconds(), 3)),
        "timing_scope": "server_wall_time_including_idle_and_reload",
        "correction_count": row.correction_count,
        "correction_scope": "changed_saved_answers_after_first_save",
        "source": row.source,
        "human_review_verified": False,
        "gate_evidence": False,
        "evaluation_scope": "local_authored_scenario_key_not_independent_human_review",
    }
    commit(db)
    return {**read_attempt(row), "replayed": False}
