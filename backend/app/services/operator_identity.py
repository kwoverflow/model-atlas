from __future__ import annotations

import datetime as dt
import hmac
import json
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import jwt
from jwt.algorithms import RSAAlgorithm

from app.schemas import ReleaseDecisionCreate
from app.services.oidc_contracts import OIDCCachedDocument, OIDCDocumentCache

TRUSTED_OPERATOR_ID_HEADER = "x-model-atlas-operator-id"
TRUSTED_OPERATOR_NAME_HEADER = "x-model-atlas-operator-name"
TRUSTED_OPERATOR_ROLE_HEADER = "x-model-atlas-operator-role"
OIDC_ROLE_PRIORITY = (
    "Admin",
    "Release Manager",
    "ML Ops Lead",
    "Model Governance",
    "QA Lead",
    "SRE Lead",
    "ML Engineer",
    "System Worker",
)
TRUSTED_IDENTITY_PROVIDER_HEADER = "x-model-atlas-identity-provider"
AUTHORIZATION_HEADER = "authorization"
SUPPORTED_JWT_ALGORITHMS = frozenset({"HS256", "RS256"})
MAX_OIDC_DOCUMENT_BYTES = 1_048_576


class JWTAuthenticationError(ValueError):
    pass


@dataclass(frozen=True)
class JWTVerificationConfig:
    enabled: bool
    issuer: str | None
    audience: str | None
    keys: dict[str, str]
    algorithms: tuple[str, ...] = ("HS256",)
    role_claim: str = "role"
    name_claim: str = "name"
    leeway_seconds: int = 30
    discovery_url: str | None = None
    jwks_uri: str | None = None
    discovery_cache_ttl_seconds: int = 3600
    jwks_cache_ttl_seconds: int = 300
    http_timeout_seconds: float = 5.0
    allow_insecure_http: bool = False


@dataclass(frozen=True)
class SignerIdentity:
    subject_id: str
    display_name: str
    role: str | None
    identity_provider: str
    auth_source: str
    identity_verified: bool
    ticket_reference: str | None

    def to_json(self) -> dict[str, str | bool | None]:
        return {
            "subject_id": self.subject_id,
            "display_name": self.display_name,
            "role": self.role,
            "identity_provider": self.identity_provider,
            "auth_source": self.auth_source,
            "identity_verified": self.identity_verified,
            "ticket_reference": self.ticket_reference,
        }


class OIDCJWTVerifier:
    def __init__(
        self,
        config: JWTVerificationConfig,
        *,
        document_cache: OIDCDocumentCache | None = None,
    ) -> None:
        self.config = config
        self.document_cache = document_cache
        self._lock = threading.RLock()
        self._discovery_document: dict[str, Any] | None = None
        self._discovery_expires_at = 0.0
        self._jwks: list[dict[str, Any]] | None = None
        self._jwks_expires_at = 0.0
        self._shared_cache_hits = 0
        self._shared_cache_misses = 0
        self._shared_cache_errors = 0

    def verify(
        self,
        token: str,
        *,
        now: dt.datetime | None = None,
    ) -> dict[str, Any]:
        if len(token.split(".")) != 3:
            raise JWTAuthenticationError("JWT must contain three segments")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise JWTAuthenticationError("JWT header is invalid") from exc
        if not isinstance(header, dict):
            raise JWTAuthenticationError("JWT header must be an object")
        algorithm = str(header.get("alg") or "").upper()
        allowed_algorithms = {
            value.strip().upper() for value in self.config.algorithms if value.strip()
        }
        if algorithm not in SUPPORTED_JWT_ALGORITHMS or algorithm not in allowed_algorithms:
            raise JWTAuthenticationError("JWT algorithm is not allowed")
        key_id_value = header.get("kid")
        key_id = str(key_id_value).strip() if key_id_value is not None else None
        verification_key = self._verification_key(
            algorithm=algorithm,
            key_id=key_id,
        )
        try:
            claims = jwt.decode(
                token,
                verification_key,
                algorithms=[algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                    "verify_aud": False,
                    "verify_iss": False,
                    "require": [],
                },
            )
        except jwt.InvalidSignatureError as exc:
            raise JWTAuthenticationError("JWT signature verification failed") from exc
        except jwt.InvalidAlgorithmError as exc:
            raise JWTAuthenticationError("JWT algorithm is not allowed") from exc
        except jwt.PyJWTError as exc:
            raise JWTAuthenticationError("JWT payload verification failed") from exc
        if not isinstance(claims, dict):
            raise JWTAuthenticationError("JWT payload must be an object")
        _validate_registered_claims(claims, config=self.config, now=now)
        return claims

    def cache_status(self) -> dict[str, Any]:
        current = time.monotonic()
        with self._lock:
            return {
                "discovery_cached": self._discovery_document is not None,
                "discovery_ttl_remaining_seconds": round(
                    max(0.0, self._discovery_expires_at - current),
                    3,
                ),
                "jwks_cached": self._jwks is not None,
                "jwks_key_count": len(self._jwks or []),
                "jwks_ttl_remaining_seconds": round(
                    max(0.0, self._jwks_expires_at - current),
                    3,
                ),
                "shared_cache_enabled": self.document_cache is not None,
                "shared_cache_hits": self._shared_cache_hits,
                "shared_cache_misses": self._shared_cache_misses,
                "shared_cache_errors": self._shared_cache_errors,
            }

    def provider_metadata(self, *, force_refresh: bool = False) -> dict[str, Any]:
        return dict(self._load_discovery_document(force_refresh=force_refresh))

    def _verification_key(
        self,
        *,
        algorithm: str,
        key_id: str | None,
    ) -> Any:
        if algorithm == "HS256":
            normalized_key_id = key_id or "default"
            secret = self.config.keys.get(normalized_key_id)
            if secret is None and len(self.config.keys) == 1:
                secret = self.config.keys.get("default")
            if not secret:
                raise JWTAuthenticationError("JWT signing key was not found")
            return secret
        jwk = self._select_jwk(key_id=key_id, force_refresh=False)
        if jwk is None:
            jwk = self._select_jwk(key_id=key_id, force_refresh=True)
        if jwk is None:
            raise JWTAuthenticationError("JWT signing key was not found")
        try:
            return RSAAlgorithm.from_jwk(json.dumps(jwk))
        except (ValueError, TypeError) as exc:
            raise JWTAuthenticationError("OIDC RSA signing key is invalid") from exc

    def _select_jwk(
        self,
        *,
        key_id: str | None,
        force_refresh: bool,
    ) -> dict[str, Any] | None:
        keys = self._load_jwks(force_refresh=force_refresh)
        candidates = [
            key
            for key in keys
            if key.get("kty") == "RSA"
            and key.get("use", "sig") == "sig"
            and (not key.get("alg") or key.get("alg") == "RS256")
            and (
                not isinstance(key.get("key_ops"), list)
                or "verify" in key["key_ops"]
            )
        ]
        if key_id:
            return next(
                (key for key in candidates if str(key.get("kid") or "") == key_id),
                None,
            )
        if len(candidates) == 1:
            return candidates[0]
        raise JWTAuthenticationError(
            "JWT kid header is required when multiple signing keys are available"
        )

    def _load_jwks(self, *, force_refresh: bool) -> list[dict[str, Any]]:
        current = time.monotonic()
        with self._lock:
            if (
                not force_refresh
                and self._jwks is not None
                and current < self._jwks_expires_at
            ):
                return self._jwks
            jwks_uri = self.config.jwks_uri or self._discovered_jwks_uri()
            payload = None
            shared_expires_at = None
            if not force_refresh:
                shared_document = self._shared_cache_get("jwks", jwks_uri)
                if shared_document is not None:
                    payload = shared_document.payload
                    shared_expires_at = shared_document.expires_at
            if payload is None:
                payload = self._fetch_json(jwks_uri, document_name="JWKS")
                self._shared_cache_put(
                    "jwks",
                    jwks_uri,
                    payload,
                    ttl_seconds=self.config.jwks_cache_ttl_seconds,
                )
            keys = payload.get("keys")
            if not isinstance(keys, list) or not keys:
                raise JWTAuthenticationError("OIDC JWKS must contain signing keys")
            normalized = [dict(key) for key in keys if isinstance(key, dict)]
            if len(normalized) != len(keys):
                raise JWTAuthenticationError("OIDC JWKS signing keys must be objects")
            self._jwks = normalized
            self._jwks_expires_at = current + _local_cache_ttl(
                configured_ttl_seconds=max(
                    15,
                    int(self.config.jwks_cache_ttl_seconds),
                ),
                shared_expires_at=shared_expires_at,
            )
            return self._jwks

    def _discovered_jwks_uri(self) -> str:
        return str(self._load_discovery_document()["jwks_uri"])

    def _load_discovery_document(
        self,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        current = time.monotonic()
        with self._lock:
            if (
                not force_refresh
                and
                self._discovery_document is not None
                and current < self._discovery_expires_at
            ):
                return self._discovery_document
            discovery_url = self.config.discovery_url
            if not discovery_url:
                if not self.config.issuer:
                    raise JWTAuthenticationError(
                        "OIDC issuer or discovery URL is required for RS256"
                    )
                discovery_url = (
                    f"{self.config.issuer.rstrip('/')}"
                    "/.well-known/openid-configuration"
                )
            payload = None
            shared_expires_at = None
            if not force_refresh:
                shared_document = self._shared_cache_get(
                    "discovery",
                    discovery_url,
                )
                if shared_document is not None:
                    payload = shared_document.payload
                    shared_expires_at = shared_document.expires_at
            if payload is None:
                payload = self._fetch_json(
                    discovery_url,
                    document_name="discovery document",
                )
                self._shared_cache_put(
                    "discovery",
                    discovery_url,
                    payload,
                    ttl_seconds=self.config.discovery_cache_ttl_seconds,
                )
            discovered_issuer = str(payload.get("issuer") or "").rstrip("/")
            expected_issuer = str(self.config.issuer or "").rstrip("/")
            if expected_issuer and discovered_issuer != expected_issuer:
                raise JWTAuthenticationError("OIDC discovery issuer does not match")
            jwks_uri = str(payload.get("jwks_uri") or "").strip()
            if not jwks_uri:
                raise JWTAuthenticationError("OIDC discovery is missing jwks_uri")
            _validate_provider_url(
                jwks_uri,
                allow_insecure_http=self.config.allow_insecure_http,
            )
            self._discovery_document = {
                **payload,
                "jwks_uri": jwks_uri,
            }
            self._discovery_expires_at = current + _local_cache_ttl(
                configured_ttl_seconds=max(
                    30,
                    int(self.config.discovery_cache_ttl_seconds),
                ),
                shared_expires_at=shared_expires_at,
            )
            return self._discovery_document

    def _shared_cache_get(
        self,
        document_type: str,
        source_url: str,
    ) -> OIDCCachedDocument | None:
        if self.document_cache is None:
            return None
        try:
            payload = self.document_cache.get(document_type, source_url)
        except Exception:  # The provider remains the availability fallback.
            self._shared_cache_errors += 1
            return None
        if payload is None:
            self._shared_cache_misses += 1
        else:
            self._shared_cache_hits += 1
        return payload

    def _shared_cache_put(
        self,
        document_type: str,
        source_url: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
    ) -> None:
        if self.document_cache is None:
            return
        try:
            self.document_cache.put(
                document_type,
                source_url,
                payload,
                ttl_seconds=ttl_seconds,
            )
        except Exception:  # A cache write must not invalidate a verified provider response.
            self._shared_cache_errors += 1

    def _fetch_json(
        self,
        url: str,
        *,
        document_name: str,
    ) -> dict[str, Any]:
        _validate_provider_url(
            url,
            allow_insecure_http=self.config.allow_insecure_http,
        )
        request = Request(
            url,
            headers={
                "accept": "application/json",
                "user-agent": "model-atlas-oidc-verifier/1",
            },
            method="GET",
        )
        try:
            with urlopen(  # noqa: S310
                request,
                timeout=max(0.5, min(self.config.http_timeout_seconds, 30.0)),
            ) as response:
                body = response.read(MAX_OIDC_DOCUMENT_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise JWTAuthenticationError(
                f"OIDC {document_name} request failed"
            ) from exc
        if len(body) > MAX_OIDC_DOCUMENT_BYTES:
            raise JWTAuthenticationError(f"OIDC {document_name} is too large")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JWTAuthenticationError(
                f"OIDC {document_name} is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise JWTAuthenticationError(
                f"OIDC {document_name} must be an object"
            )
        return payload


def _normalized(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _local_cache_ttl(
    *,
    configured_ttl_seconds: int,
    shared_expires_at: dt.datetime | None,
) -> float:
    if shared_expires_at is None:
        return float(configured_ttl_seconds)
    expires_at = shared_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    remaining = (expires_at - dt.datetime.now(dt.UTC)).total_seconds()
    return max(0.001, min(float(configured_ttl_seconds), remaining))


def _header(headers: Mapping[str, str] | None, name: str) -> str | None:
    if headers is None:
        return None
    return _normalized(headers.get(name))


def local_operator_identity() -> SignerIdentity:
    return SignerIdentity(
        subject_id="local-ui",
        display_name="Local UI",
        role=None,
        identity_provider="local-ui",
        auth_source="none",
        identity_verified=False,
        ticket_reference=None,
    )


def extract_trusted_operator_identity(
    headers: Mapping[str, str] | None,
    *,
    trusted_headers_enabled: bool = True,
) -> SignerIdentity | None:
    if not trusted_headers_enabled:
        return None

    header_subject = _header(headers, TRUSTED_OPERATOR_ID_HEADER)
    header_name = _header(headers, TRUSTED_OPERATOR_NAME_HEADER)
    header_role = _header(headers, TRUSTED_OPERATOR_ROLE_HEADER)
    header_provider = _header(headers, TRUSTED_IDENTITY_PROVIDER_HEADER)

    if not (header_subject or header_name):
        return None

    display_name = header_name or header_subject or "trusted-operator"
    return SignerIdentity(
        subject_id=header_subject or display_name,
        display_name=display_name,
        role=header_role,
        identity_provider=header_provider or "trusted-header",
        auth_source="trusted_header",
        identity_verified=True,
        ticket_reference=None,
    )


def extract_bearer_operator_identity(
    headers: Mapping[str, str] | None,
    *,
    config: JWTVerificationConfig,
    verifier: OIDCJWTVerifier | None = None,
    now: dt.datetime | None = None,
) -> SignerIdentity | None:
    authorization = _header(headers, AUTHORIZATION_HEADER)
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise JWTAuthenticationError("Authorization header must use Bearer token syntax")
    if not config.enabled:
        raise JWTAuthenticationError("Bearer JWT authentication is not enabled")
    claims = (verifier or OIDCJWTVerifier(config)).verify(token.strip(), now=now)
    return identity_from_oidc_claims(
        claims,
        config=config,
        auth_source="oidc_jwt",
    )


def identity_from_oidc_claims(
    claims: Mapping[str, Any],
    *,
    config: JWTVerificationConfig,
    auth_source: str,
) -> SignerIdentity:
    subject_id = str(claims.get("sub") or "").strip()
    if not subject_id:
        raise JWTAuthenticationError("JWT subject claim is required")
    display_name = str(_claim_value(claims, config.name_claim) or subject_id).strip()
    role_value = _claim_value(claims, config.role_claim)
    if isinstance(role_value, list):
        claimed_roles = [
            str(value).strip() for value in role_value if str(value).strip()
        ]
        roles_by_key = {role.casefold(): role for role in claimed_roles}
        role = next(
            (
                roles_by_key[known_role.casefold()]
                for known_role in OIDC_ROLE_PRIORITY
                if known_role.casefold() in roles_by_key
            ),
            claimed_roles[0] if claimed_roles else None,
        )
    else:
        role = str(role_value).strip() if role_value is not None else None
    issuer = str(claims.get("iss") or config.issuer or "jwt-issuer")
    return SignerIdentity(
        subject_id=subject_id,
        display_name=display_name or subject_id,
        role=role or None,
        identity_provider=issuer,
        auth_source=auth_source,
        identity_verified=True,
        ticket_reference=None,
    )


def verify_jwt(
    token: str,
    *,
    config: JWTVerificationConfig,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    return OIDCJWTVerifier(config).verify(token, now=now)


def verify_hs256_jwt(
    token: str,
    *,
    config: JWTVerificationConfig,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    if "HS256" not in {value.upper() for value in config.algorithms}:
        raise JWTAuthenticationError("JWT algorithm is not allowed")
    return OIDCJWTVerifier(config).verify(token, now=now)


def _validate_registered_claims(
    claims: dict[str, Any],
    *,
    config: JWTVerificationConfig,
    now: dt.datetime | None,
) -> None:
    current = int((now or dt.datetime.now(dt.UTC)).timestamp())
    leeway = max(0, int(config.leeway_seconds))
    expires_at = _numeric_claim(claims, "exp", required=True)
    if current > expires_at + leeway:
        raise JWTAuthenticationError("JWT has expired")
    not_before = _numeric_claim(claims, "nbf", required=False)
    if not_before is not None and current + leeway < not_before:
        raise JWTAuthenticationError("JWT is not active yet")
    issued_at = _numeric_claim(claims, "iat", required=False)
    if issued_at is not None and issued_at > current + leeway:
        raise JWTAuthenticationError("JWT issued-at claim is in the future")
    if config.issuer and claims.get("iss") != config.issuer:
        raise JWTAuthenticationError("JWT issuer does not match")
    if config.audience and not _audience_matches(claims.get("aud"), config.audience):
        raise JWTAuthenticationError("JWT audience does not match")


def _numeric_claim(
    claims: dict[str, Any],
    name: str,
    *,
    required: bool,
) -> int | None:
    value = claims.get(name)
    if value is None:
        if required:
            raise JWTAuthenticationError(f"JWT {name} claim is required")
        return None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise JWTAuthenticationError(f"JWT {name} claim must be numeric")
    return int(value)


def _audience_matches(value: Any, expected: str) -> bool:
    if isinstance(value, str):
        return hmac.compare_digest(value, expected)
    if isinstance(value, list):
        return any(
            isinstance(item, str) and hmac.compare_digest(item, expected)
            for item in value
        )
    return False


def _claim_value(claims: dict[str, Any], path: str) -> Any:
    value: Any = claims
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _validate_provider_url(
    value: str,
    *,
    allow_insecure_http: bool,
) -> None:
    parsed = urlparse(value)
    allowed_schemes = {"https"}
    if allow_insecure_http:
        allowed_schemes.add("http")
    if parsed.scheme not in allowed_schemes or not parsed.hostname:
        raise JWTAuthenticationError("OIDC provider URL must use an allowed HTTP scheme")
    if parsed.username or parsed.password or parsed.fragment:
        raise JWTAuthenticationError(
            "OIDC provider URL must not contain credentials or a fragment"
        )


def build_signer_identity(
    payload: ReleaseDecisionCreate,
    *,
    headers: Mapping[str, str] | None = None,
    trusted_operator_identity: SignerIdentity | None = None,
) -> SignerIdentity:
    trusted_identity = trusted_operator_identity or extract_trusted_operator_identity(headers)
    if trusted_identity is not None:
        return replace(
            trusted_identity,
            role=trusted_identity.role or _normalized(payload.signer_role),
            ticket_reference=_normalized(payload.ticket_reference),
        )

    display_name = payload.decided_by.strip()
    return SignerIdentity(
        subject_id=_normalized(payload.signer_id) or display_name,
        display_name=display_name,
        role=_normalized(payload.signer_role),
        identity_provider=_normalized(payload.identity_provider) or "local-ui",
        auth_source="self_attested",
        identity_verified=False,
        ticket_reference=_normalized(payload.ticket_reference),
    )
