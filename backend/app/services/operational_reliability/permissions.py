from __future__ import annotations

from app.schemas import (
    OperationalReliabilityPermissionRead,
)
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

from .contracts import (
    OPERATIONAL_ADMINISTRATOR_ROLES,
    OPERATIONAL_AUDITOR_ROLES,
    OPERATIONAL_RELIABILITY_POLICY_VERSION,
)


def operational_reliability_permissions(
    signer_identity: SignerIdentity,
) -> OperationalReliabilityPermissionRead:
    role_key = _role_key(signer_identity.role)
    verified = signer_identity.identity_verified
    return OperationalReliabilityPermissionRead(
        policy_version=OPERATIONAL_RELIABILITY_POLICY_VERSION,
        can_audit=bool(
            verified and role_key in {_role_key(role) for role in OPERATIONAL_AUDITOR_ROLES}
        ),
        can_administer=bool(
            verified and role_key in {_role_key(role) for role in OPERATIONAL_ADMINISTRATOR_ROLES}
        ),
        auditor_roles=list(OPERATIONAL_AUDITOR_ROLES),
        administrator_roles=list(OPERATIONAL_ADMINISTRATOR_ROLES),
        identity_verified=verified,
        signer_role=signer_identity.role,
    )


def _assert_can_administer(signer_identity: SignerIdentity) -> None:
    if not operational_reliability_permissions(signer_identity).can_administer:
        raise DomainValidationError(
            "operational reliability administration requires verified Admin or SRE Lead identity"
        )


def _role_key(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())
