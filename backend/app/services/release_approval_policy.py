from __future__ import annotations

from dataclasses import dataclass

from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

RELEASE_APPROVAL_POLICY_VERSION = "release-approval-rbac-v1"

APPROVER_ROLES = (
    "Release Manager",
    "ML Ops Lead",
    "Model Governance",
    "Admin",
)
CHANGE_REQUEST_ROLES = (
    *APPROVER_ROLES,
    "ML Engineer",
    "QA Lead",
    "SRE Lead",
)


@dataclass(frozen=True)
class ReleaseDecisionPolicySpec:
    allowed_roles: tuple[str, ...]
    requires_verified_identity: bool
    allow_missing_role: bool = False


@dataclass(frozen=True)
class ReleaseDecisionPolicyEvaluation:
    policy_version: str
    decision: str
    allowed: bool
    requires_verified_identity: bool
    allowed_roles: tuple[str, ...]
    signer_role: str | None
    identity_verified: bool
    reasons: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "decision": self.decision,
            "allowed": self.allowed,
            "requires_verified_identity": self.requires_verified_identity,
            "allowed_roles": list(self.allowed_roles),
            "signer_role": self.signer_role,
            "identity_verified": self.identity_verified,
            "reasons": list(self.reasons),
        }


DECISION_POLICY: dict[str, ReleaseDecisionPolicySpec] = {
    "APPROVE_RELEASE": ReleaseDecisionPolicySpec(
        allowed_roles=APPROVER_ROLES,
        requires_verified_identity=True,
    ),
    "REJECT_RELEASE": ReleaseDecisionPolicySpec(
        allowed_roles=APPROVER_ROLES,
        requires_verified_identity=True,
    ),
    "REQUEST_CHANGES": ReleaseDecisionPolicySpec(
        allowed_roles=CHANGE_REQUEST_ROLES,
        requires_verified_identity=False,
        allow_missing_role=True,
    ),
}


def _role_key(role: str | None) -> str | None:
    if role is None:
        return None
    normalized = " ".join(role.strip().split()).lower()
    return normalized or None


def _allowed_role_keys(roles: tuple[str, ...]) -> set[str]:
    return {_role_key(role) or "" for role in roles}


def evaluate_release_decision_policy(
    *,
    decision: str,
    signer_identity: SignerIdentity,
) -> ReleaseDecisionPolicyEvaluation:
    spec = DECISION_POLICY[decision]
    reasons: list[str] = []
    signer_role_key = _role_key(signer_identity.role)

    if spec.requires_verified_identity and not signer_identity.identity_verified:
        reasons.append(f"{decision} requires verified operator identity.")

    if signer_role_key is None:
        if not spec.allow_missing_role:
            reasons.append(
                f"{decision} requires one of these roles: {', '.join(spec.allowed_roles)}."
            )
    elif signer_role_key not in _allowed_role_keys(spec.allowed_roles):
        reasons.append(
            f"{decision} requires one of these roles: {', '.join(spec.allowed_roles)}."
        )

    return ReleaseDecisionPolicyEvaluation(
        policy_version=RELEASE_APPROVAL_POLICY_VERSION,
        decision=decision,
        allowed=not reasons,
        requires_verified_identity=spec.requires_verified_identity,
        allowed_roles=spec.allowed_roles,
        signer_role=signer_identity.role,
        identity_verified=signer_identity.identity_verified,
        reasons=tuple(reasons),
    )


def release_decision_permissions(signer_identity: SignerIdentity) -> dict[str, object]:
    evaluations = {
        decision: evaluate_release_decision_policy(
            decision=decision,
            signer_identity=signer_identity,
        ).to_json()
        for decision in DECISION_POLICY
    }
    return {
        "policy_version": RELEASE_APPROVAL_POLICY_VERSION,
        "decisions": evaluations,
    }


def assert_release_decision_allowed(
    *,
    decision: str,
    signer_identity: SignerIdentity,
) -> ReleaseDecisionPolicyEvaluation:
    evaluation = evaluate_release_decision_policy(
        decision=decision,
        signer_identity=signer_identity,
    )
    if not evaluation.allowed:
        raise DomainValidationError(
            "Release decision policy denied: " + " ".join(evaluation.reasons)
        )
    return evaluation
