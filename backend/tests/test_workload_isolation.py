from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.schemas import IsolationPreflightCreate
from app.services.workload_isolation import assert_isolation_preflight
from app.validators import DomainValidationError


def test_isolation_registry_and_preflight_enforce_network_credentials_and_tools(
    client: TestClient,
) -> None:
    registry = client.get("/api/v1/isolation/policies")
    assert registry.status_code == 200
    assert registry.json()["policy_count"] == 3
    assert {
        policy["policy_id"] for policy in registry.json()["policies"]
    } == {
        "tool-offline-strict",
        "rag-readonly-internal",
        "tool-rag-internal-authenticated",
    }

    allowed = client.post(
        "/api/v1/isolation/preflight",
        json={
            "policy_id": "tool-offline-strict",
            "workload_kind": "tool",
            "requested_tools": ["lookup_policy", "create_ticket"],
            "write_paths": ["/tmp/model-atlas/result.json"],
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["allowed"] is True
    assert allowed.json()["violations"] == []

    denied = client.post(
        "/api/v1/isolation/preflight",
        json={
            "policy_id": "tool-offline-strict",
            "workload_kind": "tool",
            "requested_tools": ["shell_exec"],
            "network_hosts": ["https://api.external.example"],
            "secret_envs": ["AWS_SECRET_ACCESS_KEY"],
            "write_paths": ["/data/rag/corpus.json"],
            "subprocess_requested": True,
        },
    )
    assert denied.status_code == 200
    body = denied.json()
    assert body["allowed"] is False
    assert len(body["violations"]) == 5
    assert any("tools are not allowed" in item for item in body["violations"])
    assert any("network access is disabled" in item for item in body["violations"])
    assert any("credentials are disabled" in item for item in body["violations"])
    assert any("outside writable roots" in item for item in body["violations"])
    assert any("subprocess" in item for item in body["violations"])

    with pytest.raises(DomainValidationError, match="preflight denied"):
        assert_isolation_preflight(
            IsolationPreflightCreate(
                policy_id="tool-offline-strict",
                workload_kind="tool",
                network_hosts=["api.external.example"],
            )
        )


def test_rag_internal_policy_allows_only_declared_runtime_and_paths(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/isolation/preflight",
        json={
            "policy_id": "rag-readonly-internal",
            "workload_kind": "rag",
            "network_hosts": ["http://ollama:11434/v1"],
            "read_paths": ["/data/rag/corpus.json"],
            "write_paths": ["/tmp/model-atlas/report.json"],
        },
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is True

    traversal = client.post(
        "/api/v1/isolation/preflight",
        json={
            "policy_id": "rag-readonly-internal",
            "workload_kind": "rag",
            "read_paths": ["/data/rag/../../etc/passwd"],
        },
    )
    assert traversal.status_code == 422
    assert "parent traversal" in traversal.text
