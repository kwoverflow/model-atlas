from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    AcceptancePolicyCreate,
    AcceptancePolicyRead,
    AcceptancePolicyRuleCreate,
    AcceptancePolicyRuleRead,
    DeploymentConfigurationCreate,
    DeploymentConfigurationRead,
    EvaluationCaseCreate,
    EvaluationCaseRead,
    EvaluationSuiteCreate,
    EvaluationSuiteRead,
    MetricDefinitionCreate,
    MetricDefinitionRead,
    WorkloadProfileCreate,
    WorkloadProfileRead,
)
from app.services import deployment_gate_resources as resources

router = APIRouter()


def pagination(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> tuple[int, int]:
    return limit, offset


@router.get("/workloads", response_model=list[WorkloadProfileRead])
def list_workloads(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[WorkloadProfileRead]:
    limit, offset = page
    return list(resources.list_workloads(db, limit=limit, offset=offset))


@router.post("/workloads", response_model=WorkloadProfileRead, status_code=201)
def create_workload(
    payload: WorkloadProfileCreate,
    db: Session = Depends(get_db),
) -> WorkloadProfileRead:
    return resources.create_workload(db, payload)


@router.get("/workloads/{workload_id}", response_model=WorkloadProfileRead)
def get_workload(workload_id: UUID, db: Session = Depends(get_db)) -> WorkloadProfileRead:
    return resources.get_workload(db, workload_id)


@router.get("/evaluation-suites", response_model=list[EvaluationSuiteRead])
def list_evaluation_suites(
    page: tuple[int, int] = Depends(pagination),
    workload_profile_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[EvaluationSuiteRead]:
    limit, offset = page
    return list(
        resources.list_evaluation_suites(
            db,
            limit=limit,
            offset=offset,
            workload_profile_id=workload_profile_id,
        )
    )


@router.post("/evaluation-suites", response_model=EvaluationSuiteRead, status_code=201)
def create_evaluation_suite(
    payload: EvaluationSuiteCreate,
    db: Session = Depends(get_db),
) -> EvaluationSuiteRead:
    return resources.create_evaluation_suite(db, payload)


@router.get("/evaluation-suites/{suite_id}", response_model=EvaluationSuiteRead)
def get_evaluation_suite(suite_id: UUID, db: Session = Depends(get_db)) -> EvaluationSuiteRead:
    return resources.get_evaluation_suite(db, suite_id)


@router.get("/evaluation-cases", response_model=list[EvaluationCaseRead])
def list_evaluation_cases(
    page: tuple[int, int] = Depends(pagination),
    evaluation_suite_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[EvaluationCaseRead]:
    limit, offset = page
    return list(
        resources.list_evaluation_cases(
            db,
            limit=limit,
            offset=offset,
            evaluation_suite_id=evaluation_suite_id,
        )
    )


@router.post("/evaluation-cases", response_model=EvaluationCaseRead, status_code=201)
def create_evaluation_case(
    payload: EvaluationCaseCreate,
    db: Session = Depends(get_db),
) -> EvaluationCaseRead:
    return resources.create_evaluation_case(db, payload)


@router.get("/evaluation-cases/{case_id}", response_model=EvaluationCaseRead)
def get_evaluation_case(case_id: UUID, db: Session = Depends(get_db)) -> EvaluationCaseRead:
    return resources.get_evaluation_case(db, case_id)


@router.get("/metric-definitions", response_model=list[MetricDefinitionRead])
def list_metric_definitions(
    page: tuple[int, int] = Depends(pagination),
    db: Session = Depends(get_db),
) -> list[MetricDefinitionRead]:
    limit, offset = page
    return list(resources.list_metric_definitions(db, limit=limit, offset=offset))


@router.post("/metric-definitions", response_model=MetricDefinitionRead, status_code=201)
def create_metric_definition(
    payload: MetricDefinitionCreate,
    db: Session = Depends(get_db),
) -> MetricDefinitionRead:
    return resources.create_metric_definition(db, payload)


@router.get("/acceptance-policies", response_model=list[AcceptancePolicyRead])
def list_acceptance_policies(
    page: tuple[int, int] = Depends(pagination),
    workload_profile_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[AcceptancePolicyRead]:
    limit, offset = page
    return list(
        resources.list_acceptance_policies(
            db,
            limit=limit,
            offset=offset,
            workload_profile_id=workload_profile_id,
        )
    )


@router.post("/acceptance-policies", response_model=AcceptancePolicyRead, status_code=201)
def create_acceptance_policy(
    payload: AcceptancePolicyCreate,
    db: Session = Depends(get_db),
) -> AcceptancePolicyRead:
    return resources.create_acceptance_policy(db, payload)


@router.get("/acceptance-policies/{policy_id}", response_model=AcceptancePolicyRead)
def get_acceptance_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
) -> AcceptancePolicyRead:
    return resources.get_acceptance_policy(db, policy_id)


@router.get("/acceptance-policy-rules", response_model=list[AcceptancePolicyRuleRead])
def list_acceptance_policy_rules(
    page: tuple[int, int] = Depends(pagination),
    acceptance_policy_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[AcceptancePolicyRuleRead]:
    limit, offset = page
    return list(
        resources.list_acceptance_policy_rules(
            db,
            limit=limit,
            offset=offset,
            acceptance_policy_id=acceptance_policy_id,
        )
    )


@router.post("/acceptance-policy-rules", response_model=AcceptancePolicyRuleRead, status_code=201)
def create_acceptance_policy_rule(
    payload: AcceptancePolicyRuleCreate,
    db: Session = Depends(get_db),
) -> AcceptancePolicyRuleRead:
    return resources.create_acceptance_policy_rule(db, payload)


@router.get("/deployment-configurations", response_model=list[DeploymentConfigurationRead])
def list_deployment_configurations(
    page: tuple[int, int] = Depends(pagination),
    workload_profile_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> list[DeploymentConfigurationRead]:
    limit, offset = page
    return list(
        resources.list_deployment_configurations(
            db,
            limit=limit,
            offset=offset,
            workload_profile_id=workload_profile_id,
        )
    )


@router.post(
    "/deployment-configurations",
    response_model=DeploymentConfigurationRead,
    status_code=201,
)
def create_deployment_configuration(
    payload: DeploymentConfigurationCreate,
    db: Session = Depends(get_db),
) -> DeploymentConfigurationRead:
    return resources.create_deployment_configuration(db, payload)


@router.get(
    "/deployment-configurations/{configuration_id}",
    response_model=DeploymentConfigurationRead,
)
def get_deployment_configuration(
    configuration_id: UUID,
    db: Session = Depends(get_db),
) -> DeploymentConfigurationRead:
    return resources.get_deployment_configuration(db, configuration_id)
