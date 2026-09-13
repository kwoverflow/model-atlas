from __future__ import annotations

import datetime as dt
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.middleware.operator_identity import OperatorIdentityMiddleware
from app.services.browser_oidc import (
    BrowserOIDCClient,
    BrowserOIDCConfig,
    BrowserSessionConfig,
)
from app.services.operator_identity import (
    JWTVerificationConfig,
    identity_from_oidc_claims,
)
from app.validators import DomainValidationError

SESSION_SECRET = "browser-session-test-secret-with-more-than-32-bytes"


def test_oidc_identity_prefers_model_atlas_role_over_provider_defaults() -> None:
    identity = identity_from_oidc_claims(
        {
            "sub": "multi-role-operator",
            "name": "Multi Role Operator",
            "roles": ["offline_access", "uma_authorization", "ML Ops Lead"],
            "iss": "https://idp.example/realms/model-atlas",
        },
        config=JWTVerificationConfig(
            enabled=True,
            issuer="https://idp.example/realms/model-atlas",
            audience="model-atlas-browser",
            keys={},
            role_claim="roles",
            name_claim="name",
        ),
        auth_source="oidc_browser_session",
    )

    assert identity.role == "ML Ops Lead"


def test_browser_oidc_pkce_flow_and_session_middleware() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": "browser-key", "alg": "RS256", "use": "sig"})
    with _browser_oidc_server(private_key, jwk) as (issuer, state):
        jwt_config = JWTVerificationConfig(
            enabled=True,
            issuer=issuer,
            audience="model-atlas-browser",
            keys={},
            algorithms=("RS256",),
            role_claim="realm.role",
            name_claim="preferred_username",
            discovery_url=f"{issuer}/.well-known/openid-configuration",
            allow_insecure_http=True,
        )
        session_config = BrowserSessionConfig(
            enabled=True,
            secret=SESSION_SECRET,
            cookie_name="model_atlas_session",
            secure=False,
        )
        browser_client = BrowserOIDCClient(
            oidc_config=BrowserOIDCConfig(
                enabled=True,
                client_id="model-atlas-browser",
                client_secret="browser-client-secret",
                redirect_uri="http://testserver/callback",
                frontend_url="http://frontend.test",
                scopes=("openid", "profile"),
                authorization_endpoint=None,
                token_endpoint=None,
            ),
            session_config=session_config,
            jwt_config=jwt_config,
        )

        login = browser_client.begin_login(return_to="/judge-labels?run=1")
        authorization = urlparse(login.authorization_url)
        query = parse_qs(authorization.query)
        assert authorization.path == "/authorize"
        assert query["response_type"] == ["code"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["scope"] == ["openid profile"]
        state["nonce"] = query["nonce"][0]

        completion = browser_client.complete_login(
            code="authorization-code-1",
            state=query["state"][0],
            transaction_token=login.transaction_token,
        )
        assert completion.identity.subject_id == "browser-operator"
        assert completion.identity.display_name == "Browser Operator"
        assert completion.identity.role == "ML Ops Lead"
        assert completion.return_url == "http://frontend.test/judge-labels?run=1"
        assert completion.provider_session_id == "provider-session-browser-1"
        assert state["token_requests"] == 1
        assert state["code_verifier"]
        assert state["basic_authorization"].startswith("Basic ")
        logout = browser_client.build_logout_target(
            provider_id_token=completion.provider_id_token,
            return_to="/judge-labels?run=1",
        )
        logout_url = urlparse(logout.url)
        logout_query = parse_qs(logout_url.query)
        assert logout.provider_logout is True
        assert logout_url.path == "/logout"
        assert logout_query["client_id"] == ["model-atlas-browser"]
        assert logout_query["id_token_hint"] == [completion.provider_id_token]
        assert logout_query["post_logout_redirect_uri"] == [
            "http://frontend.test/judge-labels?run=1"
        ]

        app = FastAPI()
        app.add_middleware(
            OperatorIdentityMiddleware,
            trusted_headers_enabled=False,
            trusted_proxy_networks=[],
            jwt_config=jwt_config,
            browser_session_config=session_config,
        )

        @app.get("/whoami")
        def whoami(request: Request) -> dict[str, Any]:
            identity = getattr(request.state, "operator_identity", None)
            return identity.to_json() if identity is not None else {"identity": None}

        with TestClient(app) as client:
            client.cookies.set("model_atlas_session", completion.session_token)
            response = client.get("/whoami")
            client.cookies.set("model_atlas_session", "invalid-session")
            invalid = client.get("/whoami")
        assert response.status_code == 200
        assert response.json()["subject_id"] == "browser-operator"
        assert response.json()["auth_source"] == "oidc_browser_session"
        assert invalid.status_code == 200
        assert invalid.json() == {"identity": None}

        with pytest.raises(DomainValidationError, match="state verification"):
            browser_client.complete_login(
                code="authorization-code-1",
                state="tampered-state",
                transaction_token=login.transaction_token,
            )
        with pytest.raises(DomainValidationError, match="local absolute path"):
            browser_client.begin_login(return_to="https://attacker.example")
        with pytest.raises(DomainValidationError, match="local absolute path"):
            browser_client.begin_login(return_to="/\\attacker.example")


def test_browser_oidc_routes_report_disabled_by_default(client: TestClient) -> None:
    status = client.get("/api/v1/operator-identity/browser-config")
    assert status.status_code == 200
    assert status.json()["enabled"] is False
    assert status.json()["authenticated"] is False
    assert status.json()["login_url"] is None

    login = client.get(
        "/api/v1/operator-identity/login",
        follow_redirects=False,
    )
    assert login.status_code == 404

    logout = client.get("/api/v1/operator-identity/logout")
    assert logout.status_code == 405


@contextmanager
def _browser_oidc_server(
    private_key: rsa.RSAPrivateKey,
    jwk: dict[str, Any],
):
    state: dict[str, Any] = {
        "nonce": None,
        "token_requests": 0,
        "code_verifier": None,
        "basic_authorization": "",
    }

    class BrowserOIDCHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/.well-known/openid-configuration":
                self._write_json(
                    {
                        "issuer": state["issuer"],
                        "authorization_endpoint": f"{state['issuer']}/authorize",
                        "token_endpoint": f"{state['issuer']}/token",
                        "jwks_uri": f"{state['issuer']}/jwks",
                        "end_session_endpoint": f"{state['issuer']}/logout",
                    }
                )
                return
            if self.path == "/jwks":
                self._write_json({"keys": [jwk]})
                return
            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/token":
                self.send_error(404)
                return
            content_length = int(self.headers.get("content-length", "0"))
            form = parse_qs(self.rfile.read(content_length).decode("ascii"))
            state["token_requests"] += 1
            state["code_verifier"] = form.get("code_verifier", [None])[0]
            state["basic_authorization"] = self.headers.get("authorization", "")
            now = dt.datetime.now(dt.UTC).replace(microsecond=0)
            id_token = jwt.encode(
                {
                    "sub": "browser-operator",
                    "preferred_username": "Browser Operator",
                    "realm": {"role": "ML Ops Lead"},
                    "iss": state["issuer"],
                    "aud": "model-atlas-browser",
                    "nonce": state["nonce"],
                    "sid": "provider-session-browser-1",
                    "iat": int(now.timestamp()),
                    "exp": int((now + dt.timedelta(minutes=5)).timestamp()),
                },
                private_key,
                algorithm="RS256",
                headers={"kid": "browser-key"},
            )
            self._write_json(
                {
                    "token_type": "Bearer",
                    "expires_in": 300,
                    "id_token": id_token,
                }
            )

        def _write_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), BrowserOIDCHandler)
    host, port = server.server_address
    state["issuer"] = f"http://{host}:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state["issuer"], state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
