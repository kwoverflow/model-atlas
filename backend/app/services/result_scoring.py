from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Protocol

from app.models import EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult

PASS_THRESHOLD = 0.8
SCORER_VERSION = "heuristic-scorer-v5"


@dataclass(frozen=True)
class ScorerDescriptor:
    scorer_id: str
    scorer_version: str
    method: str
    capabilities: frozenset[str]
    input_schema_version: str
    output_schema_version: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["capabilities"] = sorted(self.capabilities)
        return payload


@dataclass(frozen=True)
class ScoringOutcome:
    quality: float
    groundedness: float
    faithfulness: float
    method: str
    scorer_id: str
    details: dict[str, Any]


class ResultScorer(Protocol):
    scorer_id: str
    method: str
    descriptor: ScorerDescriptor

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool: ...

    def score(
        self,
        evaluation_case: EvaluationCase,
        result: AdapterCaseResult,
    ) -> ScoringOutcome: ...


@dataclass(frozen=True)
class ResultScorerRegistry:
    scorers: Sequence[ResultScorer]
    fallback_scorer: ResultScorer
    registry_id: str = "default_heuristic_registry"
    registry_version: str = SCORER_VERSION

    def select(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ResultScorer:
        for scorer in self.scorers:
            if scorer.supports(evaluation_case, result):
                return scorer
        return self.fallback_scorer

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        scorer = self.select(evaluation_case, result)
        return scorer.score(evaluation_case, result)

    def descriptor_for(self, scorer_id: str) -> ScorerDescriptor:
        for scorer in [*self.scorers, self.fallback_scorer]:
            if scorer.scorer_id == scorer_id:
                descriptor = getattr(scorer, "descriptor", None)
                if isinstance(descriptor, ScorerDescriptor):
                    return descriptor
                return ScorerDescriptor(
                    scorer_id=scorer.scorer_id,
                    scorer_version=f"{scorer.scorer_id}-legacy-v1",
                    method=scorer.method,
                    capabilities=frozenset(),
                    input_schema_version="evaluation-case-v1",
                    output_schema_version="score-outcome-v1",
                )
        return self.fallback_scorer.descriptor


class JsonSchemaScorer:
    scorer_id = "json_schema"
    method = "json_schema_coverage"
    descriptor = ScorerDescriptor(
        scorer_id=scorer_id,
        scorer_version="json-schema-scorer-v1",
        method=method,
        capabilities=frozenset({"structured_output", "json_schema"}),
        input_schema_version="evaluation-case-v1",
        output_schema_version="score-outcome-v1",
    )

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool:
        return _is_json_case(evaluation_case)

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        parsed = _parse_json(result.normalized_output)
        if not result.json_valid or not isinstance(parsed, dict):
            return _scores(
                quality=0.0,
                groundedness=0.0,
                faithfulness=0.0,
                method=self.method,
                scorer_id=self.scorer_id,
                details={"reason": "output was not a valid JSON object"},
            )

        required = _required_keys(evaluation_case.expected_output_json)
        required_coverage = _coverage(required, parsed.keys())
        type_score = _property_type_score(evaluation_case.expected_output_json, parsed)
        quality = _clamp(0.65 + 0.25 * required_coverage + 0.10 * type_score)
        return _scores(
            quality=quality,
            groundedness=quality,
            faithfulness=_clamp(0.7 + 0.3 * required_coverage),
            method=self.method,
            scorer_id=self.scorer_id,
            details={
                "required_key_coverage": required_coverage,
                "property_type_score": type_score,
                "required_keys": required,
            },
        )


class ToolCallScorer:
    scorer_id = "tool_call"
    method = "tool_schema_match"
    descriptor = ScorerDescriptor(
        scorer_id=scorer_id,
        scorer_version="tool-call-scorer-v2",
        method=method,
        capabilities=frozenset(
            {
                "tool_selection",
                "argument_schema",
                "actual_execution",
                "retry_recovery",
                "multi_step_sequence",
            }
        ),
        input_schema_version="evaluation-case-v1",
        output_schema_version="score-outcome-v1",
    )

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool:
        return _is_tool_case(evaluation_case)

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        execution_trace = result.metadata.get("tool_execution")
        if isinstance(execution_trace, dict):
            selection = _trace_rate(execution_trace, "selection_accuracy")
            arguments = _trace_rate(execution_trace, "argument_validity_rate")
            execution = _trace_rate(execution_trace, "execution_success_rate")
            sequence = 1.0 if execution_trace.get("sequence_match") else 0.0
            quality = _clamp(
                0.30 * selection + 0.25 * arguments + 0.30 * execution + 0.15 * sequence
            )
            return _scores(
                quality=quality,
                groundedness=quality,
                faithfulness=_clamp(0.5 * selection + 0.5 * execution),
                method="executable_tool_trace",
                scorer_id=self.scorer_id,
                details={
                    "trace_schema_version": execution_trace.get("schema_version"),
                    "registry_version": execution_trace.get("registry_version"),
                    "selection_accuracy": selection,
                    "argument_validity_rate": arguments,
                    "execution_success_rate": execution,
                    "sequence_match": bool(execution_trace.get("sequence_match")),
                    "retry_recovery_rate": execution_trace.get("retry_recovery_rate"),
                    "trace_status": execution_trace.get("status"),
                },
            )
        parsed = _parse_json(result.normalized_output)
        if not result.tool_call_valid or not isinstance(parsed, dict):
            return _scores(
                quality=0.0,
                groundedness=0.0,
                faithfulness=0.0,
                method=self.method,
                scorer_id=self.scorer_id,
                details={"reason": "output was not a valid tool-call JSON object"},
            )

        expected_schema = evaluation_case.expected_tool_schema_json or {}
        expected_tool = expected_schema.get("tool_name")
        actual_tool = parsed.get("tool_name") or parsed.get("name")
        tool_match = 1.0 if expected_tool is None or actual_tool == expected_tool else 0.0
        required_arguments = _required_tool_arguments(expected_schema)
        arguments = parsed.get("arguments")
        argument_keys = arguments.keys() if isinstance(arguments, dict) else []
        argument_coverage = _coverage(required_arguments, argument_keys)
        quality = _clamp(0.5 + 0.35 * tool_match + 0.15 * argument_coverage)
        return _scores(
            quality=quality,
            groundedness=quality,
            faithfulness=_clamp(0.65 + 0.35 * min(tool_match, argument_coverage)),
            method=self.method,
            scorer_id=self.scorer_id,
            details={
                "expected_tool": expected_tool,
                "actual_tool": actual_tool,
                "tool_match": tool_match,
                "required_argument_coverage": argument_coverage,
                "required_arguments": required_arguments,
            },
        )


class AgentExecutionScorer:
    scorer_id = "agent_execution"
    method = "bounded_agent_trace"
    descriptor = ScorerDescriptor(
        scorer_id=scorer_id,
        scorer_version="agent-execution-scorer-v2",
        method=method,
        capabilities=frozenset(
            {
                "bounded_plan",
                "step_execution",
                "action_sequence",
                "policy_violation",
                "operational_memory_provenance",
                "retry_recovery",
                "observation_feedback",
                "bounded_replanning",
                "human_approval_provenance",
            }
        ),
        input_schema_version="agent-execution-trace-v2",
        output_schema_version="score-outcome-v1",
    )

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool:
        return (
            isinstance(result.metadata.get("agent_execution"), dict)
            or "agent" in (evaluation_case.category or "").lower()
        )

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        trace = result.metadata.get("agent_execution")
        if not isinstance(trace, dict):
            return _scores(
                quality=0.0,
                groundedness=0.0,
                faithfulness=0.0,
                method=self.method,
                scorer_id=self.scorer_id,
                details={"reason": "agent execution trace is missing"},
            )
        task_success = 1.0 if trace.get("successful") else 0.0
        plan_validity = 1.0 if trace.get("plan_valid") else 0.0
        step_success = _trace_rate(trace, "step_success_rate")
        sequence = 1.0 if trace.get("sequence_match") else 0.0
        final_response = 1.0 if trace.get("final_response_present") else 0.0
        no_policy_violation = 1.0 if int(trace.get("policy_violation_count") or 0) == 0 else 0.0
        memory_actions = int(trace.get("memory_action_count") or 0)
        memory_provenance = (
            int(trace.get("memory_provenance_count") or 0) / memory_actions
            if memory_actions
            else 1.0
        )
        replan_count = int(trace.get("replan_count") or 0)
        replan_success = (
            int(trace.get("successful_replan_count") or 0) / replan_count if replan_count else 1.0
        )
        approval_count = int(trace.get("approval_checkpoint_count") or 0)
        approval_compliance = (
            int(trace.get("approved_checkpoint_count") or 0) / approval_count
            if approval_count
            else 1.0
        )
        observation_count = int(trace.get("observation_count") or 0)
        step_count = int(trace.get("step_count") or 0)
        observation_coverage = (
            observation_count / step_count
            if step_count and trace.get("observation_schema_version")
            else 1.0
        )
        quality = _clamp(
            0.22 * task_success
            + 0.18 * plan_validity
            + 0.12 * step_success
            + 0.12 * sequence
            + 0.10 * final_response
            + 0.10 * no_policy_violation
            + 0.04 * memory_provenance
            + 0.05 * replan_success
            + 0.04 * approval_compliance
            + 0.03 * observation_coverage
        )
        return _scores(
            quality=quality,
            groundedness=_clamp(
                0.35 * step_success
                + 0.25 * sequence
                + 0.15 * memory_provenance
                + 0.15 * replan_success
                + 0.10 * observation_coverage
            ),
            faithfulness=_clamp(
                0.35 * plan_validity
                + 0.30 * no_policy_violation
                + 0.15 * final_response
                + 0.20 * approval_compliance
            ),
            method=self.method,
            scorer_id=self.scorer_id,
            details={
                "trace_schema_version": trace.get("schema_version"),
                "memory_registry_version": trace.get("memory_registry_version"),
                "tool_registry_version": trace.get("tool_registry_version"),
                "task_success": task_success,
                "plan_validity": plan_validity,
                "step_success_rate": step_success,
                "sequence_match": bool(trace.get("sequence_match")),
                "policy_violation_count": int(trace.get("policy_violation_count") or 0),
                "final_response_present": bool(trace.get("final_response_present")),
                "memory_provenance_rate": memory_provenance,
                "replan_success_rate": replan_success,
                "approval_compliance_rate": approval_compliance,
                "observation_coverage_rate": observation_coverage,
                "trace_status": trace.get("status"),
            },
        )


class RagEvaluationScorer:
    scorer_id = "rag_evaluation"
    method = "retrieval_citation_groundedness"
    descriptor = ScorerDescriptor(
        scorer_id=scorer_id,
        scorer_version="rag-evaluation-scorer-v5",
        method=method,
        capabilities=frozenset(
            {
                "retrieval_recall",
                "citation_precision",
                "citation_recall",
                "groundedness",
                "unsupported_claim_detection",
                "refusal_contract",
                "required_fact_coverage",
                "forbidden_claim_detection",
                "evidence_selection_audit",
                "acceptable_evidence_groups",
                "any_of_evidence_contract",
                "any_of_required_fact_contract",
                "bounded_answer_contract",
            }
        ),
        input_schema_version="rag-evaluation-trace-v5",
        output_schema_version="score-outcome-v1",
    )

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool:
        return isinstance(result.metadata.get("rag_evaluation"), dict) or _is_rag_case(
            evaluation_case
        )

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        trace = result.metadata.get("rag_evaluation")
        if not isinstance(trace, dict):
            return _scores(
                quality=0.0,
                groundedness=0.0,
                faithfulness=0.0,
                method=self.method,
                scorer_id=self.scorer_id,
                details={"reason": "RAG evaluation trace is missing"},
            )
        retrieval = trace.get("retrieval")
        retrieval = retrieval if isinstance(retrieval, dict) else {}
        retrieval_recall = _trace_rate(retrieval, "retrieval_recall")
        citation_precision = _trace_rate(trace, "citation_precision")
        citation_recall = _trace_rate(trace, "citation_recall")
        groundedness = _trace_rate(trace, "groundedness_score")
        unsupported_rate = _trace_rate(trace, "unsupported_claim_rate")
        faithfulness = _clamp(1.0 - unsupported_rate)
        semantic_declared = bool(trace.get("semantic_contract_declared"))
        semantic_satisfied = (
            bool(trace.get("semantic_contract_satisfied")) if semantic_declared else True
        )
        semantic_score = 1.0 if semantic_satisfied else 0.0
        quality = _clamp(
            0.20 * retrieval_recall
            + 0.15 * citation_precision
            + 0.10 * citation_recall
            + 0.20 * groundedness
            + 0.15 * faithfulness
            + 0.20 * semantic_score
        )
        return _scores(
            quality=quality,
            groundedness=groundedness,
            faithfulness=faithfulness,
            method=self.method,
            scorer_id=self.scorer_id,
            details={
                "trace_schema_version": trace.get("schema_version"),
                "retrieval_trace_version": retrieval.get("schema_version"),
                "corpus_version": retrieval.get("corpus_version"),
                "retriever_version": retrieval.get("retriever_version"),
                "retrieval_recall": retrieval_recall,
                "evidence_contract_version": retrieval.get("evidence_contract_version"),
                "retrieval_contract_satisfied": bool(
                    retrieval.get("retrieval_contract_satisfied")
                ),
                "satisfied_evidence_group_index": retrieval.get(
                    "satisfied_evidence_group_index"
                ),
                "evidence_selector_version": (
                    retrieval.get("evidence_selection", {}).get("selector_version")
                    if isinstance(retrieval.get("evidence_selection"), dict)
                    else None
                ),
                "evidence_selection_recall": _trace_rate(retrieval, "evidence_selection_recall"),
                "evidence_selection_contract_satisfied": bool(
                    retrieval.get("evidence_selection_contract_satisfied")
                ),
                "citation_precision": citation_precision,
                "citation_recall": citation_recall,
                "citation_contract_satisfied": bool(
                    trace.get("citation_contract_satisfied")
                ),
                "groundedness_score": groundedness,
                "unsupported_claim_rate": unsupported_rate,
                "semantic_contract_declared": semantic_declared,
                "semantic_contract_version": trace.get("semantic_contract_version"),
                "semantic_contract_satisfied": semantic_satisfied,
                "must_refuse": trace.get("must_refuse"),
                "refusal_detected": bool(trace.get("refusal_detected")),
                "required_fact_coverage": _trace_rate(trace, "required_fact_coverage"),
                "required_fact_contract_satisfied": bool(
                    trace.get("required_fact_contract_satisfied")
                ),
                "satisfied_required_fact_group_index": trace.get(
                    "satisfied_required_fact_group_index"
                ),
                "forbidden_claim_violation_count": int(
                    trace.get("forbidden_claim_violation_count") or 0
                ),
                "answer_contract_version": trace.get("answer_contract_version"),
                "answer_contract_strategy": trace.get("answer_contract_strategy"),
                "answer_contract_satisfied": bool(
                    trace.get("answer_contract_satisfied", True)
                ),
                "trace_status": trace.get("status"),
            },
        )


class GroundedReferenceScorer:
    scorer_id = "grounded_reference"
    method = "reference_context_overlap"
    descriptor = ScorerDescriptor(
        scorer_id=scorer_id,
        scorer_version="grounded-reference-scorer-v1",
        method=method,
        capabilities=frozenset({"groundedness", "faithfulness", "reference_overlap"}),
        input_schema_version="evaluation-case-v1",
        output_schema_version="score-outcome-v1",
    )

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool:
        category = (evaluation_case.category or "").lower()
        return "ground" in category or evaluation_case.reference_context_json is not None

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        output = (result.normalized_output or result.raw_output or "").strip()
        if not output:
            return _scores(
                quality=0.0,
                groundedness=0.0,
                faithfulness=0.0,
                method=self.method,
                scorer_id=self.scorer_id,
                details={"reason": "empty output"},
            )

        facts = _reference_facts(evaluation_case.reference_context_json)
        fact_coverage = _fact_coverage(output, facts)
        context_corpus = (
            _stringify_json(evaluation_case.input_payload_json)
            + " "
            + _stringify_json(evaluation_case.reference_context_json)
        )
        context_overlap = _token_overlap(output, context_corpus)
        concise_score = 1.0 if len(output) <= 900 else 0.85
        groundedness = _clamp(0.72 + 0.18 * fact_coverage + 0.10 * context_overlap)
        faithfulness = _clamp(0.70 + 0.20 * fact_coverage + 0.10 * context_overlap)
        quality = _clamp(0.40 * groundedness + 0.35 * faithfulness + 0.25 * concise_score)
        return _scores(
            quality=quality,
            groundedness=groundedness,
            faithfulness=faithfulness,
            method=self.method,
            scorer_id=self.scorer_id,
            details={
                "fact_coverage": fact_coverage,
                "context_overlap": context_overlap,
                "fact_count": len(facts),
                "concise_score": concise_score,
            },
        )


class TextPresenceScorer:
    scorer_id = "text_presence"
    method = "non_empty_text"
    descriptor = ScorerDescriptor(
        scorer_id=scorer_id,
        scorer_version="text-presence-scorer-v1",
        method=method,
        capabilities=frozenset({"text_generation"}),
        input_schema_version="evaluation-case-v1",
        output_schema_version="score-outcome-v1",
    )

    def supports(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> bool:
        return True

    def score(self, evaluation_case: EvaluationCase, result: AdapterCaseResult) -> ScoringOutcome:
        output = (result.normalized_output or result.raw_output or "").strip()
        quality = 0.85 if output else 0.0
        return _scores(
            quality=quality,
            groundedness=quality,
            faithfulness=quality,
            method=self.method,
            scorer_id=self.scorer_id,
            details={"output_length": len(output)},
        )


def build_default_scorer_registry() -> ResultScorerRegistry:
    return ResultScorerRegistry(
        scorers=[
            AgentExecutionScorer(),
            RagEvaluationScorer(),
            ToolCallScorer(),
            JsonSchemaScorer(),
            GroundedReferenceScorer(),
        ],
        fallback_scorer=TextPresenceScorer(),
    )


DEFAULT_SCORER_REGISTRY = build_default_scorer_registry()


def score_case_result(
    evaluation_case: EvaluationCase,
    result: AdapterCaseResult,
    registry: ResultScorerRegistry | None = None,
) -> AdapterCaseResult:
    """Fill missing quality scores with deterministic local scoring evidence."""
    requires_domain_scoring = (
        isinstance(result.metadata.get("agent_execution"), dict)
        or isinstance(result.metadata.get("tool_execution"), dict)
        or isinstance(result.metadata.get("rag_evaluation"), dict)
    )
    if (
        not requires_domain_scoring
        and result.quality_score is not None
        and result.groundedness_score is not None
        and result.faithfulness_score is not None
    ):
        return result

    scorer_registry = registry or DEFAULT_SCORER_REGISTRY
    scores = scorer_registry.score(evaluation_case, result)
    scorer_descriptor = scorer_registry.descriptor_for(scores.scorer_id)

    quality_score = (
        scores.quality
        if requires_domain_scoring
        else (result.quality_score if result.quality_score is not None else scores.quality)
    )
    groundedness_score = (
        scores.groundedness
        if requires_domain_scoring
        else (
            result.groundedness_score
            if result.groundedness_score is not None
            else scores.groundedness
        )
    )
    faithfulness_score = (
        scores.faithfulness
        if requires_domain_scoring
        else (
            result.faithfulness_score
            if result.faithfulness_score is not None
            else scores.faithfulness
        )
    )
    human_label = result.human_label
    if human_label in {None, "captured-needs-scoring"}:
        human_label = "heuristic-pass" if quality_score >= PASS_THRESHOLD else "heuristic-fail"

    return replace(
        result,
        quality_score=quality_score,
        groundedness_score=groundedness_score,
        faithfulness_score=faithfulness_score,
        human_label=human_label,
        metadata={
            **result.metadata,
            "scorer": {
                "version": scorer_descriptor.scorer_version,
                "scorer_version": scorer_descriptor.scorer_version,
                "registry_id": scorer_registry.registry_id,
                "registry_version": scorer_registry.registry_version,
                "scorer_id": scores.scorer_id,
                "method": scores.method,
                "capabilities": sorted(scorer_descriptor.capabilities),
                "input_schema_version": scorer_descriptor.input_schema_version,
                "output_schema_version": scorer_descriptor.output_schema_version,
                "details": scores.details,
            },
        },
    )


def _is_json_case(evaluation_case: EvaluationCase) -> bool:
    return (
        evaluation_case.expected_output_json is not None
        or "json" in (evaluation_case.category or "").lower()
    )


def _trace_rate(trace: dict[str, Any], key: str) -> float:
    value = trace.get(key)
    return _clamp(float(value)) if isinstance(value, int | float) else 0.0


def _is_tool_case(evaluation_case: EvaluationCase) -> bool:
    return (
        evaluation_case.expected_tool_schema_json is not None
        or "tool" in (evaluation_case.category or "").lower()
    )


def _is_rag_case(evaluation_case: EvaluationCase) -> bool:
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    return (
        isinstance(reference.get("rag"), dict) or "rag" in (evaluation_case.category or "").lower()
    )


def _scores(
    *,
    quality: float,
    groundedness: float,
    faithfulness: float,
    method: str,
    scorer_id: str,
    details: dict[str, Any],
) -> ScoringOutcome:
    return ScoringOutcome(
        quality=round(_clamp(quality), 3),
        groundedness=round(_clamp(groundedness), 3),
        faithfulness=round(_clamp(faithfulness), 3),
        method=method,
        scorer_id=scorer_id,
        details=details,
    )


def _parse_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _required_keys(schema: dict[str, Any] | None) -> list[str]:
    required = (schema or {}).get("required", [])
    return [str(key) for key in required] if isinstance(required, list) else []


def _property_type_score(schema: dict[str, Any] | None, parsed: dict[str, Any]) -> float:
    properties = (schema or {}).get("properties", {})
    if not isinstance(properties, dict) or not properties:
        return 1.0
    scored = 0
    matched = 0
    for key, spec in properties.items():
        if key not in parsed or not isinstance(spec, dict):
            continue
        scored += 1
        expected_type = spec.get("type")
        if expected_type is None or _matches_json_type(parsed[key], str(expected_type)):
            matched += 1
    return matched / scored if scored else 1.0


def _matches_json_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def _required_tool_arguments(schema: dict[str, Any]) -> list[str]:
    arguments = schema.get("arguments")
    if isinstance(arguments, dict):
        required = arguments.get("required", [])
        if isinstance(required, list):
            return [str(item) for item in required]
    required_arguments = schema.get("required_arguments", [])
    if not isinstance(required_arguments, list):
        return []
    return [str(item) for item in required_arguments]


def _coverage(required: list[str], actual: Any) -> float:
    if not required:
        return 1.0
    actual_set = {str(item) for item in actual}
    return sum(1 for key in required if key in actual_set) / len(required)


def _reference_facts(reference_context: dict[str, Any] | None) -> list[str]:
    if not isinstance(reference_context, dict):
        return []
    facts = reference_context.get("facts", [])
    if isinstance(facts, list):
        return [str(fact) for fact in facts if str(fact).strip()]
    return []


def _fact_coverage(output: str, facts: list[str]) -> float:
    if not facts:
        return 1.0
    output_lower = output.lower()
    matched = 0
    for fact in facts:
        fact_lower = fact.lower()
        fact_tokens = _tokens(fact_lower)
        if fact_lower in output_lower or (
            fact_tokens and _token_overlap(output_lower, " ".join(fact_tokens)) >= 0.5
        ):
            matched += 1
    return matched / len(facts)


def _token_overlap(output: str, source: str) -> float:
    output_tokens = set(_tokens(output))
    source_tokens = set(_tokens(source))
    if not output_tokens or not source_tokens:
        return 0.0
    return len(output_tokens & source_tokens) / len(output_tokens)


def _tokens(value: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[\w\uac00-\ud7a3]{2,}", value)]


def _stringify_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
