"""Prepare adapter input and attach RAG evidence without exposing expected labels."""

from __future__ import annotations

from dataclasses import replace

from app.models import DeploymentConfiguration, EvaluationCase
from app.services.inference_adapters.base import AdapterCaseResult
from app.services.rag_answer_contract import (
    compile_bounded_rag_answer,
    rag_answer_contract_descriptor,
)
from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    LEGACY_RAG_EVIDENCE_CONTRACT_VERSION,
    RagEvidenceExpectation,
    parse_rag_evidence_expectation,
    rag_evidence_contract_descriptor,
)
from app.services.rag_evidence_selection import (
    EvidenceCandidate,
    select_evidence,
    selector_descriptor,
)
from app.services.rag_semantic_contract import (
    rag_semantic_contract_descriptor,
)

from .contracts import (
    LEXICAL_RETRIEVER_VERSION,
    MAX_RETRIEVAL_TOP_K,
    RAG_RETRIEVAL_TRACE_VERSION,
    SELECTED_EVIDENCE_CATEGORIES,
    RagCorpusRegistry,
    RagPreparation,
    RagRetrievalTrace,
)
from .corpus import DEFAULT_RAG_CORPUS, DEFAULT_RAG_CORPUS_REGISTRY, DEFAULT_RETRIEVER_DESCRIPTOR
from .retrieval import retrieve
from .scoring import evaluate_rag_output


def is_rag_case(evaluation_case: EvaluationCase) -> bool:
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    return (
        isinstance(reference.get("rag"), dict) or "rag" in (evaluation_case.category or "").lower()
    )


def prepare_rag_execution(
    configuration: DeploymentConfiguration,
    evaluation_case: EvaluationCase,
    registry: RagCorpusRegistry | None = None,
) -> RagPreparation | None:
    if not is_rag_case(evaluation_case):
        return None
    resolved_registry = registry or DEFAULT_RAG_CORPUS_REGISTRY
    reference = (
        evaluation_case.reference_context_json
        if isinstance(evaluation_case.reference_context_json, dict)
        else {}
    )
    case_contract = reference.get("rag")
    case_contract = case_contract if isinstance(case_contract, dict) else {}
    retrieval_config = (
        configuration.retrieval_config_json
        if isinstance(configuration.retrieval_config_json, dict)
        else {}
    )
    errors: list[str] = []
    corpus_id = str(
        case_contract.get("corpus_id")
        or retrieval_config.get("corpus_id")
        or DEFAULT_RAG_CORPUS.corpus_id
    )
    corpus = resolved_registry.get(corpus_id)
    requested_corpus_version = str(
        case_contract.get("corpus_version") or retrieval_config.get("corpus_version") or ""
    )
    if corpus is None:
        errors.append(f"corpus {corpus_id} is not registered")
    elif requested_corpus_version and requested_corpus_version != corpus.corpus_version:
        errors.append(
            f"corpus version {requested_corpus_version} does not match {corpus.corpus_version}"
        )

    retriever_id = str(retrieval_config.get("retriever_id") or "lexical_overlap")
    retriever_version = str(retrieval_config.get("retriever_version") or LEXICAL_RETRIEVER_VERSION)
    if retriever_id != DEFAULT_RETRIEVER_DESCRIPTOR.retriever_id:
        errors.append(f"retriever {retriever_id} is not supported")
    if retriever_version != DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version:
        errors.append(f"retriever version {retriever_version} is not supported")

    top_k = retrieval_config.get("top_k", 3)
    if (
        not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or not 1 <= top_k <= MAX_RETRIEVAL_TOP_K
    ):
        errors.append(f"top_k must be between 1 and {MAX_RETRIEVAL_TOP_K}")
        top_k = 3
    min_score_value = retrieval_config.get("min_score", 0.05)
    if not isinstance(min_score_value, int | float) or isinstance(min_score_value, bool):
        errors.append("min_score must be numeric")
        min_score = 0.05
    else:
        min_score = float(min_score_value)
        if not 0 <= min_score <= 1:
            errors.append("min_score must be between 0 and 1")
            min_score = 0.05

    query = str(
        case_contract.get("query")
        or evaluation_case.input_payload_json.get("query")
        or evaluation_case.input_payload_json.get("question")
        or ""
    ).strip()
    if not query:
        errors.append("RAG case query is empty")
    try:
        evidence_expectation = parse_rag_evidence_expectation(case_contract)
    except ValueError as exc:
        errors.append(f"RAG evidence contract is invalid: {exc}")
        evidence_expectation = RagEvidenceExpectation(
            contract_version=LEGACY_RAG_EVIDENCE_CONTRACT_VERSION,
            primary_chunk_ids=(),
            acceptable_groups=(),
        )
    relevant_ids = list(evidence_expectation.primary_chunk_ids)
    acceptable_groups = [list(group) for group in evidence_expectation.acceptable_groups]

    if errors or corpus is None:
        trace = RagRetrievalTrace(
            schema_version=RAG_RETRIEVAL_TRACE_VERSION,
            registry_version=resolved_registry.registry_version,
            corpus_id=corpus_id,
            corpus_version=corpus.corpus_version if corpus else requested_corpus_version,
            corpus_hash=corpus.corpus_hash if corpus else "",
            retriever_id=retriever_id,
            retriever_version=retriever_version,
            query=query,
            top_k=top_k,
            min_score=min_score,
            evidence_contract_version=evidence_expectation.contract_version,
            expected_relevant_chunk_ids=relevant_ids,
            acceptable_evidence_groups=acceptable_groups,
            retrieved_chunks=[],
            relevant_retrieved_chunk_ids=[],
            matched_acceptable_chunk_ids=[],
            retrieval_recall=0.0,
            retrieval_contract_satisfied=False,
            satisfied_evidence_group_index=None,
            retrieval_latency_ms=0.0,
            status="invalid_config",
            errors=errors,
        )
    else:
        trace = retrieve(
            corpus=corpus,
            query=query,
            relevant_chunk_ids=relevant_ids,
            acceptable_evidence_groups=(
                acceptable_groups
                if evidence_expectation.contract_version == ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
                else None
            ),
            evidence_contract_version=evidence_expectation.contract_version,
            top_k=top_k,
            min_score=min_score,
            registry_version=resolved_registry.registry_version,
        )

    selection = select_evidence(
        query=trace.query,
        category=evaluation_case.category or "",
        max_selected=1,
        candidates=[
            EvidenceCandidate(
                rank=chunk.rank,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.title,
                text=chunk.text,
                retrieval_score=chunk.score,
            )
            for chunk in trace.retrieved_chunks
        ],
    )
    selected_ids = set(selection.selected_chunk_ids)
    selected_relevant_ids = [chunk_id for chunk_id in relevant_ids if chunk_id in selected_ids]
    selection_match = evidence_expectation.match(selected_ids)
    selected_acceptable_ids = [
        chunk_id
        for chunk_id in evidence_expectation.acceptable_chunk_ids
        if chunk_id in selected_ids
    ]
    selection_applied = (evaluation_case.category or "").lower() in (SELECTED_EVIDENCE_CATEGORIES)
    selection_trace = {
        **selection.to_dict(),
        "applied_to_generation": selection_applied,
    }
    answer_contract = compile_bounded_rag_answer(
        category=evaluation_case.category or "",
        query=trace.query,
        claims=[item.claim for item in selection.selections] if selection_applied else [],
    )
    trace = replace(
        trace,
        evidence_selection=selection_trace,
        selected_relevant_chunk_ids=selected_relevant_ids,
        selected_acceptable_chunk_ids=selected_acceptable_ids,
        evidence_selection_recall=round(selection_match.coverage, 6),
        evidence_selection_contract_satisfied=selection_match.satisfied,
        satisfied_selection_group_index=selection_match.group_index,
    )
    selected_chunks = [chunk for chunk in trace.retrieved_chunks if chunk.chunk_id in selected_ids]
    adapter_chunks = (
        selected_chunks if selection_applied and selected_chunks else trace.retrieved_chunks
    )

    adapter_context = {
        "corpus_id": trace.corpus_id,
        "corpus_version": trace.corpus_version,
        "retriever_id": trace.retriever_id,
        "retriever_version": trace.retriever_version,
        "query": trace.query,
        "retrieved_chunks": [
            {
                "rank": chunk.rank,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "title": chunk.title,
                "text": chunk.text,
                "score": chunk.score,
            }
            for chunk in adapter_chunks
        ],
        "retrieval_candidates": [
            {
                "rank": chunk.rank,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "title": chunk.title,
                "score": chunk.score,
            }
            for chunk in trace.retrieved_chunks
        ],
        "evidence_selection": selection_trace,
        **({"answer_contract": answer_contract.to_dict()} if answer_contract is not None else {}),
    }
    return RagPreparation(
        retrieval_trace=trace,
        adapter_input_payload={
            **evaluation_case.input_payload_json,
            "rag_context": adapter_context,
        },
        adapter_reference_context={"rag_context": adapter_context},
        answer_contract=answer_contract.to_dict() if answer_contract is not None else None,
    )


def attach_rag_evaluation(
    evaluation_case: EvaluationCase,
    result: AdapterCaseResult,
    preparation: RagPreparation | None,
) -> AdapterCaseResult:
    if preparation is None:
        return result
    trace = evaluate_rag_output(
        result.normalized_output,
        preparation.retrieval_trace,
        expected_output=(
            evaluation_case.expected_output_json
            if isinstance(evaluation_case.expected_output_json, dict)
            else None
        ),
        answer_contract=preparation.answer_contract,
    )
    logs = [
        {
            "event_type": "rag_retrieval_completed",
            "level": "info" if trace.retrieval.status == "success" else "error",
            "message": f"RAG retrieval finished with status {trace.retrieval.status}.",
            "payload_json": {
                "corpus_id": trace.retrieval.corpus_id,
                "corpus_version": trace.retrieval.corpus_version,
                "retriever_version": trace.retrieval.retriever_version,
                "retrieved_count": len(trace.retrieval.retrieved_chunks),
                "retrieval_recall": trace.retrieval.retrieval_recall,
                "evidence_contract_version": trace.retrieval.evidence_contract_version,
                "retrieval_contract_satisfied": (trace.retrieval.retrieval_contract_satisfied),
                "satisfied_evidence_group_index": (trace.retrieval.satisfied_evidence_group_index),
            },
        },
        {
            "event_type": "rag_evidence_selected",
            "level": (
                "warning"
                if trace.retrieval.evidence_selection.get("abstain_recommended")
                else "info"
            ),
            "message": "RAG evidence selection completed.",
            "payload_json": {
                "selector_version": trace.retrieval.evidence_selection.get("selector_version"),
                "selected_chunk_ids": trace.retrieval.evidence_selection.get(
                    "selected_chunk_ids", []
                ),
                "confidence": trace.retrieval.evidence_selection.get("confidence"),
                "abstain_recommended": trace.retrieval.evidence_selection.get(
                    "abstain_recommended"
                ),
                "evidence_selection_recall": (trace.retrieval.evidence_selection_recall),
                "evidence_selection_contract_satisfied": (
                    trace.retrieval.evidence_selection_contract_satisfied
                ),
            },
        },
        {
            "event_type": "rag_evaluation_completed",
            "level": "info" if trace.successful else "error",
            "message": f"RAG evaluation finished with status {trace.status}.",
            "payload_json": {
                "schema_version": trace.schema_version,
                "citation_precision": trace.citation_precision,
                "groundedness_score": trace.groundedness_score,
                "unsupported_claim_rate": trace.unsupported_claim_rate,
                "semantic_contract_satisfied": trace.semantic_contract_satisfied,
                "semantic_contract_version": trace.semantic_contract_version,
                "required_fact_contract_satisfied": (trace.required_fact_contract_satisfied),
                "satisfied_required_fact_group_index": (trace.satisfied_required_fact_group_index),
                "refusal_detected": trace.refusal_detected,
                "answer_contract_satisfied": trace.answer_contract_satisfied,
            },
        },
    ]
    return replace(
        result,
        exact_match=trace.successful,
        json_valid=trace.output_valid,
        groundedness_score=trace.groundedness_score,
        faithfulness_score=round(1.0 - trace.unsupported_claim_rate, 6),
        error_type=(
            result.error_type
            if result.error_type
            else (None if trace.successful else "rag_evaluation_failed")
        ),
        end_to_end_latency_ms=(result.end_to_end_latency_ms + trace.retrieval.retrieval_latency_ms),
        logs=[*result.logs, *logs],
        metadata={
            **result.metadata,
            "rag_evaluation": trace.to_dict(),
            "rag_corpus": {
                "registry_version": trace.retrieval.registry_version,
                "corpus_id": trace.retrieval.corpus_id,
                "corpus_version": trace.retrieval.corpus_version,
                "corpus_hash": trace.retrieval.corpus_hash,
            },
            "retriever_descriptor": DEFAULT_RETRIEVER_DESCRIPTOR.to_dict(),
            "evidence_selector_descriptor": selector_descriptor(),
            "rag_evidence_contract_descriptor": rag_evidence_contract_descriptor(),
            "rag_semantic_contract_descriptor": rag_semantic_contract_descriptor(),
            "rag_answer_contract_descriptor": rag_answer_contract_descriptor(),
        },
    )
