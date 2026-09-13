from __future__ import annotations

from collections.abc import Sequence
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    HardwareProfile,
    MetricDefinition,
    ModelArtifact,
    WorkloadProfile,
)
from app.repositories import BaseRepository
from app.schemas import (
    AcceptancePolicyCreate,
    AcceptancePolicyRuleCreate,
    DeploymentConfigurationCreate,
    EvaluationCaseCreate,
    EvaluationSuiteCreate,
    MetricDefinitionCreate,
    WorkloadProfileCreate,
)
from app.services.deployment_gate.evidence import deployment_configuration_hash, stable_hash
from app.validators import DomainValidationError

workloads = BaseRepository(WorkloadProfile)
evaluation_suites = BaseRepository(EvaluationSuite)
evaluation_cases = BaseRepository(EvaluationCase)
metric_definitions = BaseRepository(MetricDefinition)
acceptance_policies = BaseRepository(AcceptancePolicy)
acceptance_policy_rules = BaseRepository(AcceptancePolicyRule)
deployment_configurations = BaseRepository(DeploymentConfiguration)
hardware_profiles = BaseRepository(HardwareProfile)
model_artifacts = BaseRepository(ModelArtifact)


def _get_or_422(repo: BaseRepository[Any], db: Session, entity_id: UUID, label: str) -> Any:
    entity = repo.get(db, entity_id)
    if entity is None:
        raise DomainValidationError(f"{label} was not found")
    return entity


def list_workloads(db: Session, limit: int, offset: int) -> Sequence[WorkloadProfile]:
    return workloads.list(db, limit=limit, offset=offset)


def create_workload(db: Session, payload: WorkloadProfileCreate) -> WorkloadProfile:
    return workloads.create(db, payload.model_dump())


def get_workload(db: Session, workload_id: UUID) -> WorkloadProfile:
    return _get_or_422(workloads, db, workload_id, "workload")


def list_evaluation_suites(
    db: Session,
    *,
    limit: int,
    offset: int,
    workload_profile_id: UUID | None = None,
) -> Sequence[EvaluationSuite]:
    return evaluation_suites.list(
        db,
        limit=limit,
        offset=offset,
        filters={"workload_profile_id": workload_profile_id},
    )


def create_evaluation_suite(db: Session, payload: EvaluationSuiteCreate) -> EvaluationSuite:
    _get_or_422(workloads, db, payload.workload_profile_id, "workload")
    data = payload.model_dump()
    if data["suite_hash"] is None:
        data["suite_hash"] = stable_hash({k: v for k, v in data.items() if k != "suite_hash"})
    return evaluation_suites.create(db, data)


def get_evaluation_suite(db: Session, suite_id: UUID) -> EvaluationSuite:
    return _get_or_422(evaluation_suites, db, suite_id, "evaluation_suite")


def list_evaluation_cases(
    db: Session,
    *,
    limit: int,
    offset: int,
    evaluation_suite_id: UUID | None = None,
) -> Sequence[EvaluationCase]:
    return evaluation_cases.list(
        db,
        limit=limit,
        offset=offset,
        filters={"evaluation_suite_id": evaluation_suite_id},
    )


def create_evaluation_case(db: Session, payload: EvaluationCaseCreate) -> EvaluationCase:
    _get_or_422(evaluation_suites, db, payload.evaluation_suite_id, "evaluation_suite")
    return evaluation_cases.create(db, payload.model_dump())


def get_evaluation_case(db: Session, case_id: UUID) -> EvaluationCase:
    return _get_or_422(evaluation_cases, db, case_id, "evaluation_case")


def list_metric_definitions(db: Session, limit: int, offset: int) -> Sequence[MetricDefinition]:
    return metric_definitions.list(db, limit=limit, offset=offset)


def create_metric_definition(db: Session, payload: MetricDefinitionCreate) -> MetricDefinition:
    return metric_definitions.create(db, payload.model_dump())


def list_acceptance_policies(
    db: Session,
    *,
    limit: int,
    offset: int,
    workload_profile_id: UUID | None = None,
) -> Sequence[AcceptancePolicy]:
    return acceptance_policies.list(
        db,
        limit=limit,
        offset=offset,
        filters={"workload_profile_id": workload_profile_id},
    )


def create_acceptance_policy(db: Session, payload: AcceptancePolicyCreate) -> AcceptancePolicy:
    _get_or_422(workloads, db, payload.workload_profile_id, "workload")
    data = payload.model_dump()
    if data["policy_hash"] is None:
        data["policy_hash"] = stable_hash({k: v for k, v in data.items() if k != "policy_hash"})
    return acceptance_policies.create(db, data)


def get_acceptance_policy(db: Session, policy_id: UUID) -> AcceptancePolicy:
    return _get_or_422(acceptance_policies, db, policy_id, "acceptance_policy")


def list_acceptance_policy_rules(
    db: Session,
    *,
    limit: int,
    offset: int,
    acceptance_policy_id: UUID | None = None,
) -> Sequence[AcceptancePolicyRule]:
    return acceptance_policy_rules.list(
        db,
        limit=limit,
        offset=offset,
        filters={"acceptance_policy_id": acceptance_policy_id},
    )


def create_acceptance_policy_rule(
    db: Session,
    payload: AcceptancePolicyRuleCreate,
) -> AcceptancePolicyRule:
    _get_or_422(acceptance_policies, db, payload.acceptance_policy_id, "acceptance_policy")
    _get_or_422(metric_definitions, db, payload.metric_definition_id, "metric_definition")
    return acceptance_policy_rules.create(db, payload.model_dump())


def list_deployment_configurations(
    db: Session,
    *,
    limit: int,
    offset: int,
    workload_profile_id: UUID | None = None,
) -> Sequence[DeploymentConfiguration]:
    return deployment_configurations.list(
        db,
        limit=limit,
        offset=offset,
        filters={"workload_profile_id": workload_profile_id},
    )


def _runtime_is_remote(payload: DeploymentConfigurationCreate) -> bool:
    runtime = payload.runtime_name.lower()
    runtime_config = payload.runtime_config_json
    if bool(runtime_config.get("remote")):
        return True
    base_url = runtime_config.get("base_url")
    if base_url:
        host = (urlparse(str(base_url)).hostname or "").lower()
        if host in {"localhost", "host.docker.internal", "ollama"}:
            return False
        try:
            address = ip_address(host)
        except ValueError:
            return True
        return not (address.is_private or address.is_loopback or address.is_link_local)
    return "remote" in runtime or runtime in {"openai_api", "openai-api"}


def create_deployment_configuration(
    db: Session,
    payload: DeploymentConfigurationCreate,
) -> DeploymentConfiguration:
    workload = _get_or_422(workloads, db, payload.workload_profile_id, "workload")
    _get_or_422(hardware_profiles, db, payload.hardware_profile_id, "hardware_profile")
    _get_or_422(model_artifacts, db, payload.model_artifact_id, "model_artifact")
    if workload.local_only_required and _runtime_is_remote(payload):
        raise DomainValidationError(
            "deployment configuration cannot use a remote runtime for a local-only workload"
        )
    data = payload.model_dump()
    data["configuration_hash"] = deployment_configuration_hash(data)
    return deployment_configurations.create(db, data)


def get_deployment_configuration(
    db: Session,
    configuration_id: UUID,
) -> DeploymentConfiguration:
    return _get_or_422(
        deployment_configurations,
        db,
        configuration_id,
        "deployment_configuration",
    )
