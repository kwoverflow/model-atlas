from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from app.middleware.operator_identity import (
    OperatorIdentityMiddleware,
    is_trusted_proxy,
)
from app.services.oidc_contracts import OIDCCachedDocument
from app.services.operator_identity import (
    JWTAuthenticationError,
    JWTVerificationConfig,
    OIDCJWTVerifier,
    extract_bearer_operator_identity,
    verify_hs256_jwt,
)


def test_verified_jwt_builds_operator_identity_and_rejects_tampering() -> None:
    now = dt.datetime(2026, 7, 13, 12, 0, tzinfo=dt.UTC)
    secret = "pytest-jwt-secret-with-at-least-32-bytes"
    config = JWTVerificationConfig(
        enabled=True,
        issuer="https://identity.pytest",
        audience="model-atlas",
        keys={"key-1": secret},
        role_claim="realm.role",
        name_claim="preferred_username",
        leeway_seconds=5,
    )
    claims = {
        "sub": "operator-42",
        "preferred_username": "Release Operator",
        "realm": {"role": "ML Ops Lead"},
        "iss": "https://identity.pytest",
        "aud": ["another-service", "model-atlas"],
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=5)).timestamp()),
    }
    token = _jwt(claims, secret=secret, key_id="key-1")

    identity = extract_bearer_operator_identity(
        {"authorization": f"Bearer {token}"},
        config=config,
        now=now,
    )
    assert identity is not None
    assert identity.subject_id == "operator-42"
    assert identity.display_name == "Release Operator"
    assert identity.role == "ML Ops Lead"
    assert identity.auth_source == "oidc_jwt"
    assert identity.identity_verified is True

    signing_input, encoded_signature = token.rsplit(".", 1)
    signature = base64.urlsafe_b64decode(encoded_signature + "=" * (-len(encoded_signature) % 4))
    # Change signed bytes while keeping the base64url representation canonical.
    changed_signature = bytes([signature[0] ^ 1]) + signature[1:]
    tampered = f"{signing_input}.{_base64url(changed_signature)}"
    assert jwt.get_unverified_header(tampered) == jwt.get_unverified_header(token)
    with pytest.raises(JWTAuthenticationError, match="signature verification failed"):
        verify_hs256_jwt(tampered, config=config, now=now)


def test_jwt_claim_validation_and_trusted_proxy_boundaries() -> None:
    now = dt.datetime(2026, 7, 13, 12, 0, tzinfo=dt.UTC)
    config = JWTVerificationConfig(
        enabled=True,
        issuer="issuer-a",
        audience="model-atlas",
        keys={"default": "pytest-default-secret-with-32-bytes"},
    )
    expired = _jwt(
        {
            "sub": "expired-user",
            "iss": "issuer-a",
            "aud": "model-atlas",
            "exp": int((now - dt.timedelta(minutes=1)).timestamp()),
        },
        secret="pytest-default-secret-with-32-bytes",
    )
    with pytest.raises(JWTAuthenticationError, match="expired"):
        verify_hs256_jwt(expired, config=config, now=now)

    assert is_trusted_proxy("127.0.0.1", ["127.0.0.1/32"])
    assert is_trusted_proxy("172.20.0.4", ["172.16.0.0/12"])
    assert is_trusted_proxy("testclient", ["testclient"])
    assert not is_trusted_proxy("203.0.113.4", ["127.0.0.1/32", "172.16.0.0/12"])


def test_oidc_discovery_jwks_rotation_and_middleware_integration() -> None:
    private_one, jwk_one = _rsa_key("key-1")
    private_two, jwk_two = _rsa_key("key-2")
    with _oidc_server([jwk_one]) as (issuer, state):
        now = dt.datetime.now(dt.UTC).replace(microsecond=0)
        config = JWTVerificationConfig(
            enabled=True,
            issuer=issuer,
            audience="model-atlas",
            keys={},
            algorithms=("RS256",),
            role_claim="realm.role",
            name_claim="preferred_username",
            discovery_url=f"{issuer}/.well-known/openid-configuration",
            discovery_cache_ttl_seconds=3600,
            jwks_cache_ttl_seconds=3600,
            allow_insecure_http=True,
        )
        verifier = OIDCJWTVerifier(config)
        token_one = _rs256_jwt(
            private_one,
            key_id="key-1",
            issuer=issuer,
            now=now,
        )
        claims = verifier.verify(token_one, now=now)
        assert claims["sub"] == "operator-42"
        assert state["discovery_requests"] == 1
        assert state["jwks_requests"] == 1

        state["keys"] = [jwk_two]
        token_two = _rs256_jwt(
            private_two,
            key_id="key-2",
            issuer=issuer,
            now=now,
        )
        rotated_claims = verifier.verify(token_two, now=now)
        assert rotated_claims["sub"] == "operator-42"
        assert state["discovery_requests"] == 1
        assert state["jwks_requests"] == 2
        assert verifier.cache_status()["jwks_key_count"] == 1
        with pytest.raises(JWTAuthenticationError, match="signing key was not found"):
            verifier.verify(token_one, now=now)

        auth_app = FastAPI()
        auth_app.add_middleware(
            OperatorIdentityMiddleware,
            trusted_headers_enabled=False,
            trusted_proxy_networks=[],
            jwt_config=config,
        )

        @auth_app.get("/whoami")
        def whoami(request: Request) -> dict[str, Any]:
            return request.state.operator_identity.to_json()

        with TestClient(auth_app) as client:
            response = client.get(
                "/whoami",
                headers={"Authorization": f"Bearer {token_two}"},
            )
        assert response.status_code == 200
        assert response.json()["subject_id"] == "operator-42"
        assert response.json()["role"] == "ML Ops Lead"
        assert response.json()["auth_source"] == "oidc_jwt"


def test_oidc_rejects_insecure_discovery_by_default() -> None:
    private_key, jwk = _rsa_key("key-1")
    with _oidc_server([jwk]) as (issuer, _):
        now = dt.datetime.now(dt.UTC).replace(microsecond=0)
        verifier = OIDCJWTVerifier(
            JWTVerificationConfig(
                enabled=True,
                issuer=issuer,
                audience="model-atlas",
                keys={},
                algorithms=("RS256",),
                discovery_url=f"{issuer}/.well-known/openid-configuration",
            )
        )
        token = _rs256_jwt(
            private_key,
            key_id="key-1",
            issuer=issuer,
            now=now,
        )
        with pytest.raises(JWTAuthenticationError, match="allowed HTTP scheme"):
            verifier.verify(token, now=now)


def test_oidc_verifiers_share_discovery_and_jwks_documents() -> None:
    private_key, jwk = _rsa_key("shared-key")
    shared_cache = _MemoryOIDCCache()
    with _oidc_server([jwk]) as (issuer, state):
        now = dt.datetime.now(dt.UTC).replace(microsecond=0)
        config = JWTVerificationConfig(
            enabled=True,
            issuer=issuer,
            audience="model-atlas",
            keys={},
            algorithms=("RS256",),
            discovery_url=f"{issuer}/.well-known/openid-configuration",
            allow_insecure_http=True,
        )
        token = _rs256_jwt(
            private_key,
            key_id="shared-key",
            issuer=issuer,
            now=now,
        )

        assert OIDCJWTVerifier(
            config,
            document_cache=shared_cache,
        ).verify(token, now=now)["sub"] == "operator-42"
        shared_cache.shorten_expiry(seconds=2)
        second = OIDCJWTVerifier(config, document_cache=shared_cache)
        assert second.verify(token, now=now)["sub"] == "operator-42"

        assert state["discovery_requests"] == 1
        assert state["jwks_requests"] == 1
        assert second.cache_status()["shared_cache_hits"] == 2
        assert second.cache_status()["discovery_ttl_remaining_seconds"] <= 2
        assert second.cache_status()["jwks_ttl_remaining_seconds"] <= 2


class _MemoryOIDCCache:
    def __init__(self) -> None:
        self.documents: dict[tuple[str, str], OIDCCachedDocument] = {}

    def get(
        self,
        document_type: str,
        source_url: str,
        *,
        now: dt.datetime | None = None,
    ) -> OIDCCachedDocument | None:
        return self.documents.get((document_type, source_url))

    def put(
        self,
        document_type: str,
        source_url: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
        now: dt.datetime | None = None,
    ) -> None:
        current = now or dt.datetime.now(dt.UTC)
        self.documents[(document_type, source_url)] = OIDCCachedDocument(
            payload=dict(payload),
            expires_at=current + dt.timedelta(seconds=ttl_seconds),
        )

    def shorten_expiry(self, *, seconds: int) -> None:
        expires_at = dt.datetime.now(dt.UTC) + dt.timedelta(seconds=seconds)
        self.documents = {
            key: OIDCCachedDocument(
                payload=document.payload,
                expires_at=expires_at,
            )
            for key, document in self.documents.items()
        }


def _jwt(
    claims: dict,
    *,
    secret: str,
    key_id: str = "default",
) -> str:
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    encoded_header = _base64url(json.dumps(header, separators=(",", ":")).encode())
    encoded_claims = _base64url(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_claims}".encode("ascii")
    signature = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{encoded_header}.{encoded_claims}.{_base64url(signature)}"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _rsa_key(
    key_id: str,
) -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    return private_key, {
        **jwk,
        "kid": key_id,
        "alg": "RS256",
        "use": "sig",
        "key_ops": ["verify"],
    }


def _rs256_jwt(
    private_key: rsa.RSAPrivateKey,
    *,
    key_id: str,
    issuer: str,
    now: dt.datetime,
) -> str:
    return jwt.encode(
        {
            "sub": "operator-42",
            "preferred_username": "Release Operator",
            "realm": {"role": "ML Ops Lead"},
            "iss": issuer,
            "aud": "model-atlas",
            "iat": int(now.timestamp()),
            "exp": int((now + dt.timedelta(minutes=5)).timestamp()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": key_id},
    )


@contextmanager
def _oidc_server(
    keys: list[dict[str, Any]],
):
    state: dict[str, Any] = {
        "keys": keys,
        "discovery_requests": 0,
        "jwks_requests": 0,
    }

    class OIDCHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path == "/.well-known/openid-configuration":
                state["discovery_requests"] += 1
                self._write_json(
                    {
                        "issuer": state["issuer"],
                        "jwks_uri": f"{state['issuer']}/jwks",
                        "id_token_signing_alg_values_supported": ["RS256"],
                    }
                )
                return
            if self.path == "/jwks":
                state["jwks_requests"] += 1
                self._write_json({"keys": state["keys"]})
                return
            self.send_error(404)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _write_json(self, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), OIDCHandler)
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
