from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.base import (
    GUID,
    JSON,
    Any,
    Base,
    Boolean,
    CheckConstraint,
    Float,
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

    from app.models.evaluation import (
        BenchmarkRun,
        DeploymentConfiguration,
    )
    from app.models.trust import ModelSupplyChainAttestation



class HardwareProfile(TimestampMixin, Base):
    __tablename__ = "hardware_profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    cpu_name: Mapped[str] = mapped_column(String(160), nullable=False)
    cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False)
    ram_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    gpu_name: Mapped[str] = mapped_column(String(160), nullable=False)
    gpu_vram_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    os_name: Mapped[str | None] = mapped_column(String(120))
    cuda_version: Mapped[str | None] = mapped_column(String(40))
    driver_version: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)

    benchmark_runs: Mapped[list[BenchmarkRun]] = relationship(back_populates="hardware_profile")
    deployment_configurations: Mapped[list[DeploymentConfiguration]] = relationship(
        back_populates="hardware_profile"
    )

    __table_args__ = (
        CheckConstraint("cpu_cores > 0", name="ck_hardware_profiles_cpu_cores_positive"),
        CheckConstraint("ram_gb > 0", name="ck_hardware_profiles_ram_gb_positive"),
        CheckConstraint("gpu_vram_gb >= 0", name="ck_hardware_profiles_gpu_vram_non_negative"),
        CheckConstraint("gpu_count > 0", name="ck_hardware_profiles_gpu_count_positive"),
    )

class Model(TimestampMixin, Base):
    __tablename__ = "models"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    family: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    parameter_count_b: Mapped[float | None] = mapped_column(Float)
    architecture_type: Mapped[str] = mapped_column(String(120), nullable=False)
    supports_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_vision: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_tool_calling: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_structured_output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    context_length: Mapped[int] = mapped_column(Integer, nullable=False)
    license_name: Mapped[str | None] = mapped_column(String(120))
    commercial_use_allowed: Mapped[bool | None] = mapped_column(Boolean)
    primary_languages: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)

    artifacts: Mapped[list[ModelArtifact]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("context_length > 0", name="ck_models_context_length_positive"),
        CheckConstraint(
            "parameter_count_b IS NULL OR parameter_count_b > 0",
            name="ck_models_parameter_count_positive",
        ),
    )

class ModelArtifact(TimestampMixin, Base):
    __tablename__ = "model_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(80), nullable=False)
    quantization: Mapped[str | None] = mapped_column(String(80))
    precision: Mapped[str | None] = mapped_column(String(80))
    file_size_gb: Mapped[float | None] = mapped_column(Float)
    minimum_vram_gb: Mapped[float | None] = mapped_column(Float)
    recommended_vram_gb: Mapped[float | None] = mapped_column(Float)
    context_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_compatibility: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    checksum: Mapped[str | None] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    model: Mapped[Model] = relationship(back_populates="artifacts")
    benchmark_runs: Mapped[list[BenchmarkRun]] = relationship(back_populates="model_artifact")
    deployment_configurations: Mapped[list[DeploymentConfiguration]] = relationship(
        back_populates="model_artifact"
    )
    attestations: Mapped[list[ModelArtifactAttestation]] = relationship(
        back_populates="model_artifact",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "file_size_gb IS NULL OR file_size_gb >= 0",
            name="ck_model_artifacts_file_size_non_negative",
        ),
        CheckConstraint(
            "minimum_vram_gb IS NULL OR minimum_vram_gb >= 0",
            name="ck_model_artifacts_min_vram_non_negative",
        ),
        CheckConstraint(
            "recommended_vram_gb IS NULL OR recommended_vram_gb >= 0",
            name="ck_model_artifacts_recommended_vram_non_negative",
        ),
        CheckConstraint("context_limit > 0", name="ck_model_artifacts_context_limit_positive"),
    )

class ModelArtifactAttestation(TimestampMixin, Base):
    __tablename__ = "model_artifact_attestations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    model_artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("model_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    manifest_version: Mapped[str] = mapped_column(String(80), nullable=False)
    runtime_provider: Mapped[str] = mapped_column(String(80), nullable=False)
    runtime_model_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    digest_algorithm: Mapped[str] = mapped_column(String(20), nullable=False)
    digest_value: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    verification_method: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="verified", index=True)
    attested_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    attested_by_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    attestation_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    model_artifact: Mapped[ModelArtifact] = relationship(back_populates="attestations")
    supply_chain_attestations: Mapped[list[ModelSupplyChainAttestation]] = relationship(
        back_populates="runtime_attestation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "model_artifact_id",
            "digest_value",
            name="uq_model_artifact_attestations_artifact_digest",
        ),
        CheckConstraint(
            "digest_algorithm IN ('sha256')",
            name="ck_model_artifact_attestations_digest_algorithm",
        ),
        CheckConstraint(
            "status IN ('verified', 'revoked')",
            name="ck_model_artifact_attestations_status",
        ),
    )
