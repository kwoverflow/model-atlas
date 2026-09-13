"""initial schema

Revision ID: 202607040001
Revises:
Create Date: 2026-07-04 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607040001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "hardware_profiles",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("cpu_name", sa.String(length=160), nullable=False),
        sa.Column("cpu_cores", sa.Integer(), nullable=False),
        sa.Column("ram_gb", sa.Integer(), nullable=False),
        sa.Column("gpu_name", sa.String(length=160), nullable=False),
        sa.Column("gpu_vram_gb", sa.Integer(), nullable=False),
        sa.Column("gpu_count", sa.Integer(), nullable=False),
        sa.Column("os_name", sa.String(length=120), nullable=True),
        sa.Column("cuda_version", sa.String(length=40), nullable=True),
        sa.Column("driver_version", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("cpu_cores > 0", name="ck_hardware_profiles_cpu_cores_positive"),
        sa.CheckConstraint("gpu_count > 0", name="ck_hardware_profiles_gpu_count_positive"),
        sa.CheckConstraint(
            "gpu_vram_gb >= 0", name="ck_hardware_profiles_gpu_vram_non_negative"
        ),
        sa.CheckConstraint("ram_gb > 0", name="ck_hardware_profiles_ram_gb_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_hardware_profiles_name"), "hardware_profiles", ["name"], unique=False)

    op.create_table(
        "models",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("family", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("parameter_count_b", sa.Float(), nullable=True),
        sa.Column("architecture_type", sa.String(length=120), nullable=False),
        sa.Column("supports_text", sa.Boolean(), nullable=False),
        sa.Column("supports_vision", sa.Boolean(), nullable=False),
        sa.Column("supports_tool_calling", sa.Boolean(), nullable=False),
        sa.Column("supports_structured_output", sa.Boolean(), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=False),
        sa.Column("license_name", sa.String(length=120), nullable=True),
        sa.Column("commercial_use_allowed", sa.Boolean(), nullable=True),
        sa.Column("primary_languages", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("context_length > 0", name="ck_models_context_length_positive"),
        sa.CheckConstraint(
            "parameter_count_b IS NULL OR parameter_count_b > 0",
            name="ck_models_parameter_count_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_models_family"), "models", ["family"], unique=False)
    op.create_index(op.f("ix_models_name"), "models", ["name"], unique=False)
    op.create_index(op.f("ix_models_provider"), "models", ["provider"], unique=False)

    op.create_table(
        "benchmark_tasks",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=80), nullable=False),
        sa.Column("input_format", sa.String(length=80), nullable=False),
        sa.Column("expected_output_format", sa.String(length=80), nullable=False),
        sa.Column("scoring_method", sa.String(length=120), nullable=False),
        sa.Column("dataset_version", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_benchmark_tasks_is_active"),
        "benchmark_tasks",
        ["is_active"],
        unique=False,
    )
    op.create_index(op.f("ix_benchmark_tasks_name"), "benchmark_tasks", ["name"], unique=False)

    op.create_table(
        "model_artifacts",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("model_id", uuid_type, nullable=False),
        sa.Column("artifact_name", sa.String(length=180), nullable=False),
        sa.Column("format", sa.String(length=80), nullable=False),
        sa.Column("quantization", sa.String(length=80), nullable=True),
        sa.Column("precision", sa.String(length=80), nullable=True),
        sa.Column("file_size_gb", sa.Float(), nullable=True),
        sa.Column("minimum_vram_gb", sa.Float(), nullable=True),
        sa.Column("recommended_vram_gb", sa.Float(), nullable=True),
        sa.Column("context_limit", sa.Integer(), nullable=False),
        sa.Column("runtime_compatibility", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(length=160), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "context_limit > 0", name="ck_model_artifacts_context_limit_positive"
        ),
        sa.CheckConstraint(
            "file_size_gb IS NULL OR file_size_gb >= 0",
            name="ck_model_artifacts_file_size_non_negative",
        ),
        sa.CheckConstraint(
            "minimum_vram_gb IS NULL OR minimum_vram_gb >= 0",
            name="ck_model_artifacts_min_vram_non_negative",
        ),
        sa.CheckConstraint(
            "recommended_vram_gb IS NULL OR recommended_vram_gb >= 0",
            name="ck_model_artifacts_recommended_vram_non_negative",
        ),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_model_artifacts_artifact_name"), "model_artifacts", ["artifact_name"], unique=False
    )
    op.create_index(
        op.f("ix_model_artifacts_is_active"),
        "model_artifacts",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_model_artifacts_model_id"),
        "model_artifacts",
        ["model_id"],
        unique=False,
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("benchmark_task_id", uuid_type, nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=True),
        sa.Column("prompt_hash", sa.String(length=128), nullable=False),
        sa.Column("version_label", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["benchmark_task_id"], ["benchmark_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_prompt_versions_benchmark_task_id"),
        "prompt_versions",
        ["benchmark_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_prompt_versions_is_active"),
        "prompt_versions",
        ["is_active"],
        unique=False,
    )
    op.create_index(op.f("ix_prompt_versions_name"), "prompt_versions", ["name"], unique=False)
    op.create_index(
        op.f("ix_prompt_versions_prompt_hash"), "prompt_versions", ["prompt_hash"], unique=False
    )

    op.create_table(
        "benchmark_runs",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("hardware_profile_id", uuid_type, nullable=False),
        sa.Column("model_artifact_id", uuid_type, nullable=False),
        sa.Column("benchmark_task_id", uuid_type, nullable=False),
        sa.Column("prompt_version_id", uuid_type, nullable=False),
        sa.Column("runtime_name", sa.String(length=120), nullable=False),
        sa.Column("runtime_version", sa.String(length=80), nullable=True),
        sa.Column("runtime_config_json", sa.JSON(), nullable=False),
        sa.Column("dataset_version", sa.String(length=80), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("data_source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["benchmark_task_id"], ["benchmark_tasks.id"]),
        sa.ForeignKeyConstraint(["hardware_profile_id"], ["hardware_profiles.id"]),
        sa.ForeignKeyConstraint(["model_artifact_id"], ["model_artifacts.id"]),
        sa.ForeignKeyConstraint(["prompt_version_id"], ["prompt_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_benchmark_runs_benchmark_task_id"),
        "benchmark_runs",
        ["benchmark_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_benchmark_runs_hardware_profile_id"),
        "benchmark_runs",
        ["hardware_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_benchmark_runs_model_artifact_id"),
        "benchmark_runs",
        ["model_artifact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_benchmark_runs_prompt_version_id"),
        "benchmark_runs",
        ["prompt_version_id"],
        unique=False,
    )
    op.create_index(op.f("ix_benchmark_runs_status"), "benchmark_runs", ["status"], unique=False)

    op.create_table(
        "benchmark_results",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("benchmark_run_id", uuid_type, nullable=False),
        sa.Column("sample_id", sa.String(length=120), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("exact_match", sa.Boolean(), nullable=True),
        sa.Column("json_valid", sa.Boolean(), nullable=False),
        sa.Column("tool_call_valid", sa.Boolean(), nullable=False),
        sa.Column("groundedness_score", sa.Float(), nullable=True),
        sa.Column("faithfulness_score", sa.Float(), nullable=True),
        sa.Column("human_label", sa.String(length=120), nullable=True),
        sa.Column("error_type", sa.String(length=120), nullable=True),
        sa.Column("raw_output", sa.Text(), nullable=True),
        sa.Column("normalized_output", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("data_source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "faithfulness_score IS NULL OR (faithfulness_score >= 0 AND faithfulness_score <= 1)",
            name="ck_benchmark_results_faithfulness_range",
        ),
        sa.CheckConstraint(
            "groundedness_score IS NULL OR (groundedness_score >= 0 AND groundedness_score <= 1)",
            name="ck_benchmark_results_groundedness_range",
        ),
        sa.CheckConstraint(
            "quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)",
            name="ck_benchmark_results_quality_score_range",
        ),
        sa.ForeignKeyConstraint(["benchmark_run_id"], ["benchmark_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_benchmark_results_benchmark_run_id"),
        "benchmark_results",
        ["benchmark_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_benchmark_results_sample_id"),
        "benchmark_results",
        ["sample_id"],
        unique=False,
    )

    op.create_table(
        "inference_metrics",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("benchmark_run_id", uuid_type, nullable=False),
        sa.Column("sample_id", sa.String(length=120), nullable=False),
        sa.Column("ttft_ms", sa.Float(), nullable=False),
        sa.Column("end_to_end_latency_ms", sa.Float(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("tokens_per_second", sa.Float(), nullable=False),
        sa.Column("gpu_vram_used_mb", sa.Float(), nullable=True),
        sa.Column("gpu_utilization_pct", sa.Float(), nullable=True),
        sa.Column("cpu_utilization_pct", sa.Float(), nullable=True),
        sa.Column("peak_memory_mb", sa.Float(), nullable=True),
        sa.Column("oom_occurred", sa.Boolean(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("data_source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "completion_tokens >= 0", name="ck_inference_metrics_completion_tokens"
        ),
        sa.CheckConstraint(
            "cpu_utilization_pct IS NULL OR "
            "(cpu_utilization_pct >= 0 AND cpu_utilization_pct <= 100)",
            name="ck_inference_metrics_cpu_utilization_range",
        ),
        sa.CheckConstraint(
            "end_to_end_latency_ms >= 0", name="ck_inference_metrics_latency_non_negative"
        ),
        sa.CheckConstraint(
            "gpu_utilization_pct IS NULL OR "
            "(gpu_utilization_pct >= 0 AND gpu_utilization_pct <= 100)",
            name="ck_inference_metrics_gpu_utilization_range",
        ),
        sa.CheckConstraint(
            "gpu_vram_used_mb IS NULL OR gpu_vram_used_mb >= 0",
            name="ck_inference_metrics_gpu_vram_non_negative",
        ),
        sa.CheckConstraint(
            "peak_memory_mb IS NULL OR peak_memory_mb >= 0",
            name="ck_inference_metrics_peak_memory_non_negative",
        ),
        sa.CheckConstraint("prompt_tokens >= 0", name="ck_inference_metrics_prompt_tokens"),
        sa.CheckConstraint("retry_count >= 0", name="ck_inference_metrics_retry_count"),
        sa.CheckConstraint(
            "tokens_per_second >= 0",
            name="ck_inference_metrics_tokens_per_second_non_negative",
        ),
        sa.CheckConstraint("ttft_ms >= 0", name="ck_inference_metrics_ttft_non_negative"),
        sa.ForeignKeyConstraint(["benchmark_run_id"], ["benchmark_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_inference_metrics_benchmark_run_id"),
        "inference_metrics",
        ["benchmark_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_inference_metrics_sample_id"),
        "inference_metrics",
        ["sample_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_inference_metrics_sample_id"), table_name="inference_metrics")
    op.drop_index(op.f("ix_inference_metrics_benchmark_run_id"), table_name="inference_metrics")
    op.drop_table("inference_metrics")
    op.drop_index(op.f("ix_benchmark_results_sample_id"), table_name="benchmark_results")
    op.drop_index(op.f("ix_benchmark_results_benchmark_run_id"), table_name="benchmark_results")
    op.drop_table("benchmark_results")
    op.drop_index(op.f("ix_benchmark_runs_status"), table_name="benchmark_runs")
    op.drop_index(op.f("ix_benchmark_runs_prompt_version_id"), table_name="benchmark_runs")
    op.drop_index(op.f("ix_benchmark_runs_model_artifact_id"), table_name="benchmark_runs")
    op.drop_index(op.f("ix_benchmark_runs_hardware_profile_id"), table_name="benchmark_runs")
    op.drop_index(op.f("ix_benchmark_runs_benchmark_task_id"), table_name="benchmark_runs")
    op.drop_table("benchmark_runs")
    op.drop_index(op.f("ix_prompt_versions_prompt_hash"), table_name="prompt_versions")
    op.drop_index(op.f("ix_prompt_versions_name"), table_name="prompt_versions")
    op.drop_index(op.f("ix_prompt_versions_is_active"), table_name="prompt_versions")
    op.drop_index(op.f("ix_prompt_versions_benchmark_task_id"), table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_index(op.f("ix_model_artifacts_model_id"), table_name="model_artifacts")
    op.drop_index(op.f("ix_model_artifacts_is_active"), table_name="model_artifacts")
    op.drop_index(op.f("ix_model_artifacts_artifact_name"), table_name="model_artifacts")
    op.drop_table("model_artifacts")
    op.drop_index(op.f("ix_benchmark_tasks_name"), table_name="benchmark_tasks")
    op.drop_index(op.f("ix_benchmark_tasks_is_active"), table_name="benchmark_tasks")
    op.drop_table("benchmark_tasks")
    op.drop_index(op.f("ix_models_provider"), table_name="models")
    op.drop_index(op.f("ix_models_name"), table_name="models")
    op.drop_index(op.f("ix_models_family"), table_name="models")
    op.drop_table("models")
    op.drop_index(op.f("ix_hardware_profiles_name"), table_name="hardware_profiles")
    op.drop_table("hardware_profiles")
