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

    from app.models.agent import AgentApprovalCheckpoint
    from app.models.catalog import (
        HardwareProfile,
        ModelArtifact,
    )
    from app.models.release import ReleaseDecision
    from app.models.trust import ProductionEvidenceReceipt



class BenchmarkTask(TimestampMixin, Base):
    __tablename__ = "benchmark_tasks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str] = mapped_column(String(80), nullable=False)
    input_format: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_output_format: Mapped[str] = mapped_column(String(80), nullable=False)
    scoring_method: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    prompt_versions: Mapped[list[PromptVersion]] = relationship(
        back_populates="benchmark_task", cascade="all, delete-orphan"
    )
    benchmark_runs: Mapped[list[BenchmarkRun]] = relationship(back_populates="benchmark_task")

class PromptVersion(TimestampMixin, Base):
    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    benchmark_task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("benchmark_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    user_template: Mapped[str] = mapped_column(Text, nullable=False)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    benchmark_task: Mapped[BenchmarkTask] = relationship(back_populates="prompt_versions")
    benchmark_runs: Mapped[list[BenchmarkRun]] = relationship(back_populates="prompt_version")

class ExperimentLineageEvent(TimestampMixin, Base):
    __tablename__ = "experiment_lineage_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    primary_entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    primary_entity_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    event_time: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    lineage_key: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    deployment_configuration_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("deployment_configurations.id"), index=True
    )
    evaluation_suite_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("evaluation_suites.id"), index=True
    )
    acceptance_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("acceptance_policies.id"), index=True
    )
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("prompt_versions.id"), index=True
    )
    benchmark_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("benchmark_runs.id"), index=True
    )
    gate_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("gate_evaluations.id"), index=True
    )
    deployment_baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("deployment_baselines.id"), index=True
    )
    release_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("release_decisions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="recorded", index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    data_source: Mapped[str] = mapped_column(String(80), nullable=False, default="system")

    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "primary_entity_id",
            name="uq_experiment_lineage_events_type_entity",
        ),
        CheckConstraint(
            "event_type IN ("
            "'prompt_version_created', "
            "'benchmark_run_created', "
            "'benchmark_run_completed', "
            "'benchmark_run_failed', "
            "'gate_evaluation_completed', "
            "'baseline_promoted', "
            "'baseline_superseded', "
            "'release_decision_signed'"
            ")",
            name="ck_experiment_lineage_events_event_type",
        ),
        CheckConstraint(
            "primary_entity_type IN ("
            "'prompt_version', "
            "'benchmark_run', "
            "'gate_evaluation', "
            "'deployment_baseline', "
            "'release_decision'"
            ")",
            name="ck_experiment_lineage_events_primary_entity_type",
        ),
        CheckConstraint(
            "status IN ('recorded', 'superseded', 'failed')",
            name="ck_experiment_lineage_events_status",
        ),
    )

class BenchmarkRun(TimestampMixin, Base):
    __tablename__ = "benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    hardware_profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("hardware_profiles.id"), nullable=False, index=True
    )
    model_artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("model_artifacts.id"), nullable=False, index=True
    )
    benchmark_task_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("benchmark_tasks.id"), nullable=False, index=True
    )
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("prompt_versions.id"), nullable=False, index=True
    )
    deployment_configuration_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("deployment_configurations.id"), index=True
    )
    evaluation_suite_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("evaluation_suites.id"), index=True
    )
    parent_benchmark_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("benchmark_runs.id", ondelete="SET NULL"),
        index=True,
    )
    root_benchmark_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("benchmark_runs.id", ondelete="SET NULL"),
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision_reason: Mapped[str | None] = mapped_column(String(120))
    evidence_revision_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    runtime_name: Mapped[str] = mapped_column(String(120), nullable=False)
    runtime_version: Mapped[str | None] = mapped_column(String(80))
    runtime_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(80), nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    data_source: Mapped[str] = mapped_column(String(80), nullable=False, default="synthetic_demo")

    hardware_profile: Mapped[HardwareProfile] = relationship(back_populates="benchmark_runs")
    model_artifact: Mapped[ModelArtifact] = relationship(back_populates="benchmark_runs")
    benchmark_task: Mapped[BenchmarkTask] = relationship(back_populates="benchmark_runs")
    prompt_version: Mapped[PromptVersion] = relationship(back_populates="benchmark_runs")
    deployment_configuration: Mapped[DeploymentConfiguration | None] = relationship(
        back_populates="benchmark_runs"
    )
    evaluation_suite: Mapped[EvaluationSuite | None] = relationship(back_populates="benchmark_runs")
    results: Mapped[list[BenchmarkResult]] = relationship(
        back_populates="benchmark_run", cascade="all, delete-orphan"
    )
    inference_metrics: Mapped[list[InferenceMetric]] = relationship(
        back_populates="benchmark_run", cascade="all, delete-orphan"
    )
    execution_logs: Mapped[list[BenchmarkExecutionLog]] = relationship(
        back_populates="benchmark_run", cascade="all, delete-orphan"
    )
    production_evidence_receipts: Mapped[list[ProductionEvidenceReceipt]] = relationship(
        back_populates="benchmark_run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "revision_number > 0",
            name="ck_benchmark_runs_revision_number_positive",
        ),
    )

class BenchmarkResult(TimestampMixin, Base):
    __tablename__ = "benchmark_results"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    benchmark_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evaluation_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("evaluation_cases.id"), index=True
    )
    parent_benchmark_result_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("benchmark_results.id", ondelete="SET NULL"),
        index=True,
    )
    root_benchmark_result_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("benchmark_results.id", ondelete="SET NULL"),
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    evidence_revision_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    sample_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    quality_score: Mapped[float | None] = mapped_column(Float)
    exact_match: Mapped[bool | None] = mapped_column(Boolean)
    json_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tool_call_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    groundedness_score: Mapped[float | None] = mapped_column(Float)
    faithfulness_score: Mapped[float | None] = mapped_column(Float)
    human_label: Mapped[str | None] = mapped_column(String(120))
    error_type: Mapped[str | None] = mapped_column(String(120))
    raw_output: Mapped[str | None] = mapped_column(Text)
    normalized_output: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    data_source: Mapped[str] = mapped_column(String(80), nullable=False, default="synthetic_demo")

    benchmark_run: Mapped[BenchmarkRun] = relationship(back_populates="results")
    evaluation_case: Mapped[EvaluationCase | None] = relationship(back_populates="results")
    agent_approval_checkpoints: Mapped[list[AgentApprovalCheckpoint]] = relationship(
        back_populates="benchmark_result",
        cascade="all, delete-orphan",
        foreign_keys="AgentApprovalCheckpoint.benchmark_result_id",
    )

    __table_args__ = (
        CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_benchmark_results_quality_score_range",
        ),
        CheckConstraint(
            "groundedness_score IS NULL OR (groundedness_score >= 0 AND groundedness_score <= 1)",
            name="ck_benchmark_results_groundedness_range",
        ),
        CheckConstraint(
            "faithfulness_score IS NULL OR (faithfulness_score >= 0 AND faithfulness_score <= 1)",
            name="ck_benchmark_results_faithfulness_range",
        ),
        CheckConstraint(
            "revision_number > 0",
            name="ck_benchmark_results_revision_number_positive",
        ),
    )

class JudgeLabelReviewDecision(TimestampMixin, Base):
    __tablename__ = "judge_label_review_decisions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    benchmark_result_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("benchmark_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluation_case_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("evaluation_cases.id", ondelete="SET NULL"),
        index=True,
    )
    decision_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    candidate_label_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    prior_scores_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    applied_scores_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    reviewer_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    identity_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True
    )
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    criticality: Mapped[str | None] = mapped_column(String(40), index=True)
    reviewed_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=utcnow, index=True
    )
    review_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    __table_args__ = (
        CheckConstraint(
            "decision_type IN ('approved_candidate', 'overridden', 'rejected')",
            name="ck_judge_label_review_decisions_type",
        ),
    )

class InferenceMetric(TimestampMixin, Base):
    __tablename__ = "inference_metrics"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    benchmark_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    ttft_ms: Mapped[float] = mapped_column(Float, nullable=False)
    end_to_end_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_per_second: Mapped[float] = mapped_column(Float, nullable=False)
    gpu_vram_used_mb: Mapped[float | None] = mapped_column(Float)
    gpu_utilization_pct: Mapped[float | None] = mapped_column(Float)
    cpu_utilization_pct: Mapped[float | None] = mapped_column(Float)
    peak_memory_mb: Mapped[float | None] = mapped_column(Float)
    oom_occurred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_source: Mapped[str] = mapped_column(String(80), nullable=False, default="synthetic_demo")

    benchmark_run: Mapped[BenchmarkRun] = relationship(back_populates="inference_metrics")

    __table_args__ = (
        CheckConstraint("ttft_ms >= 0", name="ck_inference_metrics_ttft_non_negative"),
        CheckConstraint(
            "end_to_end_latency_ms >= 0",
            name="ck_inference_metrics_latency_non_negative",
        ),
        CheckConstraint("prompt_tokens >= 0", name="ck_inference_metrics_prompt_tokens"),
        CheckConstraint("completion_tokens >= 0", name="ck_inference_metrics_completion_tokens"),
        CheckConstraint(
            "tokens_per_second >= 0",
            name="ck_inference_metrics_tokens_per_second_non_negative",
        ),
        CheckConstraint(
            "gpu_vram_used_mb IS NULL OR gpu_vram_used_mb >= 0",
            name="ck_inference_metrics_gpu_vram_non_negative",
        ),
        CheckConstraint(
            "gpu_utilization_pct IS NULL OR "
            "(gpu_utilization_pct >= 0 AND gpu_utilization_pct <= 100)",
            name="ck_inference_metrics_gpu_utilization_range",
        ),
        CheckConstraint(
            "cpu_utilization_pct IS NULL OR "
            "(cpu_utilization_pct >= 0 AND cpu_utilization_pct <= 100)",
            name="ck_inference_metrics_cpu_utilization_range",
        ),
        CheckConstraint(
            "peak_memory_mb IS NULL OR peak_memory_mb >= 0",
            name="ck_inference_metrics_peak_memory_non_negative",
        ),
        CheckConstraint("retry_count >= 0", name="ck_inference_metrics_retry_count"),
    )

class BenchmarkExecutionLog(TimestampMixin, Base):
    __tablename__ = "benchmark_execution_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    benchmark_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("benchmark_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(40), nullable=False, default="info", index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    occurred_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    data_source: Mapped[str] = mapped_column(String(80), nullable=False, default="captured_demo")

    benchmark_run: Mapped[BenchmarkRun] = relationship(back_populates="execution_logs")

    __table_args__ = (
        CheckConstraint(
            "level IN ('debug', 'info', 'warning', 'error')",
            name="ck_benchmark_execution_logs_level",
        ),
    )

class RecommendationScenario(TimestampMixin, Base):
    __tablename__ = "recommendation_scenarios"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

class WorkloadProfile(TimestampMixin, Base):
    __tablename__ = "workload_profiles"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(120), nullable=False)
    primary_language: Mapped[str] = mapped_column(String(40), nullable=False)
    local_only_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    data_classification: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_output_modes_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    risk_notes: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    evaluation_suites: Mapped[list[EvaluationSuite]] = relationship(
        back_populates="workload_profile", cascade="all, delete-orphan"
    )
    acceptance_policies: Mapped[list[AcceptancePolicy]] = relationship(
        back_populates="workload_profile", cascade="all, delete-orphan"
    )
    deployment_configurations: Mapped[list[DeploymentConfiguration]] = relationship(
        back_populates="workload_profile"
    )

class EvaluationSuite(TimestampMixin, Base):
    __tablename__ = "evaluation_suites"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    workload_profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("workload_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suite_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    dataset_source: Mapped[str] = mapped_column(String(120), nullable=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    workload_profile: Mapped[WorkloadProfile] = relationship(back_populates="evaluation_suites")
    cases: Mapped[list[EvaluationCase]] = relationship(
        back_populates="evaluation_suite", cascade="all, delete-orphan"
    )
    benchmark_runs: Mapped[list[BenchmarkRun]] = relationship(back_populates="evaluation_suite")
    gate_evaluations: Mapped[list[GateEvaluation]] = relationship(back_populates="evaluation_suite")

    __table_args__ = (
        UniqueConstraint(
            "workload_profile_id",
            "version_label",
            name="uq_evaluation_suites_workload_version",
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_evaluation_suites_status",
        ),
    )

class EvaluationCase(TimestampMixin, Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    evaluation_suite_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("evaluation_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_case_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    input_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    expected_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reference_context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    expected_tool_schema_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    criticality: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    data_source: Mapped[str] = mapped_column(String(80), nullable=False)

    evaluation_suite: Mapped[EvaluationSuite] = relationship(back_populates="cases")
    results: Mapped[list[BenchmarkResult]] = relationship(back_populates="evaluation_case")

    __table_args__ = (
        UniqueConstraint(
            "evaluation_suite_id",
            "external_case_id",
            name="uq_evaluation_cases_suite_external_id",
        ),
        CheckConstraint(
            "criticality IN ('critical', 'standard', 'exploratory')",
            name="ck_evaluation_cases_criticality",
        ),
        CheckConstraint("weight > 0", name="ck_evaluation_cases_weight_positive"),
    )

class MetricDefinition(TimestampMixin, Base):
    __tablename__ = "metric_definitions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    domain: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(40), nullable=False)
    direction: Mapped[str] = mapped_column(String(40), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(80), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    policy_rules: Mapped[list[AcceptancePolicyRule]] = relationship(
        back_populates="metric_definition"
    )

    __table_args__ = (
        CheckConstraint(
            "domain IN ('quality', 'reliability', 'performance', 'resource', "
            "'governance', 'evidence')",
            name="ck_metric_definitions_domain",
        ),
        CheckConstraint(
            "aggregation IN ('mean', 'rate', 'p50', 'p95', 'p99', 'max', 'min', 'count')",
            name="ck_metric_definitions_aggregation",
        ),
        CheckConstraint(
            "direction IN ('higher_is_better', 'lower_is_better', 'exact')",
            name="ck_metric_definitions_direction",
        ),
    )

class AcceptancePolicy(TimestampMixin, Base):
    __tablename__ = "acceptance_policies"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    workload_profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("workload_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    allow_conditional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    workload_profile: Mapped[WorkloadProfile] = relationship(back_populates="acceptance_policies")
    rules: Mapped[list[AcceptancePolicyRule]] = relationship(
        back_populates="acceptance_policy", cascade="all, delete-orphan"
    )
    gate_evaluations: Mapped[list[GateEvaluation]] = relationship(
        back_populates="acceptance_policy"
    )

    __table_args__ = (
        UniqueConstraint(
            "workload_profile_id",
            "version_label",
            name="uq_acceptance_policies_workload_version",
        ),
    )

class AcceptancePolicyRule(TimestampMixin, Base):
    __tablename__ = "acceptance_policy_rules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    acceptance_policy_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("acceptance_policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_definition_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("metric_definitions.id"), nullable=False, index=True
    )
    rule_name: Mapped[str] = mapped_column(String(180), nullable=False)
    operator: Mapped[str] = mapped_column(String(20), nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    minimum_sample_size: Mapped[int | None] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    message_on_fail: Mapped[str] = mapped_column(Text, nullable=False)

    acceptance_policy: Mapped[AcceptancePolicy] = relationship(back_populates="rules")
    metric_definition: Mapped[MetricDefinition] = relationship(back_populates="policy_rules")
    rule_results: Mapped[list[GateRuleResult]] = relationship(back_populates="policy_rule")

    __table_args__ = (
        CheckConstraint(
            "operator IN ('gte', 'lte', 'eq', 'gt', 'lt')",
            name="ck_acceptance_policy_rules_operator",
        ),
        CheckConstraint(
            "severity IN ('blocker', 'warning')",
            name="ck_acceptance_policy_rules_severity",
        ),
        CheckConstraint(
            "minimum_sample_size IS NULL OR minimum_sample_size >= 0",
            name="ck_acceptance_policy_rules_minimum_sample_size",
        ),
    )

class DeploymentConfiguration(TimestampMixin, Base):
    __tablename__ = "deployment_configurations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    workload_profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("workload_profiles.id"), nullable=False, index=True
    )
    hardware_profile_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("hardware_profiles.id"), nullable=False, index=True
    )
    model_artifact_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("model_artifacts.id"), nullable=False, index=True
    )
    runtime_name: Mapped[str] = mapped_column(String(120), nullable=False)
    runtime_version: Mapped[str | None] = mapped_column(String(80))
    runtime_config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    context_length: Mapped[int] = mapped_column(Integer, nullable=False)
    generation_config_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    prompt_bundle_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_schema_version: Mapped[str | None] = mapped_column(String(80))
    tool_schema_version: Mapped[str | None] = mapped_column(String(80))
    retrieval_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    concurrency_target: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    configuration_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text)

    workload_profile: Mapped[WorkloadProfile] = relationship(
        back_populates="deployment_configurations"
    )
    hardware_profile: Mapped[HardwareProfile] = relationship(
        back_populates="deployment_configurations"
    )
    model_artifact: Mapped[ModelArtifact] = relationship(back_populates="deployment_configurations")
    benchmark_runs: Mapped[list[BenchmarkRun]] = relationship(
        back_populates="deployment_configuration"
    )
    gate_evaluations: Mapped[list[GateEvaluation]] = relationship(
        back_populates="deployment_configuration"
    )
    deployment_baselines: Mapped[list[DeploymentBaseline]] = relationship(
        back_populates="deployment_configuration"
    )

    __table_args__ = (
        CheckConstraint("context_length > 0", name="ck_deployment_configurations_context_length"),
        CheckConstraint(
            "concurrency_target > 0", name="ck_deployment_configurations_concurrency_target"
        ),
        CheckConstraint(
            "status IN ('draft', 'ready', 'archived')",
            name="ck_deployment_configurations_status",
        ),
    )

class GateEvaluation(TimestampMixin, Base):
    __tablename__ = "gate_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    deployment_configuration_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("deployment_configurations.id"), nullable=False, index=True
    )
    evaluation_suite_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("evaluation_suites.id"), nullable=False, index=True
    )
    acceptance_policy_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("acceptance_policies.id"), nullable=False, index=True
    )
    baseline_gate_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("gate_evaluations.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed", index=True)
    verdict: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    evidence_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    scorecard_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    decision_summary: Mapped[str] = mapped_column(Text, nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evidence_revision_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    stale_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime(), index=True)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    superseded_by_gate_evaluation_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("gate_evaluations.id", ondelete="SET NULL"), index=True
    )
    evaluated_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)

    deployment_configuration: Mapped[DeploymentConfiguration] = relationship(
        back_populates="gate_evaluations"
    )
    evaluation_suite: Mapped[EvaluationSuite] = relationship(back_populates="gate_evaluations")
    acceptance_policy: Mapped[AcceptancePolicy] = relationship(back_populates="gate_evaluations")
    baseline_gate_evaluation: Mapped[GateEvaluation | None] = relationship(
        remote_side="GateEvaluation.id",
        foreign_keys=[baseline_gate_evaluation_id],
    )
    rule_results: Mapped[list[GateRuleResult]] = relationship(
        back_populates="gate_evaluation", cascade="all, delete-orphan"
    )
    baseline_promotions: Mapped[list[DeploymentBaseline]] = relationship(
        back_populates="gate_evaluation",
        foreign_keys="DeploymentBaseline.gate_evaluation_id",
    )
    release_decisions: Mapped[list[ReleaseDecision]] = relationship(
        back_populates="gate_evaluation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'completed', 'failed', 'stale')",
            name="ck_gate_evaluations_status",
        ),
        CheckConstraint(
            "verdict IN ('APPROVED', 'CONDITIONAL', 'BLOCKED', 'INSUFFICIENT_EVIDENCE')",
            name="ck_gate_evaluations_verdict",
        ),
    )

class DeploymentBaseline(TimestampMixin, Base):
    __tablename__ = "deployment_baselines"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    deployment_configuration_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("deployment_configurations.id"), nullable=False, index=True
    )
    evaluation_suite_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("evaluation_suites.id"), nullable=False, index=True
    )
    acceptance_policy_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("acceptance_policies.id"), nullable=False, index=True
    )
    gate_evaluation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("gate_evaluations.id"), nullable=False, index=True
    )
    promoted_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    promoted_by: Mapped[str | None] = mapped_column(String(120))
    promotion_reason: Mapped[str | None] = mapped_column(Text)
    baseline_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    superseded_at: Mapped[dt.datetime | None] = mapped_column(UTCDateTime())
    superseded_by_baseline_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("deployment_baselines.id"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    deployment_configuration: Mapped[DeploymentConfiguration] = relationship(
        back_populates="deployment_baselines"
    )
    evaluation_suite: Mapped[EvaluationSuite] = relationship()
    acceptance_policy: Mapped[AcceptancePolicy] = relationship()
    gate_evaluation: Mapped[GateEvaluation] = relationship(
        foreign_keys=[gate_evaluation_id],
        back_populates="baseline_promotions",
    )
    superseded_by_baseline: Mapped[DeploymentBaseline | None] = relationship(
        remote_side="DeploymentBaseline.id"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'superseded', 'archived')",
            name="ck_deployment_baselines_status",
        ),
    )

class GateRuleResult(TimestampMixin, Base):
    __tablename__ = "gate_rule_results"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    gate_evaluation_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("gate_evaluations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    acceptance_policy_rule_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("acceptance_policy_rules.id"), nullable=False, index=True
    )
    metric_value: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    gate_evaluation: Mapped[GateEvaluation] = relationship(back_populates="rule_results")
    policy_rule: Mapped[AcceptancePolicyRule] = relationship(back_populates="rule_results")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pass', 'fail', 'insufficient')",
            name="ck_gate_rule_results_status",
        ),
        CheckConstraint(
            "severity IN ('blocker', 'warning')",
            name="ck_gate_rule_results_severity",
        ),
        CheckConstraint("sample_size >= 0", name="ck_gate_rule_results_sample_size"),
    )
