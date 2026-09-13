from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import jwt

from app.services.oidc_contracts import OIDCDocumentCache
from app.services.operator_identity import (
    JWTAuthenticationError,
    JWTVerificationConfig,
    OIDCJWTVerifier,
    SignerIdentity,
    identity_from_oidc_claims,
)
from app.validators import DomainValidationError

BROWSER_SESSION_ISSUER = "model-atlas-browser-session"
BROWSER_SESSION_AUDIENCE = "model-atlas-ui"
BROWSER_TRANSACTION_ISSUER = "model-atlas-oidc-transaction"
BROWSER_TRANSACTION_AUDIENCE = "model-atlas-oidc-callback"
BROWSER_OIDC_VERSION = "browser-oidc-pkce-v3"
MAX_OIDC_RESPONSE_BYTES = 1_048_576


@dataclass(frozen=True)
class BrowserSessionConfig:
    enabled: bool
    secret: str | None
    cookie_name: str = "model_atlas_session"
    secure: bool = True
    ttl_seconds: int = 3600


@dataclass(frozen=True)
class BrowserOIDCConfig:
    enabled: bool
    client_id: str | None
    client_secret: str | None
    redirect_uri: str
    frontend_url: str
    scopes: tuple[str, ...]
    authorization_endpoint: str | None
    token_endpoint: str | None
    end_session_endpoint: str | None = None
    transaction_cookie_name: str = "model_atlas_oidc_transaction"


@dataclass(frozen=True)
class BrowserLoginStart:
    authorization_url: str
    transaction_token: str


@dataclass(frozen=True)
class BrowserLoginCompletion:
    identity: SignerIdentity
    session_token: str
    return_url: str
    provider_id_token: str
    provider_session_id: str | None


@dataclass(frozen=True)
class BrowserLogoutTarget:
    url: str
    provider_logout: bool


class BrowserSessionCodec:
    def __init__(self, config: BrowserSessionConfig) -> None:
        self.config = config
        if config.enabled and (not config.secret or len(config.secret) < 32):
            raise ValueError(
                "OIDC_SESSION_SECRET must contain at least 32 characters when "
                "browser login is enabled"
            )

    def encode_identity(
        self,
        identity: SignerIdentity,
        *,
        now: dt.datetime | None = None,
    ) -> str:
        secret = self._secret()
        issued_at = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
        return jwt.encode(
            {
                "iss": BROWSER_SESSION_ISSUER,
                "aud": BROWSER_SESSION_AUDIENCE,
                "sub": identity.subject_id,
                "name": identity.display_name,
                "role": identity.role,
                "identity_provider": identity.identity_provider,
                "auth_source": "oidc_browser_session",
                "iat": int(issued_at.timestamp()),
                "exp": int(
                    (
                        issued_at
                        + dt.timedelta(seconds=max(300, self.config.ttl_seconds))
                    ).timestamp()
                ),
                "jti": secrets.token_urlsafe(18),
            },
            secret,
            algorithm="HS256",
        )

    def decode_identity(
        self,
        token: str,
        *,
        now: dt.datetime | None = None,
    ) -> SignerIdentity:
        secret = self._secret()
        try:
            claims = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=BROWSER_SESSION_AUDIENCE,
                issuer=BROWSER_SESSION_ISSUER,
                options={"require": ["exp", "iat", "sub"]},
                leeway=0,
            )
        except jwt.PyJWTError as exc:
            raise JWTAuthenticationError("browser session is invalid or expired") from exc
        if now is not None and int(claims["exp"]) < int(now.timestamp()):
            raise JWTAuthenticationError("browser session is invalid or expired")
        subject_id = str(claims.get("sub") or "").strip()
        if not subject_id:
            raise JWTAuthenticationError("browser session subject is missing")
        return SignerIdentity(
            subject_id=subject_id,
            display_name=str(claims.get("name") or subject_id),
            role=(str(claims["role"]) if claims.get("role") else None),
            identity_provider=str(
                claims.get("identity_provider") or "oidc-provider"
            ),
            auth_source="oidc_browser_session",
            identity_verified=True,
            ticket_reference=None,
        )

    def _secret(self) -> str:
        if not self.config.enabled:
            raise JWTAuthenticationError("browser session authentication is disabled")
        if not self.config.secret or len(self.config.secret) < 32:
            raise JWTAuthenticationError("browser session signing secret is not configured")
        return self.config.secret


class BrowserOIDCClient:
    def __init__(
        self,
        *,
        oidc_config: BrowserOIDCConfig,
        session_config: BrowserSessionConfig,
        jwt_config: JWTVerificationConfig,
        document_cache: OIDCDocumentCache | None = None,
    ) -> None:
        self.oidc_config = oidc_config
        self.session_codec = BrowserSessionCodec(session_config)
        self.jwt_config = replace(
            jwt_config,
            audience=oidc_config.client_id,
        )
        self.verifier = OIDCJWTVerifier(
            self.jwt_config,
            document_cache=document_cache,
        )

    def begin_login(self, *, return_to: str = "/") -> BrowserLoginStart:
        self._assert_enabled()
        metadata = self._provider_metadata()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = _base64url(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        )
        transaction_token = self._encode_transaction(
            {
                "state": state,
                "nonce": nonce,
                "code_verifier": code_verifier,
                "return_to": _validated_return_path(return_to),
            }
        )
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self.oidc_config.client_id,
                "redirect_uri": self.oidc_config.redirect_uri,
                "scope": " ".join(self.oidc_config.scopes),
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return BrowserLoginStart(
            authorization_url=f"{metadata['authorization_endpoint']}?{query}",
            transaction_token=transaction_token,
        )

    def complete_login(
        self,
        *,
        code: str,
        state: str,
        transaction_token: str,
    ) -> BrowserLoginCompletion:
        self._assert_enabled()
        transaction = self._decode_transaction(transaction_token)
        if not hmac.compare_digest(str(transaction.get("state") or ""), state):
            raise DomainValidationError("OIDC login state verification failed")
        metadata = self._provider_metadata()
        token_payload = self._exchange_code(
            token_endpoint=str(metadata["token_endpoint"]),
            code=code,
            code_verifier=str(transaction["code_verifier"]),
        )
        id_token = str(token_payload.get("id_token") or "")
        if not id_token:
            raise DomainValidationError("OIDC token response is missing id_token")
        try:
            claims = self.verifier.verify(id_token)
        except JWTAuthenticationError as exc:
            raise DomainValidationError("OIDC id_token verification failed") from exc
        expected_nonce = str(transaction.get("nonce") or "")
        if not expected_nonce or not hmac.compare_digest(
            str(claims.get("nonce") or ""),
            expected_nonce,
        ):
            raise DomainValidationError("OIDC nonce verification failed")
        identity = identity_from_oidc_claims(
            claims,
            config=self.jwt_config,
            auth_source="oidc_browser_session",
        )
        return BrowserLoginCompletion(
            identity=identity,
            session_token=self.session_codec.encode_identity(identity),
            return_url=(
                f"{self.oidc_config.frontend_url.rstrip('/')}"
                f"{_validated_return_path(str(transaction.get('return_to') or '/'))}"
            ),
            provider_id_token=id_token,
            provider_session_id=(str(claims["sid"]) if claims.get("sid") else None),
        )

    def build_logout_target(
        self,
        *,
        provider_id_token: str | None,
        return_to: str = "/",
    ) -> BrowserLogoutTarget:
        local_return_url = (
            f"{self.oidc_config.frontend_url.rstrip('/')}"
            f"{_validated_return_path(return_to)}"
        )
        end_session_endpoint = self.oidc_config.end_session_endpoint
        if not end_session_endpoint:
            try:
                end_session_endpoint = str(
                    self._provider_metadata().get("end_session_endpoint") or ""
                )
            except DomainValidationError:
                end_session_endpoint = ""
        if not end_session_endpoint:
            return BrowserLogoutTarget(url=local_return_url, provider_logout=False)
        _validate_provider_url(
            end_session_endpoint,
            allow_insecure_http=self.jwt_config.allow_insecure_http,
        )
        parameters = {
            "post_logout_redirect_uri": local_return_url,
            "client_id": str(self.oidc_config.client_id or ""),
        }
        if provider_id_token:
            parameters["id_token_hint"] = provider_id_token
        separator = "&" if "?" in end_session_endpoint else "?"
        return BrowserLogoutTarget(
            url=f"{end_session_endpoint}{separator}{urlencode(parameters)}",
            provider_logout=True,
        )

    def _provider_metadata(self) -> dict[str, str]:
        authorization_endpoint = self.oidc_config.authorization_endpoint
        token_endpoint = self.oidc_config.token_endpoint
        if authorization_endpoint and token_endpoint:
            _validate_provider_url(
                authorization_endpoint,
                allow_insecure_http=self.jwt_config.allow_insecure_http,
            )
            _validate_provider_url(
                token_endpoint,
                allow_insecure_http=self.jwt_config.allow_insecure_http,
            )
            return {
                "authorization_endpoint": authorization_endpoint,
                "token_endpoint": token_endpoint,
            }
        discovery_url = self.jwt_config.discovery_url
        if not discovery_url and self.jwt_config.issuer:
            discovery_url = (
                f"{self.jwt_config.issuer.rstrip('/')}"
                "/.well-known/openid-configuration"
            )
        if not discovery_url:
            raise DomainValidationError("OIDC discovery URL is not configured")
        try:
            payload = self.verifier.provider_metadata()
        except JWTAuthenticationError as exc:
            raise DomainValidationError("OIDC discovery request failed") from exc
        discovered_issuer = str(payload.get("issuer") or "").rstrip("/")
        expected_issuer = str(self.jwt_config.issuer or "").rstrip("/")
        if expected_issuer and discovered_issuer != expected_issuer:
            raise DomainValidationError("OIDC discovery issuer does not match")
        authorization_endpoint = str(payload.get("authorization_endpoint") or "")
        token_endpoint = str(payload.get("token_endpoint") or "")
        if not authorization_endpoint or not token_endpoint:
            raise DomainValidationError(
                "OIDC discovery is missing authorization or token endpoint"
            )
        for endpoint in (authorization_endpoint, token_endpoint):
            _validate_provider_url(
                endpoint,
                allow_insecure_http=self.jwt_config.allow_insecure_http,
            )
        return {
            "authorization_endpoint": authorization_endpoint,
            "token_endpoint": token_endpoint,
            "end_session_endpoint": str(payload.get("end_session_endpoint") or ""),
        }

    def _exchange_code(
        self,
        *,
        token_endpoint: str,
        code: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        body = urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.oidc_config.redirect_uri,
                "client_id": self.oidc_config.client_id,
                "code_verifier": code_verifier,
            }
        ).encode("ascii")
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded",
            "user-agent": "model-atlas-browser-oidc/1",
        }
        if self.oidc_config.client_secret:
            credentials = base64.b64encode(
                (
                    f"{self.oidc_config.client_id}:"
                    f"{self.oidc_config.client_secret}"
                ).encode()
            ).decode("ascii")
            headers["authorization"] = f"Basic {credentials}"
        return self._fetch_json(
            token_endpoint,
            method="POST",
            body=body,
            headers=headers,
        )

    def _fetch_json(
        self,
        url: str,
        *,
        method: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        _validate_provider_url(
            url,
            allow_insecure_http=self.jwt_config.allow_insecure_http,
        )
        request = Request(url, data=body, headers=headers or {}, method=method)
        try:
            with urlopen(  # noqa: S310
                request,
                timeout=max(0.5, min(self.jwt_config.http_timeout_seconds, 30.0)),
            ) as response:
                body_bytes = response.read(MAX_OIDC_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise DomainValidationError("OIDC provider request failed") from exc
        if len(body_bytes) > MAX_OIDC_RESPONSE_BYTES:
            raise DomainValidationError("OIDC provider response is too large")
        try:
            payload = json.loads(body_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DomainValidationError("OIDC provider response is invalid JSON") from exc
        if not isinstance(payload, dict):
            raise DomainValidationError("OIDC provider response must be an object")
        return payload

    def _encode_transaction(self, payload: dict[str, Any]) -> str:
        secret = self.session_codec._secret()
        now = dt.datetime.now(dt.UTC).replace(microsecond=0)
        return jwt.encode(
            {
                **payload,
                "iss": BROWSER_TRANSACTION_ISSUER,
                "aud": BROWSER_TRANSACTION_AUDIENCE,
                "iat": int(now.timestamp()),
                "exp": int((now + dt.timedelta(minutes=10)).timestamp()),
                "jti": secrets.token_urlsafe(18),
            },
            secret,
            algorithm="HS256",
        )

    def _decode_transaction(self, token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token,
                self.session_codec._secret(),
                algorithms=["HS256"],
                audience=BROWSER_TRANSACTION_AUDIENCE,
                issuer=BROWSER_TRANSACTION_ISSUER,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "state",
                        "nonce",
                        "code_verifier",
                    ]
                },
            )
        except jwt.PyJWTError as exc:
            raise DomainValidationError(
                "OIDC login transaction is invalid or expired"
            ) from exc

    def _assert_enabled(self) -> None:
        if not self.oidc_config.enabled:
            raise DomainValidationError("browser OIDC login is disabled")
        if not self.oidc_config.client_id:
            raise DomainValidationError("OIDC client_id is not configured")


def extract_browser_session_identity(
    cookies: Any,
    *,
    config: BrowserSessionConfig,
) -> SignerIdentity | None:
    if not config.enabled:
        return None
    token = cookies.get(config.cookie_name) if cookies is not None else None
    if not token:
        return None
    return BrowserSessionCodec(config).decode_identity(str(token))


def _validated_return_path(value: str) -> str:
    normalized = value.strip() or "/"
    parsed = urlparse(normalized)
    if (
        not normalized.startswith("/")
        or normalized.startswith("//")
        or "\\" in normalized
        or any(ord(character) < 32 for character in normalized)
        or parsed.scheme
        or parsed.netloc
    ):
        raise DomainValidationError("OIDC return_to must be a local absolute path")
    return normalized


def _validate_provider_url(value: str, *, allow_insecure_http: bool) -> None:
    parsed = urlparse(value)
    allowed_schemes = {"https"}
    if allow_insecure_http:
        allowed_schemes.add("http")
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise DomainValidationError("OIDC provider URL must use an allowed HTTP scheme")
    if parsed.username or parsed.password or parsed.fragment:
        raise DomainValidationError("OIDC provider URL cannot contain credentials or a fragment")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
