from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    BenchmarkResultCreate,
    BenchmarkResultRead,
    BenchmarkRunCreate,
    BenchmarkRunRead,
    BenchmarkTaskCreate,
    BenchmarkTaskRead,
    HardwareProfileCreate,
    HardwareProfileRead,
    InferenceMetricCreate,
    InferenceMetricRead,
    ModelArtifactCreate,
    ModelArtifactRead,
    ModelCreate,
    ModelRead,
    PromptVersionCreate,
    PromptVersionRead,
)
from app.services import benchmarks, catalog

router = APIRouter()


def pagination(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> tuple[int, int]:
    return limit, offset


@router.get("/hardware-profiles", response_model=list[HardwareProfileRead])
def list_hardware_profiles(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[HardwareProfileRead]:
    limit, offset = page
    return list(catalog.list_hardware_profiles(db, limit=limit, offset=offset))


@router.post("/hardware-profiles", response_model=HardwareProfileRead, status_code=201)
def create_hardware_profile(
    payload: HardwareProfileCreate,
    db: Session = Depends(get_db),
) -> HardwareProfileRead:
    return catalog.create_hardware_profile(db, payload)


@router.get("/models", response_model=list[ModelRead])
def list_models(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[ModelRead]:
    limit, offset = page
    return list(catalog.list_models(db, limit=limit, offset=offset))


@router.post("/models", response_model=ModelRead, status_code=201)
def create_model(payload: ModelCreate, db: Session = Depends(get_db)) -> ModelRead:
    return catalog.create_model(db, payload)


@router.get("/model-artifacts", response_model=list[ModelArtifactRead])
def list_model_artifacts(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[ModelArtifactRead]:
    limit, offset = page
    return list(catalog.list_model_artifacts(db, limit=limit, offset=offset))


@router.post("/model-artifacts", response_model=ModelArtifactRead, status_code=201)
def create_model_artifact(
    payload: ModelArtifactCreate,
    db: Session = Depends(get_db),
) -> ModelArtifactRead:
    return catalog.create_model_artifact(db, payload)


@router.get("/benchmark-tasks", response_model=list[BenchmarkTaskRead])
def list_benchmark_tasks(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[BenchmarkTaskRead]:
    limit, offset = page
    return list(benchmarks.list_benchmark_tasks(db, limit=limit, offset=offset))


@router.post("/benchmark-tasks", response_model=BenchmarkTaskRead, status_code=201)
def create_benchmark_task(
    payload: BenchmarkTaskCreate,
    db: Session = Depends(get_db),
) -> BenchmarkTaskRead:
    return benchmarks.create_benchmark_task(db, payload)


@router.get("/prompt-versions", response_model=list[PromptVersionRead])
def list_prompt_versions(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[PromptVersionRead]:
    limit, offset = page
    return list(benchmarks.list_prompt_versions(db, limit=limit, offset=offset))


@router.post("/prompt-versions", response_model=PromptVersionRead, status_code=201)
def create_prompt_version(
    payload: PromptVersionCreate,
    db: Session = Depends(get_db),
) -> PromptVersionRead:
    return benchmarks.create_prompt_version(db, payload)


@router.get("/benchmark-runs", response_model=list[BenchmarkRunRead])
def list_benchmark_runs(
    page: tuple[int, int] = Depends(pagination),
    model_artifact_id: UUID | None = None,
    benchmark_task_id: UUID | None = None,
    hardware_profile_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[BenchmarkRunRead]:
    limit, offset = page
    return list(
        benchmarks.list_benchmark_runs(
            db,
            limit=limit,
            offset=offset,
            model_artifact_id=model_artifact_id,
            benchmark_task_id=benchmark_task_id,
            hardware_profile_id=hardware_profile_id,
        )
    )


@router.post("/benchmark-runs", response_model=BenchmarkRunRead, status_code=201)
def create_benchmark_run(
    payload: BenchmarkRunCreate,
    db: Session = Depends(get_db),
) -> BenchmarkRunRead:
    return benchmarks.create_benchmark_run(db, payload)


@router.get("/benchmark-results", response_model=list[BenchmarkResultRead])
def list_benchmark_results(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[BenchmarkResultRead]:
    limit, offset = page
    return list(benchmarks.list_benchmark_results(db, limit=limit, offset=offset))


@router.post("/benchmark-results", response_model=BenchmarkResultRead, status_code=201)
def create_benchmark_result(
    payload: BenchmarkResultCreate,
    db: Session = Depends(get_db),
) -> BenchmarkResultRead:
    return benchmarks.create_benchmark_result(db, payload)


@router.get("/inference-metrics", response_model=list[InferenceMetricRead])
def list_inference_metrics(
    page: tuple[int, int] = Depends(pagination),
    benchmark_run_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[InferenceMetricRead]:
    limit, offset = page
    return list(
        benchmarks.list_inference_metrics(
            db,
            limit=limit,
            offset=offset,
            benchmark_run_id=benchmark_run_id,
        )
    )


@router.post("/inference-metrics", response_model=InferenceMetricRead, status_code=201)
def create_inference_metric(
    payload: InferenceMetricCreate,
    db: Session = Depends(get_db),
) -> InferenceMetricRead:
    return benchmarks.create_inference_metric(db, payload)
