"""Versioned RAG data contracts shared by retrieval, execution, and scoring."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

RAG_CORPUS_REGISTRY_VERSION = "rag-corpus-registry-v1"


RAG_RETRIEVAL_TRACE_VERSION = "rag-retrieval-trace-v3"


RAG_EVALUATION_TRACE_VERSION = "rag-evaluation-trace-v5"


RAG_EVALUATION_SUMMARY_VERSION = "rag-evaluation-summary-v5"


LEXICAL_RETRIEVER_VERSION = "lexical-overlap-v1"


MAX_RETRIEVAL_TOP_K = 10


SEMANTIC_FACT_MATCH_THRESHOLD = 0.5


FORBIDDEN_CLAIM_MATCH_THRESHOLD = 0.75


SELECTED_EVIDENCE_CATEGORIES = {
    "rag_version_or_scope",
    "insufficient_evidence_refusal",
}


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    document_id: str
    title: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RagCorpus:
    corpus_id: str
    corpus_version: str
    display_name: str
    description: str
    language: str
    chunks: tuple[RagChunk, ...]
    corpus_hash: str

    def summary(self) -> dict[str, Any]:
        return {
            "corpus_id": self.corpus_id,
            "corpus_version": self.corpus_version,
            "display_name": self.display_name,
            "description": self.description,
            "language": self.language,
            "chunk_count": len(self.chunks),
            "document_count": len({chunk.document_id for chunk in self.chunks}),
            "corpus_hash": self.corpus_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.summary(), "chunks": [chunk.to_dict() for chunk in self.chunks]}


@dataclass(frozen=True)
class RagCorpusRegistry:
    corpora: dict[str, RagCorpus]
    registry_id: str = "model_atlas_local_rag_corpora"
    registry_version: str = RAG_CORPUS_REGISTRY_VERSION

    def get(self, corpus_id: str) -> RagCorpus | None:
        return self.corpora.get(corpus_id)

    def descriptor(self) -> dict[str, Any]:
        return {
            "registry_id": self.registry_id,
            "registry_version": self.registry_version,
            "corpus_count": len(self.corpora),
            "corpora": [self.corpora[key].summary() for key in sorted(self.corpora)],
        }


@dataclass(frozen=True)
class RetrieverDescriptor:
    retriever_id: str = "lexical_overlap"
    retriever_version: str = LEXICAL_RETRIEVER_VERSION
    display_name: str = "Deterministic Lexical Overlap"
    capabilities: tuple[str, ...] = ("local", "deterministic", "top_k", "min_score")
    input_schema_version: str = "rag-query-v1"
    output_schema_version: str = RAG_RETRIEVAL_TRACE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int
    chunk_id: str
    document_id: str
    title: str
    text: str
    score: float


@dataclass(frozen=True)
class RagRetrievalTrace:
    schema_version: str
    registry_version: str
    corpus_id: str
    corpus_version: str
    corpus_hash: str
    retriever_id: str
    retriever_version: str
    query: str
    top_k: int
    min_score: float
    evidence_contract_version: str
    expected_relevant_chunk_ids: list[str]
    acceptable_evidence_groups: list[list[str]]
    retrieved_chunks: list[RetrievedChunk]
    relevant_retrieved_chunk_ids: list[str]
    matched_acceptable_chunk_ids: list[str]
    retrieval_recall: float
    retrieval_contract_satisfied: bool
    satisfied_evidence_group_index: int | None
    retrieval_latency_ms: float
    status: str
    errors: list[str] = field(default_factory=list)
    evidence_selection: dict[str, Any] = field(default_factory=dict)
    selected_relevant_chunk_ids: list[str] = field(default_factory=list)
    selected_acceptable_chunk_ids: list[str] = field(default_factory=list)
    evidence_selection_recall: float = 0.0
    evidence_selection_contract_satisfied: bool = False
    satisfied_selection_group_index: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RagPreparation:
    retrieval_trace: RagRetrievalTrace
    adapter_input_payload: dict[str, Any]
    adapter_reference_context: dict[str, Any]
    answer_contract: dict[str, Any] | None = None


@dataclass(frozen=True)
class RagEvaluationTrace:
    schema_version: str
    status: str
    successful: bool
    output_valid: bool
    output_error: str | None
    answer: str
    citations: list[str]
    claims: list[str]
    invalid_citation_ids: list[str]
    correct_citation_ids: list[str]
    citation_precision: float
    citation_recall: float
    citation_contract_satisfied: bool
    satisfied_citation_group_index: int | None
    groundedness_score: float
    unsupported_claim_count: int
    unsupported_claim_rate: float
    claim_support_scores: list[float]
    semantic_contract_declared: bool
    semantic_contract_version: str
    semantic_contract_satisfied: bool
    must_refuse: bool | None
    refusal_detected: bool
    refusal_requirement_satisfied: bool
    required_facts: list[str]
    acceptable_required_fact_groups: list[list[str]]
    required_fact_group_results: list[list[dict[str, Any]]]
    required_fact_results: list[dict[str, Any]]
    required_fact_coverage: float
    required_fact_contract_satisfied: bool
    matched_required_facts: list[str]
    satisfied_required_fact_group_index: int | None
    forbidden_claims: list[str]
    forbidden_claim_results: list[dict[str, Any]]
    forbidden_claim_violation_count: int
    answer_contract_version: str | None
    answer_contract_strategy: str | None
    answer_contract_applied: bool
    answer_contract_satisfied: bool
    retrieval: RagRetrievalTrace

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
