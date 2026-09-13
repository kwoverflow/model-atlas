from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jwt

from app.services.deployment_gate.evidence import stable_hash
from app.validators import DomainValidationError

MAX_JWKS_BYTES = 1_048_576
MAX_SIGNED_STATEMENT_LENGTH = 262_144


@dataclass(frozen=True)
class VerifiedSignedStatement:
    header: dict[str, Any]
    claims: dict[str, Any]
    key_fingerprint: str

    @property
    def issuer(self) -> str:
        return str(self.claims["iss"])

    @property
    def statement_id(self) -> str:
        return str(self.claims["jti"])

    @property
    def key_id(self) -> str:
        return str(self.header["kid"])

    @property
    def algorithm(self) -> str:
        return str(self.header["alg"])


@dataclass(frozen=True)
class UnverifiedSignedStatementIdentity:
    issuer: str
    key_id: str
    algorithm: str


def verify_signed_statement(
    compact_jws: str,
    *,
    jwks_path: str | None,
    allowed_issuers: list[str],
    allowed_algorithms: list[str],
    max_age_seconds: int,
    now: dt.datetime | None = None,
) -> VerifiedSignedStatement:
    if not jwks_path or not allowed_issuers or not allowed_algorithms:
        raise DomainValidationError("signed evidence trust policy is not configured")
    identity = inspect_signed_statement(compact_jws)
    if identity.algorithm not in allowed_algorithms:
        raise DomainValidationError("signed evidence JWS algorithm is not allowed")
    jwk = _load_jwk(
        jwks_path,
        key_id=identity.key_id,
        algorithm=identity.algorithm,
    )
    return verify_signed_statement_with_jwk(
        compact_jws,
        jwk=jwk,
        allowed_issuers=allowed_issuers,
        allowed_algorithms=allowed_algorithms,
        max_age_seconds=max_age_seconds,
        now=now,
    )


def inspect_signed_statement(compact_jws: str) -> UnverifiedSignedStatementIdentity:
    token = compact_jws.strip()
    if not token or len(token) > MAX_SIGNED_STATEMENT_LENGTH:
        raise DomainValidationError("signed evidence JWS is missing or too large")
    try:
        header = jwt.get_unverified_header(token)
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
            algorithms=[],
        )
    except jwt.PyJWTError as exc:
        raise DomainValidationError("signed evidence JWS header or payload is invalid") from exc
    if not isinstance(claims, dict):
        raise DomainValidationError("signed evidence JWS payload must be an object")
    key_id = str(header.get("kid") or "").strip()
    algorithm = str(header.get("alg") or "").strip()
    issuer = str(claims.get("iss") or "").strip()
    if not key_id:
        raise DomainValidationError("signed evidence JWS kid is required")
    if not algorithm:
        raise DomainValidationError("signed evidence JWS algorithm is required")
    if not issuer:
        raise DomainValidationError("signed evidence JWS issuer is required")
    return UnverifiedSignedStatementIdentity(
        issuer=issuer,
        key_id=key_id,
        algorithm=algorithm,
    )


def verify_signed_statement_with_jwk(
    compact_jws: str,
    *,
    jwk: dict[str, Any],
    allowed_issuers: list[str],
    allowed_algorithms: list[str],
    max_age_seconds: int,
    now: dt.datetime | None = None,
) -> VerifiedSignedStatement:
    token = compact_jws.strip()
    identity = inspect_signed_statement(token)
    if identity.algorithm not in allowed_algorithms:
        raise DomainValidationError("signed evidence JWS algorithm is not allowed")
    if identity.issuer not in allowed_issuers:
        raise DomainValidationError("signed evidence JWS issuer is not trusted")
    if str(jwk.get("kid") or "").strip() != identity.key_id:
        raise DomainValidationError("signed evidence JWK kid does not match the JWS")
    jwk_algorithm = str(jwk.get("alg") or "").strip()
    if jwk_algorithm and jwk_algorithm != identity.algorithm:
        raise DomainValidationError("signed evidence JWK algorithm does not match the JWS")
    if str(jwk.get("use") or "sig") != "sig":
        raise DomainValidationError("signed evidence JWK is not a signing key")
    try:
        signing_key = jwt.PyJWK.from_dict(jwk, algorithm=identity.algorithm).key
        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[identity.algorithm],
            issuer=allowed_issuers,
            options={
                "verify_aud": False,
                "require": ["iss", "iat", "jti"],
            },
        )
    except jwt.InvalidSignatureError as exc:
        raise DomainValidationError("signed evidence JWS signature is invalid") from exc
    except jwt.InvalidIssuerError as exc:
        raise DomainValidationError("signed evidence JWS issuer is not trusted") from exc
    except jwt.PyJWTError as exc:
        raise DomainValidationError("signed evidence JWS claims are invalid") from exc
    if not isinstance(claims, dict):
        raise DomainValidationError("signed evidence JWS payload must be an object")
    statement_id = str(claims.get("jti") or "").strip()
    if not statement_id or len(statement_id) > 200:
        raise DomainValidationError("signed evidence JWS jti is invalid")
    observed_at = now or dt.datetime.now(dt.UTC)
    issued_at = _issued_at(claims.get("iat"))
    age_seconds = (observed_at - issued_at).total_seconds()
    if age_seconds < -60:
        raise DomainValidationError("signed evidence JWS was issued in the future")
    if age_seconds > max_age_seconds:
        raise DomainValidationError("signed evidence JWS is older than the trust policy allows")
    return VerifiedSignedStatement(
        header=dict(jwt.get_unverified_header(token)),
        claims=dict(claims),
        key_fingerprint=stable_hash(jwk),
    )


def _load_jwk(path_value: str, *, key_id: str, algorithm: str) -> dict[str, Any]:
    path = Path(path_value)
    try:
        if not path.is_file() or path.stat().st_size > MAX_JWKS_BYTES:
            raise DomainValidationError("signed evidence JWKS file is missing or too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except DomainValidationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DomainValidationError("signed evidence JWKS file is invalid") from exc
    keys = payload.get("keys") if isinstance(payload, dict) else None
    if not isinstance(keys, list):
        raise DomainValidationError("signed evidence JWKS must contain a keys list")
    matching = [
        key
        for key in keys
        if isinstance(key, dict) and str(key.get("kid") or "") == key_id
    ]
    if len(matching) != 1:
        raise DomainValidationError("signed evidence JWS kid is unknown or ambiguous")
    jwk = dict(matching[0])
    jwk_algorithm = str(jwk.get("alg") or "").strip()
    if jwk_algorithm and jwk_algorithm != algorithm:
        raise DomainValidationError("signed evidence JWK algorithm does not match the JWS")
    if str(jwk.get("use") or "sig") != "sig":
        raise DomainValidationError("signed evidence JWK is not a signing key")
    return jwk


def _issued_at(value: Any) -> dt.datetime:
    if isinstance(value, bool):
        raise DomainValidationError("signed evidence JWS iat is invalid")
    try:
        timestamp = float(value)
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("signed evidence JWS iat is invalid") from exc
    try:
        return dt.datetime.fromtimestamp(timestamp, tz=dt.UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise DomainValidationError("signed evidence JWS iat is invalid") from exc
