from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    DeploymentConfiguration,
    Model,
    ModelArtifact,
    ModelArtifactAttestation,
)
from app.schemas import (
    ObservedRuntimeConfigurationCreate,
    ObservedRuntimeConfigurationRead,
    RuntimeModelManifestRead,
)
from app.services.agent_jobs import MAINTENANCE_ROLES
from app.services.deployment_gate.evidence import (
    deployment_configuration_hash,
    stable_hash,
)
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

MODEL_ARTIFACT_MANIFEST_VERSION = "model-artifact-manifest-v1"
MODEL_ARTIFACT_ATTESTATION_VERSION = "model-artifact-attestation-v1"
OBSERVED_CONFIGURATION_VERSION = "observed-runtime-configuration-v1"
MAX_RUNTIME_MANIFEST_BYTES = 1_048_576
_SHA256_PATTERN = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")


def inspect_ollama_model(
    *,
    base_url: str,
    model_name: str,
    allowed_hosts: list[str],
    timeout_seconds: float = 5.0,
    opener: Callable[..., Any] = urlopen,
) -> RuntimeModelManifestRead:
    normalized_base_url = _validated_runtime_base_url(
        base_url,
        allowed_hosts=allowed_hosts,
    )
    normalized_model_name = model_name.strip()
    if not normalized_model_name:
        raise DomainValidationError("runtime model_name is required")
    request = Request(
        f"{normalized_base_url}/api/tags",
        headers={
            "accept": "application/json",
            "user-agent": "model-atlas-artifact-attestor/1",
        },
        method="GET",
    )
    try:
        with opener(
            request,
            timeout=max(0.5, min(float(timeout_seconds), 30.0)),
        ) as response:
            final_url = str(response.geturl())
            _validated_runtime_base_url(final_url, allowed_hosts=allowed_hosts)
            body = response.read(MAX_RUNTIME_MANIFEST_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise DomainValidationError("Ollama model registry request failed") from exc
    if len(body) > MAX_RUNTIME_MANIFEST_BYTES:
        raise DomainValidationError("Ollama model registry response is too large")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DomainValidationError("Ollama model registry response is invalid JSON") from exc
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise DomainValidationError("Ollama model registry response is missing models")
    model = next(
        (
            item
            for item in models
            if isinstance(item, dict)
            and normalized_model_name
            in {str(item.get("name") or ""), str(item.get("model") or "")}
        ),
        None,
    )
    if model is None:
        raise DomainValidationError(
            f"Ollama model was not found in the runtime registry: {normalized_model_name}"
        )
    digest = _normalized_sha256_digest(model.get("digest"))
    try:
        size_bytes = int(model.get("size"))
    except (TypeError, ValueError) as exc:
        raise DomainValidationError("Ollama model registry size is invalid") from exc
    if size_bytes <= 0:
        raise DomainValidationError("Ollama model registry size must be positive")
    details = model.get("details")
    normalized_details = dict(details) if isinstance(details, dict) else {}
    manifest_payload = {
        "manifest_version": MODEL_ARTIFACT_MANIFEST_VERSION,
        "runtime_provider": "ollama",
        "runtime_model_name": normalized_model_name,
        "source_uri": normalized_base_url,
        "digest_algorithm": "sha256",
        "digest_value": digest,
        "size_bytes": size_bytes,
        "modified_at": (
            str(model["modified_at"]) if model.get("modified_at") else None
        ),
        "details": normalized_details,
    }
    return RuntimeModelManifestRead(
        **manifest_payload,
        manifest_hash=stable_hash(manifest_payload),
    )


def create_observed_runtime_configuration(
    db: Session,
    *,
    payload: ObservedRuntimeConfigurationCreate,
    signer_identity: SignerIdentity,
    allowed_hosts: list[str],
    timeout_seconds: float = 5.0,
    opener: Callable[..., Any] = urlopen,
) -> ObservedRuntimeConfigurationRead:
    _assert_attestation_operator(signer_identity)
    source = db.get(
        DeploymentConfiguration,
        payload.source_deployment_configuration_id,
    )
    if source is None:
        raise DomainValidationError("source deployment_configuration was not found")
    manifest = inspect_ollama_model(
        base_url=payload.base_url,
        model_name=payload.model_name,
        allowed_hosts=allowed_hosts,
        timeout_seconds=timeout_seconds,
        opener=opener,
    )
    model, model_created = _get_or_create_observed_model(
        db,
        manifest=manifest,
        source=source,
    )
    artifact, artifact_created = _get_or_create_observed_artifact(
        db,
        model=model,
        manifest=manifest,
        source=source,
    )
    attestation, attestation_created = _get_or_create_attestation(
        db,
        artifact=artifact,
        manifest=manifest,
        signer_identity=signer_identity,
        notes=payload.notes,
    )
    configuration, configuration_created = _get_or_create_configuration(
        db,
        source=source,
        artifact=artifact,
        attestation=attestation,
        manifest=manifest,
        requested_name=payload.configuration_name,
        notes=payload.notes,
    )
    db.commit()
    for entity in (artifact, attestation, configuration):
        db.refresh(entity)
    return ObservedRuntimeConfigurationRead(
        schema_version=OBSERVED_CONFIGURATION_VERSION,
        manifest=manifest,
        model_artifact=artifact,
        attestation=attestation,
        deployment_configuration=configuration,
        model_created=model_created,
        artifact_created=artifact_created,
        attestation_created=attestation_created,
        configuration_created=configuration_created,
    )


def list_model_artifact_attestations(
    db: Session,
    *,
    model_artifact_id: Any | None = None,
    limit: int = 100,
) -> list[ModelArtifactAttestation]:
    query = select(ModelArtifactAttestation)
    if model_artifact_id is not None:
        query = query.where(
            ModelArtifactAttestation.model_artifact_id == model_artifact_id
        )
    return list(
        db.scalars(
            query.order_by(ModelArtifactAttestation.attested_at.desc()).limit(limit)
        ).all()
    )


def latest_verified_attestation(
    db: Session,
    *,
    model_artifact_id: Any,
) -> ModelArtifactAttestation | None:
    return db.scalar(
        select(ModelArtifactAttestation)
        .where(ModelArtifactAttestation.model_artifact_id == model_artifact_id)
        .where(ModelArtifactAttestation.status == "verified")
        .where(ModelArtifactAttestation.identity_verified.is_(True))
        .order_by(ModelArtifactAttestation.attested_at.desc())
    )


def _get_or_create_observed_model(
    db: Session,
    *,
    manifest: RuntimeModelManifestRead,
    source: DeploymentConfiguration,
) -> tuple[Model, bool]:
    model_name = _catalog_model_name(manifest.runtime_model_name)
    existing = db.scalar(select(Model).where(Model.name == model_name))
    if existing is not None:
        return existing, False
    details = manifest.details
    parameter_count = _parameter_count(manifest.runtime_model_name)
    family = str(details.get("family") or manifest.runtime_model_name.split(":", 1)[0])
    model = Model(
        provider="Observed Ollama runtime",
        family=family[:120],
        name=model_name,
        display_name=f"{manifest.runtime_model_name} (observed)"[:180],
        parameter_count_b=parameter_count,
        architecture_type=str(details.get("family") or "runtime-observed model")[:120],
        supports_text=True,
        supports_vision=False,
        supports_tool_calling=False,
        supports_structured_output=True,
        context_length=source.context_length,
        license_name=None,
        commercial_use_allowed=None,
        primary_languages=[],
        source_url=None,
        notes=(
            "Created from an attested Ollama runtime manifest. License and capability "
            "metadata require governance review."
        ),
    )
    db.add(model)
    db.flush()
    return model, True


def _get_or_create_observed_artifact(
    db: Session,
    *,
    model: Model,
    manifest: RuntimeModelManifestRead,
    source: DeploymentConfiguration,
) -> tuple[ModelArtifact, bool]:
    existing = db.scalar(
        select(ModelArtifact).where(ModelArtifact.checksum == manifest.digest_value)
    )
    if existing is not None:
        return existing, False
    quantization = manifest.details.get("quantization_level")
    artifact = ModelArtifact(
        model_id=model.id,
        artifact_name=f"{manifest.runtime_model_name}-ollama"[:180],
        format="ollama-manifest",
        quantization=str(quantization)[:80] if quantization else None,
        precision=None,
        file_size_gb=round(manifest.size_bytes / 1_000_000_000, 4),
        minimum_vram_gb=None,
        recommended_vram_gb=None,
        context_limit=source.context_length,
        runtime_compatibility=["ollama", "openai_compatible"],
        checksum=manifest.digest_value,
        is_active=True,
        notes="Artifact metadata was created from a verified Ollama registry manifest.",
    )
    db.add(artifact)
    db.flush()
    return artifact, True


def _get_or_create_attestation(
    db: Session,
    *,
    artifact: ModelArtifact,
    manifest: RuntimeModelManifestRead,
    signer_identity: SignerIdentity,
    notes: str | None,
) -> tuple[ModelArtifactAttestation, bool]:
    existing = db.scalar(
        select(ModelArtifactAttestation)
        .where(ModelArtifactAttestation.model_artifact_id == artifact.id)
        .where(ModelArtifactAttestation.digest_value == manifest.digest_value)
    )
    if existing is not None:
        return existing, False
    attested_at = dt.datetime.now(dt.UTC).replace(microsecond=0)
    attestation_payload = {
        "version": MODEL_ARTIFACT_ATTESTATION_VERSION,
        "model_artifact_id": str(artifact.id),
        "manifest_hash": manifest.manifest_hash,
        "digest_value": manifest.digest_value,
        "runtime_model_name": manifest.runtime_model_name,
        "verification_method": "ollama_registry_api",
        "attested_by": signer_identity.to_json(),
    }
    attestation = ModelArtifactAttestation(
        model_artifact_id=artifact.id,
        manifest_version=manifest.manifest_version,
        runtime_provider=manifest.runtime_provider,
        runtime_model_name=manifest.runtime_model_name,
        source_uri=manifest.source_uri,
        digest_algorithm=manifest.digest_algorithm,
        digest_value=manifest.digest_value,
        manifest_hash=manifest.manifest_hash,
        manifest_json=manifest.model_dump(mode="json"),
        verification_method="ollama_registry_api",
        status="verified",
        attested_at=attested_at,
        attested_by_identity_json=signer_identity.to_json(),
        identity_verified=True,
        attestation_hash=stable_hash(attestation_payload),
        notes=notes.strip() if notes and notes.strip() else None,
    )
    db.add(attestation)
    db.flush()
    return attestation, True


def _get_or_create_configuration(
    db: Session,
    *,
    source: DeploymentConfiguration,
    artifact: ModelArtifact,
    attestation: ModelArtifactAttestation,
    manifest: RuntimeModelManifestRead,
    requested_name: str | None,
    notes: str | None,
) -> tuple[DeploymentConfiguration, bool]:
    runtime_config = {
        **dict(source.runtime_config_json or {}),
        "base_url": manifest.source_uri,
        "model": manifest.runtime_model_name,
        "model_digest": manifest.digest_value,
        "artifact_attestation_hash": attestation.attestation_hash,
        "local_only": True,
    }
    name = (
        requested_name.strip()
        if requested_name and requested_name.strip()
        else f"{source.name} - {manifest.runtime_model_name}"
    )[:180]
    payload = {
        "name": name,
        "workload_profile_id": source.workload_profile_id,
        "hardware_profile_id": source.hardware_profile_id,
        "model_artifact_id": artifact.id,
        "runtime_name": "ollama",
        "runtime_version": "manifest-attested-v1",
        "runtime_config_json": runtime_config,
        "context_length": min(source.context_length, artifact.context_limit),
        "generation_config_json": dict(source.generation_config_json or {}),
        "prompt_bundle_json": dict(source.prompt_bundle_json or {}),
        "output_schema_version": source.output_schema_version,
        "tool_schema_version": source.tool_schema_version,
        "retrieval_config_json": (
            dict(source.retrieval_config_json)
            if isinstance(source.retrieval_config_json, dict)
            else None
        ),
        "concurrency_target": source.concurrency_target,
        "status": "draft",
        "notes": (
            notes.strip()
            if notes and notes.strip()
            else (
                "Draft cloned from configuration "
                f"{source.id} after verified runtime manifest inspection."
            )
        ),
    }
    configuration_hash = deployment_configuration_hash(payload)
    existing = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.configuration_hash == configuration_hash
        )
    )
    if existing is not None:
        return existing, False
    configuration = DeploymentConfiguration(
        **payload,
        configuration_hash=configuration_hash,
    )
    db.add(configuration)
    db.flush()
    return configuration, True


def _validated_runtime_base_url(value: str, *, allowed_hosts: list[str]) -> str:
    parsed = urlparse(value.strip())
    normalized_allowed_hosts = {host.strip().lower() for host in allowed_hosts if host.strip()}
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise DomainValidationError("runtime base_url must be an HTTP(S) URL")
    if hostname not in normalized_allowed_hosts:
        raise DomainValidationError("runtime base_url host is not allowed for attestation")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise DomainValidationError(
            "runtime base_url cannot contain credentials, query, or fragment"
        )
    path = parsed.path.rstrip("/")
    if path.endswith("/api/tags"):
        path = path[: -len("/api/tags")]
    if path.endswith("/v1"):
        path = path[:-3]
    if path not in {"", "/"}:
        raise DomainValidationError("runtime base_url path must be empty or /v1")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _normalized_sha256_digest(value: Any) -> str:
    match = _SHA256_PATTERN.fullmatch(str(value or "").strip())
    if match is None:
        raise DomainValidationError("Ollama model digest must be a SHA-256 value")
    return f"sha256:{match.group(1).lower()}"


def _catalog_model_name(runtime_model_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", runtime_model_name.lower())
    normalized = normalized.replace(":", "-").strip("-")
    return f"observed-{normalized}"[:160]


def _parameter_count(value: str) -> float | None:
    match = re.search(r"(?<![0-9])([0-9]+(?:\.[0-9]+)?)\s*b\b", value.lower())
    return float(match.group(1)) if match else None


def _assert_attestation_operator(identity: SignerIdentity) -> None:
    role = (identity.role or "").strip().lower()
    if not identity.identity_verified:
        raise DomainValidationError("model attestation requires verified identity")
    if role not in MAINTENANCE_ROLES:
        raise DomainValidationError("operator role cannot attest model artifacts")
