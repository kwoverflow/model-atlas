"""Deterministic lexical retrieval and evidence-contract accounting."""

from __future__ import annotations

import time
from typing import Any

from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    parse_rag_evidence_expectation,
)

from .contracts import (
    RAG_CORPUS_REGISTRY_VERSION,
    RAG_RETRIEVAL_TRACE_VERSION,
    RagChunk,
    RagCorpus,
    RagRetrievalTrace,
    RetrievedChunk,
)
from .corpus import DEFAULT_RETRIEVER_DESCRIPTOR
from .text import _tokens


def retrieve(
    *,
    corpus: RagCorpus,
    query: str,
    relevant_chunk_ids: list[str],
    acceptable_evidence_groups: list[list[str]] | None = None,
    evidence_contract_version: str | None = None,
    top_k: int,
    min_score: float,
    registry_version: str = RAG_CORPUS_REGISTRY_VERSION,
) -> RagRetrievalTrace:
    started = time.perf_counter()
    expectation_payload: dict[str, Any] = {"relevant_chunk_ids": relevant_chunk_ids}
    if acceptable_evidence_groups is not None:
        expectation_payload.update(
            {
                "evidence_contract_version": (
                    evidence_contract_version or ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
                ),
                "acceptable_evidence_groups": acceptable_evidence_groups,
            }
        )
    expectation = parse_rag_evidence_expectation(expectation_payload)
    query_tokens = set(_tokens(query))
    scored: list[tuple[float, RagChunk]] = []
    for chunk in corpus.chunks:
        chunk_tokens = set(_tokens(f"{chunk.title} {chunk.text}"))
        overlap = query_tokens & chunk_tokens
        if not query_tokens or not overlap:
            score = 0.0
        else:
            query_coverage = len(overlap) / len(query_tokens)
            chunk_density = len(overlap) / max(1, len(chunk_tokens))
            score = round(0.9 * query_coverage + 0.1 * chunk_density, 6)
        if score >= min_score:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1].chunk_id))
    retrieved = [
        RetrievedChunk(
            rank=index,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            title=chunk.title,
            text=chunk.text,
            score=score,
        )
        for index, (score, chunk) in enumerate(scored[:top_k], start=1)
    ]
    retrieved_ids = {chunk.chunk_id for chunk in retrieved}
    relevant_retrieved = [chunk_id for chunk_id in relevant_chunk_ids if chunk_id in retrieved_ids]
    contract_match = expectation.match(retrieved_ids)
    matched_acceptable = [
        chunk_id for chunk_id in expectation.acceptable_chunk_ids if chunk_id in retrieved_ids
    ]
    return RagRetrievalTrace(
        schema_version=RAG_RETRIEVAL_TRACE_VERSION,
        registry_version=registry_version,
        corpus_id=corpus.corpus_id,
        corpus_version=corpus.corpus_version,
        corpus_hash=corpus.corpus_hash,
        retriever_id=DEFAULT_RETRIEVER_DESCRIPTOR.retriever_id,
        retriever_version=DEFAULT_RETRIEVER_DESCRIPTOR.retriever_version,
        query=query,
        top_k=top_k,
        min_score=min_score,
        evidence_contract_version=expectation.contract_version,
        expected_relevant_chunk_ids=relevant_chunk_ids,
        acceptable_evidence_groups=[list(group) for group in expectation.acceptable_groups],
        retrieved_chunks=retrieved,
        relevant_retrieved_chunk_ids=relevant_retrieved,
        matched_acceptable_chunk_ids=matched_acceptable,
        retrieval_recall=round(contract_match.coverage, 6),
        retrieval_contract_satisfied=contract_match.satisfied,
        satisfied_evidence_group_index=contract_match.group_index,
        retrieval_latency_ms=round(max(0.0, (time.perf_counter() - started) * 1000), 3),
        status="success" if retrieved else "empty",
        errors=[],
    )
