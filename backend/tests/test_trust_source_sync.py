from __future__ import annotations

import datetime as dt
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes import trust_registry as trust_registry_routes
from app.models import EvidenceTrustRoot, EvidenceTrustSource, EvidenceTrustSourceSync
from app.services.trust_registry import (
    evidence_trust_root_read,
    evidence_trust_source_read,
)
from app.services.trust_source_sync import FetchedJwksPayload, TrustSourceFetchError


def _operator_headers(subject: str = "trust-source-governor") -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": subject,
        "x-model-atlas-operator-name": subject.replace("-", " ").title(),
        "x-model-atlas-operator-role": "Model Governance",
    }


def _public_jwk(key_id: str) -> tuple[Any, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": key_id, "alg": "RS256", "use": "sig"})
    return private_key, jwk


def _fetched(payload: dict[str, Any]) -> FetchedJwksPayload:
    return FetchedJwksPayload(
        payload=payload,
        http_status=200,
        fetched_at=dt.datetime.now(dt.UTC),
    )


def test_trust_source_preview_apply_rotation_and_freshness(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        trust_registry_routes.settings,
        "trust_source_allowed_hosts",
        ["keys.example.test"],
    )
    monkeypatch.setattr(
        trust_registry_routes.settings,
        "trust_source_allow_insecure_http",
        False,
    )
    _old_private_key, old_jwk = _public_jwk("publisher-2026")
    state = {"payload": {"keys": [old_jwk]}}

    def fetcher(*args: Any, **kwargs: Any) -> FetchedJwksPayload:
        return _fetched(state["payload"])

    monkeypatch.setattr(trust_registry_routes, "fetch_remote_jwks", fetcher)
    source_response = client.post(
        "/api/v1/trust-registry/sources",
        headers=_operator_headers(),
        json={
            "name": "External publisher registry",
            "source_kind": "jwks",
            "purpose": "model_publisher",
            "issuer": "external-test-publisher",
            "trust_tier": "external",
            "endpoint_url": "https://keys.example.test/publisher/jwks.json",
            "allowed_algorithms": ["RS256"],
            "freshness_seconds": 300,
        },
    )
    assert source_response.status_code == 201, source_response.text
    source = source_response.json()["trust_source"]
    assert source["status"] == "unsynced"
    assert source["production_eligible"] is False

    preview_response = client.post(
        f"/api/v1/trust-registry/sources/{source['id']}/sync",
        headers=_operator_headers(),
        json={"mode": "preview"},
    )
    assert preview_response.status_code == 201, preview_response.text
    preview = preview_response.json()
    assert preview["sync"]["status"] == "succeeded"
    assert preview["sync"]["trigger"] == "manual"
    assert preview["sync"]["schedule_id"] is None
    assert preview["sync"]["job_id"] is None
    assert preview["sync"]["candidate_count"] == 1
    assert preview["sync"]["imported_count"] == 0
    assert preview["trust_source"]["status"] == "unsynced"
    assert db_session.scalar(select(EvidenceTrustRoot.id)) is None

    apply_response = client.post(
        f"/api/v1/trust-registry/sources/{source['id']}/sync",
        headers=_operator_headers(),
        json={"mode": "apply"},
    )
    assert apply_response.status_code == 201, apply_response.text
    applied = apply_response.json()
    assert applied["sync"]["imported_count"] == 1
    assert applied["trust_source"]["status"] == "healthy"
    assert applied["trust_source"]["production_eligible"] is True

    roots = client.get("/api/v1/trust-registry/roots").json()
    old_root = next(root for root in roots if root["key_id"] == "publisher-2026")
    assert old_root["trust_source_id"] == source["id"]
    assert old_root["source_key_current"] is True
    assert old_root["production_eligible"] is True

    def unavailable_after_apply(*args: Any, **kwargs: Any) -> FetchedJwksPayload:
        raise TrustSourceFetchError("transport_error", "publisher registry unavailable")

    monkeypatch.setattr(
        trust_registry_routes,
        "fetch_remote_jwks",
        unavailable_after_apply,
    )
    degraded_response = client.post(
        f"/api/v1/trust-registry/sources/{source['id']}/sync",
        headers=_operator_headers(),
        json={"mode": "apply"},
    )
    assert degraded_response.status_code == 201, degraded_response.text
    assert degraded_response.json()["sync"]["status"] == "failed"
    assert degraded_response.json()["trust_source"]["status"] == "degraded"
    old_root = next(
        root
        for root in client.get("/api/v1/trust-registry/roots").json()
        if root["key_id"] == "publisher-2026"
    )
    assert old_root["production_eligible"] is True
    degraded_metrics = client.get("/api/v1/operations/metrics").json()
    degraded_samples = {
        sample["name"]: sample["value"] for sample in degraded_metrics["samples"]
    }
    assert degraded_samples["model_atlas_trust_source_degraded"] == 1
    assert any(
        alert["key"] == "trust_source_degraded"
        for alert in degraded_metrics["alerts"]
    )

    monkeypatch.setattr(trust_registry_routes, "fetch_remote_jwks", fetcher)

    _new_private_key, new_jwk = _public_jwk("publisher-2027")
    state["payload"] = {"keys": [new_jwk]}
    rotation_response = client.post(
        f"/api/v1/trust-registry/sources/{source['id']}/sync",
        headers=_operator_headers(),
        json={"mode": "apply", "notes": "publisher rotation snapshot"},
    )
    assert rotation_response.status_code == 201, rotation_response.text
    assert rotation_response.json()["sync"]["imported_count"] == 1

    roots = client.get("/api/v1/trust-registry/roots").json()
    old_root = next(root for root in roots if root["key_id"] == "publisher-2026")
    new_root = next(root for root in roots if root["key_id"] == "publisher-2027")
    assert old_root["source_key_current"] is False
    assert old_root["production_eligible"] is False
    assert new_root["source_key_current"] is True
    assert new_root["production_eligible"] is True

    source_record = db_session.get(EvidenceTrustSource, source["id"])
    new_root_record = db_session.get(EvidenceTrustRoot, new_root["id"])
    assert source_record is not None
    assert new_root_record is not None
    latest_apply = db_session.scalar(
        select(EvidenceTrustSourceSync)
        .where(EvidenceTrustSourceSync.trust_source_id == source_record.id)
        .where(EvidenceTrustSourceSync.mode == "apply")
        .where(EvidenceTrustSourceSync.status == "succeeded")
        .order_by(
            EvidenceTrustSourceSync.completed_at.desc(),
            EvidenceTrustSourceSync.created_at.desc(),
        )
        .limit(1)
    )
    assert latest_apply is not None
    stale_at = latest_apply.completed_at + dt.timedelta(seconds=301)
    assert evidence_trust_source_read(
        db_session,
        source_record,
        now=stale_at,
    ).status == "stale"
    assert evidence_trust_root_read(
        db_session,
        new_root_record,
        now=stale_at,
    ).production_eligible is False


def test_trust_source_failures_are_audited_and_do_not_partially_apply(
    client: TestClient,
    db_session: Session,
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        trust_registry_routes.settings,
        "trust_source_allowed_hosts",
        ["fixture.internal"],
    )
    monkeypatch.setattr(
        trust_registry_routes.settings,
        "trust_source_allow_insecure_http",
        True,
    )
    rejected_source = client.post(
        "/api/v1/trust-registry/sources",
        headers=_operator_headers(),
        json={
            "name": "Insecure production source",
            "purpose": "production_collector",
            "issuer": "collector.example",
            "trust_tier": "internal_ca",
            "endpoint_url": "http://fixture.internal/collector-jwks.json",
            "allowed_algorithms": ["RS256"],
            "allow_insecure_http": True,
        },
    )
    assert rejected_source.status_code == 422
    assert "HTTPS" in rejected_source.text or "development tier" in rejected_source.text

    source_response = client.post(
        "/api/v1/trust-registry/sources",
        headers=_operator_headers(),
        json={
            "name": "Development JWKS fixture",
            "purpose": "model_publisher",
            "issuer": "development-publisher",
            "trust_tier": "development",
            "endpoint_url": "http://fixture.internal/publisher-jwks.json",
            "allowed_algorithms": ["RS256"],
            "allow_insecure_http": True,
        },
    )
    assert source_response.status_code == 201, source_response.text
    source = source_response.json()["trust_source"]

    def unavailable(*args: Any, **kwargs: Any) -> FetchedJwksPayload:
        raise TrustSourceFetchError("transport_error", "fixture unavailable")

    monkeypatch.setattr(trust_registry_routes, "fetch_remote_jwks", unavailable)
    failed_response = client.post(
        f"/api/v1/trust-registry/sources/{source['id']}/sync",
        headers=_operator_headers(),
        json={"mode": "apply"},
    )
    assert failed_response.status_code == 201, failed_response.text
    failed = failed_response.json()
    assert failed["sync"]["status"] == "failed"
    assert failed["sync"]["error_code"] == "transport_error"
    assert failed["trust_source"]["status"] == "failed"
    assert db_session.scalar(select(EvidenceTrustRoot.id)) is None

    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    private_jwk = json.loads(RSAAlgorithm.to_jwk(private_key))
    private_jwk.update({"kid": "private-key", "alg": "RS256", "use": "sig"})
    monkeypatch.setattr(
        trust_registry_routes,
        "fetch_remote_jwks",
        lambda *args, **kwargs: _fetched({"keys": [private_jwk]}),
    )
    private_response = client.post(
        f"/api/v1/trust-registry/sources/{source['id']}/sync",
        headers=_operator_headers(),
        json={"mode": "apply"},
    )
    assert private_response.status_code == 201, private_response.text
    assert private_response.json()["sync"]["status"] == "failed"
    assert private_response.json()["sync"]["error_code"] == "invalid_jwks"
    assert db_session.scalar(select(EvidenceTrustRoot.id)) is None

    overview = client.get("/api/v1/trust-registry/overview").json()
    assert overview["schema_version"] == "model-atlas-trust-registry-overview-v3"
    assert overview["trust_source_count"] == 1
    assert overview["failed_source_count"] == 1

    metrics = client.get("/api/v1/operations/metrics").json()
    samples = {sample["name"]: sample["value"] for sample in metrics["samples"]}
    assert samples["model_atlas_trust_source_failed"] == 1
    assert any(alert["key"] == "trust_source_failed" for alert in metrics["alerts"])
