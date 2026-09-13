from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcceptancePolicy,
    AcceptancePolicyRule,
    EvaluationCase,
    EvaluationSuite,
    MetricDefinition,
    WorkloadProfile,
)
from app.reference_workload.cases import ReferenceCasePack, reference_case_hash
from app.reference_workload.corpus import ReferenceCorpusBundle
from app.reference_workload.manifest import canonical_json, stable_hash
from app.services.result_scoring import SCORER_VERSION
from app.services.tool_execution import TOOL_REGISTRY_VERSION

REFERENCE_SUITE_NAME = "Model Atlas Korean Operator Assistant Reference Suite"
REFERENCE_POLICY_NAME = "Model Atlas Operator Assistant Local Evaluation Policy v1"
REFERENCE_DATA_SOURCE = "local_authored"


class ReferenceWorkloadApprovalRequired(RuntimeError):
    def __init__(self, case_pack: ReferenceCasePack) -> None:
        self.case_pack = case_pack
        super().__init__(
            "reference workload bootstrap requires the approved case taxonomy; "
            f"observed {case_pack.approved_case_count} approved cases and "
            f"{case_pack.approved_critical_case_count} approved critical cases"
        )


class ReferenceBootstrapConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class MetricSpec:
    key: str
    display_name: str
    domain: str
    aggregation: str
    direction: str
    description: str


@dataclass(frozen=True)
class RuleSpec:
    metric_key: str
    name: str
    operator: str
    threshold: float
    severity: str
    minimum_sample_size: int


METRIC_SPECS = (
    MetricSpec(
        "critical_case_failure_rate",
        "Critical case failure rate",
        "reliability",
        "rate",
        "lower_is_better",
        "Active critical cases that failed their executable evidence contract.",
    ),
    MetricSpec(
        "json_validity_rate",
        "JSON validity rate",
        "quality",
        "rate",
        "higher_is_better",
        "Structured-output cases that returned valid JSON.",
    ),
    MetricSpec(
        "tool_argument_validity_rate",
        "Tool argument validity rate",
        "quality",
        "rate",
        "higher_is_better",
        "Executable Tool steps with schema-valid arguments.",
    ),
    MetricSpec(
        "tool_execution_success_rate",
        "Tool execution success rate",
        "reliability",
        "rate",
        "higher_is_better",
        "Bounded Tool steps that completed successfully.",
    ),
    MetricSpec(
        "rag_citation_precision",
        "RAG citation precision",
        "quality",
        "rate",
        "higher_is_better",
        "Citations that identify retrieved relevant chunks.",
    ),
    MetricSpec(
        "rag_groundedness_score",
        "RAG groundedness score",
        "quality",
        "mean",
        "higher_is_better",
        "Atomic answer claims supported by cited reference chunks.",
    ),
    MetricSpec(
        "rag_unsupported_claim_rate",
        "RAG unsupported claim rate",
        "reliability",
        "rate",
        "lower_is_better",
        "Answer claims without sufficient support in cited chunks.",
    ),
    MetricSpec(
        "agent_task_success_rate",
        "Agent task success rate",
        "quality",
        "rate",
        "higher_is_better",
        "Bounded Agent cases that completed without unrecovered policy failures.",
    ),
    MetricSpec(
        "oom_rate",
        "OOM rate",
        "reliability",
        "rate",
        "lower_is_better",
        "Observed inference trials that reported out-of-memory failure.",
    ),
    MetricSpec(
        "p95_end_to_end_latency_ms",
        "P95 end-to-end latency",
        "performance",
        "p95",
        "lower_is_better",
        "Observed end-to-end case latency at the 95th percentile.",
    ),
    MetricSpec(
        "real_case_count",
        "Actual local-runtime case count",
        "evidence",
        "count",
        "higher_is_better",
        "Distinct non-synthetic active cases with stored results.",
    ),
)

RULE_SPECS = (
    RuleSpec("critical_case_failure_rate", "No critical failures", "eq", 0.0, "blocker", 20),
    RuleSpec("json_validity_rate", "Valid structured output", "gte", 0.98, "blocker", 1),
    RuleSpec("tool_argument_validity_rate", "Valid Tool arguments", "gte", 0.95, "blocker", 10),
    RuleSpec(
        "tool_execution_success_rate", "Successful Tool execution", "gte", 0.95, "blocker", 10
    ),
    RuleSpec("rag_citation_precision", "Precise citations", "gte", 0.95, "blocker", 20),
    RuleSpec("rag_groundedness_score", "Grounded answers", "gte", 0.85, "blocker", 20),
    RuleSpec("rag_unsupported_claim_rate", "Bound unsupported claims", "lte", 0.05, "blocker", 20),
    RuleSpec("agent_task_success_rate", "Complete bounded Agent tasks", "gte", 0.90, "blocker", 6),
    RuleSpec("oom_rate", "No observed OOM", "eq", 0.0, "blocker", 60),
    RuleSpec("p95_end_to_end_latency_ms", "Portfolio latency target", "lte", 8000.0, "warning", 60),
    RuleSpec("real_case_count", "Actual local-runtime coverage", "gte", 60.0, "blocker", 60),
)


def _workload_payload() -> dict[str, Any]:
    return {
        "name": "Model Atlas Korean Operator Assistant",
        "slug": "model-atlas-operator-assistant-ko",
        "description": (
            "Korean operator workload for grounded Model Atlas guidance, bounded Tools, "
            "refusal, recovery, and Agent evaluation."
        ),
        "domain": "ai_platform_operations",
        "primary_language": "ko",
        "local_only_required": True,
        "data_classification": "project_internal_public_submission",
        "expected_output_modes_json": [
            "grounded_answer",
            "structured_json",
            "tool_call",
            "multi_step_agent_trace",
        ],
        "risk_notes": (
            "Local reference evidence cannot be interpreted as production authorization."
        ),
        "is_active": True,
    }


def _ensure_workload(db: Session) -> tuple[WorkloadProfile, bool]:
    payload = _workload_payload()
    workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == payload["slug"]))
    if workload is None:
        workload = WorkloadProfile(**payload)
        db.add(workload)
        db.flush()
        return workload, True
    immutable_fields = ("name", "domain", "primary_language", "data_classification")
    mismatches = [field for field in immutable_fields if getattr(workload, field) != payload[field]]
    if mismatches:
        raise ReferenceBootstrapConflict(
            f"reference workload identity conflicts on: {', '.join(mismatches)}"
        )
    return workload, False


def _suite_hash(
    corpus_bundle: ReferenceCorpusBundle,
    case_pack: ReferenceCasePack,
) -> str:
    return stable_hash(
        {
            "workload_version": corpus_bundle.manifest.contract.workload_version,
            "corpus_id": corpus_bundle.corpus.corpus_id,
            "corpus_version": corpus_bundle.corpus.corpus_version,
            "corpus_hash": corpus_bundle.corpus.corpus_hash,
            "case_contract_version": (corpus_bundle.manifest.contract.case_contract_version),
            "tool_registry_version": TOOL_REGISTRY_VERSION,
            "scorer_versions": [SCORER_VERSION],
            "active_approved_cases": [
                case.model_dump(mode="json") for case in case_pack.approved_cases
            ],
        }
    )


def _case_payload(case: Any, case_hash: str) -> dict[str, Any]:
    source_reference = dict(case.reference_context or {})
    source_reference["source_review"] = case.review.model_dump(mode="json")
    source_reference["reference_case_hash"] = case_hash
    return {
        "external_case_id": case.external_case_id,
        "category": case.category,
        "title": case.title,
        "input_payload_json": case.input_payload,
        "expected_output_json": case.expected_output,
        "reference_context_json": source_reference,
        "expected_tool_schema_json": case.expected_tool_schema,
        "tags_json": [tag for tag in case.tags if tag != "draft"] + ["approved_source"],
        "criticality": case.criticality,
        "weight": case.weight,
        "is_active": True,
        "data_source": REFERENCE_DATA_SOURCE,
    }


def _normalized_stored_case(case: EvaluationCase) -> dict[str, Any]:
    return {
        "external_case_id": case.external_case_id,
        "category": case.category,
        "title": case.title,
        "input_payload_json": case.input_payload_json,
        "expected_output_json": case.expected_output_json,
        "reference_context_json": case.reference_context_json,
        "expected_tool_schema_json": case.expected_tool_schema_json,
        "tags_json": case.tags_json,
        "criticality": case.criticality,
        "weight": case.weight,
        "is_active": case.is_active,
        "data_source": case.data_source,
    }


def _ensure_suite(
    db: Session,
    workload: WorkloadProfile,
    corpus_bundle: ReferenceCorpusBundle,
    case_pack: ReferenceCasePack,
) -> tuple[EvaluationSuite, bool]:
    version = corpus_bundle.manifest.contract.workload_version
    expected_hash = _suite_hash(corpus_bundle, case_pack)
    suite = db.scalar(
        select(EvaluationSuite)
        .where(EvaluationSuite.workload_profile_id == workload.id)
        .where(EvaluationSuite.version_label == version)
    )
    created = False
    if suite is None:
        suite = EvaluationSuite(
            workload_profile_id=workload.id,
            name=REFERENCE_SUITE_NAME,
            version_label=version,
            description=(
                "Human-approved Korean reference cases over the locked Model Atlas corpus."
            ),
            suite_hash=expected_hash,
            status="active",
            dataset_source=REFERENCE_DATA_SOURCE,
            is_synthetic=False,
        )
        db.add(suite)
        db.flush()
        created = True
    elif suite.suite_hash != expected_hash:
        raise ReferenceBootstrapConflict(
            "reference suite inputs changed without a workload version change; "
            "create a new workload version to preserve evidence lineage"
        )

    expected_payloads = {
        case.external_case_id: _case_payload(case, reference_case_hash(case))
        for case in case_pack.approved_cases
    }
    stored_cases = list(
        db.scalars(
            select(EvaluationCase).where(EvaluationCase.evaluation_suite_id == suite.id)
        ).all()
    )
    if not stored_cases:
        db.add_all(
            EvaluationCase(evaluation_suite_id=suite.id, **payload)
            for payload in expected_payloads.values()
        )
        db.flush()
    else:
        stored_by_id = {case.external_case_id: case for case in stored_cases}
        if set(stored_by_id) != set(expected_payloads):
            raise ReferenceBootstrapConflict(
                "stored reference cases differ from the approved case manifest"
            )
        for external_case_id, expected in expected_payloads.items():
            observed = _normalized_stored_case(stored_by_id[external_case_id])
            if canonical_json(observed) != canonical_json(expected):
                raise ReferenceBootstrapConflict(
                    f"stored reference case changed: {external_case_id}"
                )
    return suite, created


def _ensure_metrics(db: Session) -> dict[str, MetricDefinition]:
    definitions: dict[str, MetricDefinition] = {}
    for spec in METRIC_SPECS:
        definition = db.scalar(select(MetricDefinition).where(MetricDefinition.key == spec.key))
        if definition is None:
            definition = MetricDefinition(
                key=spec.key,
                display_name=spec.display_name,
                domain=spec.domain,
                aggregation=spec.aggregation,
                direction=spec.direction,
                unit="ms" if spec.key.endswith("_ms") else None,
                description=spec.description,
                calculation_version="reference-workload-policy-metrics-v1",
                is_active=True,
            )
            db.add(definition)
            db.flush()
        definitions[spec.key] = definition
    return definitions


def _policy_hash(workload_id: Any) -> str:
    return stable_hash(
        {
            "workload_profile_id": str(workload_id),
            "name": REFERENCE_POLICY_NAME,
            "version_label": "1.0.0",
            "rules": [spec.__dict__ for spec in RULE_SPECS],
        }
    )


def _ensure_policy(
    db: Session,
    workload: WorkloadProfile,
    metrics: dict[str, MetricDefinition],
) -> tuple[AcceptancePolicy, bool]:
    expected_hash = _policy_hash(workload.id)
    policy = db.scalar(
        select(AcceptancePolicy)
        .where(AcceptancePolicy.workload_profile_id == workload.id)
        .where(AcceptancePolicy.version_label == "1.0.0")
    )
    created = False
    if policy is None:
        policy = AcceptancePolicy(
            workload_profile_id=workload.id,
            name=REFERENCE_POLICY_NAME,
            version_label="1.0.0",
            description=(
                "Configurable portfolio targets for the Korean operator-assistant workload; "
                "not a universal production standard."
            ),
            policy_hash=expected_hash,
            allow_conditional=True,
            is_active=True,
        )
        db.add(policy)
        db.flush()
        created = True
    elif policy.policy_hash != expected_hash:
        raise ReferenceBootstrapConflict("reference policy changed without a version change")

    stored_rules = list(
        db.scalars(
            select(AcceptancePolicyRule).where(
                AcceptancePolicyRule.acceptance_policy_id == policy.id
            )
        ).all()
    )
    if not stored_rules:
        db.add_all(
            AcceptancePolicyRule(
                acceptance_policy_id=policy.id,
                metric_definition_id=metrics[spec.metric_key].id,
                rule_name=spec.name,
                operator=spec.operator,
                threshold_value=spec.threshold,
                severity=spec.severity,
                minimum_sample_size=spec.minimum_sample_size,
                required=True,
                enabled=True,
                message_on_fail=(
                    f"{spec.name} failed for the reference workload. Inspect stored evidence."
                ),
            )
            for spec in RULE_SPECS
        )
        db.flush()
    elif len(stored_rules) != len(RULE_SPECS):
        raise ReferenceBootstrapConflict("reference policy rules are partially present")
    return policy, created


def bootstrap_reference_workload(
    db: Session,
    *,
    corpus_bundle: ReferenceCorpusBundle,
    case_pack: ReferenceCasePack,
) -> dict[str, Any]:
    if not case_pack.portfolio_ready:
        raise ReferenceWorkloadApprovalRequired(case_pack)

    workload, workload_created = _ensure_workload(db)
    suite, suite_created = _ensure_suite(db, workload, corpus_bundle, case_pack)
    metrics = _ensure_metrics(db)
    policy, policy_created = _ensure_policy(db, workload, metrics)
    db.commit()
    return {
        "schema_version": "model-atlas-reference-bootstrap-summary-v1",
        "workload_profile_id": str(workload.id),
        "evaluation_suite_id": str(suite.id),
        "acceptance_policy_id": str(policy.id),
        "workload_version": corpus_bundle.manifest.contract.workload_version,
        "corpus_hash": corpus_bundle.corpus.corpus_hash,
        "suite_hash": suite.suite_hash,
        "policy_hash": policy.policy_hash,
        "approved_case_count": case_pack.approved_case_count,
        "approved_critical_case_count": case_pack.approved_critical_case_count,
        "metric_count": len(metrics),
        "policy_rule_count": len(RULE_SPECS),
        "created": {
            "workload": workload_created,
            "suite": suite_created,
            "policy": policy_created,
        },
        "portfolio_ready": True,
        "production_readiness": "not_production_ready",
    }
