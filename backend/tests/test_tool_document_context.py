from types import SimpleNamespace

from app.services.benchmark_execution import _tool_document_context
from app.services.rag_evaluation import RagChunk, RagCorpus, RagCorpusRegistry
from app.services.tool_selection_prompt import build_tool_selection_prompt


def test_catalog_is_bound_to_configured_corpus_and_never_unions_other_workloads():
    first = RagCorpus(
        corpus_id="first",
        corpus_version="1",
        corpus_hash="first-hash",
        display_name="First",
        description="Test",
        language="en",
        chunks=(RagChunk("chunk", "docs/first.md", "First", "Source"),),
    )
    second = RagCorpus(
        corpus_id="second",
        corpus_version="1",
        corpus_hash="second-hash",
        display_name="Second",
        description="Test",
        language="en",
        chunks=(RagChunk("other-chunk", "private/other.md", "Other", "Other source"),),
    )
    registry = RagCorpusRegistry({"first": first, "second": second})
    configuration = SimpleNamespace(
        retrieval_config_json={
            "corpus_id": "first",
            "corpus_hash": "first-hash",
            "corpus_version": "1",
        }
    )
    context = _tool_document_context(configuration, registry)
    assert context["document_ids"] == ["docs/first.md"]
    assert context["corpus_hash"] == "first-hash"
    configuration.retrieval_config_json["corpus_hash"] = "stale"
    assert _tool_document_context(configuration, registry) is None
    configuration.retrieval_config_json = {}
    assert _tool_document_context(configuration, registry) is None


def test_compact_prompt_keeps_public_document_catalog_and_binds_it_to_hash():
    payload = {
        "request": "open a document",
        "available_tools": [
            {
                "tool_name": "lookup_document",
                "description": "Read only",
                "argument_schema": {
                    "type": "object",
                    "properties": {"document_id": {"type": "string"}},
                    "required": ["document_id"],
                },
            }
        ],
        "available_document_ids": ["docs/first.md"],
        "document_catalog_provenance": {"corpus_hash": "first-hash"},
    }
    first = build_tool_selection_prompt(payload)
    assert first.user_payload["available_document_ids"] == ["docs/first.md"]
    payload["available_document_ids"] = ["docs/second.md"]
    second = build_tool_selection_prompt(payload)
    assert first.source_hash != second.source_hash
    assert first.user_payload["available_document_ids"] == ["docs/first.md"]
