"""Opt-in bilingual BM25 fusion. Inputs contain no evaluation labels."""

from __future__ import annotations

import math
from dataclasses import replace

from app.services.rag_bm25 import rank_bm25
from app.services.rag_evaluation import RagCorpus, RetrievedChunk

RETRIEVER_VERSION = "bilingual-bm25-rrf-v1"
RANK_WINDOW = 50
RANK_CONSTANT = 60


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]], *, top_k: int = 5
) -> list[RetrievedChunk]:
    """Fuse equally weighted ranked lists; raw retrieval score scales are not mixed."""
    if type(top_k) is not int or not 1 <= top_k <= RANK_WINDOW:
        raise ValueError("top_k must be an integer between 1 and 50")
    scores, sources = {}, {}
    for ranking in rankings:
        if len(ranking) > RANK_WINDOW:
            raise ValueError("ranking exceeds the fixed rank window")
        seen = set()
        for rank, chunk in enumerate(ranking, start=1):
            if chunk.chunk_id in seen or chunk.rank != rank:
                raise ValueError("ranking must have unique IDs and contiguous ranks")
            if not math.isfinite(chunk.score) or chunk.score <= 0:
                raise ValueError("fusion only accepts positive matching scores")
            seen.add(chunk.chunk_id)
            if chunk.chunk_id in sources:
                previous = sources[chunk.chunk_id]
                if (previous.document_id, previous.title, previous.text) != (
                    chunk.document_id,
                    chunk.title,
                    chunk.text,
                ):
                    raise ValueError("conflicting source content for one chunk ID")
            sources[chunk.chunk_id] = chunk
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1 / (RANK_CONSTANT + rank)
    identifiers = sorted(scores, key=lambda key: (-scores[key], key))[:top_k]
    return [
        replace(sources[key], rank=rank, score=round(scores[key], 12))
        for rank, key in enumerate(identifiers, start=1)
    ]


def bilingual_rankings(
    *, corpus: RagCorpus, query: str, translated_query: str, top_k: int = 5
) -> dict[str, list[RetrievedChunk]]:
    original = rank_bm25(corpus=corpus, query=query, top_k=RANK_WINDOW)
    translated = rank_bm25(corpus=corpus, query=translated_query, top_k=RANK_WINDOW)
    fused = reciprocal_rank_fusion([original, translated], top_k=top_k)
    return {
        "bm25_original": original[:top_k],
        "bm25_translated": translated[:top_k],
        "bilingual_rrf": fused,
    }
