from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkResult,
    BenchmarkRun,
    BenchmarkTask,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    HardwareProfile,
    InferenceMetric,
    Model,
    ModelArtifact,
    PromptVersion,
    WorkloadProfile,
)
from app.reference_workload.bootstrap import REFERENCE_SUITE_NAME
from app.reference_workload.corpus import ReferenceCorpusBundle
from app.reference_workload.manifest import canonical_json, stable_hash
from app.schemas import (
    BenchmarkExecutionCreate,
    BenchmarkTaskCreate,
    DeploymentConfigurationCreate,
    HardwareProfileCreate,
    ModelArtifactCreate,
    ModelCreate,
    PromptVersionCreate,
)
from app.services.benchmark_execution import run_benchmark_execution
from app.services.benchmarks import create_benchmark_task, create_prompt_version
from app.services.catalog import create_hardware_profile, create_model, create_model_artifact
from app.services.deployment_gate.evidence import EvidenceBundle, deployment_configuration_hash
from app.services.deployment_gate.metrics import calculate_metrics, metrics_to_scorecard
from app.services.deployment_gate_resources import create_deployment_configuration
from app.services.tool_execution import TOOL_REGISTRY_VERSION

RUNTIME_MATRIX_SCHEMA_VERSION = "model-atlas-reference-runtime-matrix-v1"
RUNTIME_MATRIX_RESULT_VERSION = "model-atlas-reference-runtime-matrix-result-v1"
RUNTIME_COMPARISON_VERSION = "model-atlas-reference-runtime-comparison-v1"
REFERENCE_WORKLOAD_SLUG = "model-atlas-operator-assistant-ko"
REFERENCE_TASK_NAME = "Model Atlas Korean Operator Assistant Evaluation"
ACTUAL_RUNTIME_DATA_SOURCE = "local_actual_runtime"
DIAGNOSTIC_RUNTIME_DATA_SOURCE = "local_actual_runtime_diagnostic"
DIAGNOSTIC_MAX_TOKENS = 384
ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SMOKE_CATEGORY_ORDER = (
    "rag_single_document",
    "rag_multi_document",
    "rag_version_or_scope",
    "insufficient_evidence_refusal",
    "tool_single_step",
    "rag_tool_combined",
    "tool_failure_recovery",
    "agent_multi_step",
)
PROMPT_BUNDLES = {
    "operator-assistant-ko-v1": (
        "Model Atlas 운영 지원 어시스턴트로 동작하세요. 제공된 실행 컨텍스트와 등록된 "
        "로컬 도구만 사용하고, 근거가 부족하면 추측하지 마세요. 숨은 추론은 출력하지 마세요."
    ),
    "operator-assistant-ko-v2": (
        "Model Atlas 운영 지원 어시스턴트로 동작하세요. 결론보다 검증 가능한 근거와 "
        "실행 경계를 우선하고, 불충분한 근거·허용되지 않은 동작·복구 실패를 명시적으로 "
        "거절하세요. 제공된 로컬 컨텍스트와 등록 도구만 사용하고 숨은 추론은 출력하지 마세요."
    ),
}


class RuntimeMatrixError(RuntimeError):
    pass


class RuntimeGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int = Field(default=512, gt=0, le=8192)


class RuntimeMatrixEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    enabled: bool = True
    base_url_env: str = Field(min_length=1, max_length=120)
    api_key_env: str | None = Field(default=None, max_length=120)
    model_env: str = Field(min_length=1, max_length=120)
    context_length: int = Field(gt=0, le=1_048_576)
    prompt_bundle: str = Field(min_length=1, max_length=120)
    generation: RuntimeGeneration = Field(default_factory=RuntimeGeneration)
    trials: int = Field(default=2, ge=1, le=20)
    concurrency: int = Field(default=1, ge=1, le=16)

    @field_validator("base_url_env", "api_key_env", "model_env")
    @classmethod
    def validate_environment_name(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_PATTERN.fullmatch(value):
            raise ValueError("environment variable names must use uppercase letters, digits, and _")
        return value

    @field_validator("prompt_bundle")
    @classmethod
    def validate_prompt_bundle(cls, value: str) -> str:
        if value not in PROMPT_BUNDLES:
            raise ValueError(f"unsupported prompt bundle: {value}")
        return value


class RuntimeMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["model-atlas-reference-runtime-matrix-v1"]
    workload_slug: Literal["model-atlas-operator-assistant-ko"]
    entries: tuple[RuntimeMatrixEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_entry_names(self) -> RuntimeMatrix:
        names = [entry.name for entry in self.entries]
        if len(names) != len(set(names)):
            raise ValueError("runtime matrix entry names must be unique")
        return self


class ResolvedRuntimeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entry: RuntimeMatrixEntry
    base_url: str
    model_name: str
    api_key_configured: bool


class RuntimeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_provider: str
    runtime_version: str | None
    model_name: str
    digest: str
    format: str
    family: str
    parameter_size: str | None = None
    quantization: str | None = None
    size_bytes: int | None = None
    context_length: int | None = None


def load_runtime_matrix(path: Path) -> RuntimeMatrix:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeMatrixError(f"runtime matrix could not be read: {path}: {exc}") from exc
    try:
        return RuntimeMatrix.model_validate(payload)
    except ValueError as exc:
        raise RuntimeMatrixError(f"runtime matrix is invalid: {exc}") from exc


def resolve_runtime_entry(
    entry: RuntimeMatrixEntry,
    *,
    environment: Mapping[str, str] | None = None,
) -> ResolvedRuntimeEntry:
    env = environment if environment is not None else os.environ
    missing = [name for name in (entry.base_url_env, entry.model_env) if not env.get(name)]
    if missing:
        raise RuntimeMatrixError(
            f"missing required environment variables: {', '.join(sorted(missing))}"
        )
    base_url = str(env[entry.base_url_env]).strip().rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeMatrixError(f"{entry.base_url_env} must contain an HTTP(S) base URL")
    return ResolvedRuntimeEntry(
        entry=entry,
        base_url=base_url,
        model_name=str(env[entry.model_env]).strip(),
        api_key_configured=bool(entry.api_key_env and env.get(entry.api_key_env)),
    )


def _request_json(
    url: str,
    *,
    api_key: str | None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    headers = {"accept": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeMatrixError(f"runtime returned a non-object response: {url}")
    return payload


def probe_runtime(
    resolved: ResolvedRuntimeEntry,
    *,
    environment: Mapping[str, str] | None = None,
) -> RuntimeObservation:
    env = environment if environment is not None else os.environ
    api_key = env.get(resolved.entry.api_key_env) if resolved.entry.api_key_env else None
    try:
        model_payload = _request_json(
            f"{resolved.base_url}/v1/models",
            api_key=api_key,
        )
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeMatrixError(
            f"runtime endpoint unavailable: {type(exc).__name__}: {exc}"
        ) from exc
    model_ids = [
        str(item["id"])
        for item in model_payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]
    if resolved.model_name not in model_ids:
        raise RuntimeMatrixError(
            f"configured model {resolved.model_name!r} was not found; observed: {model_ids[:10]}"
        )

    try:
        tags = _request_json(f"{resolved.base_url}/api/tags", api_key=api_key)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeMatrixError(
            "model digest could not be observed from the runtime registry"
        ) from exc
    record = next(
        (
            item
            for item in tags.get("models", [])
            if isinstance(item, dict)
            and resolved.model_name in {str(item.get("name")), str(item.get("model"))}
        ),
        None,
    )
    digest = str(record.get("digest", "")).removeprefix("sha256:") if record else ""
    if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise RuntimeMatrixError("model digest could not be observed from the runtime registry")
    details = record.get("details") if isinstance(record.get("details"), dict) else {}
    try:
        version_payload = _request_json(f"{resolved.base_url}/api/version", api_key=api_key)
        runtime_version = str(version_payload.get("version") or "") or None
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError):
        runtime_version = None
    return RuntimeObservation(
        runtime_provider="ollama_openai_compatible",
        runtime_version=runtime_version,
        model_name=resolved.model_name,
        digest=digest.lower(),
        format=str(details.get("format") or "runtime_registry"),
        family=str(details.get("family") or resolved.model_name.split(":", 1)[0]),
        parameter_size=(
            str(details.get("parameter_size")) if details.get("parameter_size") else None
        ),
        quantization=(
            str(details.get("quantization_level")) if details.get("quantization_level") else None
        ),
        size_bytes=int(record["size"]) if record and isinstance(record.get("size"), int) else None,
        context_length=(
            int(details["context_length"])
            if isinstance(details.get("context_length"), int)
            else None
        ),
    )


def _system_memory_gb() -> int:
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        page_count = int(os.sysconf("SC_PHYS_PAGES"))
        return max(1, round(page_size * page_count / 1024**3))
    except (AttributeError, OSError, ValueError):
        return 1


def _hardware_payload(environment: Mapping[str, str]) -> HardwareProfileCreate:
    cpu_name = (
        environment.get("REFERENCE_HARDWARE_CPU_NAME") or platform.processor() or "unobserved"
    )
    cpu_cores = int(environment.get("REFERENCE_HARDWARE_CPU_CORES") or os.cpu_count() or 1)
    ram_gb = int(environment.get("REFERENCE_HARDWARE_RAM_GB") or _system_memory_gb())
    gpu_name = environment.get("REFERENCE_HARDWARE_GPU_NAME") or "not_observed"
    gpu_vram_gb = int(environment.get("REFERENCE_HARDWARE_GPU_VRAM_GB") or 0)
    identity = {
        "cpu_name": cpu_name,
        "cpu_cores": cpu_cores,
        "ram_gb": ram_gb,
        "gpu_name": gpu_name,
        "gpu_vram_gb": gpu_vram_gb,
        "os_name": platform.platform(),
    }
    return HardwareProfileCreate(
        name=environment.get("REFERENCE_HARDWARE_NAME")
        or f"reference-local-runtime-{stable_hash(identity)[:12]}",
        **identity,
        notes="Observed by the reference runtime matrix; GPU fields may be explicitly unavailable.",
    )


def _ensure_hardware(db: Session, environment: Mapping[str, str]) -> HardwareProfile:
    payload = _hardware_payload(environment)
    existing = db.scalar(select(HardwareProfile).where(HardwareProfile.name == payload.name))
    return existing or create_hardware_profile(db, payload)


def _ensure_model_and_artifact(
    db: Session,
    observation: RuntimeObservation,
    *,
    requested_context_length: int,
) -> tuple[Model, ModelArtifact]:
    context_length = max(requested_context_length, observation.context_length or 0)
    model_name = f"reference-{observation.digest[:12]}-{observation.model_name}"[:160]
    model = db.scalar(select(Model).where(Model.name == model_name))
    if model is None:
        model = create_model(
            db,
            ModelCreate(
                provider="ollama",
                family=observation.family[:120],
                name=model_name,
                display_name=observation.model_name[:180],
                architecture_type="decoder_only_transformer",
                supports_text=True,
                supports_tool_calling=False,
                supports_structured_output=False,
                context_length=context_length,
                primary_languages=["ko"],
                notes="Identity created from an observed local runtime digest.",
            ),
        )
    checksum = f"sha256:{observation.digest}"
    artifact = db.scalar(
        select(ModelArtifact)
        .where(ModelArtifact.model_id == model.id)
        .where(ModelArtifact.artifact_name == observation.model_name)
        .where(ModelArtifact.checksum == checksum)
    )
    if artifact is None:
        artifact = create_model_artifact(
            db,
            ModelArtifactCreate(
                model_id=model.id,
                artifact_name=observation.model_name,
                format=observation.format[:80],
                quantization=observation.quantization,
                file_size_gb=(
                    round(observation.size_bytes / 1024**3, 6)
                    if observation.size_bytes is not None
                    else None
                ),
                context_limit=context_length,
                runtime_compatibility=["ollama", "openai_compatible"],
                checksum=checksum,
                notes=(
                    "Digest and model metadata observed from the local Ollama registry; "
                    f"parameter_size={observation.parameter_size or 'not_observed'}."
                ),
            ),
        )
    return model, artifact


def _ensure_task(db: Session) -> BenchmarkTask:
    task = db.scalar(select(BenchmarkTask).where(BenchmarkTask.name == REFERENCE_TASK_NAME))
    if task is not None:
        return task
    return create_benchmark_task(
        db,
        BenchmarkTaskCreate(
            name=REFERENCE_TASK_NAME,
            category="reference_workload",
            description="Korean operator RAG, Tool, refusal, recovery, and bounded Agent cases.",
            task_type="mixed_operator_assistance",
            language="ko",
            input_format="evaluation_case_v1",
            expected_output_format="mixed_structured_output",
            scoring_method="model_atlas_reference_scorers",
            dataset_version="reference-workload-1.0.0",
        ),
    )


def _ensure_prompt(db: Session, task: BenchmarkTask, bundle_name: str) -> PromptVersion:
    system_prompt = PROMPT_BUNDLES[bundle_name]
    prompt_hash = stable_hash(
        {
            "bundle": bundle_name,
            "system_prompt": system_prompt,
            "user_template": "{evaluation_case_json}",
        }
    )
    prompt = db.scalar(
        select(PromptVersion)
        .where(PromptVersion.benchmark_task_id == task.id)
        .where(PromptVersion.prompt_hash == prompt_hash)
    )
    if prompt is not None:
        return prompt
    return create_prompt_version(
        db,
        PromptVersionCreate(
            name=f"Reference operator prompt {bundle_name}",
            benchmark_task_id=task.id,
            system_prompt=system_prompt,
            user_template="{evaluation_case_json}",
            output_schema=None,
            prompt_hash=prompt_hash,
            version_label=bundle_name,
            notes="Versioned prompt bundle for the Sprint 6A runtime matrix.",
        ),
    )


def _ensure_configuration(
    db: Session,
    *,
    workload: WorkloadProfile,
    hardware: HardwareProfile,
    artifact: ModelArtifact,
    resolved: ResolvedRuntimeEntry,
    observation: RuntimeObservation,
    corpus_bundle: ReferenceCorpusBundle,
    mode: Literal["smoke", "portfolio", "diagnostic"] = "portfolio",
) -> DeploymentConfiguration:
    entry = resolved.entry
    prompt_hash = stable_hash(
        {
            "bundle": entry.prompt_bundle,
            "system_prompt": PROMPT_BUNDLES[entry.prompt_bundle],
            "user_template": "{evaluation_case_json}",
        }
    )
    runtime_config = {
        "base_url": resolved.base_url,
        "model": resolved.model_name,
        "api_key_env": entry.api_key_env,
        "model_digest": f"sha256:{observation.digest}",
        "remote": False,
    }
    if mode != "portfolio":
        runtime_config["reference_workload_mode"] = mode
    name_prefix = {
        "smoke": "Reference smoke",
        "diagnostic": "Reference diagnostic",
        "portfolio": "Reference runtime",
    }[mode]
    payload = DeploymentConfigurationCreate(
        name=f"{name_prefix}: {entry.name}",
        workload_profile_id=workload.id,
        hardware_profile_id=hardware.id,
        model_artifact_id=artifact.id,
        runtime_name=observation.runtime_provider,
        runtime_version=observation.runtime_version,
        runtime_config_json=runtime_config,
        context_length=entry.context_length,
        generation_config_json=entry.generation.model_dump(),
        prompt_bundle_json={
            "name": entry.prompt_bundle,
            "prompt_hash": prompt_hash,
        },
        output_schema_version="reference-workload-output-v1",
        tool_schema_version=TOOL_REGISTRY_VERSION,
        retrieval_config_json={
            "corpus_id": corpus_bundle.corpus.corpus_id,
            "corpus_version": corpus_bundle.corpus.corpus_version,
            "corpus_hash": corpus_bundle.corpus.corpus_hash,
            "retriever_id": "lexical_overlap",
            "retriever_version": "lexical-overlap-v1",
            "top_k": 5,
            "min_score": 0.0,
        },
        concurrency_target=entry.concurrency,
        status="ready",
        notes=(
            "Actual local-runtime smoke configuration; not Gate evidence."
            if mode == "smoke"
            else (
                "Actual local-runtime diagnostic configuration; not portfolio or Gate evidence."
                if mode == "diagnostic"
                else "Actual local-runtime matrix configuration; not production evidence."
            )
        ),
    )
    expected_hash = deployment_configuration_hash(payload.model_dump())
    existing = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.configuration_hash == expected_hash
        )
    )
    return existing or create_deployment_configuration(db, payload)


def _reference_records(
    db: Session,
    *,
    workload_profile_id: UUID,
    evaluation_suite_id: UUID,
) -> tuple[WorkloadProfile, EvaluationSuite]:
    workload = db.get(WorkloadProfile, workload_profile_id)
    suite = db.get(EvaluationSuite, evaluation_suite_id)
    if workload is None or workload.slug != REFERENCE_WORKLOAD_SLUG:
        raise RuntimeMatrixError("reference workload profile was not found")
    if (
        suite is None
        or suite.name != REFERENCE_SUITE_NAME
        or suite.workload_profile_id != workload.id
    ):
        raise RuntimeMatrixError("reference evaluation suite was not found")
    return workload, suite


def _smoke_case_ids(db: Session, suite_id: UUID, limit: int) -> list[str]:
    cases = list(
        db.scalars(
            select(EvaluationCase)
            .where(EvaluationCase.evaluation_suite_id == suite_id)
            .where(EvaluationCase.is_active.is_(True))
            .order_by(EvaluationCase.external_case_id)
        ).all()
    )
    selected: list[EvaluationCase] = []
    for category in SMOKE_CATEGORY_ORDER:
        match = next((case for case in cases if case.category == category), None)
        if match is not None and match not in selected:
            selected.append(match)
        if len(selected) >= limit:
            break
    remaining = sorted(
        (case for case in cases if case not in selected),
        key=lambda case: (case.criticality != "critical", case.external_case_id),
    )
    selected.extend(remaining[: max(0, limit - len(selected))])
    return [case.external_case_id for case in selected[:limit]]


def execute_runtime_matrix(
    db: Session,
    *,
    matrix: RuntimeMatrix,
    workload_profile_id: UUID,
    evaluation_suite_id: UUID,
    corpus_bundle: ReferenceCorpusBundle,
    mode: Literal["smoke", "portfolio", "diagnostic"],
    environment: Mapping[str, str] | None = None,
    max_cases: int | None = None,
    case_ids: list[str] | None = None,
    case_timeout_ms: int = 120_000,
) -> dict[str, Any]:
    env = environment if environment is not None else os.environ
    workload, suite = _reference_records(
        db,
        workload_profile_id=workload_profile_id,
        evaluation_suite_id=evaluation_suite_id,
    )
    active_case_count = int(
        db.scalar(
            select(func.count())
            .select_from(EvaluationCase)
            .where(EvaluationCase.evaluation_suite_id == suite.id)
            .where(EvaluationCase.is_active.is_(True))
        )
        or 0
    )
    enabled_entries = [entry for entry in matrix.entries if entry.enabled]
    diagnostic_case_ids = [case_id.strip() for case_id in case_ids or [] if case_id.strip()]
    if mode == "diagnostic":
        if not diagnostic_case_ids:
            raise RuntimeMatrixError("diagnostic mode requires at least one explicit case ID")
        if len(diagnostic_case_ids) != len(set(diagnostic_case_ids)):
            raise RuntimeMatrixError("diagnostic case IDs must be unique")
        if len(diagnostic_case_ids) > 20:
            raise RuntimeMatrixError("diagnostic mode is limited to 20 explicit case IDs")
        available_case_ids = set(
            db.scalars(
                select(EvaluationCase.external_case_id)
                .where(EvaluationCase.evaluation_suite_id == suite.id)
                .where(EvaluationCase.is_active.is_(True))
            ).all()
        )
        missing = sorted(set(diagnostic_case_ids) - available_case_ids)
        if missing:
            raise RuntimeMatrixError(
                "diagnostic cases were not found as active reference cases: " + ", ".join(missing)
            )
    elif diagnostic_case_ids:
        raise RuntimeMatrixError("explicit case IDs are supported only in diagnostic mode")
    if mode == "portfolio":
        errors = []
        if active_case_count < 60:
            errors.append(
                f"portfolio mode requires at least 60 active cases; found {active_case_count}"
            )
        if len(enabled_entries) < 3:
            errors.append(
                "portfolio mode requires at least 3 enabled configurations; "
                f"found {len(enabled_entries)}"
            )
        if any(entry.trials < 2 for entry in enabled_entries):
            errors.append("portfolio mode requires at least 2 trials per enabled configuration")
        if max_cases is not None and max_cases < 60:
            errors.append("portfolio mode max_cases cannot be lower than 60")
        if errors:
            raise RuntimeMatrixError("; ".join(errors))

    task = _ensure_task(db)
    hardware = _ensure_hardware(db, env)
    smoke_case_limit = min(max_cases or 10, 10)
    smoke_case_ids = _smoke_case_ids(db, suite.id, smoke_case_limit) if mode == "smoke" else None
    statuses: list[dict[str, Any]] = []
    smoke_completed = False
    for entry in matrix.entries:
        effective_entry = (
            entry.model_copy(
                update={
                    "generation": entry.generation.model_copy(
                        update={"max_tokens": DIAGNOSTIC_MAX_TOKENS}
                    )
                }
            )
            if mode == "diagnostic"
            else entry
        )
        base_status = {
            "name": entry.name,
            "enabled": entry.enabled,
            "model_env": entry.model_env,
            "prompt_bundle": entry.prompt_bundle,
            "trials": 1 if mode in {"smoke", "diagnostic"} else entry.trials,
            "concurrency": 1 if mode in {"smoke", "diagnostic"} else entry.concurrency,
            "generation": effective_entry.generation.model_dump(),
        }
        if not entry.enabled:
            statuses.append({**base_status, "status": "not_run", "reason": "entry disabled"})
            continue
        if mode == "smoke" and smoke_completed:
            statuses.append(
                {
                    **base_status,
                    "status": "not_run",
                    "reason": "smoke mode stops after the first successful configuration",
                }
            )
            continue
        try:
            resolved = resolve_runtime_entry(effective_entry, environment=env)
            observation = probe_runtime(resolved, environment=env)
            _, artifact = _ensure_model_and_artifact(
                db,
                observation,
                requested_context_length=entry.context_length,
            )
            prompt = _ensure_prompt(db, task, entry.prompt_bundle)
            configuration = _ensure_configuration(
                db,
                workload=workload,
                hardware=hardware,
                artifact=artifact,
                resolved=resolved,
                observation=observation,
                corpus_bundle=corpus_bundle,
                mode=mode,
            )
            outcome = run_benchmark_execution(
                db,
                BenchmarkExecutionCreate(
                    deployment_configuration_id=configuration.id,
                    evaluation_suite_id=suite.id,
                    benchmark_task_id=task.id,
                    prompt_version_id=prompt.id,
                    adapter_name="openai_compatible",
                    data_source=(
                        DIAGNOSTIC_RUNTIME_DATA_SOURCE
                        if mode == "diagnostic"
                        else ACTUAL_RUNTIME_DATA_SOURCE
                    ),
                    max_cases=smoke_case_limit if mode == "smoke" else max_cases,
                    evaluation_case_external_ids=(
                        diagnostic_case_ids if mode == "diagnostic" else smoke_case_ids
                    ),
                    seed=42,
                    reliability_mode=True,
                    trials_per_case=(1 if mode in {"smoke", "diagnostic"} else entry.trials),
                    concurrency=(1 if mode in {"smoke", "diagnostic"} else entry.concurrency),
                    case_timeout_ms=case_timeout_ms,
                ),
                rag_corpus_registry=corpus_bundle.registry,
            )
            statuses.append(
                {
                    **base_status,
                    "status": "completed",
                    "reason": None,
                    "runtime_provider": observation.runtime_provider,
                    "runtime_version": observation.runtime_version,
                    "model_name": observation.model_name,
                    "model_digest": f"sha256:{observation.digest}",
                    "model_artifact_id": str(artifact.id),
                    "deployment_configuration_id": str(configuration.id),
                    "configuration_hash": configuration.configuration_hash,
                    "benchmark_run_id": str(outcome.run.id),
                    "result_count": outcome.result_count,
                    "metric_count": outcome.metric_count,
                    "rag_evaluation_summary": outcome.rag_evaluation_summary,
                    "tool_execution_summary": outcome.tool_execution_summary,
                    "runtime_reliability_summary": outcome.runtime_reliability_summary,
                    "agent_execution_summary": outcome.agent_execution_summary,
                }
            )
            smoke_completed = True
        except Exception as exc:
            db.rollback()
            statuses.append(
                {
                    **base_status,
                    "status": "unavailable" if isinstance(exc, RuntimeMatrixError) else "failed",
                    "reason": str(exc),
                }
            )

    completed = [item for item in statuses if item["status"] == "completed"]
    distinct_artifacts = {
        item["model_artifact_id"] for item in completed if item.get("model_artifact_id")
    }
    portfolio_checks = {
        "active_case_count_at_least_60": active_case_count >= 60,
        "completed_configuration_count_at_least_3": len(completed) >= 3,
        "distinct_artifact_count_at_least_2": len(distinct_artifacts) >= 2,
        "all_completed_runs_have_at_least_60_results": bool(completed)
        and all(int(item.get("result_count", 0)) >= 60 for item in completed),
    }
    result = {
        "schema_version": RUNTIME_MATRIX_RESULT_VERSION,
        "generated_at": dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        "mode": mode,
        "matrix_hash": stable_hash(matrix.model_dump(mode="json")),
        "workload_profile_id": str(workload.id),
        "evaluation_suite_id": str(suite.id),
        "suite_hash": suite.suite_hash,
        "corpus_hash": corpus_bundle.corpus.corpus_hash,
        "active_case_count": active_case_count,
        "entries": statuses,
        "summary": {
            "configured_entry_count": len(matrix.entries),
            "enabled_entry_count": len(enabled_entries),
            "completed_entry_count": len(completed),
            "unavailable_entry_count": sum(item["status"] == "unavailable" for item in statuses),
            "failed_entry_count": sum(item["status"] == "failed" for item in statuses),
            "actual_result_count": sum(int(item.get("result_count", 0)) for item in completed),
            "distinct_artifact_count": len(distinct_artifacts),
        },
        "portfolio_completion": {
            "status": (
                "not_applicable"
                if mode == "diagnostic"
                else (
                    "ready"
                    if mode == "portfolio" and all(portfolio_checks.values())
                    else "incomplete"
                )
            ),
            "checks": portfolio_checks,
        },
        "production_readiness": "not_production_ready",
    }
    if mode == "diagnostic":
        result["diagnostic_scope"] = {
            "case_ids": diagnostic_case_ids,
            "max_tokens": DIAGNOSTIC_MAX_TOKENS,
            "authoritative_portfolio_evidence": False,
            "gate_evidence": False,
        }
        return result
    return build_stored_runtime_comparison(db, result)


def build_stored_runtime_comparison(
    db: Session,
    matrix_result: Mapping[str, Any],
) -> dict[str, Any]:
    if matrix_result.get("schema_version") != RUNTIME_MATRIX_RESULT_VERSION:
        raise RuntimeMatrixError("runtime matrix result schema version is unsupported")
    comparison_rows: list[dict[str, Any]] = []
    for entry in matrix_result.get("entries", []):
        if not isinstance(entry, dict) or entry.get("status") != "completed":
            continue
        try:
            run_id = UUID(str(entry["benchmark_run_id"]))
        except (KeyError, ValueError) as exc:
            raise RuntimeMatrixError("completed matrix entry has an invalid run ID") from exc
        run = db.get(BenchmarkRun, run_id)
        if run is None or run.status != "completed":
            raise RuntimeMatrixError(f"completed benchmark run was not found: {run_id}")
        if run.data_source != ACTUAL_RUNTIME_DATA_SOURCE:
            raise RuntimeMatrixError(f"benchmark run {run_id} is not actual local-runtime evidence")
        configuration = run.deployment_configuration
        suite = run.evaluation_suite
        if configuration is None or suite is None:
            raise RuntimeMatrixError(f"benchmark run {run_id} is missing comparison lineage")
        results = list(
            db.scalars(
                select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id == run.id)
            ).all()
        )
        metrics = list(
            db.scalars(
                select(InferenceMetric).where(InferenceMetric.benchmark_run_id == run.id)
            ).all()
        )
        case_ids = {
            result.evaluation_case_id for result in results if result.evaluation_case_id is not None
        }
        cases = list(
            db.scalars(select(EvaluationCase).where(EvaluationCase.id.in_(case_ids))).all()
        )
        cases_by_id = {case.id: case for case in cases}
        result_case_map = {
            result.id: cases_by_id[result.evaluation_case_id]
            for result in results
            if result.evaluation_case_id in cases_by_id
        }
        evidence = EvidenceBundle(
            deployment_configuration=configuration,
            evaluation_suite=suite,
            active_cases=cases,
            runs=[run],
            results=results,
            metrics=metrics,
            source_distribution={ACTUAL_RUNTIME_DATA_SOURCE: len(results)},
            result_case_map=result_case_map,
        )
        scorecard = metrics_to_scorecard(calculate_metrics(evidence))
        comparison_rows.append(
            {
                "entry_name": entry["name"],
                "benchmark_run_id": str(run.id),
                "deployment_configuration_id": str(configuration.id),
                "configuration_hash": configuration.configuration_hash,
                "model_artifact_id": str(run.model_artifact_id),
                "model_name": entry.get("model_name"),
                "model_digest": entry.get("model_digest"),
                "prompt_bundle": entry.get("prompt_bundle"),
                "result_count": len(results),
                "metric_count": len(metrics),
                "scorecard": scorecard,
            }
        )

    baseline = comparison_rows[0] if comparison_rows else None
    for row in comparison_rows:
        row["delta_from_baseline"] = _scorecard_delta(
            baseline["scorecard"] if baseline else {},
            row["scorecard"],
        )
    comparison = {
        "schema_version": RUNTIME_COMPARISON_VERSION,
        "baseline_entry_name": baseline["entry_name"] if baseline else None,
        "configuration_count": len(comparison_rows),
        "rows": comparison_rows,
    }
    comparison["comparison_hash"] = stable_hash(comparison)
    return {**dict(matrix_result), "stored_comparison": comparison}


def _scorecard_delta(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, float | None]:
    keys = (
        "mean_quality_score",
        "json_validity_rate",
        "tool_selection_accuracy",
        "tool_argument_validity_rate",
        "tool_execution_success_rate",
        "rag_groundedness_score",
        "rag_unsupported_claim_rate",
        "agent_task_success_rate",
        "critical_case_failure_rate",
        "p95_end_to_end_latency_ms",
        "oom_rate",
    )
    deltas: dict[str, float | None] = {}
    for key in keys:
        baseline_value = (baseline.get(key) or {}).get("value")
        candidate_value = (candidate.get(key) or {}).get("value")
        deltas[key] = (
            round(float(candidate_value) - float(baseline_value), 6)
            if baseline_value is not None and candidate_value is not None
            else None
        )
    return deltas


def write_runtime_matrix_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{canonical_json(result)}\n", encoding="utf-8")
