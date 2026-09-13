from fastapi import APIRouter

from app.schemas import (
    IsolationPolicyRegistryRead,
    IsolationPreflightCreate,
    IsolationPreflightRead,
)
from app.services.workload_isolation import (
    isolation_policy_registry,
    validate_isolation_preflight,
)

router = APIRouter()


@router.get("/policies", response_model=IsolationPolicyRegistryRead)
def get_isolation_policies() -> IsolationPolicyRegistryRead:
    return isolation_policy_registry()


@router.post("/preflight", response_model=IsolationPreflightRead)
def evaluate_isolation_preflight(
    payload: IsolationPreflightCreate,
) -> IsolationPreflightRead:
    return validate_isolation_preflight(payload)
