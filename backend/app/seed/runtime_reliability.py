from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    DeploymentConfiguration,
    EvaluationCase,
    EvaluationSuite,
    MetricDefinition,
    WorkloadProfile,
)
from app.seed.demo import (
    DEPLOYMENT_NAMES,
    RELIABILITY_DEPLOYMENT_NAMES,
    RELIABILITY_POLICY_NAME,
    RELIABILITY_SUITE_NAME,
    WORKLOAD_SLUG,
    seed_demo_data,
)
from app.services.deployment_gate.evidence import (
    deployment_configuration_hash,
    stable_hash,
)

RELIABILITY_SUITE_VERSION = "v1-repeated-trials"
RELIABILITY_POLICY_VERSION = "v1-runtime-reliability"
RELIABILITY_DATA_SOURCE = "local_authored"


def _case_payloads() -> list[dict[str, Any]]:
    specs = [
        ("runtime-rel-001", "Short interactive request", 650, 1_024, "critical"),
        ("runtime-rel-002", "Structured medium request", 720, 4_096, "critical"),
        ("runtime-rel-003", "Sustained generation request", 840, 8_192, "standard"),
        ("runtime-rel-004", "Large prompt request", 960, 16_384, "standard"),
        ("runtime-rel-005", "High context pressure", 1_100, 28_672, "critical"),
        ("runtime-rel-006", "Near-limit context pressure", 1_250, 30_720, "critical"),
    ]
    return [
        {
            "external_case_id": external_case_id,
            "category": "runtime_reliability",
            "title": title,
            "input_payload_json": {
                "request": f"Execute reliability probe {external_case_id}",
                "reliability": {
                    "base_latency_ms": base_latency_ms,
                    "latency_jitter_ms": [-20, 0, 15, -10, 20],
                    "context_tokens": context_tokens,
                    "context_stress": context_tokens >= 28_000,
                    "completion_tokens": 128,
                    "gpu_vram_used_mb": 9_200,
                    "peak_memory_mb": 20_500,
                },
            },
            "expected_output_json": None,
            "reference_context_json": None,
            "expected_tool_schema_json": None,
            "tags_json": [
                "runtime",
                "reliability",
                "context-stress" if context_tokens >= 28_000 else "steady-state",
            ],
            "criticality": criticality,
            "weight": 1.5 if criticality == "critical" else 1.0,
            "is_active": True,
            "data_source": RELIABILITY_DATA_SOURCE,
        }
        for (
            external_case_id,
            title,
            base_latency_ms,
            context_tokens,
            criticality,
        ) in specs
    ]


def _ensure_metric_definitions(db: Session) -> dict[str, MetricDefinition]:
    specs = [
        (
            "reliability_success_rate",
            "Reliability success rate",
            "rate",
            "higher_is_better",
            None,
            "Successful repeated runtime trials.",
        ),
        (
            "reliability_timeout_rate",
            "Reliability timeout rate",
            "rate",
            "lower_is_better",
            None,
            "Trials that exceed or report the case timeout.",
        ),
        (
            "reliability_oom_rate",
            "Reliability OOM rate",
            "rate",
            "lower_is_better",
            None,
            "Trials that terminate because of out-of-memory pressure.",
        ),
        (
            "p99_end_to_end_latency_ms",
            "P99 end-to-end latency",
            "p99",
            "lower_is_better",
            "ms",
            "Nearest-rank P99 latency across reliability trials.",
        ),
        (
            "latency_variation_coefficient",
            "Latency variation coefficient",
            "mean",
            "lower_is_better",
            None,
            "Mean per-case latency coefficient of variation across repeated trials.",
        ),
        (
            "trial_coverage_rate",
            "Trial coverage rate",
            "rate",
            "higher_is_better",
            None,
            "Observed unique trials divided by the declared trial contract.",
        ),
        (
            "context_stress_success_rate",
            "Context stress success rate",
            "rate",
            "higher_is_better",
            None,
            "Successful trials at explicitly marked high context pressure.",
        ),
    ]
    definitions: dict[str, MetricDefinition] = {}
    for key, display_name, aggregation, direction, unit, description in specs:
        definition = db.scalar(select(MetricDefinition).where(MetricDefinition.key == key))
        if definition is None:
            definition = MetricDefinition(
                key=key,
                display_name=display_name,
                domain="reliability" if "latency" not in key else "performance",
                aggregation=aggregation,
                direction=direction,
                unit=unit,
                description=description,
                calculation_version="runtime-reliability-metrics-v1",
                is_active=True,
            )
            db.add(definition)
            db.flush()
        definitions[key] = definition
    return definitions


def _create_configuration(
    db: Session,
    workload: WorkloadProfile,
    *,
    name: str,
    latency_multiplier: float,
) -> DeploymentConfiguration:
    base_configuration = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.name == DEPLOYMENT_NAMES[0]
        )
    )
    if base_configuration is None:
        raise RuntimeError("The base demo deployment configuration is required.")
    payload = {
        "name": name,
        "workload_profile_id": workload.id,
        "hardware_profile_id": base_configuration.hardware_profile_id,
        "model_artifact_id": base_configuration.model_artifact_id,
        "runtime_name": f"{base_configuration.runtime_name} / {name[-1]}",
        "runtime_version": base_configuration.runtime_version,
        "runtime_config_json": {
            **dict(base_configuration.runtime_config_json or {}),
            "reliability_latency_multiplier": latency_multiplier,
        },
        "context_length": base_configuration.context_length,
        "generation_config_json": dict(base_configuration.generation_config_json or {}),
        "prompt_bundle_json": {
            "bundle": "model-atlas-runtime-reliability",
            "version": "reliability-v1",
        },
        "output_schema_version": base_configuration.output_schema_version,
        "tool_schema_version": None,
        "retrieval_config_json": None,
        "concurrency_target": 4,
        "status": "ready",
        "notes": "Locally authored Sprint 4D repeated-trial runtime fixture.",
    }
    configuration = DeploymentConfiguration(
        **payload,
        configuration_hash=deployment_configuration_hash(payload),
    )
    db.add(configuration)
    db.flush()
    return configuration


def seed_runtime_reliability_pack(db: Session) -> dict[str, Any]:
    workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    if workload is None:
        seed_demo_data(db)
        workload = db.scalar(
            select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG)
        )
    if workload is None:
        raise RuntimeError("The demo workload is required before reliability seeding.")

    existing_suite = db.scalar(
        select(EvaluationSuite).where(EvaluationSuite.name == RELIABILITY_SUITE_NAME)
    )
    existing_policy = db.scalar(
        select(AcceptancePolicy).where(AcceptancePolicy.name == RELIABILITY_POLICY_NAME)
    )
    existing_configurations = list(
        db.scalars(
            select(DeploymentConfiguration).where(
                DeploymentConfiguration.name.in_(RELIABILITY_DEPLOYMENT_NAMES)
            )
        ).all()
    )
    if (
        existing_suite is not None
        and existing_policy is not None
        and len(existing_configurations) == len(RELIABILITY_DEPLOYMENT_NAMES)
    ):
        case_count = len(
            list(
                db.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.evaluation_suite_id == existing_suite.id
                    )
                ).all()
            )
        )
        return {
            "evaluation_suite_id": str(existing_suite.id),
            "acceptance_policy_id": str(existing_policy.id),
            "deployment_configuration_ids": [
                str(configuration.id) for configuration in existing_configurations
            ],
            "case_count": case_count,
            "created": False,
        }
    if existing_suite or existing_policy or existing_configurations:
        raise RuntimeError(
            "Runtime reliability seed is partially present. Reset the demo seed, then retry."
        )

    metric_definitions = _ensure_metric_definitions(db)
    case_payloads = _case_payloads()
    suite_payload = {
        "workload_profile_id": workload.id,
        "name": RELIABILITY_SUITE_NAME,
        "version_label": RELIABILITY_SUITE_VERSION,
        "description": (
            "Repeated runtime trials covering stability, timeout, OOM, tail latency, and "
            "high-context pressure."
        ),
        "status": "active",
        "dataset_source": RELIABILITY_DATA_SOURCE,
        "is_synthetic": False,
    }
    suite = EvaluationSuite(
        **suite_payload,
        suite_hash=stable_hash({**suite_payload, "case_contracts": case_payloads}),
    )
    db.add(suite)
    db.flush()
    db.add_all(EvaluationCase(evaluation_suite_id=suite.id, **case) for case in case_payloads)

    policy_payload = {
        "workload_profile_id": workload.id,
        "name": RELIABILITY_POLICY_NAME,
        "version_label": RELIABILITY_POLICY_VERSION,
        "description": (
            "Blocks release on missing trials, runtime failures, timeout, OOM, unstable "
            "latency, or failed high-context probes."
        ),
        "allow_conditional": True,
        "is_active": True,
    }
    policy = AcceptancePolicy(
        **policy_payload,
        policy_hash=stable_hash(policy_payload),
    )
    db.add(policy)
    db.flush()
    rule_specs = [
        ("reliability_success_rate", "Every trial must succeed", "gte", 1.0, 30),
        ("reliability_timeout_rate", "Timeouts are blocked", "lte", 0.0, 30),
        ("reliability_oom_rate", "OOM failures are blocked", "lte", 0.0, 30),
        ("p99_end_to_end_latency_ms", "P99 latency must stay bounded", "lte", 2_000.0, 30),
        (
            "latency_variation_coefficient",
            "Repeated latency must remain stable",
            "lte",
            0.10,
            30,
        ),
        ("trial_coverage_rate", "Every declared trial must be present", "gte", 1.0, 30),
        (
            "context_stress_success_rate",
            "High-context trials must succeed",
            "gte",
            1.0,
            10,
        ),
    ]
    db.add_all(
        AcceptancePolicyRule(
            acceptance_policy_id=policy.id,
            metric_definition_id=metric_definitions[metric_key].id,
            rule_name=rule_name,
            operator=operator,
            threshold_value=threshold,
            severity="blocker",
            minimum_sample_size=minimum_sample_size,
            required=True,
            enabled=True,
            message_on_fail=f"{rule_name}. Inspect the runtime reliability trace.",
        )
        for metric_key, rule_name, operator, threshold, minimum_sample_size in rule_specs
    )
    configurations = [
        _create_configuration(
            db,
            workload,
            name=name,
            latency_multiplier=1.0 if index == 0 else 1.25,
        )
        for index, name in enumerate(RELIABILITY_DEPLOYMENT_NAMES)
    ]
    db.commit()
    return {
        "deployment_configuration_ids": [
            str(configuration.id) for configuration in configurations
        ],
        "deployment_configuration_names": [
            configuration.name for configuration in configurations
        ],
        "evaluation_suite_id": str(suite.id),
        "evaluation_suite_name": suite.name,
        "evaluation_suite_version": suite.version_label,
        "acceptance_policy_id": str(policy.id),
        "acceptance_policy_name": policy.name,
        "case_count": len(case_payloads),
        "trials_per_case": 5,
        "expected_trial_count": len(case_payloads) * 5,
        "context_stress_case_count": sum(
            1
            for case in case_payloads
            if case["input_payload_json"]["reliability"]["context_stress"]
        ),
        "created": True,
    }


def main() -> None:
    with SessionLocal() as db:
        summary = seed_runtime_reliability_pack(db)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
