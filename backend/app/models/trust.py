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
    Integer,
    Mapped,
    String,
    Text,
    TimestampMixin,
    UniqueConstraint,
    UTCDateTime,
    dt,
    mapped_column,
    relationship,
    utcnow,
    uuid,
)

if TYPE_CHECKING:

    from app.models.catalog import ModelArtifactAttestation
    from app.models.evaluation import BenchmarkRun



class ModelSupplyChainAttestation(TimestampMixin, Base):
    __tablename__ = "model_supply_chain_attestations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model_artifact_attestation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("model_artifact_attestations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    publisher_trust_root_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_roots.id", ondelete="SET NULL"),
        index=True,
    )
    publisher_trust_tier: Mapped[str] = mapped_column(
        String(40), nullable=False, default="development", index=True
    )
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    statement_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    statement_type: Mapped[str] = mapped_column(String(200), nullable=False)
    predicate_type: Mapped[str] = mapped_column(String(300), nullable=False)
    publisher: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    publisher_key_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    signature_algorithm: Mapped[str] = mapped_column(String(30), nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_digest: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sbom_format: Mapped[str] = mapped_column(String(80), nullable=False)
    sbom_version: Mapped[str] = mapped_column(String(40), nullable=False)
    sbom_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    sbom_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    statement_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    statement_jws: Mapped[str] = mapped_column(Text, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    verified_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    verified_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    attestation_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    runtime_attestation: Mapped[ModelArtifactAttestation] = relationship(
        back_populates="supply_chain_attestations"
    )
    actions: Mapped[list[ModelSupplyChainAttestationAction]] = relationship(
        back_populates="supply_chain_attestation",
        cascade="all, delete-orphan",
    )
    production_evidence_receipts: Mapped[list[ProductionEvidenceReceipt]] = relationship(
        back_populates="supply_chain_attestation"
    )
    publisher_trust_root: Mapped[EvidenceTrustRoot | None] = relationship(
        back_populates="publisher_attestations",
        foreign_keys=[publisher_trust_root_id],
    )
    transparency_proofs: Mapped[list[SupplyChainTransparencyProof]] = relationship(
        back_populates="supply_chain_attestation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "signature_algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_model_supply_chain_attestations_algorithm",
        ),
        CheckConstraint(
            "sbom_format IN ('CycloneDX')",
            name="ck_model_supply_chain_attestations_sbom_format",
        ),
        CheckConstraint(
            "publisher_trust_tier IN ('development', 'internal_ca', 'external')",
            name="ck_model_supply_chain_attestations_trust_tier",
        ),
    )

class ModelSupplyChainAttestationAction(TimestampMixin, Base):
    __tablename__ = "model_supply_chain_attestation_actions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    supply_chain_attestation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("model_supply_chain_attestations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_reference: Mapped[str | None] = mapped_column(String(200))
    actor_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    supply_chain_attestation: Mapped[ModelSupplyChainAttestation] = relationship(
        back_populates="actions"
    )

    __table_args__ = (
        UniqueConstraint(
            "supply_chain_attestation_id",
            "action_type",
            name="uq_model_supply_chain_actions_attestation_type",
        ),
        CheckConstraint(
            "action_type IN ('revoked')",
            name="ck_model_supply_chain_actions_type",
        ),
    )

class EvidenceTrustSource(TimestampMixin, Base):
    __tablename__ = "evidence_trust_sources"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False, unique=True, index=True)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    trust_tier: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    allowed_algorithms_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    allow_insecure_http: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    freshness_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    registered_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    registered_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    configuration_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    syncs: Mapped[list[EvidenceTrustSourceSync]] = relationship(
        back_populates="trust_source",
        cascade="all, delete-orphan",
    )
    schedule: Mapped[EvidenceTrustSourceSchedule | None] = relationship(
        back_populates="trust_source",
        cascade="all, delete-orphan",
        uselist=False,
    )
    trust_roots: Mapped[list[EvidenceTrustRoot]] = relationship(
        back_populates="trust_source",
        foreign_keys="EvidenceTrustRoot.trust_source_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "purpose",
            "issuer",
            "endpoint_url",
            name="uq_evidence_trust_sources_purpose_issuer_endpoint",
        ),
        CheckConstraint(
            "source_kind IN ('jwks')",
            name="ck_evidence_trust_sources_kind",
        ),
        CheckConstraint(
            "purpose IN ('model_publisher', 'production_collector', 'transparency_log')",
            name="ck_evidence_trust_sources_purpose",
        ),
        CheckConstraint(
            "trust_tier IN ('development', 'internal_ca', 'external')",
            name="ck_evidence_trust_sources_tier",
        ),
        CheckConstraint(
            "freshness_seconds >= 60 AND freshness_seconds <= 604800",
            name="ck_evidence_trust_sources_freshness",
        ),
    )

class EvidenceTrustSourceSync(TimestampMixin, Base):
    __tablename__ = "evidence_trust_source_syncs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trust_source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False, default="manual", index=True)
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_source_schedules.id", ondelete="SET NULL"),
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("agent_execution_jobs.id", ondelete="SET NULL"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    scheduled_for: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    http_status: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    completed_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    key_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_keys_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), index=True)
    error_message: Mapped[str | None] = mapped_column(Text)
    actor_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    sync_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    trust_source: Mapped[EvidenceTrustSource] = relationship(back_populates="syncs")
    imported_roots: Mapped[list[EvidenceTrustRoot]] = relationship(
        back_populates="trust_source_sync",
        foreign_keys="EvidenceTrustRoot.trust_source_sync_id",
    )

    __table_args__ = (
        CheckConstraint(
            "mode IN ('preview', 'apply')",
            name="ck_evidence_trust_source_syncs_mode",
        ),
        CheckConstraint(
            "status IN ('succeeded', 'failed')",
            name="ck_evidence_trust_source_syncs_status",
        ),
        CheckConstraint(
            "trigger IN ('manual', 'scheduled')",
            name="ck_evidence_trust_source_syncs_trigger",
        ),
        CheckConstraint(
            "key_count >= 0 AND candidate_count >= 0 AND imported_count >= 0 "
            "AND unchanged_count >= 0 AND rejected_count >= 0 AND attempt_number > 0",
            name="ck_evidence_trust_source_syncs_counts",
        ),
    )

class EvidenceTrustSourceSchedule(TimestampMixin, Base):
    __tablename__ = "evidence_trust_source_schedules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trust_source_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_sources.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    jitter_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_base_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    retry_max_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    retry_jitter_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    next_run_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    last_enqueued_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    last_completed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    last_job_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("agent_execution_jobs.id", ondelete="SET NULL"), index=True
    )
    last_sync_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), index=True)
    run_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(160), index=True)
    lease_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    configured_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)

    trust_source: Mapped[EvidenceTrustSource] = relationship(back_populates="schedule")

    __table_args__ = (
        CheckConstraint(
            "interval_seconds >= 60 AND interval_seconds <= 604800",
            name="ck_evidence_trust_source_schedules_interval",
        ),
        CheckConstraint(
            "jitter_seconds >= 0 AND jitter_seconds < interval_seconds",
            name="ck_evidence_trust_source_schedules_jitter",
        ),
        CheckConstraint(
            "max_attempts >= 1 AND max_attempts <= 10",
            name="ck_evidence_trust_source_schedules_attempts",
        ),
        CheckConstraint(
            "retry_base_seconds >= 1 AND retry_base_seconds <= retry_max_seconds "
            "AND retry_max_seconds <= 3600 AND retry_jitter_seconds >= 0 "
            "AND retry_jitter_seconds <= retry_max_seconds",
            name="ck_evidence_trust_source_schedules_retry",
        ),
        CheckConstraint(
            "run_sequence >= 0 AND consecutive_failures >= 0",
            name="ck_evidence_trust_source_schedules_counts",
        ),
        CheckConstraint(
            "(lease_token_hash IS NULL AND lease_owner IS NULL AND lease_expires_at IS NULL) "
            "OR (lease_token_hash IS NOT NULL AND lease_owner IS NOT NULL "
            "AND lease_expires_at IS NOT NULL)",
            name="ck_evidence_trust_source_schedules_lease",
        ),
    )

class EvidenceTrustRoot(TimestampMixin, Base):
    __tablename__ = "evidence_trust_roots"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    key_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    algorithm: Mapped[str] = mapped_column(String(30), nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    public_key_jwk_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    trust_tier: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(String(500))
    valid_from: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    valid_until: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    supersedes_trust_root_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_roots.id", ondelete="SET NULL"),
        index=True,
    )
    trust_source_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_sources.id", ondelete="SET NULL"),
        index=True,
    )
    trust_source_sync_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_source_syncs.id", ondelete="SET NULL"),
        index=True,
    )
    registered_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    registered_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    registration_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    supersedes_trust_root: Mapped[EvidenceTrustRoot | None] = relationship(
        remote_side=[id],
        foreign_keys=[supersedes_trust_root_id],
    )
    trust_source: Mapped[EvidenceTrustSource | None] = relationship(
        back_populates="trust_roots",
        foreign_keys=[trust_source_id],
    )
    trust_source_sync: Mapped[EvidenceTrustSourceSync | None] = relationship(
        back_populates="imported_roots",
        foreign_keys=[trust_source_sync_id],
    )
    actions: Mapped[list[EvidenceTrustRootAction]] = relationship(
        back_populates="trust_root",
        cascade="all, delete-orphan",
    )
    publisher_attestations: Mapped[list[ModelSupplyChainAttestation]] = relationship(
        back_populates="publisher_trust_root",
        foreign_keys="ModelSupplyChainAttestation.publisher_trust_root_id",
    )
    collector_receipts: Mapped[list[ProductionEvidenceReceipt]] = relationship(
        back_populates="collector_trust_root",
        foreign_keys="ProductionEvidenceReceipt.collector_trust_root_id",
    )
    transparency_proofs: Mapped[list[SupplyChainTransparencyProof]] = relationship(
        back_populates="log_trust_root",
        foreign_keys="SupplyChainTransparencyProof.log_trust_root_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "purpose",
            "issuer",
            "key_id",
            name="uq_evidence_trust_roots_purpose_issuer_key",
        ),
        CheckConstraint(
            "purpose IN ('model_publisher', 'production_collector', 'transparency_log')",
            name="ck_evidence_trust_roots_purpose",
        ),
        CheckConstraint(
            "algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_evidence_trust_roots_algorithm",
        ),
        CheckConstraint(
            "trust_tier IN ('development', 'internal_ca', 'external')",
            name="ck_evidence_trust_roots_tier",
        ),
        CheckConstraint(
            "source_type IN "
            "('development', 'internal_ca', 'external_registry', 'transparency_log')",
            name="ck_evidence_trust_roots_source_type",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_evidence_trust_roots_validity",
        ),
    )

class EvidenceTrustRootAction(TimestampMixin, Base):
    __tablename__ = "evidence_trust_root_actions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    trust_root_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_roots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_reference: Mapped[str | None] = mapped_column(String(200))
    actor_identity_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    action_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    trust_root: Mapped[EvidenceTrustRoot] = relationship(back_populates="actions")

    __table_args__ = (
        UniqueConstraint(
            "trust_root_id",
            "action_type",
            name="uq_evidence_trust_root_actions_root_type",
        ),
        CheckConstraint(
            "action_type IN ('rotated', 'retired', 'revoked')",
            name="ck_evidence_trust_root_actions_type",
        ),
    )

class SupplyChainTransparencyProof(TimestampMixin, Base):
    __tablename__ = "supply_chain_transparency_proofs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    supply_chain_attestation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("model_supply_chain_attestations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    log_trust_root_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_roots.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    proof_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    log_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)
    tree_size: Mapped[int] = mapped_column(Integer, nullable=False)
    integrated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    leaf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    root_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    inclusion_path_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    checkpoint_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checkpoint_jws: Mapped[str] = mapped_column(Text, nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(30), nullable=False)
    key_id: Mapped[str] = mapped_column(String(200), nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    verified_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    verified_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    proof_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    supply_chain_attestation: Mapped[ModelSupplyChainAttestation] = relationship(
        back_populates="transparency_proofs"
    )
    log_trust_root: Mapped[EvidenceTrustRoot] = relationship(
        back_populates="transparency_proofs",
        foreign_keys=[log_trust_root_id],
    )

    __table_args__ = (
        UniqueConstraint(
            "supply_chain_attestation_id",
            "log_id",
            "log_index",
            name="uq_supply_chain_transparency_log_entry",
        ),
        CheckConstraint(
            "log_index >= 0 AND tree_size > 0 AND log_index < tree_size",
            name="ck_supply_chain_transparency_position",
        ),
        CheckConstraint(
            "signature_algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_supply_chain_transparency_algorithm",
        ),
    )

class ProductionEvidenceReceipt(TimestampMixin, Base):
    __tablename__ = "production_evidence_receipts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    benchmark_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("benchmark_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_artifact_attestation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("model_artifact_attestations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supply_chain_attestation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("model_supply_chain_attestations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collector_trust_root_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evidence_trust_roots.id", ondelete="SET NULL"),
        index=True,
    )
    collector_trust_tier: Mapped[str] = mapped_column(
        String(40), nullable=False, default="development", index=True
    )
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    capture_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    issuer: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    key_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    signature_algorithm: Mapped[str] = mapped_column(String(30), nullable=False)
    key_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_digest: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_environment_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    capture_started_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    capture_ended_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metric_count: Mapped[int] = mapped_column(Integer, nullable=False)
    statement_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    statement_jws: Mapped[str] = mapped_column(Text, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    verified_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    verified_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    receipt_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    benchmark_run: Mapped[BenchmarkRun] = relationship(
        back_populates="production_evidence_receipts"
    )
    runtime_attestation: Mapped[ModelArtifactAttestation] = relationship()
    supply_chain_attestation: Mapped[ModelSupplyChainAttestation] = relationship(
        back_populates="production_evidence_receipts"
    )
    collector_trust_root: Mapped[EvidenceTrustRoot | None] = relationship(
        back_populates="collector_receipts",
        foreign_keys=[collector_trust_root_id],
    )

    __table_args__ = (
        CheckConstraint(
            "signature_algorithm IN ('RS256', 'ES256', 'EdDSA')",
            name="ck_production_evidence_receipts_algorithm",
        ),
        CheckConstraint(
            "capture_ended_at >= capture_started_at",
            name="ck_production_evidence_receipts_capture_window",
        ),
        CheckConstraint(
            "result_count >= 0 AND metric_count >= 0",
            name="ck_production_evidence_receipts_counts_non_negative",
        ),
        CheckConstraint(
            "collector_trust_tier IN ('development', 'internal_ca', 'external')",
            name="ck_production_evidence_receipts_trust_tier",
        ),
    )
