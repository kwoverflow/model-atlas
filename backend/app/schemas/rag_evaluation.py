from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RagChunkRead(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagCorpusSummaryRead(BaseModel):
    corpus_id: str
    corpus_version: str
    display_name: str
    description: str
    language: str
    chunk_count: int
    document_count: int
    corpus_hash: str


class RagCorpusRead(RagCorpusSummaryRead):
    chunks: list[RagChunkRead] = Field(default_factory=list)


class RagCorpusRegistryRead(BaseModel):
    registry_id: str
    registry_version: str
    corpus_count: int
    corpora: list[RagCorpusSummaryRead] = Field(default_factory=list)


class RetrieverDescriptorRead(BaseModel):
    retriever_id: str
    retriever_version: str
    display_name: str
    capabilities: list[str] = Field(default_factory=list)
    input_schema_version: str
    output_schema_version: str


class RetrievedChunkRead(BaseModel):
    rank: int
    chunk_id: str
    document_id: str
    title: str
    text: str
    score: float


class RagRetrievalTraceRead(BaseModel):
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
    evidence_contract_version: str = "rag-evidence-contract-v1"
    expected_relevant_chunk_ids: list[str] = Field(default_factory=list)
    acceptable_evidence_groups: list[list[str]] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunkRead] = Field(default_factory=list)
    relevant_retrieved_chunk_ids: list[str] = Field(default_factory=list)
    matched_acceptable_chunk_ids: list[str] = Field(default_factory=list)
    retrieval_recall: float
    retrieval_contract_satisfied: bool = False
    satisfied_evidence_group_index: int | None = None
    retrieval_latency_ms: float
    status: Literal["success", "empty", "invalid_config"]
    errors: list[str] = Field(default_factory=list)
    evidence_selection: dict[str, Any] = Field(default_factory=dict)
    selected_relevant_chunk_ids: list[str] = Field(default_factory=list)
    selected_acceptable_chunk_ids: list[str] = Field(default_factory=list)
    evidence_selection_recall: float = 0.0
    evidence_selection_contract_satisfied: bool = False
    satisfied_selection_group_index: int | None = None


class RagEvaluationTraceRead(BaseModel):
    schema_version: str
    status: Literal["success", "failed"]
    successful: bool
    output_valid: bool
    output_error: str | None = None
    answer: str
    citations: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    invalid_citation_ids: list[str] = Field(default_factory=list)
    correct_citation_ids: list[str] = Field(default_factory=list)
    citation_precision: float
    citation_recall: float
    citation_contract_satisfied: bool = False
    satisfied_citation_group_index: int | None = None
    groundedness_score: float
    unsupported_claim_count: int
    unsupported_claim_rate: float
    claim_support_scores: list[float] = Field(default_factory=list)
    semantic_contract_declared: bool = False
    semantic_contract_version: str = "rag-semantic-contract-v1"
    semantic_contract_satisfied: bool = True
    must_refuse: bool | None = None
    refusal_detected: bool = False
    refusal_requirement_satisfied: bool = True
    required_facts: list[str] = Field(default_factory=list)
    acceptable_required_fact_groups: list[list[str]] = Field(default_factory=list)
    required_fact_group_results: list[list[dict[str, Any]]] = Field(default_factory=list)
    required_fact_results: list[dict[str, Any]] = Field(default_factory=list)
    required_fact_coverage: float = 1.0
    required_fact_contract_satisfied: bool = True
    matched_required_facts: list[str] = Field(default_factory=list)
    satisfied_required_fact_group_index: int | None = None
    forbidden_claims: list[str] = Field(default_factory=list)
    forbidden_claim_results: list[dict[str, Any]] = Field(default_factory=list)
    forbidden_claim_violation_count: int = 0
    answer_contract_version: str | None = None
    answer_contract_strategy: str | None = None
    answer_contract_applied: bool = False
    answer_contract_satisfied: bool = True
    retrieval: RagRetrievalTraceRead


class RagEvaluationTraceRecordRead(BaseModel):
    benchmark_result_id: UUID
    evaluation_case_id: UUID | None = None
    sample_id: str
    case_title: str | None = None
    criticality: str | None = None
    trace: RagEvaluationTraceRead
