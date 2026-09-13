from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    BenchmarkExecutionCreate,
    BenchmarkExecutionDetailRead,
    BenchmarkExecutionLogRead,
    BenchmarkExecutionRead,
    RuntimeHealthRead,
    ToolRegistryRead,
)
from app.services import benchmark_execution
from app.services.operator_identity import local_operator_identity

router = APIRouter()


@router.get("/runtime-health", response_model=RuntimeHealthRead)
def runtime_health(
    deployment_configuration_id: UUID,
    adapter_name: str = Query(default="mock", pattern="^(mock|openai_compatible)$"),
    base_url: str | None = None,
    model: str | None = None,
    db: Session = Depends(get_db),
) -> RuntimeHealthRead:
    adapter_config_json = {
        key: value
        for key, value in {"base_url": base_url, "model": model}.items()
        if value
    }
    return benchmark_execution.check_runtime_health(
        db,
        deployment_configuration_id=deployment_configuration_id,
        adapter_name=adapter_name,
        adapter_config_json=adapter_config_json,
    )


@router.post("", response_model=BenchmarkExecutionRead, status_code=201)
def create_benchmark_execution(
    payload: BenchmarkExecutionCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> BenchmarkExecutionRead:
    outcome = benchmark_execution.run_benchmark_execution(
        db,
        payload,
        requester_identity=(
            getattr(request.state, "operator_identity", None)
            or local_operator_identity()
        ),
    )
    return BenchmarkExecutionRead(
        benchmark_run=outcome.run,
        result_count=outcome.result_count,
        metric_count=outcome.metric_count,
        log_count=outcome.log_count,
        tool_execution_summary=outcome.tool_execution_summary,
        rag_evaluation_summary=outcome.rag_evaluation_summary,
        runtime_reliability_summary=outcome.runtime_reliability_summary,
        agent_execution_summary=outcome.agent_execution_summary,
    )


@router.get("/tool-registry", response_model=ToolRegistryRead)
def get_tool_registry() -> ToolRegistryRead:
    return ToolRegistryRead.model_validate(
        benchmark_execution.get_tool_registry_descriptor()
    )


@router.get("/{benchmark_run_id}", response_model=BenchmarkExecutionDetailRead)
def get_benchmark_execution(
    benchmark_run_id: UUID,
    db: Session = Depends(get_db),
) -> BenchmarkExecutionDetailRead:
    return BenchmarkExecutionDetailRead.model_validate(
        benchmark_execution.get_benchmark_execution_detail(
            db,
            benchmark_run_id=benchmark_run_id,
        )
    )


@router.get("/{benchmark_run_id}/logs", response_model=list[BenchmarkExecutionLogRead])
def list_benchmark_execution_logs(
    benchmark_run_id: UUID,
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[BenchmarkExecutionLogRead]:
    return benchmark_execution.list_execution_logs(
        db,
        benchmark_run_id=benchmark_run_id,
        limit=limit,
        offset=offset,
    )
