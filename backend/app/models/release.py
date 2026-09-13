from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.base import (
    GUID,
    JSON,
    Any,
    Base,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Mapped,
    String,
    Text,
    TimestampMixin,
    UTCDateTime,
    dt,
    mapped_column,
    relationship,
    utcnow,
    uuid,
)

if TYPE_CHECKING:

    from app.models.evaluation import (
        AcceptancePolicy,
        DeploymentConfiguration,
        EvaluationSuite,
        GateEvaluation,
    )



class ReleaseDecision(TimestampMixin, Base):
    __tablename__ = "release_decisions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    gate_evaluation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("gate_evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deployment_configuration_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("deployment_configurations.id"), nullable=False, index=True
    )
    evaluation_suite_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("evaluation_suites.id"), nullable=False, index=True
    )
    acceptance_policy_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("acceptance_policies.id"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    release_readiness_status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    decided_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    decided_by: Mapped[str] = mapped_column(String(120), nullable=False)
    signer_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    identity_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    signature_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    signature_statement: Mapped[str | None] = mapped_column(Text)
    approval_policy_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    snapshot_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    replaces_release_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("release_decisions.id", ondelete="SET NULL"),
        index=True,
    )

    gate_evaluation: Mapped[GateEvaluation] = relationship(back_populates="release_decisions")
    deployment_configuration: Mapped[DeploymentConfiguration] = relationship()
    evaluation_suite: Mapped[EvaluationSuite] = relationship()
    acceptance_policy: Mapped[AcceptancePolicy] = relationship()

    __table_args__ = (
        CheckConstraint(
            "decision IN ('APPROVE_RELEASE', 'REJECT_RELEASE', 'REQUEST_CHANGES')",
            name="ck_release_decisions_decision",
        ),
        CheckConstraint(
            "release_readiness_status IN ("
            "'READY', "
            "'READY_TO_PROMOTE', "
            "'NEEDS_REVIEW', "
            "'BLOCKED', "
            "'INSUFFICIENT_EVIDENCE'"
            ")",
            name="ck_release_decisions_readiness_status",
        ),
    )

class ReleaseDecisionAction(TimestampMixin, Base):
    __tablename__ = "release_decision_actions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    release_decision_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("release_decisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    actor_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_gate_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("gate_evaluations.id", ondelete="SET NULL"),
        index=True,
    )
    replacement_release_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("release_decisions.id", ondelete="SET NULL"),
        index=True,
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('stale_detected', 'review_requested', "
            "'acknowledged', 'revoked', 'replaced')",
            name="ck_release_decision_actions_type",
        ),
    )
