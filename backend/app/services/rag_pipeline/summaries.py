"""Aggregate serialized RAG traces into versioned evaluation summaries."""

from __future__ import annotations

from typing import Any

from .contracts import RAG_EVALUATION_SUMMARY_VERSION


def summarize_rag_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_recalls = [_nested_number(trace, "retrieval", "retrieval_recall") for trace in traces]
    citation_precisions = [_number(trace.get("citation_precision")) for trace in traces]
    citation_recalls = [_number(trace.get("citation_recall")) for trace in traces]
    groundedness_scores = [_number(trace.get("groundedness_score")) for trace in traces]
    unsupported_rates = [_number(trace.get("unsupported_claim_rate")) for trace in traces]
    evidence_selection_recalls = [
        _nested_number(trace, "retrieval", "evidence_selection_recall") for trace in traces
    ]
    semantic_traces = [trace for trace in traces if trace.get("semantic_contract_declared")]
    refusal_traces = [trace for trace in semantic_traces if trace.get("must_refuse") is True]
    required_fact_coverages = [
        _number(trace.get("required_fact_coverage")) for trace in semantic_traces
    ]
    corpus_versions = sorted(
        {
            str(retrieval.get("corpus_version"))
            for trace in traces
            if isinstance((retrieval := trace.get("retrieval")), dict)
            and retrieval.get("corpus_version")
        }
    )
    retriever_versions = sorted(
        {
            str(retrieval.get("retriever_version"))
            for trace in traces
            if isinstance((retrieval := trace.get("retrieval")), dict)
            and retrieval.get("retriever_version")
        }
    )
    return {
        "schema_version": RAG_EVALUATION_SUMMARY_VERSION,
        "rag_case_count": len(traces),
        "successful_case_count": sum(1 for trace in traces if trace.get("successful")),
        "failed_case_count": sum(1 for trace in traces if not trace.get("successful")),
        "retrieval_empty_case_count": sum(
            1
            for trace in traces
            if isinstance(trace.get("retrieval"), dict)
            and trace["retrieval"].get("status") == "empty"
        ),
        "average_retrieval_recall": _mean(retrieval_recalls),
        "average_citation_precision": _mean(citation_precisions),
        "average_citation_recall": _mean(citation_recalls),
        "average_groundedness_score": _mean(groundedness_scores),
        "average_unsupported_claim_rate": _mean(unsupported_rates),
        "average_evidence_selection_recall": _mean(evidence_selection_recalls),
        "retrieval_contract_satisfied_count": sum(
            1
            for trace in traces
            if isinstance((retrieval := trace.get("retrieval")), dict)
            and retrieval.get("retrieval_contract_satisfied") is True
        ),
        "citation_contract_satisfied_count": sum(
            1 for trace in traces if trace.get("citation_contract_satisfied") is True
        ),
        "evidence_selection_contract_satisfied_count": sum(
            1
            for trace in traces
            if isinstance((retrieval := trace.get("retrieval")), dict)
            and retrieval.get("evidence_selection_contract_satisfied") is True
        ),
        "alternative_evidence_match_count": sum(
            1
            for trace in traces
            if isinstance((retrieval := trace.get("retrieval")), dict)
            and isinstance(retrieval.get("satisfied_selection_group_index"), int)
            and retrieval["satisfied_selection_group_index"] > 0
        ),
        "low_confidence_selection_count": sum(
            1
            for trace in traces
            if isinstance((retrieval := trace.get("retrieval")), dict)
            and isinstance((selection := retrieval.get("evidence_selection")), dict)
            and selection.get("abstain_recommended") is True
        ),
        "semantic_contract_case_count": len(semantic_traces),
        "semantic_contract_successful_case_count": sum(
            1 for trace in semantic_traces if trace.get("semantic_contract_satisfied")
        ),
        "required_fact_contract_satisfied_count": sum(
            1 for trace in semantic_traces if trace.get("required_fact_contract_satisfied") is True
        ),
        "alternative_required_fact_match_count": sum(
            1
            for trace in semantic_traces
            if isinstance(trace.get("satisfied_required_fact_group_index"), int)
            and trace["satisfied_required_fact_group_index"] > 0
        ),
        "bounded_answer_contract_case_count": sum(
            1 for trace in traces if trace.get("answer_contract_applied") is True
        ),
        "bounded_answer_contract_satisfied_count": sum(
            1
            for trace in traces
            if trace.get("answer_contract_applied") is True
            and trace.get("answer_contract_satisfied") is True
        ),
        "refusal_case_count": len(refusal_traces),
        "successful_refusal_case_count": sum(
            1 for trace in refusal_traces if trace.get("semantic_contract_satisfied")
        ),
        "average_required_fact_coverage": _mean(required_fact_coverages),
        "forbidden_claim_violation_count": sum(
            int(trace.get("forbidden_claim_violation_count") or 0) for trace in semantic_traces
        ),
        "corpus_versions": corpus_versions,
        "retriever_versions": retriever_versions,
    }


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _nested_number(value: dict[str, Any], parent: str, key: str) -> float | None:
    nested = value.get(parent)
    return _number(nested.get(key)) if isinstance(nested, dict) else None


def _mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(sum(present) / len(present), 6) if present else None
