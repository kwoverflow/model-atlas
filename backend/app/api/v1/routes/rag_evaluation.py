from fastapi import APIRouter, HTTPException

from app.schemas import (
    RagCorpusRead,
    RagCorpusRegistryRead,
    RetrieverDescriptorRead,
)
from app.services.rag_evaluation import (
    DEFAULT_RAG_CORPUS_REGISTRY,
    DEFAULT_RETRIEVER_DESCRIPTOR,
)

router = APIRouter()


@router.get("/corpora", response_model=RagCorpusRegistryRead)
def get_corpus_registry() -> RagCorpusRegistryRead:
    return RagCorpusRegistryRead.model_validate(DEFAULT_RAG_CORPUS_REGISTRY.descriptor())


@router.get("/corpora/{corpus_id}", response_model=RagCorpusRead)
def get_corpus(corpus_id: str) -> RagCorpusRead:
    corpus = DEFAULT_RAG_CORPUS_REGISTRY.get(corpus_id)
    if corpus is None:
        raise HTTPException(status_code=404, detail="RAG corpus was not found")
    return RagCorpusRead.model_validate(corpus.to_dict())


@router.get("/retriever", response_model=RetrieverDescriptorRead)
def get_retriever() -> RetrieverDescriptorRead:
    return RetrieverDescriptorRead.model_validate(
        DEFAULT_RETRIEVER_DESCRIPTOR.to_dict()
    )
