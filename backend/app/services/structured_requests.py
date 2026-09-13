"""Persisted local request lab. Confirmation and execution stay outside official Gate evidence."""

from __future__ import annotations

import copy
import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from app.models.base import utcnow
from app.models.structured_requests import StructuredRequest, StructuredRequestCheck
from app.schemas.structured_requests import StructuredTicketInput
from app.services.inference_adapters.nullable_presence_tool import NullablePresenceToolAdapter
from app.services.structured_ticket_contract import (
    VERSION,
    compare_structured_ticket,
    digest,
    proposal_digest,
    public_descriptor,
)
from app.services.tool_execution import build_fault_tool_registry, execute_tool_calls
from app.services.tool_fault_scenarios import ToolFaultScenario

CONFIRMATION_TTL = dt.timedelta(minutes=15)
HANDLER_HASH = "e3f6e0a1cb986c2a3530a5cf3a0a92b188278e7cd508034c2d23544cb8cb2887"


def registry_and_hash():
    from app.services import tool_execution

    registry = build_fault_tool_registry()
    tool = registry.get("create_ticket")
    if (
        tool.handler is not tool_execution._create_ticket
        or tool.descriptor.side_effect_mode != "simulated"
        or tool.descriptor.tool_version != "create_ticket-fault-fixture-v1"
    ):
        raise HTTPException(409, "local_tool_contract_changed")
    source_hash = proposal_digest(Path(tool_execution.__file__).read_bytes().decode("utf-8"))
    if source_hash != HANDLER_HASH:
        raise HTTPException(409, "local_handler_source_changed")
    return registry, digest({"descriptor": tool.descriptor.to_dict(), "source_hash": source_hash})


def owner_key(actor):
    return digest(
        {k: actor.to_json()[k] for k in ("subject_id", "identity_provider", "auth_source")}
    )


def contract_hash(record):
    return digest(
        {
            "version": VERSION,
            "id": str(record.id),
            "owner": record.owner_key,
            "revision": record.revision,
            "draft": record.draft_json,
            "tool_contract_hash": record.tool_contract_hash,
        }
    )


def event(record, kind, actor, **details):
    record.events_json = [
        *record.events_json,
        {
            "event": kind,
            "at": utcnow().isoformat(),
            "revision": record.revision,
            "contract_hash": record.contract_hash,
            "actor": actor.to_json(),
            **details,
        },
    ]


def commit(db):
    try:
        db.commit()
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(409, "concurrent_contract_change") from exc


def get_owned(db, request_id, actor, *, lock=False):
    query = (
        select(StructuredRequest)
        .where(StructuredRequest.id == request_id, StructuredRequest.owner_key == owner_key(actor))
        .execution_options(populate_existing=True)
    )
    record = db.scalar(query.with_for_update() if lock else query)
    if record is None:
        raise HTTPException(404, "request_contract_not_found")
    return record


def check_binding(record, binding):
    if (
        record.revision != binding.expected_revision
        or record.contract_hash != binding.expected_hash
    ):
        raise HTTPException(409, "stale_request_contract")
    if contract_hash(record) != record.contract_hash:
        raise HTTPException(409, "request_contract_integrity_failed")


def read_check(check):
    return {
        "id": str(check.id),
        "request_id": str(check.request_id),
        "revision": check.revision,
        "contract_hash": check.contract_hash,
        "proposal": check.proposal,
        "proposal_hash": check.proposal_hash,
        "source": check.source,
        "verdict": check.verdict_json,
        "generation": check.generation_json,
        "execution": check.execution_json,
        "created_at": check.created_at,
    }


def read_request(db, record):
    checks = db.scalars(
        select(StructuredRequestCheck)
        .where(StructuredRequestCheck.request_id == record.id)
        .order_by(StructuredRequestCheck.created_at.desc())
        .limit(20)
    ).all()
    return {
        "id": str(record.id),
        "revision": record.revision,
        "status": record.status,
        "draft": record.draft_json,
        "contract_hash": record.contract_hash,
        "confirmation": record.confirmation_json,
        "expires_at": record.expires_at,
        "expired": bool(record.expires_at and record.expires_at <= utcnow()),
        "executed_check_id": str(record.executed_check_id) if record.executed_check_id else None,
        "events": record.events_json,
        "checks": [read_check(c) for c in checks],
        "created_at": record.created_at,
        "gate_evidence": False,
        "scope": "local_simulated_ticket_only",
    }


def save_draft(db, draft, actor, *, request_id=None, binding=None, commit_changes=True):
    _, tool_hash = registry_and_hash()
    if request_id is None:
        record = StructuredRequest(
            id=uuid4(),
            owner_key=owner_key(actor),
            revision=1,
            status="draft",
            draft_json={},
            contract_hash="",
            tool_contract_hash=tool_hash,
            events_json=[],
        )
        db.add(record)
    else:
        record = get_owned(db, request_id, actor, lock=True)
        check_binding(record, binding)
        record.revision += 1
    record.draft_json = draft.model_dump()
    record.tool_contract_hash = tool_hash
    record.status = "draft"
    record.confirmation_json = None
    record.expires_at = None
    record.executed_check_id = None
    record.contract_hash = contract_hash(record)
    event(record, "draft_saved", actor)
    if commit_changes:
        commit(db)
    else:
        db.flush()  # The workflow caller atomically links this draft before committing.
    return read_request(db, record)


def confirm(db, request_id, binding, actor):
    record = get_owned(db, request_id, actor, lock=True)
    check_binding(record, binding)
    _, tool_hash = registry_and_hash()
    if tool_hash != record.tool_contract_hash:
        raise HTTPException(409, "local_tool_contract_changed")
    if record.status != "draft":
        raise HTTPException(409, "only_drafts_can_be_confirmed")
    if StructuredTicketInput.model_validate(record.draft_json).priority.mode == "unresolved":
        raise HTTPException(422, "priority_unresolved")
    now = utcnow()
    record.status = "confirmed"
    record.expires_at = now + CONFIRMATION_TTL
    record.confirmation_json = {
        "contract_hash": record.contract_hash,
        "revision": record.revision,
        "actor": actor.to_json(),
        "authority": "authenticated_operator_assertion"
        if actor.identity_verified
        else "local_unverified_assertion",
        "confirmed_at": now.isoformat(),
        "gate_evidence": False,
    }
    event(record, "confirmed", actor)
    commit(db)
    return read_request(db, record)


def revoke(db, request_id, binding, actor):
    record = get_owned(db, request_id, actor, lock=True)
    check_binding(record, binding)
    record.status = "revoked"
    record.confirmation_json = None
    event(record, "revoked", actor)
    commit(db)
    return read_request(db, record)


def verdict_for(record, proposal, registry, tool_hash):
    verdict = compare_structured_ticket(
        StructuredTicketInput.model_validate(record.draft_json), proposal, registry
    )
    reasons = verdict["reasons"]
    confirmation = record.confirmation_json or {}
    if (
        record.status != "confirmed"
        or confirmation.get("contract_hash") != record.contract_hash
        or confirmation.get("revision") != record.revision
    ):
        reasons.append("request_not_confirmed")
    if record.expires_at is None or record.expires_at <= utcnow():
        reasons.append("confirmation_expired")
    if record.executed_check_id is not None:
        reasons.append("contract_already_executed")
    if contract_hash(record) != record.contract_hash or record.tool_contract_hash != tool_hash:
        reasons.append("contract_integrity_failed")
    return {
        **verdict,
        "allowed": not reasons,
        "contract_hash": record.contract_hash,
        "revision": record.revision,
        "confirmation_authority": confirmation.get("authority"),
        "gate_evidence": False,
    }


def add_check(
    db, request_id, binding, actor, proposal, *, source="manual_proposal", generation=None
):
    record = get_owned(db, request_id, actor, lock=True)
    check_binding(record, binding)
    registry, tool_hash = registry_and_hash()
    check = StructuredRequestCheck(
        id=uuid4(),
        request_id=record.id,
        revision=record.revision,
        contract_hash=record.contract_hash,
        proposal=proposal,
        proposal_hash=proposal_digest(proposal),
        source=source,
        generation_json=generation,
        verdict_json=verdict_for(record, proposal, registry, tool_hash),
    )
    db.add(check)
    event(
        record,
        "proposal_checked",
        actor,
        check_id=str(check.id),
        allowed=check.verdict_json["allowed"],
    )
    commit(db)
    return read_check(check)


class LocalProposalAdapter(NullablePresenceToolAdapter):
    def _candidate_base_urls(self, configuration):
        return ["http://ollama:11434", "http://localhost:11434", "http://127.0.0.1:11434"]

    def _headers(self, configuration):
        return {"content-type": "application/json"}

    def _post_json(self, configuration, base_url, path, body, *, deadline):
        self.requests.append(copy.deepcopy(body))
        return super()._post_json(configuration, base_url, path, body, deadline=deadline)


def generate(db, request_id, binding, actor):
    record = get_owned(db, request_id, actor)
    check_binding(record, binding)
    registry, tool_hash = registry_and_hash()
    if (
        record.status != "confirmed"
        or record.expires_at is None
        or record.expires_at <= utcnow()
        or record.executed_check_id
    ):
        raise HTTPException(409, "confirmed_unused_request_required")
    if record.tool_contract_hash != tool_hash:
        raise HTTPException(409, "local_tool_contract_changed")
    original_request = record.draft_json["original_request"]
    db.rollback()  # Do not hold a DB transaction or row lock during inference.
    public = SimpleNamespace(
        external_case_id=str(request_id),
        category="tool_single_step",
        title="Structured request lab",
        reference_context_json=None,
        expected_output_json=None,
        expected_tool_schema_json={},
        input_payload_json={
            "query": original_request,
            "instruction": "Use the registered local tool. Preserve explicitly requested values.",
            "available_tools": [public_descriptor(registry)],
        },
    )
    configuration = SimpleNamespace(
        runtime_config_json={
            "model": "qwen2.5:1.5b",
            "_case_timeout_ms": 120000,
            "tool_selection_prompt": "legacy",
        },
        generation_config_json={"temperature": 0, "max_tokens": 256},
        model_artifact=SimpleNamespace(artifact_name="qwen2.5:1.5b"),
    )
    adapter = LocalProposalAdapter()
    adapter.requests = []
    try:
        result = adapter.run_case(configuration=configuration, evaluation_case=public, seed=42)
    except Exception as exc:
        raise HTTPException(502, "local_proposal_generation_failed") from exc
    generation = {
        "model": "qwen2.5:1.5b",
        "adapter": "diagnostic_nullable_presence_tool",
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "latency_ms": result.end_to_end_latency_ms,
        "metadata": result.metadata,
        "requests": adapter.requests,
        "structured_constraints_sent_to_model": False,
        "usage_may_include_estimates": True,
    }
    return add_check(
        db,
        request_id,
        binding,
        actor,
        result.normalized_output,
        source="local_model_proposal",
        generation=generation,
    )


def execute(db, request_id, check_id, actor):
    record = get_owned(db, request_id, actor, lock=True)
    check = db.scalar(
        select(StructuredRequestCheck).where(
            StructuredRequestCheck.id == check_id, StructuredRequestCheck.request_id == record.id
        )
    )
    if check is None:
        raise HTTPException(404, "proposal_check_not_found")
    if check.execution_json is not None:
        return {**read_check(check), "replayed": True}
    if check.revision != record.revision or check.contract_hash != record.contract_hash:
        raise HTTPException(409, "stale_proposal_check")
    if proposal_digest(check.proposal) != check.proposal_hash:
        raise HTTPException(409, "proposal_integrity_failed")
    registry, tool_hash = registry_and_hash()
    verdict = verdict_for(record, check.proposal, registry, tool_hash)
    if not verdict["allowed"]:
        raise HTTPException(409, {"code": "execution_blocked", "reasons": verdict["reasons"]})
    record.executed_check_id = check.id
    event(record, "execution_claimed", actor, check_id=str(check.id))
    try:
        db.flush()  # Optimistic version claim precedes even the local handler invocation.
    except StaleDataError as exc:
        db.rollback()
        raise HTTPException(409, "concurrent_contract_change") from exc
    execution_case = SimpleNamespace(
        external_case_id=str(record.id),
        category="tool_single_step",
        expected_tool_schema_json={"tool_name": "create_ticket"},
        input_payload_json={},
    )
    trace = execute_tool_calls(
        execution_case,
        verdict["normalized_proposal"],
        registry,
        fault_scenario=ToolFaultScenario("normal"),
    ).to_dict()
    check.execution_json = {
        "executed_at": utcnow().isoformat(),
        "actor": actor.to_json(),
        "verdict": verdict,
        "trace": trace,
        "side_effect_mode": "simulated",
        "gate_evidence": False,
    }
    event(
        record, "simulated_execution", actor, check_id=str(check.id), successful=trace["successful"]
    )
    commit(db)
    return {**read_check(check), "replayed": False}
