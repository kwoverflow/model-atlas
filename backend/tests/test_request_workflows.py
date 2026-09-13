import copy
import json
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from app.models.request_workflows import RequestWorkflowAttempt
from app.models.structured_requests import StructuredRequest
from app.services import structured_requests as lab
from app.services.request_workflow_catalog import cases, catalog
from app.services.structured_ticket_contract import digest, proposal_digest

BASE = "/api/v1/request-workflows"
LAB = "/api/v1/structured-requests"
HEADERS = {"x-model-atlas-lab-action": "1"}


def api(client, path, method="GET", body=None, status=200, headers=HEADERS):
    response = client.request(method, path, json=body, headers=headers)
    assert response.status_code == status, response.text
    return response.json()


def start(client, case_id="WF-01", source="automated_qa", headers=HEADERS):
    return api(
        client, BASE + "/attempts", "POST", {"task_id": case_id, "source": source}, 201, headers
    )


def path(row):
    return f"{BASE}/attempts/{row['id']}"


def expected(row):
    return next(c["expected"] for c in cases() if c["id"] == row["task"]["id"])


def draft_for(row):
    value = expected(row)
    return {
        "original_request": row["task"]["request"],
        "query": value["query"],
        "priority": value["priority"],
    }


def bind(request):
    return {"expected_revision": request["revision"], "expected_hash": request["contract_hash"]}


def create(client, row, draft=None):
    return api(
        client,
        path(row) + "/request",
        "POST",
        {
            "expected_revision": row["revision"],
            "draft": draft or draft_for(row),
        },
        201,
    )


def run_contract(client, request, arguments=None):
    request = api(
        client, f"{LAB}/{request['id']}/confirm", "POST", {**bind(request), "acknowledged": True}
    )
    if arguments is None:
        arguments = {"query": request["draft"]["query"]}
        if request["draft"]["priority"]["mode"] == "set":
            arguments["priority"] = request["draft"]["priority"]["value"]
    check = api(
        client,
        f"{LAB}/{request['id']}/checks",
        "POST",
        {
            **bind(request),
            "proposal": json.dumps({"tool_name": "create_ticket", "arguments": arguments}),
        },
        201,
    )
    if check["verdict"]["allowed"]:
        api(client, f"{LAB}/{request['id']}/checks/{check['id']}/execute", "POST")
    return check


def finish_payload(row, **overrides):
    return {
        "expected_revision": row["revision"],
        "request_state_hash": row["request_state_hash"],
        "disposition": "finished",
        "assistance": "not_applicable",
        "acknowledged": True,
        **overrides,
    }


def finish(client, row, **overrides):
    latest = api(client, path(row))
    return api(client, path(row) + "/finish", "POST", finish_payload(latest, **overrides))


def test_catalog_withholds_keys_and_is_stable(client):
    public = api(client, BASE + "/catalog")
    assert len(public["tasks"]) == 10 and public["hash"] == catalog()["hash"]
    assert "expected" not in json.dumps(public)
    row = start(client)
    assert row["request"] is None and "expected" not in json.dumps(row)
    assert not row["gate_evidence"] and not row["human_review_verified"]


@pytest.mark.parametrize("task_id", [f"WF-{i:02d}" for i in range(1, 11)])
def test_full_workflow_using_actual_contract_service(client, monkeypatch, task_id):
    monkeypatch.setattr(
        lab.LocalProposalAdapter, "run_case", lambda *a, **k: pytest.fail("unexpected inference")
    )
    row = start(client, task_id)
    if expected(row)["decision"] == "execute":
        request = create(client, row)
        check = run_contract(client, request)
        assert check["verdict"]["allowed"]
        result = finish(client, row)["result"]
        assert result["metrics"]["manual_proposal_count"] == 1
        assert result["metrics"]["execution_count"] == 1
    else:
        result = finish(client, row, disposition="clarification_requested")["result"]
        assert result["request_snapshot"] is None
    assert result["assessment"] == "matches_task"
    assert result["metrics"]["model_proposal_count"] == 0
    assert not result["gate_evidence"] and not result["human_review_verified"]
    without_hash = {k: v for k, v in result.items() if k != "evidence_hash"}
    assert result["evidence_hash"] == digest(without_hash)


def test_wrong_confirmation_executes_but_is_never_scored_as_success(client):
    row = start(client)
    wrong = {**draft_for(row), "priority": {"mode": "set", "value": "high"}}
    request = create(client, row, wrong)
    run_contract(client, request)
    result = finish(client, row)["result"]
    assert result["assessment"] == "does_not_match_task"
    assert result["mismatches"] == ["priority", "execution_arguments"]
    assert result["metrics"]["execution_count"] == 1 and result["unsafe_execution_ids"]


def test_previous_bad_execution_survives_correction(client):
    row = start(client)
    request = create(client, row, {**draft_for(row), "query": "wrong"})
    bad = run_contract(client, request)
    request = api(client, f"{LAB}/{request['id']}")
    fixed = api(client, f"{LAB}/{request['id']}", "PUT", {**bind(request), "draft": draft_for(row)})
    run_contract(client, fixed)
    result = finish(client, row)["result"]
    assert result["mismatches"] == ["execution_arguments"]
    assert result["unsafe_execution_ids"] == [bad["id"]]
    assert result["metrics"]["execution_count"] == 2
    assert result["metrics"]["saved_revision_count_after_first"] == 1


def test_blocked_proposal_is_visible_and_cannot_be_reported_as_execution_success(client):
    row = start(client)
    request = create(client, row)
    check = run_contract(client, request, {"query": "wrong", "priority": "low"})
    assert not check["verdict"]["allowed"]
    result = finish(client, row)["result"]
    assert result["assessment"] == "does_not_match_task"
    assert result["mismatches"] == ["successful_current_execution"]
    assert result["metrics"]["blocked_proposal_count"] == 1


def test_end_requires_fresh_full_state_not_only_contract_revision(client):
    row = start(client)
    request = create(client, row)
    stale = api(client, path(row))
    run_contract(client, request)
    error = api(client, path(row) + "/finish", "POST", finish_payload(stale), 409)
    assert error["detail"] == "stale_workflow_request_state"


def test_submitted_snapshot_is_immutable_and_replay_is_exact(client):
    row = start(client)
    request = create(client, row)
    run_contract(client, request)
    current = api(client, path(row))
    payload = finish_payload(current)
    first = api(client, path(row) + "/finish", "POST", payload)
    replay = api(client, path(row) + "/finish", "POST", payload)
    assert replay["replayed"] and replay["result"] == first["result"]
    api(client, path(row) + "/finish", "POST", {**payload, "note": "changed"}, 409)
    request = api(client, f"{LAB}/{request['id']}")
    api(
        client,
        f"{LAB}/{request['id']}",
        "PUT",
        {**bind(request), "draft": {**draft_for(row), "query": "after submission"}},
    )
    assert api(client, path(row))["result"] == first["result"]
    api(client, path(row) + "/help", "POST", {"expected_revision": first["revision"]}, 409)


@pytest.mark.parametrize("disposition", ["finished", "clarification_requested", "abandoned"])
def test_empty_and_abandoned_attempts_are_not_silently_passed(client, disposition):
    row = start(client)
    if disposition == "finished":
        api(client, path(row) + "/finish", "POST", finish_payload(row), 422)
    else:
        result = finish(client, row, disposition=disposition, note="stopped")["result"]
        assert result["assessment"] == (
            "abandoned" if disposition == "abandoned" else "does_not_match_task"
        )


def test_assistance_separation_and_all_rows_summary_not_page_count(client):
    row = start(client, "WF-09", "participant_self_report")
    row = api(client, path(row) + "/help", "POST", {"expected_revision": 0})
    assert row["help_count"] == 1 and len(row["help_events"]) == 1
    api(
        client,
        path(row) + "/finish",
        "POST",
        finish_payload(row, disposition="clarification_requested", assistance="none_reported"),
        422,
    )
    finish(client, row, disposition="clarification_requested", assistance="received")
    qa = start(client, "WF-09")
    finish(client, qa, disposition="clarification_requested")
    open_row = start(client)
    assert open_row["ended_at"] is None
    groups = api(client, BASE + "/summary")["groups"]
    assert sum(g["total"] for g in groups) == 3
    assert len(groups) == 3
    assert len(api(client, BASE + "/attempts?limit=1&offset=1")) == 1
    assert sum(g["open"] for g in groups) == 1


@pytest.mark.parametrize(
    "source,assistance",
    [("automated_qa", "received"), ("participant_self_report", "not_applicable")],
)
def test_provenance_cannot_be_promoted(client, source, assistance):
    row = start(client, "WF-09", source)
    api(
        client,
        path(row) + "/finish",
        "POST",
        finish_payload(row, disposition="clarification_requested", assistance=assistance),
        422,
    )
    api(
        client,
        path(row) + "/finish",
        "POST",
        {**finish_payload(row), "source": "verified_human"},
        422,
    )


def test_contract_creation_is_atomic_and_only_one_contract_can_be_linked(
    client, db_session, monkeypatch
):
    row = start(client)

    def conflict():
        raise StaleDataError("simulated concurrent workflow update")

    with monkeypatch.context() as patch:
        patch.setattr(db_session, "commit", conflict)
        api(
            client,
            path(row) + "/request",
            "POST",
            {"expected_revision": 0, "draft": draft_for(row)},
            409,
        )
    assert db_session.scalar(select(func.count()).select_from(StructuredRequest)) == 0
    request = create(client, row)
    current = api(client, path(row))
    assert current["request_id"] == request["id"]
    api(
        client,
        path(row) + "/request",
        "POST",
        {"expected_revision": current["revision"], "draft": draft_for(row)},
        409,
    )


def test_more_than_twenty_checks_are_frozen(client):
    row = start(client)
    request = create(client, row)
    for _ in range(21):
        api(
            client,
            f"{LAB}/{request['id']}/checks",
            "POST",
            {**bind(request), "proposal": "not json"},
            201,
        )
    result = finish(client, row)["result"]
    assert result["metrics"]["proposal_count"] == 21
    assert len(result["request_snapshot"]["checks"]) == 21


def test_original_request_cannot_be_replaced_at_creation(client):
    row = start(client)
    draft = {**draft_for(row), "original_request": "another request"}
    api(client, path(row) + "/request", "POST", {"expected_revision": 0, "draft": draft}, 422)


def test_owner_role_origin_and_acknowledgment_boundaries(client):
    def headers(name):
        return {
            **HEADERS,
            "x-model-atlas-operator-id": name,
            "x-model-atlas-operator-role": "ML Engineer",
        }

    alice, bob = headers("alice"), headers("bob")
    row = start(client, "WF-09", headers=alice)
    api(client, path(row), headers=bob, status=404)
    assert api(client, BASE + "/attempts", headers=bob) == []
    assert api(client, BASE + "/summary", headers=bob)["groups"] == []
    api(
        client,
        path(row) + "/finish",
        "POST",
        finish_payload(row, disposition="clarification_requested"),
        404,
        bob,
    )
    api(client, BASE + "/attempts", "POST", {"task_id": "WF-01", "source": "automated_qa"}, 403, {})
    api(
        client,
        BASE + "/attempts",
        "POST",
        {"task_id": "WF-01", "source": "automated_qa"},
        403,
        {**HEADERS, "origin": "https://untrusted.example"},
    )
    api(client, path(row) + "/finish", "POST", finish_payload(row, acknowledged=False), 422, alice)
    api(client, path(row) + "/finish", "POST", finish_payload(row, acknowledged="true"), 422, alice)


def test_frozen_task_not_new_catalog_used_for_scoring(client, monkeypatch):
    row = start(client)
    request = create(client, row)
    run_contract(client, request)
    monkeypatch.setattr(
        "app.services.request_workflows.scenario", lambda _: pytest.fail("catalog reread")
    )
    assert finish(client, row)["result"]["assessment"] == "matches_task"


def test_aggregate_pack_versions_are_separate(client, db_session):
    a, b = start(client), start(client)
    row = db_session.get(RequestWorkflowAttempt, UUID(b["id"]))
    changed = copy.deepcopy(row.scenario_json)
    changed["task"]["pack_hash"] = "b" * 64
    row.scenario_json = changed
    db_session.commit()
    assert a["task"]["pack_hash"] != "b" * 64
    assert len(api(client, BASE + "/summary")["groups"]) == 2


def test_export_canonical_bytes_survive_browser_numeric_serialization(client, db_session):
    row = start(client, "WF-09")
    finish(client, row, disposition="clarification_requested")
    stored = db_session.get(RequestWorkflowAttempt, UUID(row["id"]))
    value = copy.deepcopy(stored.result_json)
    value["numeric_roundtrip_test"] = [0.0, 1.0, 0.125, 1e-7]
    value["evidence_hash"] = digest({k: v for k, v in value.items() if k != "evidence_hash"})
    stored.result_json = value
    db_session.commit()
    exported = api(client, path(row))
    assert exported["evidence"]["verified"]
    # Browser JSON export removes .0 from numeric values but preserves the canonical string.
    roundtrip = json.loads(
        json.dumps(exported),
        parse_float=lambda s: int(float(s)) if float(s).is_integer() else float(s),
    )
    assert proposal_digest(roundtrip["evidence"]["canonical_json"]) == value["evidence_hash"]
    decoded = json.loads(roundtrip["evidence"]["canonical_json"])
    assert decoded == {k: v for k, v in roundtrip["result"].items() if k != "evidence_hash"}
    assert db_session.get(RequestWorkflowAttempt, UUID(row["id"])).result_json == value


def test_read_reports_evidence_tampering_without_rehashing_or_promoting(client, db_session):
    row = start(client, "WF-09")
    finished = finish(client, row, disposition="clarification_requested")
    stored = db_session.get(RequestWorkflowAttempt, UUID(row["id"]))
    value = copy.deepcopy(stored.result_json)
    value["metrics"]["execution_count"] = 100
    stored.result_json = value
    db_session.commit()
    readback = api(client, path(row))
    assert not readback["evidence"]["verified"]
    assert readback["result"]["evidence_hash"] == finished["result"]["evidence_hash"]
    assert not readback["gate_evidence"]
