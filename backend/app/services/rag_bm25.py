"""Opt-in, label-blind retrieval candidate backed by SQLite FTS5 BM25."""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from contextlib import closing

from app.services.rag_evaluation import RagCorpus, RetrievedChunk

RETRIEVER_VERSION = "sqlite-bm25-ko-bigram-v1"
MAX_QUERY_CHARACTERS = 4096
MAX_QUERY_TERMS = 256
TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\uac00-\ud7a3]+")
STOPWORDS = frozenset("a an and are at for from in is of on the to what which who".split())


def retrieval_tokens(value: str) -> list[str]:
    tokens = []
    for token in TOKEN_PATTERN.findall(unicodedata.normalize("NFKC", value).lower()):
        if len(token) < 2 or token in STOPWORDS:
            continue
        tokens.append(token)
        if "\uac00" <= token[0] <= "\ud7a3" and len(token) > 2:
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
    return tokens


def rank_bm25(*, corpus: RagCorpus, query: str, top_k: int = 5) -> list[RetrievedChunk]:
    """Return only matching chunks; scores are positive BM25, not probabilities."""
    if type(top_k) is not int or not 1 <= top_k <= 1000:
        raise ValueError("top_k must be an integer between 1 and 1000")
    if not isinstance(query, str) or len(query) > MAX_QUERY_CHARACTERS:
        raise ValueError("query must be a string of at most 4096 characters")
    terms = sorted(set(retrieval_tokens(query)))
    if len(terms) > MAX_QUERY_TERMS:
        raise ValueError("query exceeds the 256-term retrieval budget")
    if len({chunk.chunk_id for chunk in corpus.chunks}) != len(corpus.chunks):
        raise ValueError("duplicate corpus chunk IDs")
    if not terms or not corpus.chunks:
        return []
    # Tokenization removes FTS operators; quoting and binding keep input out of SQL syntax.
    match_query = " OR ".join(f'"{term}"' for term in terms)
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("CREATE VIRTUAL TABLE chunks USING fts5(title, body)")
        connection.executemany(
            "INSERT INTO chunks(rowid, title, body) VALUES (?, ?, ?)",
            (
                (
                    index,
                    " ".join(retrieval_tokens(chunk.title)),
                    " ".join(retrieval_tokens(chunk.text)),
                )
                for index, chunk in enumerate(corpus.chunks, start=1)
            ),
        )
        rows = connection.execute(
            "SELECT rowid, bm25(chunks, 2.0, 1.0) FROM chunks WHERE chunks MATCH ?",
            (match_query,),
        ).fetchall()
    ranked = sorted(rows, key=lambda row: (row[1], corpus.chunks[row[0] - 1].chunk_id))
    return [
        RetrievedChunk(
            rank=rank,
            chunk_id=corpus.chunks[index - 1].chunk_id,
            document_id=corpus.chunks[index - 1].document_id,
            title=corpus.chunks[index - 1].title,
            text=corpus.chunks[index - 1].text,
            score=round(-score, 12),
        )
        for rank, (index, score) in enumerate(ranked[:top_k], start=1)
    ]
