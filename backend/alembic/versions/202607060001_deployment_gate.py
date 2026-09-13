"""deployment gate

Revision ID: 202607060001
Revises: 202607050001
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "202607060001"
down_revision: str | None = "202607050001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

uuid_type = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "workload_profiles",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=120), nullable=False),
        sa.Column("primary_language", sa.String(length=40), nullable=False),
        sa.Column("local_only_required", sa.Boolean(), nullable=False),
        sa.Column("data_classification", sa.String(length=80), nullable=False),
        sa.Column("expected_output_modes_json", sa.JSON(), nullable=False),
        sa.Column("risk_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_workload_profiles_is_active"), "workload_profiles", ["is_active"])
    op.create_index(op.f("ix_workload_profiles_name"), "workload_profiles", ["name"])
    op.create_index(op.f("ix_workload_profiles_slug"), "workload_profiles", ["slug"])

    op.create_table(
        "metric_definitions",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("aggregation", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=40), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("calculation_version", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "aggregation IN ('mean', 'rate', 'p50', 'p95', 'max', 'min', 'count')",
            name="ck_metric_definitions_aggregation",
        ),
        sa.CheckConstraint(
            "direction IN ('higher_is_better', 'lower_is_better', 'exact')",
            name="ck_metric_definitions_direction",
        ),
        sa.CheckConstraint(
            "domain IN ('quality', 'reliability', 'performance', 'resource', "
            "'governance', 'evidence')",
            name="ck_metric_definitions_domain",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_metric_definitions_is_active"), "metric_definitions", ["is_active"])
    op.create_index(op.f("ix_metric_definitions_key"), "metric_definitions", ["key"])

    op.create_table(
        "evaluation_suites",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("workload_profile_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("version_label", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suite_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("dataset_source", sa.String(length=120), nullable=False),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="ck_evaluation_suites_status",
        ),
        sa.ForeignKeyConstraint(
            ["workload_profile_id"],
            ["workload_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workload_profile_id",
            "version_label",
            name="uq_evaluation_suites_workload_version",
        ),
    )
    op.create_index(op.f("ix_evaluation_suites_name"), "evaluation_suites", ["name"])
    op.create_index(op.f("ix_evaluation_suites_status"), "evaluation_suites", ["status"])
    op.create_index(op.f("ix_evaluation_suites_suite_hash"), "evaluation_suites", ["suite_hash"])
    op.create_index(
        op.f("ix_evaluation_suites_workload_profile_id"),
        "evaluation_suites",
        ["workload_profile_id"],
    )

    op.create_table(
        "acceptance_policies",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("workload_profile_id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("version_label", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("policy_hash", sa.String(length=128), nullable=False),
        sa.Column("allow_conditional", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workload_profile_id"],
            ["workload_profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workload_profile_id",
            "version_label",
            name="uq_acceptance_policies_workload_version",
        ),
    )
    op.create_index(op.f("ix_acceptance_policies_is_active"), "acceptance_policies", ["is_active"])
    op.create_index(op.f("ix_acceptance_policies_name"), "acceptance_policies", ["name"])
    op.create_index(
        op.f("ix_acceptance_policies_policy_hash"),
        "acceptance_policies",
        ["policy_hash"],
    )
    op.create_index(
        op.f("ix_acceptance_policies_workload_profile_id"),
        "acceptance_policies",
        ["workload_profile_id"],
    )

    op.create_table(
        "deployment_configurations",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("workload_profile_id", uuid_type, nullable=False),
        sa.Column("hardware_profile_id", uuid_type, nullable=False),
        sa.Column("model_artifact_id", uuid_type, nullable=False),
        sa.Column("runtime_name", sa.String(length=120), nullable=False),
        sa.Column("runtime_version", sa.String(length=80), nullable=True),
        sa.Column("runtime_config_json", sa.JSON(), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=False),
        sa.Column("generation_config_json", sa.JSON(), nullable=False),
        sa.Column("prompt_bundle_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_version", sa.String(length=80), nullable=True),
        sa.Column("tool_schema_version", sa.String(length=80), nullable=True),
        sa.Column("retrieval_config_json", sa.JSON(), nullable=True),
        sa.Column("concurrency_target", sa.Integer(), nullable=False),
        sa.Column("configuration_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "concurrency_target > 0",
            name="ck_deployment_configurations_concurrency_target",
        ),
        sa.CheckConstraint(
            "context_length > 0",
            name="ck_deployment_configurations_context_length",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'ready', 'archived')",
            name="ck_deployment_configurations_status",
        ),
        sa.ForeignKeyConstraint(["hardware_profile_id"], ["hardware_profiles.id"]),
        sa.ForeignKeyConstraint(["model_artifact_id"], ["model_artifacts.id"]),
        sa.ForeignKeyConstraint(["workload_profile_id"], ["workload_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_deployment_configurations_configuration_hash"),
        "deployment_configurations",
        ["configuration_hash"],
    )
    op.create_index(
        op.f("ix_deployment_configurations_hardware_profile_id"),
        "deployment_configurations",
        ["hardware_profile_id"],
    )
    op.create_index(
        op.f("ix_deployment_configurations_model_artifact_id"),
        "deployment_configurations",
        ["model_artifact_id"],
    )
    op.create_index(
        op.f("ix_deployment_configurations_name"),
        "deployment_configurations",
        ["name"],
    )
    op.create_index(
        op.f("ix_deployment_configurations_status"),
        "deployment_configurations",
        ["status"],
    )
    op.create_index(
        op.f("ix_deployment_configurations_workload_profile_id"),
        "deployment_configurations",
        ["workload_profile_id"],
    )

    op.create_table(
        "acceptance_policy_rules",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("acceptance_policy_id", uuid_type, nullable=False),
        sa.Column("metric_definition_id", uuid_type, nullable=False),
        sa.Column("rule_name", sa.String(length=180), nullable=False),
        sa.Column("operator", sa.String(length=20), nullable=False),
        sa.Column("threshold_value", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("minimum_sample_size", sa.Integer(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("message_on_fail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "minimum_sample_size IS NULL OR minimum_sample_size >= 0",
            name="ck_acceptance_policy_rules_minimum_sample_size",
        ),
        sa.CheckConstraint(
            "operator IN ('gte', 'lte', 'eq', 'gt', 'lt')",
            name="ck_acceptance_policy_rules_operator",
        ),
        sa.CheckConstraint(
            "severity IN ('blocker', 'warning')",
            name="ck_acceptance_policy_rules_severity",
        ),
        sa.ForeignKeyConstraint(
            ["acceptance_policy_id"],
            ["acceptance_policies.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["metric_definition_id"], ["metric_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_acceptance_policy_rules_acceptance_policy_id"),
        "acceptance_policy_rules",
        ["acceptance_policy_id"],
    )
    op.create_index(
        op.f("ix_acceptance_policy_rules_enabled"),
        "acceptance_policy_rules",
        ["enabled"],
    )
    op.create_index(
        op.f("ix_acceptance_policy_rules_metric_definition_id"),
        "acceptance_policy_rules",
        ["metric_definition_id"],
    )

    op.create_table(
        "evaluation_cases",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("evaluation_suite_id", uuid_type, nullable=False),
        sa.Column("external_case_id", sa.String(length=120), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("input_payload_json", sa.JSON(), nullable=False),
        sa.Column("expected_output_json", sa.JSON(), nullable=True),
        sa.Column("reference_context_json", sa.JSON(), nullable=True),
        sa.Column("expected_tool_schema_json", sa.JSON(), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("criticality", sa.String(length=40), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("data_source", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "criticality IN ('critical', 'standard', 'exploratory')",
            name="ck_evaluation_cases_criticality",
        ),
        sa.CheckConstraint("weight > 0", name="ck_evaluation_cases_weight_positive"),
        sa.ForeignKeyConstraint(
            ["evaluation_suite_id"],
            ["evaluation_suites.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evaluation_suite_id",
            "external_case_id",
            name="uq_evaluation_cases_suite_external_id",
        ),
    )
    op.create_index(op.f("ix_evaluation_cases_category"), "evaluation_cases", ["category"])
    op.create_index(
        op.f("ix_evaluation_cases_criticality"),
        "evaluation_cases",
        ["criticality"],
    )
    op.create_index(
        op.f("ix_evaluation_cases_evaluation_suite_id"),
        "evaluation_cases",
        ["evaluation_suite_id"],
    )
    op.create_index(
        op.f("ix_evaluation_cases_external_case_id"),
        "evaluation_cases",
        ["external_case_id"],
    )
    op.create_index(op.f("ix_evaluation_cases_is_active"), "evaluation_cases", ["is_active"])

    op.add_column("benchmark_runs", sa.Column("deployment_configuration_id", uuid_type))
    op.add_column("benchmark_runs", sa.Column("evaluation_suite_id", uuid_type))
    op.create_index(
        op.f("ix_benchmark_runs_deployment_configuration_id"),
        "benchmark_runs",
        ["deployment_configuration_id"],
    )
    op.create_index(
        op.f("ix_benchmark_runs_evaluation_suite_id"),
        "benchmark_runs",
        ["evaluation_suite_id"],
    )
    op.create_foreign_key(
        op.f("fk_benchmark_runs_deployment_configuration_id_deployment_configurations"),
        "benchmark_runs",
        "deployment_configurations",
        ["deployment_configuration_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_benchmark_runs_evaluation_suite_id_evaluation_suites"),
        "benchmark_runs",
        "evaluation_suites",
        ["evaluation_suite_id"],
        ["id"],
    )

    op.add_column("benchmark_results", sa.Column("evaluation_case_id", uuid_type))
    op.create_index(
        op.f("ix_benchmark_results_evaluation_case_id"),
        "benchmark_results",
        ["evaluation_case_id"],
    )
    op.create_foreign_key(
        op.f("fk_benchmark_results_evaluation_case_id_evaluation_cases"),
        "benchmark_results",
        "evaluation_cases",
        ["evaluation_case_id"],
        ["id"],
    )

    op.create_table(
        "gate_evaluations",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("deployment_configuration_id", uuid_type, nullable=False),
        sa.Column("evaluation_suite_id", uuid_type, nullable=False),
        sa.Column("acceptance_policy_id", uuid_type, nullable=False),
        sa.Column("baseline_gate_evaluation_id", uuid_type, nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("verdict", sa.String(length=40), nullable=False),
        sa.Column("evidence_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("scorecard_json", sa.JSON(), nullable=False),
        sa.Column("decision_summary", sa.Text(), nullable=False),
        sa.Column("decision_hash", sa.String(length=128), nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'completed', 'failed')",
            name="ck_gate_evaluations_status",
        ),
        sa.CheckConstraint(
            "verdict IN ('APPROVED', 'CONDITIONAL', 'BLOCKED', 'INSUFFICIENT_EVIDENCE')",
            name="ck_gate_evaluations_verdict",
        ),
        sa.ForeignKeyConstraint(["acceptance_policy_id"], ["acceptance_policies.id"]),
        sa.ForeignKeyConstraint(["baseline_gate_evaluation_id"], ["gate_evaluations.id"]),
        sa.ForeignKeyConstraint(
            ["deployment_configuration_id"],
            ["deployment_configurations.id"],
        ),
        sa.ForeignKeyConstraint(["evaluation_suite_id"], ["evaluation_suites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_gate_evaluations_acceptance_policy_id"),
        "gate_evaluations",
        ["acceptance_policy_id"],
    )
    op.create_index(
        op.f("ix_gate_evaluations_baseline_gate_evaluation_id"),
        "gate_evaluations",
        ["baseline_gate_evaluation_id"],
    )
    op.create_index(
        op.f("ix_gate_evaluations_decision_hash"),
        "gate_evaluations",
        ["decision_hash"],
    )
    op.create_index(
        op.f("ix_gate_evaluations_deployment_configuration_id"),
        "gate_evaluations",
        ["deployment_configuration_id"],
    )
    op.create_index(
        op.f("ix_gate_evaluations_evaluation_suite_id"),
        "gate_evaluations",
        ["evaluation_suite_id"],
    )
    op.create_index(op.f("ix_gate_evaluations_status"), "gate_evaluations", ["status"])
    op.create_index(op.f("ix_gate_evaluations_verdict"), "gate_evaluations", ["verdict"])

    op.create_table(
        "gate_rule_results",
        sa.Column("id", uuid_type, nullable=False),
        sa.Column("gate_evaluation_id", uuid_type, nullable=False),
        sa.Column("acceptance_policy_rule_id", uuid_type, nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=True),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sample_size >= 0", name="ck_gate_rule_results_sample_size"),
        sa.CheckConstraint(
            "severity IN ('blocker', 'warning')",
            name="ck_gate_rule_results_severity",
        ),
        sa.CheckConstraint(
            "status IN ('pass', 'fail', 'insufficient')",
            name="ck_gate_rule_results_status",
        ),
        sa.ForeignKeyConstraint(["acceptance_policy_rule_id"], ["acceptance_policy_rules.id"]),
        sa.ForeignKeyConstraint(
            ["gate_evaluation_id"],
            ["gate_evaluations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_gate_rule_results_acceptance_policy_rule_id"),
        "gate_rule_results",
        ["acceptance_policy_rule_id"],
    )
    op.create_index(
        op.f("ix_gate_rule_results_gate_evaluation_id"),
        "gate_rule_results",
        ["gate_evaluation_id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_gate_rule_results_gate_evaluation_id"), table_name="gate_rule_results")
    op.drop_index(
        op.f("ix_gate_rule_results_acceptance_policy_rule_id"),
        table_name="gate_rule_results",
    )
    op.drop_table("gate_rule_results")
    op.drop_index(op.f("ix_gate_evaluations_verdict"), table_name="gate_evaluations")
    op.drop_index(op.f("ix_gate_evaluations_status"), table_name="gate_evaluations")
    op.drop_index(
        op.f("ix_gate_evaluations_evaluation_suite_id"),
        table_name="gate_evaluations",
    )
    op.drop_index(
        op.f("ix_gate_evaluations_deployment_configuration_id"),
        table_name="gate_evaluations",
    )
    op.drop_index(op.f("ix_gate_evaluations_decision_hash"), table_name="gate_evaluations")
    op.drop_index(
        op.f("ix_gate_evaluations_baseline_gate_evaluation_id"),
        table_name="gate_evaluations",
    )
    op.drop_index(
        op.f("ix_gate_evaluations_acceptance_policy_id"),
        table_name="gate_evaluations",
    )
    op.drop_table("gate_evaluations")

    op.drop_constraint(
        op.f("fk_benchmark_results_evaluation_case_id_evaluation_cases"),
        "benchmark_results",
        type_="foreignkey",
    )
    op.drop_index(
        op.f("ix_benchmark_results_evaluation_case_id"),
        table_name="benchmark_results",
    )
    op.drop_column("benchmark_results", "evaluation_case_id")

    op.drop_constraint(
        op.f("fk_benchmark_runs_evaluation_suite_id_evaluation_suites"),
        "benchmark_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_benchmark_runs_deployment_configuration_id_deployment_configurations"),
        "benchmark_runs",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_benchmark_runs_evaluation_suite_id"), table_name="benchmark_runs")
    op.drop_index(
        op.f("ix_benchmark_runs_deployment_configuration_id"),
        table_name="benchmark_runs",
    )
    op.drop_column("benchmark_runs", "evaluation_suite_id")
    op.drop_column("benchmark_runs", "deployment_configuration_id")

    op.drop_index(op.f("ix_evaluation_cases_is_active"), table_name="evaluation_cases")
    op.drop_index(op.f("ix_evaluation_cases_external_case_id"), table_name="evaluation_cases")
    op.drop_index(op.f("ix_evaluation_cases_evaluation_suite_id"), table_name="evaluation_cases")
    op.drop_index(op.f("ix_evaluation_cases_criticality"), table_name="evaluation_cases")
    op.drop_index(op.f("ix_evaluation_cases_category"), table_name="evaluation_cases")
    op.drop_table("evaluation_cases")

    op.drop_index(
        op.f("ix_acceptance_policy_rules_metric_definition_id"),
        table_name="acceptance_policy_rules",
    )
    op.drop_index(
        op.f("ix_acceptance_policy_rules_enabled"),
        table_name="acceptance_policy_rules",
    )
    op.drop_index(
        op.f("ix_acceptance_policy_rules_acceptance_policy_id"),
        table_name="acceptance_policy_rules",
    )
    op.drop_table("acceptance_policy_rules")

    op.drop_index(
        op.f("ix_deployment_configurations_workload_profile_id"),
        table_name="deployment_configurations",
    )
    op.drop_index(
        op.f("ix_deployment_configurations_status"),
        table_name="deployment_configurations",
    )
    op.drop_index(op.f("ix_deployment_configurations_name"), table_name="deployment_configurations")
    op.drop_index(
        op.f("ix_deployment_configurations_model_artifact_id"),
        table_name="deployment_configurations",
    )
    op.drop_index(
        op.f("ix_deployment_configurations_hardware_profile_id"),
        table_name="deployment_configurations",
    )
    op.drop_index(
        op.f("ix_deployment_configurations_configuration_hash"),
        table_name="deployment_configurations",
    )
    op.drop_table("deployment_configurations")

    op.drop_index(
        op.f("ix_acceptance_policies_workload_profile_id"),
        table_name="acceptance_policies",
    )
    op.drop_index(op.f("ix_acceptance_policies_policy_hash"), table_name="acceptance_policies")
    op.drop_index(op.f("ix_acceptance_policies_name"), table_name="acceptance_policies")
    op.drop_index(op.f("ix_acceptance_policies_is_active"), table_name="acceptance_policies")
    op.drop_table("acceptance_policies")

    op.drop_index(op.f("ix_evaluation_suites_workload_profile_id"), table_name="evaluation_suites")
    op.drop_index(op.f("ix_evaluation_suites_suite_hash"), table_name="evaluation_suites")
    op.drop_index(op.f("ix_evaluation_suites_status"), table_name="evaluation_suites")
    op.drop_index(op.f("ix_evaluation_suites_name"), table_name="evaluation_suites")
    op.drop_table("evaluation_suites")

    op.drop_index(op.f("ix_metric_definitions_key"), table_name="metric_definitions")
    op.drop_index(op.f("ix_metric_definitions_is_active"), table_name="metric_definitions")
    op.drop_table("metric_definitions")

    op.drop_index(op.f("ix_workload_profiles_slug"), table_name="workload_profiles")
    op.drop_index(op.f("ix_workload_profiles_name"), table_name="workload_profiles")
    op.drop_index(op.f("ix_workload_profiles_is_active"), table_name="workload_profiles")
    op.drop_table("workload_profiles")
