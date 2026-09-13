"""Compatibility facade for the RAG pipeline.

Existing consumers may keep importing here. Implementations live in rag_pipeline;
pipeline modules must not import this facade.
"""

from .rag_pipeline.contracts import (
    FORBIDDEN_CLAIM_MATCH_THRESHOLD as FORBIDDEN_CLAIM_MATCH_THRESHOLD,
)
from .rag_pipeline.contracts import (
    LEXICAL_RETRIEVER_VERSION as LEXICAL_RETRIEVER_VERSION,
)
from .rag_pipeline.contracts import (
    MAX_RETRIEVAL_TOP_K as MAX_RETRIEVAL_TOP_K,
)
from .rag_pipeline.contracts import (
    RAG_CORPUS_REGISTRY_VERSION as RAG_CORPUS_REGISTRY_VERSION,
)
from .rag_pipeline.contracts import (
    RAG_EVALUATION_SUMMARY_VERSION as RAG_EVALUATION_SUMMARY_VERSION,
)
from .rag_pipeline.contracts import (
    RAG_EVALUATION_TRACE_VERSION as RAG_EVALUATION_TRACE_VERSION,
)
from .rag_pipeline.contracts import (
    RAG_RETRIEVAL_TRACE_VERSION as RAG_RETRIEVAL_TRACE_VERSION,
)
from .rag_pipeline.contracts import (
    SELECTED_EVIDENCE_CATEGORIES as SELECTED_EVIDENCE_CATEGORIES,
)
from .rag_pipeline.contracts import (
    SEMANTIC_FACT_MATCH_THRESHOLD as SEMANTIC_FACT_MATCH_THRESHOLD,
)
from .rag_pipeline.contracts import (
    RagChunk as RagChunk,
)
from .rag_pipeline.contracts import (
    RagCorpus as RagCorpus,
)
from .rag_pipeline.contracts import (
    RagCorpusRegistry as RagCorpusRegistry,
)
from .rag_pipeline.contracts import (
    RagEvaluationTrace as RagEvaluationTrace,
)
from .rag_pipeline.contracts import (
    RagPreparation as RagPreparation,
)
from .rag_pipeline.contracts import (
    RagRetrievalTrace as RagRetrievalTrace,
)
from .rag_pipeline.contracts import (
    RetrievedChunk as RetrievedChunk,
)
from .rag_pipeline.contracts import (
    RetrieverDescriptor as RetrieverDescriptor,
)
from .rag_pipeline.corpus import (
    DEFAULT_RAG_CORPUS as DEFAULT_RAG_CORPUS,
)
from .rag_pipeline.corpus import (
    DEFAULT_RAG_CORPUS_REGISTRY as DEFAULT_RAG_CORPUS_REGISTRY,
)
from .rag_pipeline.corpus import (
    DEFAULT_RETRIEVER_DESCRIPTOR as DEFAULT_RETRIEVER_DESCRIPTOR,
)
from .rag_pipeline.corpus import (
    _build_default_corpus as _build_default_corpus,
)
from .rag_pipeline.corpus import (
    _stable_hash as _stable_hash,
)
from .rag_pipeline.execution import (
    attach_rag_evaluation as attach_rag_evaluation,
)
from .rag_pipeline.execution import (
    is_rag_case as is_rag_case,
)
from .rag_pipeline.execution import (
    prepare_rag_execution as prepare_rag_execution,
)
from .rag_pipeline.retrieval import (
    retrieve as retrieve,
)
from .rag_pipeline.scoring import (
    _citations as _citations,
)
from .rag_pipeline.scoring import (
    _claim_support_score as _claim_support_score,
)
from .rag_pipeline.scoring import (
    _claims as _claims,
)
from .rag_pipeline.scoring import (
    _evaluate_semantic_contract as _evaluate_semantic_contract,
)
from .rag_pipeline.scoring import (
    _semantic_match_result as _semantic_match_result,
)
from .rag_pipeline.scoring import (
    _semantic_match_score as _semantic_match_score,
)
from .rag_pipeline.scoring import (
    evaluate_rag_output as evaluate_rag_output,
)
from .rag_pipeline.summaries import (
    _mean as _mean,
)
from .rag_pipeline.summaries import (
    _nested_number as _nested_number,
)
from .rag_pipeline.summaries import (
    _number as _number,
)
from .rag_pipeline.summaries import (
    summarize_rag_traces as summarize_rag_traces,
)
from .rag_pipeline.text import (
    _contains_negation as _contains_negation,
)
from .rag_pipeline.text import (
    _detect_refusal as _detect_refusal,
)
from .rag_pipeline.text import (
    _semantic_tokens as _semantic_tokens,
)
from .rag_pipeline.text import (
    _tokens as _tokens,
)
