from __future__ import annotations

import datetime as dt

from conftest import TestingSessionLocal
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.middleware.operator_identity import (
    BrowserCSRFConfig,
    OperatorIdentityMiddleware,
)
from app.models import OIDCBrowserSession, OIDCBrowserSessionEvent, OIDCCacheEntry
from app.services.browser_oidc import BrowserSessionConfig
from app.services.oidc_state import (
    DatabaseBrowserSessionStore,
    DatabaseOIDCDocumentCache,
)
from app.services.operator_identity import JWTVerificationConfig

SESSION_SECRET = "database-browser-session-secret-with-more-than-32-bytes"


def test_database_session_is_shared_hashed_encrypted_and_revocable(
    db_session: Session,
) -> None:
    now = dt.datetime(2026, 7, 22, 8, 0, tzinfo=dt.UTC)
    first = DatabaseBrowserSessionStore(
        TestingSessionLocal,
        secret=SESSION_SECRET,
        ttl_seconds=600,
    )
    second = DatabaseBrowserSessionStore(
        TestingSessionLocal,
        secret=SESSION_SECRET,
        ttl_seconds=600,
    )

    issued = first.issue(
        subject_id="operator-5hc",
        display_name="5H-C Operator",
        role="ML Ops Lead",
        identity_provider="https://idp.example/realms/model-atlas",
        provider_session_id="provider-session-1",
        provider_id_token="provider-id-token-secret",
        client_descriptor="127.0.0.1\0pytest-browser",
        now=now,
    )
    resolved = second.resolve(issued.session_token, now=now + dt.timedelta(seconds=1))

    assert resolved is not None
    assert resolved.session_id == issued.context.session_id
    assert second.csrf_matches(resolved, issued.csrf_token)
    assert not second.csrf_matches(resolved, "wrong-token")

    row = db_session.scalar(select(OIDCBrowserSession))
    assert row is not None
    assert issued.session_token not in row.token_hash
    assert issued.csrf_token not in row.csrf_token_hash
    assert row.provider_id_token_ciphertext != "provider-id-token-secret"
    assert row.provider_session_hash
    assert row.client_fingerprint
    issued_event = db_session.scalar(select(OIDCBrowserSessionEvent))
    assert issued_event is not None
    assert issued_event.event_type == "issued"
    assert issued_event.event_hash

    revoked = second.revoke(
        issued.session_token,
        reason="pytest_logout",
        now=now + dt.timedelta(seconds=2),
    )
    assert revoked is not None
    assert revoked.provider_id_token == "provider-id-token-secret"
    assert first.resolve(
        issued.session_token,
        now=now + dt.timedelta(seconds=3),
    ) is None
    assert first.counts(now=now + dt.timedelta(seconds=3)) == {
        "active": 0,
        "revoked": 1,
    }
    db_session.expire_all()
    row = db_session.scalar(select(OIDCBrowserSession))
    assert row is not None
    assert row.provider_id_token_ciphertext is None
    assert row.provider_session_id is None
    assert row.provider_session_hash
    assert row.provider_token_purged_at == now + dt.timedelta(seconds=2)
    events = list(
        db_session.scalars(
            select(OIDCBrowserSessionEvent).order_by(
                OIDCBrowserSessionEvent.occurred_at
            )
        ).all()
    )
    assert [event.event_type for event in events] == ["issued", "revoked"]
    assert events[1].previous_event_hash == events[0].event_hash


def test_oidc_document_cache_is_shared_and_honors_expiry(db_session: Session) -> None:
    now = dt.datetime(2026, 7, 22, 8, 0, tzinfo=dt.UTC)
    first = DatabaseOIDCDocumentCache(TestingSessionLocal, instance_name="backend-a")
    second = DatabaseOIDCDocumentCache(TestingSessionLocal, instance_name="backend-b")
    source_url = "https://idp.example/.well-known/openid-configuration"
    payload = {
        "issuer": "https://idp.example",
        "jwks_uri": "https://idp.example/jwks",
    }

    first.put("discovery", source_url, payload, ttl_seconds=60, now=now)

    cached = second.get("discovery", source_url, now=now)
    assert cached is not None
    assert cached.payload == payload
    assert cached.expires_at == now + dt.timedelta(seconds=60)
    assert second.get(
        "discovery",
        source_url,
        now=now + dt.timedelta(seconds=61),
    ) is None
    assert first.counts(now=now + dt.timedelta(seconds=61)) == {
        "fresh": 0,
        "stale": 1,
    }
    row = db_session.scalar(select(OIDCCacheEntry))
    assert row is not None
    assert row.content_hash
    assert row.refreshed_by == "backend-a"


def test_browser_session_csrf_origin_and_forwarded_header_boundaries(
    db_session: Session,
) -> None:
    store = DatabaseBrowserSessionStore(
        TestingSessionLocal,
        secret=SESSION_SECRET,
        ttl_seconds=600,
    )
    issued = store.issue(
        subject_id="operator-5hc",
        display_name="5H-C Operator",
        role="ML Ops Lead",
        identity_provider="https://idp.example",
        provider_session_id=None,
        provider_id_token=None,
    )
    app = FastAPI()
    app.add_middleware(
        OperatorIdentityMiddleware,
        trusted_headers_enabled=False,
        trusted_proxy_networks=[],
        jwt_config=JWTVerificationConfig(
            enabled=False,
            issuer=None,
            audience=None,
            keys={},
        ),
        browser_session_config=BrowserSessionConfig(
            enabled=True,
            secret=SESSION_SECRET,
            cookie_name="model_atlas_session",
            secure=False,
        ),
        browser_session_store=store,
        browser_csrf_config=BrowserCSRFConfig(
            enabled=True,
            cookie_name="model_atlas_csrf",
            header_name="x-model-atlas-csrf",
            allowed_origins=["https://atlas.example"],
        ),
    )

    @app.api_route("/operator", methods=["GET", "POST"])
    def operator(request: Request) -> dict[str, str]:
        return {"subject_id": request.state.operator_identity.subject_id}

    with TestClient(app) as client:
        client.cookies.set("model_atlas_session", issued.session_token)
        client.cookies.set("model_atlas_csrf", issued.csrf_token)

        assert client.get("/operator").status_code == 200
        assert client.post("/operator").status_code == 403
        assert client.post(
            "/operator",
            headers={"Origin": "https://atlas.example"},
        ).status_code == 403
        assert client.post(
            "/operator",
            headers={
                "Origin": "https://attacker.example",
                "X-Model-Atlas-CSRF": issued.csrf_token,
            },
        ).status_code == 403
        allowed = client.post(
            "/operator",
            headers={
                "Origin": "https://atlas.example",
                "X-Model-Atlas-CSRF": issued.csrf_token,
            },
        )
        assert allowed.status_code == 200
        assert allowed.json()["subject_id"] == "operator-5hc"

        forwarded = client.get(
            "/operator",
            headers={"X-Forwarded-For": "203.0.113.7"},
        )
        assert forwarded.status_code == 400

        client.cookies.set("model_atlas_session", "unknown-session")
        assert client.get("/operator").status_code == 401
