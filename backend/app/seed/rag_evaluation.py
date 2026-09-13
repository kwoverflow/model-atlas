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
    RAG_DEPLOYMENT_NAME,
    RAG_POLICY_NAME,
    RAG_SUITE_NAME,
    WORKLOAD_SLUG,
    seed_demo_data,
)
from app.services.deployment_gate.evidence import (
    deployment_configuration_hash,
    stable_hash,
)
from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS,
    DEFAULT_RETRIEVER_DESCRIPTOR,
)

RAG_SUITE_VERSION = "v1-local-rag"
RAG_POLICY_VERSION = "v1-local-rag"
RAG_DATA_SOURCE = "local_authored"


def _output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["answer", "citations", "claims"],
        "properties": {
            "answer": {"type": "string"},
            "citations": {"type": "array", "items": {"type": "string"}},
            "claims": {"type": "array", "items": {"type": "string"}},
        },
    }


def _case_payloads() -> list[dict[str, Any]]:
    specs = [
        (
            "rag-eval-001",
            "Release gate requirement",
            "approved deployment gate verified evidence baseline promotion",
            ["ops-release-001"],
            "critical",
        ),
        (
            "rag-eval-002",
            "Rollback ownership and recovery",
            "rollback owner platform team target recovery time 30 minutes",
            ["ops-rollback-001"],
            "critical",
        ),
        (
            "rag-eval-003",
            "Severity one incident response",
            "severity one incidents immediate paging incident commander",
            ["ops-incident-001"],
            "critical",
        ),
        (
            "rag-eval-004",
            "Evaluation record retention",
            "evaluation result records retained 180 days",
            ["ops-retention-001"],
            "critical",
        ),
        (
            "rag-eval-005",
            "Restricted data boundary",
            "restricted data local infrastructure external services",
            ["ops-privacy-001"],
            "standard",
        ),
        (
            "rag-eval-006",
            "Interactive latency target",
            "interactive workloads p95 latency below 5000 milliseconds",
            ["ops-latency-001"],
            "standard",
        ),
        (
            "rag-eval-007",
            "Production release approval roles",
            "production release approval roles Release Manager ML Ops Lead",
            ["ops-access-001"],
            "standard",
        ),
        (
            "rag-eval-008",
            "Critical case review requirement",
            "critical evaluation cases explicit review production readiness",
            ["ops-review-001"],
            "standard",
        ),
        (
            "rag-eval-009",
            "Prompt baseline comparison",
            "prompt changes compared active baseline",
            ["ops-prompt-001"],
            "standard",
        ),
        (
            "rag-eval-010",
            "Release and review multi-hop answer",
            (
                "approved deployment gate verified evidence critical evaluation explicit review "
                "production readiness"
            ),
            ["ops-release-001", "ops-review-001"],
            "critical",
        ),
    ]
    return [
        {
            "external_case_id": external_case_id,
            "category": "rag_grounded_answer",
            "title": title,
            "input_payload_json": {
                "query": query,
                "instruction": (
                    "Answer only from retrieved chunks and return answer, citations, and claims."
                ),
            },
            "expected_output_json": _output_schema(),
            "reference_context_json": {
                "rag": {
                    "corpus_id": DEFAULT_RAG_CORPUS.corpus_id,
                    "corpus_version": DEFAULT_RAG_CORPUS.corpus_version,
                    "query": query,
                    "relevant_chunk_ids": relevant_chunk_ids,
                }
            },
            "expected_tool_schema_json": None,
            "tags_json": ["rag", "retrieval", "citation", criticality],
            "criticality": criticality,
            "weight": 1.5 if criticality == "critical" else 1.0,
            "is_active": True,
            "data_source": RAG_DATA_SOURCE,
        }
        for external_case_id, title, query, relevant_chunk_ids, criticality in specs
    ]


def _ensure_metric_definitions(db: Session) -> dict[str, MetricDefinition]:
    specs = [
        (
            "rag_retrieval_recall",
            "RAG retrieval recall",
            "reliability",
            "higher_is_better",
            "Relevant reference chunks returned by the configured retriever.",
        ),
        (
            "rag_citation_precision",
            "RAG citation precision",
            "quality",
            "higher_is_better",
            "Citations that point to retrieved, relevant chunks.",
        ),
        (
            "rag_citation_recall",
            "RAG citation recall",
            "quality",
            "higher_is_better",
            "Relevant reference chunks covered by answer citations.",
        ),
        (
            "rag_groundedness_score",
            "RAG groundedness score",
            "quality",
            "higher_is_better",
            "Claim token support from the chunks cited by the answer.",
        ),
        (
            "rag_unsupported_claim_rate",
            "RAG unsupported claim rate",
            "reliability",
            "lower_is_better",
            "Answer claims without sufficient support in cited chunks.",
        ),
    ]
    definitions: dict[str, MetricDefinition] = {}
    for key, display_name, domain, direction, description in specs:
        definition = db.scalar(select(MetricDefinition).where(MetricDefinition.key == key))
        if definition is None:
            definition = MetricDefinition(
                key=key,
                display_name=display_name,
                domain=domain,
                aggregation="rate" if key != "rag_groundedness_score" else "mean",
                direction=direction,
                unit=None,
                description=description,
                calculation_version="rag-evaluation-metrics-v1",
                is_active=True,
            )
            db.add(definition)
            db.flush()
        definitions[key] = definition
    return definitions


def _create_deployment_configuration(
    db: Session,
    workload: WorkloadProfile,
) -> DeploymentConfiguration:
    base_configuration = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.name == DEPLOYMENT_NAMES[0]
        )
    )
    if base_configuration is None:
        raise RuntimeError("The base demo deployment configuration is required.")
    retrieval_config = {
        "corpus_id": DEFAULT_RAG_CORPUS.corpus_id,
        "corpus_version": DEFAULT_RAG_CORPUS.corpus_version,
        "corpus_hash": DEFAULT_RAG_CORPUS.corpus_hash,
        "retriever_id": DEFAULT_RETRIEVER_DESCRIPTOR.retriever_id,
        "retriever_version": DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version,
        "top_k": 3,
        "min_score": 0.05,
    }
    payload = {
        "name": RAG_DEPLOYMENT_NAME,
        "workload_profile_id": workload.id,
        "hardware_profile_id": base_configuration.hardware_profile_id,
        "model_artifact_id": base_configuration.model_artifact_id,
        "runtime_name": base_configuration.runtime_name,
        "runtime_version": base_configuration.runtime_version,
        "runtime_config_json": dict(base_configuration.runtime_config_json or {}),
        "context_length": base_configuration.context_length,
        "generation_config_json": dict(base_configuration.generation_config_json or {}),
        "prompt_bundle_json": {
            "bundle": "model-atlas-rag-assistant",
            "version": "rag-v1",
        },
        "output_schema_version": "rag-answer-v1",
        "tool_schema_version": None,
        "retrieval_config_json": retrieval_config,
        "concurrency_target": 1,
        "status": "ready",
        "notes": "Locally authored Sprint 4C RAG evaluation configuration.",
    }
    configuration = DeploymentConfiguration(
        **payload,
        configuration_hash=deployment_configuration_hash(payload),
    )
    db.add(configuration)
    db.flush()
    return configuration


def seed_rag_evaluation_pack(db: Session) -> dict[str, Any]:
    workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    if workload is None:
        seed_demo_data(db)
        workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    if workload is None:
        raise RuntimeError("The demo workload is required before RAG pack seeding.")

    existing_suite = db.scalar(
        select(EvaluationSuite).where(EvaluationSuite.name == RAG_SUITE_NAME)
    )
    existing_policy = db.scalar(
        select(AcceptancePolicy).where(AcceptancePolicy.name == RAG_POLICY_NAME)
    )
    existing_configuration = db.scalar(
        select(DeploymentConfiguration).where(
            DeploymentConfiguration.name == RAG_DEPLOYMENT_NAME
        )
    )
    existing = [existing_suite, existing_policy, existing_configuration]
    if all(item is not None for item in existing):
        case_count = len(
            list(
                db.scalars(
                    select(EvaluationCase).where(
                        EvaluationCase.evaluation_suite_id == existing_suite.id
                    )
                )
            )
        )
        return {
            "deployment_configuration_id": str(existing_configuration.id),
            "evaluation_suite_id": str(existing_suite.id),
            "acceptance_policy_id": str(existing_policy.id),
            "case_count": case_count,
            "created": False,
        }
    if any(item is not None for item in existing):
        raise RuntimeError("RAG seed is partially present. Run the base demo seed, then retry.")

    metric_definitions = _ensure_metric_definitions(db)
    configuration = _create_deployment_configuration(db, workload)
    case_payloads = _case_payloads()
    suite_payload = {
        "workload_profile_id": workload.id,
        "name": RAG_SUITE_NAME,
        "version_label": RAG_SUITE_VERSION,
        "description": (
            "Locally authored retrieval, citation, groundedness, and unsupported-claim cases."
        ),
        "status": "active",
        "dataset_source": RAG_DATA_SOURCE,
        "is_synthetic": False,
    }
    suite = EvaluationSuite(
        **suite_payload,
        suite_hash=stable_hash(
            {
                **suite_payload,
                "corpus_hash": DEFAULT_RAG_CORPUS.corpus_hash,
                "case_contracts": [
                    {
                        "external_case_id": case["external_case_id"],
                        "rag": case["reference_context_json"]["rag"],
                    }
                    for case in case_payloads
                ],
            }
        ),
    )
    db.add(suite)
    db.flush()
    db.add_all(EvaluationCase(evaluation_suite_id=suite.id, **case) for case in case_payloads)

    policy_payload = {
        "workload_profile_id": workload.id,
        "name": RAG_POLICY_NAME,
        "version_label": RAG_POLICY_VERSION,
        "description": (
            "Blocks release on retrieval misses, citation errors, weak groundedness, or "
            "unsupported claims."
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
        ("rag_retrieval_recall", "Relevant chunks must be retrieved", "gte", 1.0),
        ("rag_citation_precision", "Citations must be precise", "gte", 1.0),
        ("rag_citation_recall", "Citations must cover relevant chunks", "gte", 1.0),
        ("rag_groundedness_score", "Claims must be grounded", "gte", 0.85),
        ("rag_unsupported_claim_rate", "Unsupported claims are blocked", "lte", 0.0),
    ]
    db.add_all(
        AcceptancePolicyRule(
            acceptance_policy_id=policy.id,
            metric_definition_id=metric_definitions[metric_key].id,
            rule_name=rule_name,
            operator=operator,
            threshold_value=threshold,
            severity="blocker",
            minimum_sample_size=10,
            required=True,
            enabled=True,
            message_on_fail=f"{rule_name}. Inspect the RAG evaluation trace.",
        )
        for metric_key, rule_name, operator, threshold in rule_specs
    )
    db.commit()
    return {
        "deployment_configuration_id": str(configuration.id),
        "deployment_configuration_name": configuration.name,
        "evaluation_suite_id": str(suite.id),
        "evaluation_suite_name": suite.name,
        "evaluation_suite_version": suite.version_label,
        "acceptance_policy_id": str(policy.id),
        "acceptance_policy_name": policy.name,
        "corpus_id": DEFAULT_RAG_CORPUS.corpus_id,
        "corpus_version": DEFAULT_RAG_CORPUS.corpus_version,
        "corpus_hash": DEFAULT_RAG_CORPUS.corpus_hash,
        "case_count": len(case_payloads),
        "critical_case_count": sum(
            1 for case in case_payloads if case["criticality"] == "critical"
        ),
        "created": True,
    }


def main() -> None:
    with SessionLocal() as db:
        summary = seed_rag_evaluation_pack(db)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
