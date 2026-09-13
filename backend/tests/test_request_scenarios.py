import datetime as dt
import json
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from app.models.request_scenarios import RequestScenarioRun, RequestStudyAttempt
from app.models.structured_requests import StructuredRequest, StructuredRequestCheck
from app.services import request_scenario_runner as runner
from app.services.request_scenario_catalog import catalog, pack

BASE = "/api/v1/request-scenarios"
HEADERS = {"x-model-atlas-lab-action": "1"}


@pytest.fixture(scope="module")
def report():
    return runner.run_scenarios()


@pytest.mark.parametrize("case_id", [f"SRC-{i:02d}" for i in range(1, 16)])
def test_fixed_scenario_observations(report, case_id):
    row = next(r for r in report["rows"] if r["id"] == case_id)
    assert row["outcome"] == ("known_limitation" if case_id == "SRC-15" else "passed")
    assert all(row["expectations"].values())


def test_misconfirmation_is_visible_not_counted_as_pass(report):
    assert report["counts"] == {"passed": 14, "known_limitation": 1, "regression": 0, "error": 0}
    row = report["rows"][-1]
    assert row["fixture"]["draft"]["priority"]["value"] == "high"
    assert row["fixture"]["study_answer"]["priority"]["value"] == "low"
    assert row["observed"]["handler_invocations"] == 1
    assert row["outcome"] == "known_limitation"
    assert report["model_calls"] == 0 and not report["human_review"] and not report["gate_evidence"]
    assert len(report["implementation_hashes"]) == 8


def test_catalog_is_stable_and_snapshots_do_not_mutate_fixture():
    first, second = pack(), pack()
    assert first["hash"] == second["hash"]
    snapshot = first["cases"][0].snapshot()
    snapshot["draft"]["query"] = "changed"
    assert pack()["hash"] == second["hash"]


def test_regression_and_runtime_error_are_not_silently_passed(monkeypatch):
    original = runner.observe

    def changed(db, case):
        if case.id == "SRC-01":
            raise RuntimeError("fixture infrastructure failure")
        return original(db, case)

    monkeypatch.setattr(runner, "observe", changed)
    monkeypatch.setattr(runner.lab, "revoke", lambda *a, **k: None)
    result = runner.run_scenarios()
    assert result["status"] == "failed"
    assert result["counts"]["error"] == 1
    assert result["counts"]["regression"] == 1
    revoked = next(r for r in result["rows"] if r["id"] == "SRC-11")
    assert not revoked["expectations"]["handler_invocations"]


def test_runner_api_is_isolated_and_never_calls_model(client, db_session, monkeypatch):
    monkeypatch.setattr(
        runner.lab.LocalProposalAdapter, "run_case", lambda *a, **k: pytest.fail("model called")
    )
    response = client.post(f"{BASE}/runs", headers=HEADERS)
    assert response.status_code == 201, response.text
    assert response.json()["report"]["database"] == "isolated_in_memory_sqlite"
    for model in (StructuredRequest, StructuredRequestCheck, RequestStudyAttempt):
        assert db_session.scalar(select(func.count()).select_from(model)) == 0
    assert db_session.scalar(select(func.count()).select_from(RequestScenarioRun)) == 1
    assert client.get(f"{BASE}/runs").json()[0]["id"] == response.json()["id"]


def start(client, case_id="SRC-01", source="automated_qa", headers=HEADERS):
    response = client.post(
        f"{BASE}/studies", headers=headers, json={"scenario_id": case_id, "source": source}
    )
    assert response.status_code == 201, response.text
    return response.json()


def answer(case_id="SRC-01"):
    return next(c.study_answer for c in catalog() if c.id == case_id)


def save(client, record, value=None):
    response = client.put(
        f"{BASE}/studies/{record['id']}",
        headers=HEADERS,
        json={
            "expected_revision": record["revision"],
            "answer": value or answer(record["task"]["id"]),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit_payload(record):
    return {
        "expected_revision": record["revision"],
        "expected_hash": record["answer_hash"],
        "acknowledged": True,
    }


def submit(client, record, payload=None):
    return client.post(
        f"{BASE}/studies/{record['id']}/submit",
        headers=HEADERS,
        json=payload or submit_payload(record),
    )


def test_study_answer_key_is_withheld_until_submission(client):
    catalog_data = client.get(f"{BASE}/catalog").json()
    assert catalog_data["count"] == 15 and len(catalog_data["tasks"]) == 7
    assert all(
        set(t) == {"id", "request", "pack_version", "pack_hash"} for t in catalog_data["tasks"]
    )
    initial = start(client)
    assert "expected" not in json.dumps(initial) and initial["answer"] is None
    saved = save(client, initial)
    assert "expected" not in json.dumps(saved)
    result = submit(client, saved).json()
    assert result["result"]["expected"] == answer()
    assert result["result"]["matches_scenario_key"]


@pytest.mark.parametrize("source", ["automated_qa", "participant_self_report"])
def test_source_is_immutable_and_never_becomes_verified_review(client, source):
    record = save(client, start(client, source=source))
    response = submit(client, record)
    assert response.status_code == 200
    result = response.json()
    assert result["source"] == result["result"]["source"] == source
    assert not result["human_review_verified"] and not result["gate_evidence"]
    assert not result["result"]["human_review_verified"] and not result["result"]["gate_evidence"]
    assert (
        client.put(
            f"{BASE}/studies/{record['id']}",
            headers=HEADERS,
            json={"expected_revision": 1, "answer": answer(), "source": "participant_self_report"},
        ).status_code
        == 422
    )


def test_saved_corrections_and_elapsed_wall_time_are_precise(client, db_session):
    record = start(client)
    row = db_session.get(RequestStudyAttempt, UUID(record["id"]))
    row.started_at -= dt.timedelta(seconds=30)
    db_session.commit()
    first = save(client, record)
    assert first["correction_count"] == 0 and first["revision"] == 1
    repeated = save(client, first)
    assert repeated["revision"] == 1 and repeated["correction_count"] == 0
    wrong = {**answer(), "priority": {"mode": "set", "value": "high"}}
    second = save(client, first, wrong)
    assert second["revision"] == 2 and second["correction_count"] == 1
    assert second["answer_hash"] != first["answer_hash"]
    assert submit(client, first).status_code == 409
    response = submit(client, second).json()
    assert not response["result"]["matches_scenario_key"]
    assert response["result"]["mismatches"] == ["priority"]
    assert response["result"]["elapsed_seconds"] >= 30
    assert response["result"]["correction_count"] == 1
    replay = submit(client, second).json()
    assert replay["replayed"] and replay["result"] == response["result"]
    assert (
        client.put(
            f"{BASE}/studies/{record['id']}",
            headers=HEADERS,
            json={"expected_revision": 2, "answer": answer()},
        ).status_code
        == 409
    )


def test_conflict_requires_clarification_in_study_key(client):
    record = save(client, start(client, "SRC-09"))
    assert record["answer"] == {
        "decision": "clarify",
        "query": "",
        "priority": {"mode": "unresolved"},
    }
    assert submit(client, record).json()["result"]["matches_scenario_key"]


@pytest.mark.parametrize(
    "invalid",
    [
        {"decision": "confirm", "query": "x", "priority": {"mode": "unresolved"}},
        {"decision": "clarify", "query": "x", "priority": {"mode": "unresolved"}},
        {"decision": "confirm", "query": "x", "priority": {"mode": "omit", "value": "normal"}},
    ],
)
def test_invalid_study_inputs_are_rejected(client, invalid):
    record = start(client)
    assert (
        client.put(
            f"{BASE}/studies/{record['id']}",
            headers=HEADERS,
            json={"expected_revision": 0, "answer": invalid},
        ).status_code
        == 422
    )


@pytest.mark.parametrize("ack", [False, 1, "true", None])
def test_submission_requires_strict_acknowledgment(client, ack):
    record = save(client, start(client))
    assert (
        submit(client, record, {**submit_payload(record), "acknowledged": ack}).status_code == 422
    )


def test_stale_version_and_tampered_answer_fail_closed(client, db_session):
    initial = start(client)
    saved = save(client, initial)
    assert (
        client.put(
            f"{BASE}/studies/{initial['id']}",
            headers=HEADERS,
            json={"expected_revision": 0, "answer": answer()},
        ).status_code
        == 409
    )
    row = db_session.get(RequestStudyAttempt, UUID(initial["id"]))
    row.answer_json = {**row.answer_json, "query": "tampered"}
    db_session.commit()
    assert submit(client, saved).json()["detail"] == "study_answer_integrity_failed"


def test_study_version_conflict_returns_409(client, db_session, monkeypatch):
    record = start(client)

    def conflict():
        raise StaleDataError("another writer")

    monkeypatch.setattr(db_session, "commit", conflict)
    assert (
        client.put(
            f"{BASE}/studies/{record['id']}",
            headers=HEADERS,
            json={"expected_revision": 0, "answer": answer()},
        ).status_code
        == 409
    )


def operator(subject):
    return {
        **HEADERS,
        "x-model-atlas-operator-id": subject,
        "x-model-atlas-operator-role": "ML Engineer",
    }


def test_owner_and_action_boundaries(client):
    record = start(client, headers=operator("alice"))
    assert client.get(f"{BASE}/studies/{record['id']}", headers=operator("bob")).status_code == 404
    assert client.get(f"{BASE}/studies", headers=operator("bob")).json() == []
    assert (
        client.put(
            f"{BASE}/studies/{record['id']}",
            headers=operator("bob"),
            json={"expected_revision": 0, "answer": answer()},
        ).status_code
        == 404
    )
    assert client.post(f"{BASE}/runs").status_code == 403
    assert (
        client.post(
            f"{BASE}/runs", headers={**HEADERS, "origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{BASE}/studies",
            headers=HEADERS,
            json={"scenario_id": "SRC-01", "source": "verified_human"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"{BASE}/studies",
            headers=HEADERS,
            json={"scenario_id": "SRC-12", "source": "automated_qa"},
        ).status_code
        == 404
    )
