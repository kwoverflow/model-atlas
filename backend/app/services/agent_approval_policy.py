from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

AGENT_CONTROL_POLICY_VERSION = "agent-control-approval-rbac-v1"
DEFAULT_AGENT_APPROVER_ROLES = (
    "Release Manager",
    "ML Ops Lead",
    "SRE Lead",
    "Model Governance",
    "Admin",
)
DEFAULT_AGENT_RESUMER_ROLES = (
    "Release Manager",
    "ML Ops Lead",
    "SRE Lead",
    "Admin",
)
AGENT_EVIDENCE_IMPORT_ROLES = (
    "ML Ops Lead",
    "SRE Lead",
    "Model Governance",
    "Admin",
)
DEFAULT_CHECKPOINT_EXPIRY_SECONDS = 3_600
MIN_CHECKPOINT_EXPIRY_SECONDS = 60
MAX_CHECKPOINT_EXPIRY_SECONDS = 604_800

AgentCheckpointOperation = Literal["decide", "revoke", "resume"]


@dataclass(frozen=True)
class AgentCheckpointPolicy:
    policy_version: str
    checkpoint_id: str
    allowed_roles: tuple[str, ...]
    resume_roles: tuple[str, ...]
    requires_verified_identity: bool
    separation_of_duties: bool
    expires_in_seconds: int

    def to_json(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "checkpoint_id": self.checkpoint_id,
            "allowed_roles": list(self.allowed_roles),
            "resume_roles": list(self.resume_roles),
            "requires_verified_identity": self.requires_verified_identity,
            "separation_of_duties": self.separation_of_duties,
            "expires_in_seconds": self.expires_in_seconds,
        }


@dataclass(frozen=True)
class AgentCheckpointPolicyEvaluation:
    policy_version: str
    checkpoint_id: str
    operation: AgentCheckpointOperation
    allowed: bool
    allowed_roles: tuple[str, ...]
    signer_role: str | None
    identity_verified: bool
    separation_of_duties: bool
    requester_subject_id: str
    signer_subject_id: str
    reasons: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "checkpoint_id": self.checkpoint_id,
            "operation": self.operation,
            "allowed": self.allowed,
            "allowed_roles": list(self.allowed_roles),
            "signer_role": self.signer_role,
            "identity_verified": self.identity_verified,
            "separation_of_duties": self.separation_of_duties,
            "requester_subject_id": self.requester_subject_id,
            "signer_subject_id": self.signer_subject_id,
            "reasons": list(self.reasons),
        }


def resolve_agent_checkpoint_policy(
    contract: dict[str, Any],
    *,
    checkpoint_id: str,
) -> AgentCheckpointPolicy:
    defaults = contract.get("approval_policy")
    defaults = dict(defaults) if isinstance(defaults, dict) else {}
    checkpoint_policies = contract.get("approval_policies")
    checkpoint_policies = (
        checkpoint_policies if isinstance(checkpoint_policies, dict) else {}
    )
    checkpoint_override = checkpoint_policies.get(checkpoint_id)
    checkpoint_override = (
        dict(checkpoint_override) if isinstance(checkpoint_override, dict) else {}
    )
    merged = {**defaults, **checkpoint_override}
    return AgentCheckpointPolicy(
        policy_version=AGENT_CONTROL_POLICY_VERSION,
        checkpoint_id=checkpoint_id,
        allowed_roles=_roles(
            merged.get("allowed_roles"),
            default=DEFAULT_AGENT_APPROVER_ROLES,
        ),
        resume_roles=_roles(
            merged.get("resume_roles"),
            default=DEFAULT_AGENT_RESUMER_ROLES,
        ),
        requires_verified_identity=_bool(
            merged.get("requires_verified_identity"),
            default=True,
        ),
        separation_of_duties=_bool(
            merged.get("separation_of_duties"),
            default=True,
        ),
        expires_in_seconds=_bounded_expiry(merged.get("expires_in_seconds")),
    )


def checkpoint_policy_from_json(payload: dict[str, Any]) -> AgentCheckpointPolicy:
    checkpoint_id = str(payload.get("checkpoint_id") or "").strip()
    if not checkpoint_id:
        raise DomainValidationError("agent checkpoint policy is missing checkpoint_id")
    return AgentCheckpointPolicy(
        policy_version=str(
            payload.get("policy_version") or AGENT_CONTROL_POLICY_VERSION
        ),
        checkpoint_id=checkpoint_id,
        allowed_roles=_roles(
            payload.get("allowed_roles"),
            default=DEFAULT_AGENT_APPROVER_ROLES,
        ),
        resume_roles=_roles(
            payload.get("resume_roles"),
            default=DEFAULT_AGENT_RESUMER_ROLES,
        ),
        requires_verified_identity=_bool(
            payload.get("requires_verified_identity"),
            default=True,
        ),
        separation_of_duties=_bool(
            payload.get("separation_of_duties"),
            default=True,
        ),
        expires_in_seconds=_bounded_expiry(payload.get("expires_in_seconds")),
    )


def evaluate_agent_checkpoint_policy(
    *,
    policy: AgentCheckpointPolicy,
    operation: AgentCheckpointOperation,
    signer_identity: SignerIdentity,
    requester_subject_id: str,
) -> AgentCheckpointPolicyEvaluation:
    allowed_roles = policy.resume_roles if operation == "resume" else policy.allowed_roles
    reasons: list[str] = []
    if policy.requires_verified_identity and not signer_identity.identity_verified:
        reasons.append(f"Agent checkpoint {operation} requires verified operator identity.")
    signer_role_key = _role_key(signer_identity.role)
    if signer_role_key is None or signer_role_key not in {
        _role_key(role) for role in allowed_roles
    }:
        reasons.append(
            f"Agent checkpoint {operation} requires one of these roles: "
            f"{', '.join(allowed_roles)}."
        )
    if (
        operation == "decide"
        and policy.separation_of_duties
        and signer_identity.subject_id == requester_subject_id
    ):
        reasons.append(
            "Agent checkpoint decision requires a different operator from the requester."
        )
    return AgentCheckpointPolicyEvaluation(
        policy_version=policy.policy_version,
        checkpoint_id=policy.checkpoint_id,
        operation=operation,
        allowed=not reasons,
        allowed_roles=allowed_roles,
        signer_role=signer_identity.role,
        identity_verified=signer_identity.identity_verified,
        separation_of_duties=policy.separation_of_duties,
        requester_subject_id=requester_subject_id,
        signer_subject_id=signer_identity.subject_id,
        reasons=tuple(reasons),
    )


def assert_agent_checkpoint_operation_allowed(
    *,
    policy: AgentCheckpointPolicy,
    operation: AgentCheckpointOperation,
    signer_identity: SignerIdentity,
    requester_subject_id: str,
) -> AgentCheckpointPolicyEvaluation:
    evaluation = evaluate_agent_checkpoint_policy(
        policy=policy,
        operation=operation,
        signer_identity=signer_identity,
        requester_subject_id=requester_subject_id,
    )
    if not evaluation.allowed:
        raise DomainValidationError(
            "Agent checkpoint policy denied: " + " ".join(evaluation.reasons)
        )
    return evaluation


def assert_agent_evidence_import_allowed(
    signer_identity: SignerIdentity,
) -> None:
    reasons: list[str] = []
    if not signer_identity.identity_verified:
        reasons.append("Agent evidence import requires verified operator identity.")
    role_key = _role_key(signer_identity.role)
    if role_key is None or role_key not in {
        _role_key(role) for role in AGENT_EVIDENCE_IMPORT_ROLES
    }:
        reasons.append(
            "Agent evidence import requires one of these roles: "
            + ", ".join(AGENT_EVIDENCE_IMPORT_ROLES)
            + "."
        )
    if reasons:
        raise DomainValidationError("Agent evidence import policy denied: " + " ".join(reasons))


def _roles(value: Any, *, default: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return default
    roles = tuple(
        dict.fromkeys(
            str(item).strip()
            for item in value[:20]
            if str(item).strip()
        )
    )
    return roles or default


def _role_key(role: str | None) -> str | None:
    if role is None:
        return None
    normalized = " ".join(role.strip().split()).lower()
    return normalized or None


def _bool(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _bounded_expiry(value: Any) -> int:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return DEFAULT_CHECKPOINT_EXPIRY_SECONDS
    return max(
        MIN_CHECKPOINT_EXPIRY_SECONDS,
        min(int(value), MAX_CHECKPOINT_EXPIRY_SECONDS),
    )
