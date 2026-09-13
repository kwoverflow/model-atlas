from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import DeploymentConfiguration
from app.validators import DomainValidationError
from tests.test_deployment_gate import _build_gate_graph


class _OllamaRegistryHandler(BaseHTTPRequestHandler):
    digest = "d" * 64

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/api/tags":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(
            {
                "models": [
                    {
                        "name": "qwen2.5:0.5b",
                        "model": "qwen2.5:0.5b",
                        "modified_at": "2026-07-20T00:00:00Z",
                        "size": 397_000_000,
                        "digest": self.digest,
                        "details": {
                            "family": "qwen2",
                            "parameter_size": "494.03M",
                            "quantization_level": "Q4_K_M",
                        },
                    }
                ]
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def ollama_registry_url() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OllamaRegistryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _operator_headers() -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": "artifact-attestor",
        "x-model-atlas-operator-name": "Artifact Attestor",
        "x-model-atlas-operator-role": "ML Ops Lead",
    }


def test_observed_runtime_manifest_creates_draft_configuration_idempotently(
    client: TestClient,
    db_session: Session,
    ollama_registry_url: str,
) -> None:
    ids = _build_gate_graph(db_session, config_name="attestation-source")
    payload = {
        "source_deployment_configuration_id": str(
            ids["deployment_configuration_id"]
        ),
        "base_url": ollama_registry_url,
        "model_name": "qwen2.5:0.5b",
        "configuration_name": "Qwen2.5 0.5B Attested Ollama",
    }

    response = client.post(
        "/api/v1/model-validation/observed-runtime-configurations",
        headers=_operator_headers(),
        json=payload,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    digest = f"sha256:{_OllamaRegistryHandler.digest}"
    assert body["manifest"]["digest_value"] == digest
    assert body["model_artifact"]["checksum"] == digest
    assert body["attestation"]["status"] == "verified"
    assert body["attestation"]["identity_verified"] is True
    assert body["deployment_configuration"]["status"] == "draft"
    assert body["deployment_configuration"]["runtime_config_json"]["model"] == (
        "qwen2.5:0.5b"
    )
    assert body["deployment_configuration"]["runtime_config_json"][
        "model_digest"
    ] == digest
    assert body["model_created"] is True
    assert body["artifact_created"] is True
    assert body["attestation_created"] is True
    assert body["configuration_created"] is True

    repeated = client.post(
        "/api/v1/model-validation/observed-runtime-configurations",
        headers=_operator_headers(),
        json=payload,
    )
    assert repeated.status_code == 201
    assert repeated.json()["configuration_created"] is False
    assert repeated.json()["attestation_created"] is False

    configuration = db_session.get(
        DeploymentConfiguration,
        body["deployment_configuration"]["id"],
    )
    assert configuration is not None
    assert configuration.model_artifact.checksum == digest

    attestations = client.get(
        "/api/v1/model-validation/artifact-attestations",
        params={"model_artifact_id": body["model_artifact"]["id"]},
    )
    assert attestations.status_code == 200
    assert len(attestations.json()) == 1


def test_model_attestation_blocks_unverified_operator_and_unlisted_host(
    client: TestClient,
    db_session: Session,
    ollama_registry_url: str,
) -> None:
    ids = _build_gate_graph(db_session, config_name="attestation-policy")
    payload = {
        "source_deployment_configuration_id": str(
            ids["deployment_configuration_id"]
        ),
        "base_url": ollama_registry_url,
        "model_name": "qwen2.5:0.5b",
    }

    unverified = client.post(
        "/api/v1/model-validation/observed-runtime-configurations",
        json=payload,
    )
    assert unverified.status_code == 422
    assert "verified identity" in unverified.text

    forbidden_host = client.post(
        "/api/v1/model-validation/observed-runtime-configurations",
        headers=_operator_headers(),
        json={**payload, "base_url": "http://metadata.internal:11434"},
    )
    assert forbidden_host.status_code == 422
    assert "host is not allowed" in forbidden_host.text

    with pytest.raises(DomainValidationError, match="host is not allowed"):
        from app.services.model_artifact_attestation import inspect_ollama_model

        inspect_ollama_model(
            base_url="http://metadata.internal:11434",
            model_name="qwen2.5:0.5b",
            allowed_hosts=["127.0.0.1"],
        )
