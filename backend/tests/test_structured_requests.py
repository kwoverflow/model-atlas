import copy
import datetime as dt
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.orm.exc import StaleDataError

from app.api.v1.routes import structured_requests as routes
from app.models.structured_requests import StructuredRequest, StructuredRequestCheck
from app.schemas.structured_requests import StructuredTicketInput
from app.services import structured_requests as service
from app.services.structured_ticket_contract import compare_structured_ticket

BASE = "/api/v1/structured-requests"
HEADERS = {"x-model-atlas-lab-action": "1"}


def draft(priority=None):
    return {
        "original_request": "Automated test only: create a ticket for Original, priority low.",
        "query": "Original",
        "priority": priority or {"mode": "set", "value": "low"},
    }


def proposal(priority="low", query="Original", tool="create_ticket"):
    arguments = {"query": query}
    if priority is not None:
        arguments["priority"] = priority
    return json.dumps({"tool_name": tool, "arguments": arguments})


def binding(record):
    return {"expected_revision": record["revision"], "expected_hash": record["contract_hash"]}


def create(client, payload=None, *, confirmed=True, headers=HEADERS):
    response = client.post(BASE, json=payload or draft(), headers=headers)
    assert response.status_code == 201, response.text
    record = response.json()
    if confirmed:
        response = client.post(
            f"{BASE}/{record['id']}/confirm",
            json={**binding(record), "acknowledged": True},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        record = response.json()
    return record


def check(client, record, raw=None):
    response = client.post(
        f"{BASE}/{record['id']}/checks",
        json={**binding(record), "proposal": raw or proposal()},
        headers=HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()


def execute(client, record, checked):
    return client.post(f"{BASE}/{record['id']}/checks/{checked['id']}/execute", headers=HEADERS)


@pytest.mark.parametrize(
    "choice", [{"mode": "set", "value": p} for p in ("low", "normal", "high")] + [{"mode": "omit"}]
)
@pytest.mark.parametrize("generated", [None, "low", "normal", "high"])
def test_exact_value_and_omission_matrix(choice, generated):
    registry, _ = service.registry_and_hash()
    raw = proposal(generated)
    result = compare_structured_ticket(StructuredTicketInput(**draft(choice)), raw, registry)
    assert result["allowed"] == (
        generated == (choice["value"] if choice["mode"] == "set" else None)
    )
    assert not result["argument_repair"] and not result["model_inference"]
    assert json.loads(result["normalized_proposal"])["arguments"] == json.loads(raw)["arguments"]


@pytest.mark.parametrize(
    "raw",
    [
        proposal(query="Changed"),
        proposal(tool="lookup_policy"),
        '{"tool_name":"create_ticket","arguments":{"query":"Original","priority":"low","priority":"high"}}',
        '{"tool_name":"create_ticket","arguments":{"query":"Original","priority":null}}',
        '{"tool_name":"create_ticket","arguments":{"query":"Original","priority":NaN}}',
        '{"tool_name":"create_ticket","arguments":{"query":"Original","priority":"low","extra":true}}',
        "[]",
        "not JSON",
    ],
)
def test_invalid_or_wrong_calls_cannot_execute(client, raw, monkeypatch):
    record = create(client)
    checked = check(client, record, raw)
    assert not checked["verdict"]["allowed"]
    monkeypatch.setattr(
        service, "execute_tool_calls", lambda *a, **k: pytest.fail("handler reached")
    )
    assert execute(client, record, checked).status_code == 409


@pytest.mark.parametrize(
    "priority",
    [
        {"mode": "set"},
        {"mode": "set", "value": ""},
        {"mode": "omit", "value": "normal"},
        {"mode": "unresolved", "value": "low"},
    ],
)
def test_schema_has_no_implicit_default(client, priority):
    assert client.post(BASE, json=draft(priority), headers=HEADERS).status_code == 422


@pytest.mark.parametrize("acknowledged", [False, None, 1, "true"])
def test_confirmation_requires_explicit_boolean(client, acknowledged):
    record = create(client, confirmed=False)
    response = client.post(
        f"{BASE}/{record['id']}/confirm",
        headers=HEADERS,
        json={**binding(record), "acknowledged": acknowledged},
    )
    assert response.status_code == 422


def test_unresolved_and_unconfirmed_requests_never_execute(client):
    record = create(client, draft({"mode": "unresolved"}), confirmed=False)
    response = client.post(
        f"{BASE}/{record['id']}/confirm",
        headers=HEADERS,
        json={**binding(record), "acknowledged": True},
    )
    assert response.status_code == 422
    assert execute(client, record, check(client, record)).status_code == 409
    other = create(client, confirmed=False)
    assert execute(client, other, check(client, other)).status_code == 409
    assert (
        client.post(
            f"{BASE}/{other['id']}/generate", headers=HEADERS, json=binding(other)
        ).status_code
        == 409
    )


def test_lifecycle_is_persisted_idempotent_and_not_gate_evidence(client, monkeypatch):
    record = create(client)
    assert not record["confirmation"]["actor"]["identity_verified"]
    assert record["confirmation"]["authority"] == "local_unverified_assertion"
    first, second = check(client, record), check(client, record)
    calls = []
    original = service.execute_tool_calls

    def track(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "execute_tool_calls", track)
    result = execute(client, record, first)
    assert result.status_code == 200, result.text
    receipt = result.json()
    assert not receipt["replayed"]
    assert receipt["execution"]["trace"]["successful"]
    assert receipt["execution"]["trace"]["fault_scenario"]["handler_invocation_count"] == 1
    assert not receipt["execution"]["gate_evidence"]
    assert receipt["execution"]["side_effect_mode"] == "simulated"
    replay = execute(client, record, first).json()
    assert replay["replayed"] and replay["execution"] == receipt["execution"]
    assert execute(client, record, second).status_code == 409
    assert len(calls) == 1
    stored = client.get(f"{BASE}/{record['id']}").json()
    assert stored["executed_check_id"] == first["id"]
    assert [e["event"] for e in stored["events"]].count("simulated_execution") == 1
    assert client.get(BASE).json()[0]["id"] == record["id"]


def test_edit_invalidates_confirmation_and_old_proposals(client):
    record = create(client)
    checked = check(client, record)
    changed = draft({"mode": "omit"})
    response = client.put(
        f"{BASE}/{record['id']}", headers=HEADERS, json={**binding(record), "draft": changed}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["revision"] == 2 and updated["confirmation"] is None
    assert updated["contract_hash"] != record["contract_hash"]
    assert execute(client, record, checked).json()["detail"] == "stale_proposal_check"
    for suffix in ("confirm", "generate", "revoke", "checks"):
        payload = {**binding(record)}
        if suffix == "confirm":
            payload["acknowledged"] = True
        if suffix == "checks":
            payload["proposal"] = proposal()
        assert (
            client.post(
                f"{BASE}/{record['id']}/{suffix}", headers=HEADERS, json=payload
            ).status_code
            == 409
        )


@pytest.mark.parametrize(
    "invalidate", ["revoke", "expire", "tamper_proposal", "tamper_contract", "tool_hash"]
)
def test_execution_revalidates_saved_check(client, db_session, invalidate, monkeypatch):
    record = create(client)
    checked = check(client, record)
    assert checked["verdict"]["allowed"]
    row = db_session.get(StructuredRequest, UUID(record["id"]))
    if invalidate == "revoke":
        assert (
            client.post(
                f"{BASE}/{record['id']}/revoke", headers=HEADERS, json=binding(record)
            ).status_code
            == 200
        )
    elif invalidate == "expire":
        row.expires_at = service.utcnow() - dt.timedelta(seconds=1)
    elif invalidate == "tamper_proposal":
        db_session.get(StructuredRequestCheck, UUID(checked["id"])).proposal = proposal("high")
    elif invalidate == "tamper_contract":
        row.draft_json = draft({"mode": "set", "value": "high"})
    else:
        row.tool_contract_hash = "a" * 64
    db_session.commit()
    monkeypatch.setattr(
        service, "execute_tool_calls", lambda *a, **k: pytest.fail("handler reached")
    )
    assert execute(client, record, checked).status_code == 409


def test_concurrent_version_failure_precedes_handler(client, db_session, monkeypatch):
    record = create(client)
    checked = check(client, record)

    def conflict(*args, **kwargs):
        raise StaleDataError("another transaction won")

    monkeypatch.setattr(db_session, "flush", conflict)
    monkeypatch.setattr(
        service, "execute_tool_calls", lambda *a, **k: pytest.fail("handler reached")
    )
    assert execute(client, record, checked).json()["detail"] == "concurrent_contract_change"


def operator(subject, role="ML Engineer"):
    return {
        **HEADERS,
        "x-model-atlas-operator-id": subject,
        "x-model-atlas-operator-role": role,
        "x-model-atlas-identity-provider": "test",
    }


def test_authenticated_owner_isolation_and_server_actor(client):
    record = create(client, headers=operator("alice"))
    assert record["confirmation"]["actor"]["subject_id"] == "alice"
    assert record["confirmation"]["authority"] == "authenticated_operator_assertion"
    assert client.get(f"{BASE}/{record['id']}", headers=operator("bob")).status_code == 404
    assert client.get(BASE, headers=operator("bob")).json() == []
    assert (
        client.post(
            f"{BASE}/{record['id']}/revoke", headers=operator("bob"), json=binding(record)
        ).status_code
        == 404
    )
    assert client.get(BASE, headers=operator("alice", "Viewer")).status_code == 403
    assert (
        client.post(
            BASE, headers=operator("alice"), json={**draft(), "actor": {"subject_id": "bob"}}
        ).status_code
        == 422
    )


def test_write_origin_and_explicit_action(client, monkeypatch):
    assert client.post(BASE, json=draft()).status_code == 403
    assert (
        client.post(
            BASE, json=draft(), headers={**HEADERS, "origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    config = SimpleNamespace(oidc_jwt_enabled=True, oidc_browser_login_enabled=False)
    monkeypatch.setattr(routes, "get_settings", lambda: config)
    assert client.get(BASE).status_code == 401


def install_generation(monkeypatch, callback=None):
    seen = []

    def run(self, *, configuration, evaluation_case, seed):
        seen.append(copy.deepcopy(evaluation_case.input_payload_json))
        assert evaluation_case.expected_tool_schema_json == {}
        if callback:
            callback()
        return SimpleNamespace(
            normalized_output=proposal(),
            prompt_tokens=10,
            completion_tokens=5,
            end_to_end_latency_ms=4,
            metadata={},
        )

    monkeypatch.setattr(service.LocalProposalAdapter, "run_case", run)
    return seen


def test_user_constraints_are_not_sent_to_model(client, monkeypatch):
    payload = draft()
    payload["query"] = "PRIVATE-CONFIRMED-QUERY"
    record = create(client, payload)
    seen = install_generation(monkeypatch)
    response = client.post(f"{BASE}/{record['id']}/generate", headers=HEADERS, json=binding(record))
    assert response.status_code == 201, response.text
    checked = response.json()
    assert checked["source"] == "local_model_proposal" and not checked["verdict"]["allowed"]
    assert not checked["generation"]["structured_constraints_sent_to_model"]
    assert "PRIVATE-CONFIRMED-QUERY" not in json.dumps(seen)
    assert record["contract_hash"] not in json.dumps(seen)
    assert seen[0]["query"] == payload["original_request"]
    assert [t["tool_name"] for t in seen[0]["available_tools"]] == ["create_ticket"]


@pytest.mark.parametrize("change", ["edit", "revoke"])
def test_inflight_model_response_cannot_bypass_changed_contract(
    client, db_session, monkeypatch, change
):
    record = create(client)

    def mutate():
        row = db_session.get(StructuredRequest, UUID(record["id"]))
        if change == "edit":
            row.revision += 1
            row.contract_hash = service.contract_hash(row)
        else:
            row.status = "revoked"
            row.confirmation_json = None
        db_session.commit()

    install_generation(monkeypatch, mutate)
    response = client.post(f"{BASE}/{record['id']}/generate", headers=HEADERS, json=binding(record))
    if change == "edit":
        assert response.status_code == 409
    else:
        assert response.status_code == 201
        assert "request_not_confirmed" in response.json()["verdict"]["reasons"]


def test_local_generation_failure_creates_no_proposal(client, monkeypatch):
    record = create(client)

    def fail(*args, **kwargs):
        raise TimeoutError("local model unavailable")

    monkeypatch.setattr(service.LocalProposalAdapter, "run_case", fail)
    assert (
        client.post(
            f"{BASE}/{record['id']}/generate", headers=HEADERS, json=binding(record)
        ).status_code
        == 502
    )
    assert client.get(f"{BASE}/{record['id']}").json()["checks"] == []


def test_changed_handler_source_is_not_supported(client, monkeypatch):
    monkeypatch.setattr(service, "HANDLER_HASH", "0" * 64)
    assert (
        client.post(BASE, headers=HEADERS, json=draft()).json()["detail"]
        == "local_handler_source_changed"
    )


def test_local_adapter_ignores_external_url_and_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "https://external.example")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "private-test-key")
    adapter = service.LocalProposalAdapter()
    config = SimpleNamespace(runtime_config_json={"base_url": "https://external.example"})
    assert adapter._candidate_base_urls(config) == [
        "http://ollama:11434",
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    ]
    assert adapter._headers(config) == {"content-type": "application/json"}
