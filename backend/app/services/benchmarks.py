from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

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
    ModelArtifact,
    PromptVersion,
)
from app.repositories import BaseRepository
from app.schemas import (
    BenchmarkResultCreate,
    BenchmarkRunCreate,
    BenchmarkTaskCreate,
    InferenceMetricCreate,
    PromptVersionCreate,
)
from app.services.experiment_lineage import (
    record_benchmark_run_event,
    record_prompt_version_created,
)
from app.validators import DomainValidationError, validate_vram_within_hardware

benchmark_tasks = BaseRepository(BenchmarkTask)
prompt_versions = BaseRepository(PromptVersion)
benchmark_runs = BaseRepository(BenchmarkRun)
benchmark_results = BaseRepository(BenchmarkResult)
inference_metrics = BaseRepository(InferenceMetric)
hardware_profiles = BaseRepository(HardwareProfile)
model_artifacts = BaseRepository(ModelArtifact)
deployment_configurations = BaseRepository(DeploymentConfiguration)
evaluation_suites = BaseRepository(EvaluationSuite)
evaluation_cases = BaseRepository(EvaluationCase)


def list_benchmark_tasks(db: Session, limit: int, offset: int) -> Sequence[BenchmarkTask]:
    return benchmark_tasks.list(db, limit=limit, offset=offset)


def create_benchmark_task(db: Session, payload: BenchmarkTaskCreate) -> BenchmarkTask:
    return benchmark_tasks.create(db, payload.model_dump())


def list_prompt_versions(db: Session, limit: int, offset: int) -> Sequence[PromptVersion]:
    return prompt_versions.list(db, limit=limit, offset=offset)


def create_prompt_version(db: Session, payload: PromptVersionCreate) -> PromptVersion:
    if benchmark_tasks.get(db, payload.benchmark_task_id) is None:
        raise DomainValidationError("prompt_version must reference an existing benchmark task")
    prompt = prompt_versions.create(db, payload.model_dump())
    record_prompt_version_created(db, prompt, commit=True)
    return prompt


def list_benchmark_runs(
    db: Session,
    *,
    limit: int,
    offset: int,
    model_artifact_id: UUID | None = None,
    benchmark_task_id: UUID | None = None,
    hardware_profile_id: UUID | None = None,
) -> Sequence[BenchmarkRun]:
    return benchmark_runs.list(
        db,
        limit=limit,
        offset=offset,
        filters={
            "model_artifact_id": model_artifact_id,
            "benchmark_task_id": benchmark_task_id,
            "hardware_profile_id": hardware_profile_id,
        },
    )


def create_benchmark_run(db: Session, payload: BenchmarkRunCreate) -> BenchmarkRun:
    if hardware_profiles.get(db, payload.hardware_profile_id) is None:
        raise DomainValidationError("benchmark_run must reference an existing hardware profile")
    artifact = model_artifacts.get(db, payload.model_artifact_id)
    if artifact is None:
        raise DomainValidationError("benchmark_run must reference an existing model artifact")
    if not artifact.is_active:
        raise DomainValidationError("benchmark runs cannot reference inactive model artifacts")
    if benchmark_tasks.get(db, payload.benchmark_task_id) is None:
        raise DomainValidationError("benchmark_run must reference an existing benchmark task")
    prompt = prompt_versions.get(db, payload.prompt_version_id)
    if prompt is None:
        raise DomainValidationError("benchmark_run must reference an existing prompt version")
    if prompt.benchmark_task_id != payload.benchmark_task_id:
        raise DomainValidationError("prompt_version must belong to the benchmark task")
    deployment_configuration = None
    if payload.deployment_configuration_id is not None:
        deployment_configuration = deployment_configurations.get(
            db,
            payload.deployment_configuration_id,
        )
        if deployment_configuration is None:
            raise DomainValidationError(
                "benchmark_run deployment_configuration_id must reference an existing "
                "deployment configuration"
            )
        if deployment_configuration.hardware_profile_id != payload.hardware_profile_id:
            raise DomainValidationError("deployment configuration hardware does not match run")
        if deployment_configuration.model_artifact_id != payload.model_artifact_id:
            raise DomainValidationError("deployment configuration artifact does not match run")
    if payload.evaluation_suite_id is not None:
        evaluation_suite = evaluation_suites.get(db, payload.evaluation_suite_id)
        if evaluation_suite is None:
            raise DomainValidationError(
                "benchmark_run evaluation_suite_id must reference an existing evaluation suite"
            )
        if (
            deployment_configuration is not None
            and evaluation_suite.workload_profile_id
            != deployment_configuration.workload_profile_id
        ):
            raise DomainValidationError("evaluation suite workload does not match configuration")
    run = benchmark_runs.create(db, payload.model_dump())
    record_benchmark_run_event(db, run, commit=True)
    return run


def list_benchmark_results(db: Session, limit: int, offset: int) -> Sequence[BenchmarkResult]:
    return benchmark_results.list(db, limit=limit, offset=offset)


def create_benchmark_result(db: Session, payload: BenchmarkResultCreate) -> BenchmarkResult:
    run = benchmark_runs.get(db, payload.benchmark_run_id)
    if run is None:
        raise DomainValidationError("benchmark results cannot exist without a valid benchmark run")
    if payload.evaluation_case_id is not None:
        evaluation_case = evaluation_cases.get(db, payload.evaluation_case_id)
        if evaluation_case is None:
            raise DomainValidationError(
                "benchmark_result evaluation_case_id must reference an existing evaluation case"
            )
        if run.evaluation_suite_id is None:
            raise DomainValidationError("gate-related benchmark results require a suite-linked run")
        if evaluation_case.evaluation_suite_id != run.evaluation_suite_id:
            raise DomainValidationError("evaluation case must belong to the run evaluation suite")
        if not evaluation_case.is_active:
            raise DomainValidationError("gate-related benchmark results require an active case")
    return benchmark_results.create(db, payload.model_dump())


def list_inference_metrics(
    db: Session,
    *,
    limit: int,
    offset: int,
    benchmark_run_id: UUID | None = None,
) -> Sequence[InferenceMetric]:
    return inference_metrics.list(
        db,
        limit=limit,
        offset=offset,
        filters={"benchmark_run_id": benchmark_run_id},
    )


def create_inference_metric(db: Session, payload: InferenceMetricCreate) -> InferenceMetric:
    run = benchmark_runs.get(db, payload.benchmark_run_id)
    if run is None:
        raise DomainValidationError("inference metrics cannot exist without a valid benchmark run")
    hardware = hardware_profiles.get(db, run.hardware_profile_id)
    if hardware is None:
        raise DomainValidationError("benchmark_run hardware profile is missing")
    validate_vram_within_hardware(payload.gpu_vram_used_mb, hardware.gpu_vram_gb)
    return inference_metrics.create(db, payload.model_dump())
