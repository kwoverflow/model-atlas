from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app.services.deployment_gate.evidence import stable_hash
from app.services.supply_chain import (
    IN_TOTO_STATEMENT_TYPE,
    PRODUCTION_CAPTURE_SCHEMA_VERSION,
    SUPPLY_CHAIN_PREDICATE_TYPE,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create development-only signed supply-chain evidence bundles."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    publisher = subparsers.add_parser("publisher")
    publisher.add_argument("--output-dir", type=Path, required=True)
    publisher.add_argument("--runtime-attestation-id", required=True)
    publisher.add_argument("--runtime-model-name", required=True)
    publisher.add_argument("--artifact-digest", required=True)
    publisher.add_argument("--artifact-attestation-hash", required=True)
    publisher.add_argument("--runtime-manifest-hash", required=True)
    publisher.add_argument("--publisher-issuer", default="model-atlas-demo-publisher")
    publisher.add_argument("--key-id", default="model-atlas-demo-2026")

    production = subparsers.add_parser("production")
    production.add_argument("--output-dir", type=Path, required=True)
    production.add_argument("--private-key", type=Path, required=True)
    production.add_argument("--key-id", default="model-atlas-demo-2026")
    production.add_argument("--collector-issuer", default="model-atlas-demo-collector")
    production.add_argument("--benchmark-run-id", required=True)
    production.add_argument("--deployment-configuration-id", required=True)
    production.add_argument("--runtime-attestation-id", required=True)
    production.add_argument("--supply-chain-attestation-id", required=True)
    production.add_argument("--artifact-digest", required=True)
    production.add_argument("--artifact-attestation-hash", required=True)
    production.add_argument("--supply-chain-attestation-hash", required=True)
    production.add_argument("--capture-started-at", required=True)
    production.add_argument("--capture-ended-at", required=True)
    production.add_argument("--result-count", type=int, required=True)
    production.add_argument("--metric-count", type=int, required=True)
    production.add_argument("--environment-name", required=True)
    args = parser.parse_args()

    summary = (
        _publisher_bundle(args)
        if args.command == "publisher"
        else _production_bundle(args)
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


def _publisher_bundle(args: argparse.Namespace) -> dict[str, Any]:
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    private_key_path = output_dir / "demo-publisher-private.pem"
    private_key = _load_or_create_private_key(private_key_path)
    jwks_path = output_dir / "publisher-jwks.json"
    _write_jwks(jwks_path, private_key=private_key, key_id=args.key_id)
    digest = _digest_hex(args.artifact_digest)
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
            "tools": {
                "components": [
                    {
                        "type": "application",
                        "name": "model-atlas-supply-chain-bundler",
                        "version": "v1",
                    }
                ]
            },
        },
        "components": [
            {
                "type": "machine-learning-model",
                "name": args.runtime_model_name,
                "version": "ollama-manifest",
                "hashes": [{"alg": "SHA-256", "content": digest}],
                "properties": [
                    {
                        "name": "model-atlas:runtime-attestation-id",
                        "value": args.runtime_attestation_id,
                    }
                ],
            }
        ],
    }
    sbom_path = output_dir / "cyclonedx-sbom.json"
    _write_json(sbom_path, sbom)
    claims = {
        "iss": args.publisher_issuer,
        "iat": int(dt.datetime.now(dt.UTC).timestamp()),
        "jti": f"model-supply-chain-{uuid4()}",
        "_type": IN_TOTO_STATEMENT_TYPE,
        "subject": [
            {
                "name": args.runtime_model_name,
                "digest": {"sha256": digest},
            }
        ],
        "predicateType": SUPPLY_CHAIN_PREDICATE_TYPE,
        "predicate": {
            "artifact_attestation_hash": args.artifact_attestation_hash,
            "runtime_manifest_hash": args.runtime_manifest_hash,
            "builder": {"id": args.publisher_issuer},
            "buildType": "model-atlas.dev/ollama-manifest-export/v1",
            "sbom": {
                "format": "CycloneDX",
                "spec_version": sbom["specVersion"],
                "digest": {"sha256": stable_hash(sbom)},
            },
        },
    }
    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": args.key_id},
    )
    request_path = output_dir / "supply-chain-request.json"
    _write_json(
        request_path,
        {
            "model_artifact_attestation_id": args.runtime_attestation_id,
            "signed_statement_jws": token,
            "sbom_json": sbom,
            "notes": "Development-only publisher evidence generated by Model Atlas Sprint 5G.",
        },
    )
    return {
        "jwks_path": str(jwks_path),
        "private_key_path": str(private_key_path),
        "sbom_path": str(sbom_path),
        "request_path": str(request_path),
        "publisher_issuer": args.publisher_issuer,
        "statement_id": claims["jti"],
        "sbom_digest": stable_hash(sbom),
    }


def _production_bundle(args: argparse.Namespace) -> dict[str, Any]:
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    private_key = serialization.load_pem_private_key(
        args.private_key.read_bytes(),
        password=None,
    )
    claims = {
        "iss": args.collector_issuer,
        "iat": int(dt.datetime.now(dt.UTC).timestamp()),
        "jti": f"production-capture-{uuid4()}",
        "schema_version": PRODUCTION_CAPTURE_SCHEMA_VERSION,
        "benchmark_run_id": args.benchmark_run_id,
        "deployment_configuration_id": args.deployment_configuration_id,
        "model_artifact_attestation_id": args.runtime_attestation_id,
        "supply_chain_attestation_id": args.supply_chain_attestation_id,
        "subject_digest": f"sha256:{_digest_hex(args.artifact_digest)}",
        "artifact_attestation_hash": args.artifact_attestation_hash,
        "supply_chain_attestation_hash": args.supply_chain_attestation_hash,
        "capture_started_at": args.capture_started_at,
        "capture_ended_at": args.capture_ended_at,
        "result_count": args.result_count,
        "metric_count": args.metric_count,
        "source_environment": {"name": args.environment_name},
    }
    token = jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": args.key_id},
    )
    request_path = output_dir / "production-receipt-request.json"
    _write_json(
        request_path,
        {
            "signed_statement_jws": token,
            "notes": "Signed production capture receipt generated by Model Atlas.",
        },
    )
    return {
        "request_path": str(request_path),
        "collector_issuer": args.collector_issuer,
        "capture_id": claims["jti"],
    }


def _load_or_create_private_key(path: Path) -> Any:
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=3072)
    path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return private_key


def _write_jwks(path: Path, *, private_key: Any, key_id: str) -> None:
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": key_id, "alg": "RS256", "use": "sig"})
    _write_json(path, {"keys": [jwk]})


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _digest_hex(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("sha256:"):
        normalized = normalized[7:]
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError("artifact digest must be SHA-256")
    return normalized


if __name__ == "__main__":
    main()
