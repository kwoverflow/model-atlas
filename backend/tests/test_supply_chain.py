from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.routes import supply_chain as supply_chain_routes
from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    DeploymentConfiguration,
    EvaluationCase,
    GateEvaluation,
    ModelArtifactAttestation,
)
from app.schemas import GateEvaluationCreate
from app.services.deployment_gate.evaluator import create_gate_evaluation
from app.services.deployment_gate.evidence import stable_hash
from app.services.evidence_trust import summarize_gate_evidence_trust
from app.services.supply_chain import verified_production_run_ids
from app.services.trust_registry import transparency_leaf_hash
from tests.test_deployment_gate import _build_gate_graph

DIGEST = f"sha256:{'a' * 64}"


def _operator_headers(
    subject: str = "supply-chain-verifier",
    role: str = "ML Ops Lead",
) -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": subject,
        "x-model-atlas-operator-name": subject.replace("-", " ").title(),
        "x-model-atlas-operator-role": role,
    }


def _trust_key(
    tmp_path: Path,
    *,
    key_id: str = "publisher-2026",
) -> tuple[Any, Path, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": key_id, "alg": "RS256", "use": "sig"})
    path = tmp_path / f"{key_id}-jwks.json"
    path.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")
    return private_key, path, jwk


def _runtime_attestation(
    db: Session,
    ids: dict[str, Any],
) -> tuple[DeploymentConfiguration, ModelArtifactAttestation, BenchmarkRun]:
    deployment = db.get(
        DeploymentConfiguration,
        ids["deployment_configuration_id"],
    )
    assert deployment is not None
    deployment.model_artifact.checksum = DIGEST
    manifest = {
        "manifest_version": "model-artifact-manifest-v1",
        "runtime_provider": "test-runtime",
        "runtime_model_name": deployment.model_artifact.artifact_name,
        "source_uri": "https://registry.example.test",
        "digest_algorithm": "sha256",
        "digest_value": DIGEST,
        "size_bytes": 1234,
        "details": {},
    }
    attestation = ModelArtifactAttestation(
        model_artifact_id=deployment.model_artifact_id,
        manifest_version="model-artifact-manifest-v1",
        runtime_provider="test-runtime",
        runtime_model_name=deployment.model_artifact.artifact_name,
        source_uri="https://registry.example.test",
        digest_algorithm="sha256",
        digest_value=DIGEST,
        manifest_hash=stable_hash(manifest),
        manifest_json=manifest,
        verification_method="test_registry_api",
        status="verified",
        attested_at=dt.datetime.now(dt.UTC),
        attested_by_identity_json={"subject_id": "runtime-attestor"},
        identity_verified=True,
        attestation_hash=stable_hash(
            {"artifact": str(deployment.model_artifact_id), "digest": DIGEST}
        ),
    )
    db.add(attestation)
    run = db.scalar(
        select(BenchmarkRun).where(
            BenchmarkRun.deployment_configuration_id == deployment.id
        )
    )
    assert run is not None
    db.commit()
    db.refresh(attestation)
    return deployment, attestation, run


def _sbom(artifact_name: str) -> dict[str, Any]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": "urn:uuid:11111111-1111-1111-1111-111111111111",
        "version": 1,
        "components": [
            {
                "type": "machine-learning-model",
                "name": artifact_name,
                "version": "test-v1",
                "hashes": [{"alg": "SHA-256", "content": DIGEST[7:]}],
            }
        ],
    }


def _supply_chain_token(
    private_key: Any,
    *,
    runtime_attestation: ModelArtifactAttestation,
    sbom: dict[str, Any],
    statement_id: str = "supply-chain-test-1",
) -> str:
    claims = {
        "iss": "test-model-publisher",
        "iat": int(time.time()),
        "jti": statement_id,
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "name": runtime_attestation.runtime_model_name,
                "digest": {"sha256": DIGEST[7:]},
            }
        ],
        "predicateType": (
            "https://model-atlas.dev/attestations/model-supply-chain/v1"
        ),
        "predicate": {
            "artifact_attestation_hash": runtime_attestation.attestation_hash,
            "runtime_manifest_hash": runtime_attestation.manifest_hash,
            "builder": {"id": "test-model-publisher"},
            "sbom": {
                "format": "CycloneDX",
                "spec_version": sbom["specVersion"],
                "digest": {"sha256": stable_hash(sbom)},
            },
        },
    }
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "publisher-2026"},
    )


def _production_token(
    private_key: Any,
    *,
    deployment: DeploymentConfiguration,
    runtime_attestation: ModelArtifactAttestation,
    supply_chain_attestation: dict[str, Any],
    run: BenchmarkRun,
    result_count: int = 3,
    metric_count: int = 3,
) -> str:
    claims = {
        "iss": "test-production-collector",
        "iat": int(time.time()),
        "jti": "production-capture-test-1",
        "schema_version": "model-atlas-production-capture-v1",
        "benchmark_run_id": str(run.id),
        "deployment_configuration_id": str(deployment.id),
        "model_artifact_attestation_id": str(runtime_attestation.id),
        "supply_chain_attestation_id": supply_chain_attestation["id"],
        "subject_digest": DIGEST,
        "artifact_attestation_hash": runtime_attestation.attestation_hash,
        "supply_chain_attestation_hash": supply_chain_attestation[
            "attestation_hash"
        ],
        "capture_started_at": run.started_at.isoformat(),
        "capture_ended_at": run.completed_at.isoformat(),
        "result_count": result_count,
        "metric_count": metric_count,
        "source_environment": {
            "name": "production-test",
            "region": "local-fixture",
        },
    }
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": "publisher-2026"},
    )


def _register_trust_root(
    client: TestClient,
    *,
    jwk: dict[str, Any],
    purpose: str,
    issuer: str,
    trust_tier: str = "internal_ca",
    source_type: str = "internal_ca",
    supersedes_trust_root_id: str | None = None,
    subject: str = "trust-root-registrar",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/trust-registry/roots",
        headers=_operator_headers(subject, "Model Governance"),
        json={
            "name": f"{issuer} {purpose}",
            "purpose": purpose,
            "issuer": issuer,
            "key_id": jwk["kid"],
            "algorithm": jwk["alg"],
            "public_key_jwk_json": jwk,
            "trust_tier": trust_tier,
            "source_type": source_type,
            "source_uri": "spiffe://model-atlas.test/trust-root",
            "supersedes_trust_root_id": supersedes_trust_root_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["trust_root"]


def _transparency_entry(attestation: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "model-atlas-transparency-entry-v1",
        "supply_chain_attestation_id": attestation["id"],
        "attestation_hash": attestation["attestation_hash"],
        "statement_id": attestation["statement_id"],
        "subject_digest": attestation["subject_digest"],
    }


def _transparency_token(
    private_key: Any,
    *,
    entry: dict[str, Any],
    key_id: str = "publisher-2026",
) -> str:
    leaf_hash = transparency_leaf_hash(entry)
    claims = {
        "iss": "test-transparency-log",
        "iat": int(time.time()),
        "jti": "transparency-proof-test-1",
        "schema_version": "model-atlas-transparency-checkpoint-v1",
        "log_id": "test-transparency-log",
        "tree_size": 1,
        "root_hash": leaf_hash,
        "leaf_hash": leaf_hash,
        "integrated_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    return jwt.encode(
        claims,
        private_key,
        algorithm="RS256",
        headers={"kid": key_id},
    )


def _configure_trust(monkeypatch: Any, jwks_path: Path) -> None:
    monkeypatch.setattr(
        supply_chain_routes.settings,
        "model_publisher_jwks_path",
        str(jwks_path),
    )
    monkeypatch.setattr(
        supply_chain_routes.settings,
        "model_publisher_allowed_issuers",
        ["test-model-publisher"],
    )
    monkeypatch.setattr(
        supply_chain_routes.settings,
        "production_evidence_jwks_path",
        str(jwks_path),
    )
    monkeypatch.setattr(
        supply_chain_routes.settings,
        "production_evidence_allowed_issuers",
        ["test-production-collector"],
    )


def test_signed_supply_chain_attestation_is_verified_and_revoked_append_only(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    ids = _build_gate_graph(db_session, config_name="signed-supply-chain")
    deployment, runtime_attestation, _run = _runtime_attestation(db_session, ids)
    private_key, jwks_path, _jwk = _trust_key(tmp_path)
    _configure_trust(monkeypatch, jwks_path)
    sbom = _sbom(deployment.model_artifact.artifact_name)
    token = _supply_chain_token(
        private_key,
        runtime_attestation=runtime_attestation,
        sbom=sbom,
    )

    response = client.post(
        "/api/v1/supply-chain/model-attestations",
        headers=_operator_headers(),
        json={
            "model_artifact_attestation_id": str(runtime_attestation.id),
            "signed_statement_jws": token,
            "sbom_json": sbom,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["attestation"]["status"] == "verified"
    assert body["attestation"]["signature_verified"] is True
    assert body["attestation"]["sbom_digest"] == stable_hash(sbom)
    assert body["attestation"]["publisher_trust_tier"] == "development"
    assert body["attestation"]["transparency_status"] == "missing"
    assert body["attestation"]["production_eligible"] is False

    repeated = client.post(
        "/api/v1/supply-chain/model-attestations",
        headers=_operator_headers(),
        json={
            "model_artifact_attestation_id": str(runtime_attestation.id),
            "signed_statement_jws": token,
            "sbom_json": sbom,
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["created"] is False

    self_revocation = client.post(
        f"/api/v1/supply-chain/model-attestations/{body['attestation']['id']}/revocations",
        headers=_operator_headers(),
        json={"reason": "test self revocation"},
    )
    assert self_revocation.status_code == 422
    assert "separation" in self_revocation.text

    revocation = client.post(
        f"/api/v1/supply-chain/model-attestations/{body['attestation']['id']}/revocations",
        headers=_operator_headers("supply-chain-revoker", "SRE Lead"),
        json={
            "reason": "publisher key compromise drill",
            "ticket_reference": "SEC-5G-1",
        },
    )
    assert revocation.status_code == 201, revocation.text
    records = client.get(
        "/api/v1/supply-chain/model-attestations",
        params={"model_artifact_id": str(deployment.model_artifact_id)},
    ).json()
    assert records[0]["status"] == "revoked"
    assert records[0]["revocation_count"] == 1


def test_signed_production_receipt_controls_production_trust(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="signed-production",
        data_source="production_captured",
    )
    deployment, runtime_attestation, run = _runtime_attestation(db_session, ids)
    private_key, jwks_path, jwk = _trust_key(tmp_path)
    _configure_trust(monkeypatch, jwks_path)
    _register_trust_root(
        client,
        jwk=jwk,
        purpose="model_publisher",
        issuer="test-model-publisher",
    )
    collector_root = _register_trust_root(
        client,
        jwk=jwk,
        purpose="production_collector",
        issuer="test-production-collector",
    )
    _register_trust_root(
        client,
        jwk=jwk,
        purpose="transparency_log",
        issuer="test-transparency-log",
    )
    sbom = _sbom(deployment.model_artifact.artifact_name)
    supply_response = client.post(
        "/api/v1/supply-chain/model-attestations",
        headers=_operator_headers(),
        json={
            "model_artifact_attestation_id": str(runtime_attestation.id),
            "signed_statement_jws": _supply_chain_token(
                private_key,
                runtime_attestation=runtime_attestation,
                sbom=sbom,
            ),
            "sbom_json": sbom,
        },
    )
    assert supply_response.status_code == 201, supply_response.text
    supply_attestation = supply_response.json()["attestation"]
    assert supply_attestation["publisher_trust_tier"] == "internal_ca"
    assert supply_attestation["production_eligible"] is False

    transparency_entry = _transparency_entry(supply_attestation)
    transparency_response = client.post(
        "/api/v1/trust-registry/transparency-proofs",
        headers=_operator_headers("transparency-verifier", "SRE Lead"),
        json={
            "supply_chain_attestation_id": supply_attestation["id"],
            "signed_checkpoint_jws": _transparency_token(
                private_key,
                entry=transparency_entry,
            ),
            "entry_json": transparency_entry,
            "log_index": 0,
            "inclusion_path": [],
        },
    )
    assert transparency_response.status_code == 201, transparency_response.text
    assert transparency_response.json()["proof"]["production_eligible"] is True

    standard_case = db_session.scalar(
        select(EvaluationCase)
        .where(EvaluationCase.evaluation_suite_id == ids["evaluation_suite_id"])
        .where(EvaluationCase.criticality == "standard")
    )
    assert standard_case is not None
    for index in range(17):
        db_session.add(
            BenchmarkResult(
                benchmark_run_id=run.id,
                evaluation_case_id=standard_case.id,
                sample_id=f"signed-production-extra-{index:02d}",
                quality_score=0.92,
                exact_match=True,
                json_valid=True,
                tool_call_valid=False,
                groundedness_score=0.92,
                faithfulness_score=0.92,
                human_label="reviewed-pass",
                normalized_output="{\"ok\": true}",
                metadata_json={
                    "judge_label": {"applied": True, "source": "human_review"}
                },
                data_source="production_captured",
            )
        )
    db_session.commit()

    assert verified_production_run_ids(db_session, {run.id}) == set()
    receipt_response = client.post(
        "/api/v1/supply-chain/production-receipts",
        headers=_operator_headers("production-evidence-verifier", "SRE Lead"),
        json={
            "signed_statement_jws": _production_token(
                private_key,
                deployment=deployment,
                runtime_attestation=runtime_attestation,
                supply_chain_attestation=supply_attestation,
                run=run,
                result_count=20,
            )
        },
    )
    assert receipt_response.status_code == 201, receipt_response.text
    assert receipt_response.json()["receipt"]["result_count"] == 20
    assert receipt_response.json()["receipt"]["production_eligible"] is True
    assert verified_production_run_ids(db_session, {run.id}) == {run.id}

    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    trust = summarize_gate_evidence_trust(db_session, gate)
    assert trust.production_captured_count == 20
    assert trust.unverified_production_captured_count == 0
    assert trust.production_readiness == "production_ready"
    assert isinstance(gate, GateEvaluation)

    collector_revocation = client.post(
        f"/api/v1/trust-registry/roots/{collector_root['id']}/actions",
        headers=_operator_headers("collector-key-revoker", "Admin"),
        json={
            "action_type": "revoked",
            "reason": "collector key compromise drill",
            "ticket_reference": "SEC-5H-2",
        },
    )
    assert collector_revocation.status_code == 201, collector_revocation.text
    assert verified_production_run_ids(db_session, {run.id}) == set()


def test_trust_root_rotation_and_revocation_are_append_only_and_separated(
    client: TestClient,
    tmp_path: Path,
) -> None:
    _old_private_key, _old_path, old_jwk = _trust_key(
        tmp_path,
        key_id="publisher-2026",
    )
    old_root = _register_trust_root(
        client,
        jwk=old_jwk,
        purpose="model_publisher",
        issuer="rotation-test-publisher",
    )
    self_revocation = client.post(
        f"/api/v1/trust-registry/roots/{old_root['id']}/actions",
        headers=_operator_headers("trust-root-registrar", "Model Governance"),
        json={"action_type": "revoked", "reason": "self-revocation should fail"},
    )
    assert self_revocation.status_code == 422
    assert "separation" in self_revocation.text

    _new_private_key, _new_path, new_jwk = _trust_key(
        tmp_path,
        key_id="publisher-2027",
    )
    new_root = _register_trust_root(
        client,
        jwk=new_jwk,
        purpose="model_publisher",
        issuer="rotation-test-publisher",
        supersedes_trust_root_id=old_root["id"],
    )
    roots = client.get("/api/v1/trust-registry/roots").json()
    statuses = {root["id"]: root["status"] for root in roots}
    assert statuses[old_root["id"]] == "retired"
    assert statuses[new_root["id"]] == "active"

    revocation = client.post(
        f"/api/v1/trust-registry/roots/{new_root['id']}/actions",
        headers=_operator_headers("independent-revoker", "Admin"),
        json={
            "action_type": "revoked",
            "reason": "key compromise exercise",
            "ticket_reference": "SEC-5H-1",
        },
    )
    assert revocation.status_code == 201, revocation.text
    assert revocation.json()["action_type"] == "revoked"
