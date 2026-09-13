"""Run the actual contract service against synthetic inputs in a disposable in-memory DB."""

import datetime as dt
import hashlib
import time
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.structured_requests import StructuredRequest, StructuredRequestCheck
from app.schemas.structured_requests import ContractBinding, StructuredTicketInput
from app.services import structured_requests as lab
from app.services.operator_identity import SignerIdentity
from app.services.request_scenario_catalog import Scenario, pack

FIXTURE_ACTOR = SignerIdentity(
    subject_id="automated-scenario-runner",
    display_name="Automated QA",
    role=None,
    identity_provider="synthetic-fixture",
    auth_source="automated_fixture",
    identity_verified=False,
    ticket_reference=None,
)


def _binding(record):
    return ContractBinding(
        expected_revision=record["revision"], expected_hash=record["contract_hash"]
    )


def observe(db: Session, case: Scenario) -> dict:
    draft = StructuredTicketInput.model_validate(case.draft)
    record = lab.save_draft(db, draft, FIXTURE_ACTOR)
    request_id = UUID(record["id"])
    binding = _binding(record)
    confirmation_status = 200
    try:
        lab.confirm(db, request_id, binding, FIXTURE_ACTOR)
    except HTTPException as exc:
        confirmation_status = exc.status_code
        if case.action != "unresolved":
            raise
    checked = lab.add_check(
        db, request_id, binding, FIXTURE_ACTOR, case.proposal, source="synthetic_scenario_proposal"
    )
    check_id = UUID(checked["id"])
    if case.action == "edit":
        changed = draft.model_copy(update={"query": draft.query + " 수정"})
        lab.save_draft(db, changed, FIXTURE_ACTOR, request_id=request_id, binding=binding)
    elif case.action == "revoke":
        lab.revoke(db, request_id, binding, FIXTURE_ACTOR)
    elif case.action == "expire":
        # Fixture-only time setup; the live API exposes no expiry override.
        db.get(StructuredRequest, request_id).expires_at = lab.utcnow() - dt.timedelta(seconds=1)
        db.commit()
    elif case.action in {"replay", "consumed"}:
        first = lab.execute(db, request_id, check_id, FIXTURE_ACTOR)
        if not first["execution"]["trace"]["successful"]:
            raise RuntimeError("initial fixture execution failed")
        if case.action == "consumed":
            other = lab.add_check(
                db,
                request_id,
                binding,
                FIXTURE_ACTOR,
                case.proposal,
                source="synthetic_scenario_proposal",
            )
            check_id = UUID(other["id"])
    status, reasons, replayed, successful = 200, [], False, False
    try:
        result = lab.execute(db, request_id, check_id, FIXTURE_ACTOR)
        replayed = result["replayed"]
        successful = result["execution"]["trace"]["successful"]
    except HTTPException as exc:
        status = exc.status_code
        detail = exc.detail
        reasons = (
            detail.get("reasons", [detail.get("code")]) if isinstance(detail, dict) else [detail]
        )
    traces = [
        c.execution_json["trace"]
        for c in db.scalars(
            select(StructuredRequestCheck).where(StructuredRequestCheck.request_id == request_id)
        )
        if c.execution_json
    ]
    invocations = sum(t["fault_scenario"]["handler_invocation_count"] for t in traces)
    expectations = {
        "status": status == case.expected_status,
        "reason": case.expected_reason is None or case.expected_reason in reasons,
        "handler_invocations": invocations == case.expected_invocations,
        "success_when_allowed": status != 200 or successful,
        "replay": replayed == (case.action == "replay"),
        "unresolved_confirmation": case.action != "unresolved" or confirmation_status == 422,
    }
    matched = all(expectations.values())
    return {
        "id": case.id,
        "title": case.title,
        "outcome": "regression"
        if not matched
        else "known_limitation"
        if case.known_limitation
        else "passed",
        "expected": {
            "status": case.expected_status,
            "reason": case.expected_reason,
            "handler_invocations": case.expected_invocations,
        },
        "observed": {
            "status": status,
            "reasons": reasons,
            "handler_invocations": invocations,
            "replayed": replayed,
            "confirmation_status": confirmation_status,
        },
        "expectations": expectations,
        "fixture": case.snapshot(),
        "initial_verdict": checked["verdict"],
        "traces": traces,
    }


def run_scenarios() -> dict:
    started = time.perf_counter()
    fixed = pack()
    engine = create_engine("sqlite://")
    rows = []
    try:
        StructuredRequest.metadata.create_all(
            engine,
            tables=[
                StructuredRequest.__table__,
                StructuredRequestCheck.__table__,
            ],
        )
        for case in fixed["cases"]:
            with Session(engine) as db:
                try:
                    rows.append(observe(db, case))
                except Exception as exc:
                    db.rollback()
                    rows.append(
                        {
                            "id": case.id,
                            "title": case.title,
                            "outcome": "error",
                            "error_type": type(exc).__name__,
                            "fixture": case.snapshot(),
                        }
                    )
    finally:
        engine.dispose()
    counts = {
        status: sum(row["outcome"] == status for row in rows)
        for status in ("passed", "known_limitation", "regression", "error")
    }
    root = Path(__file__).resolve().parents[1]
    paths = [
        "services/structured_requests.py",
        "services/structured_ticket_contract.py",
        "services/tool_execution.py",
        "services/tool_call_contract.py",
        "services/request_scenario_catalog.py",
        "services/request_scenario_runner.py",
        "schemas/structured_requests.py",
        "models/structured_requests.py",
    ]
    return {
        "version": fixed["version"],
        "pack_hash": fixed["hash"],
        "scope": "automated_synthetic_contract_regression_only",
        "gate_evidence": False,
        "human_review": False,
        "model_calls": 0,
        "side_effect_mode": "simulated",
        "database": "isolated_in_memory_sqlite",
        "rows": rows,
        "counts": counts,
        "status": "failed"
        if counts["regression"] or counts["error"]
        else "completed_with_limitations",
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "implementation_hashes": {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths
        },
    }
