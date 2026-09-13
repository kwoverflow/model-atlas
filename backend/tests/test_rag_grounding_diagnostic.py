from __future__ import annotations

import copy
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.rag_grounding_diagnostic import (
    compare_retrieval,
    evaluator_case,
    observe,
    prepare_candidate,
    public_case,
    summarize_observations,
)
from app.services.inference_adapters.cited_rag import (
    CitedRagAdapter,
    validate_paired_output,
)
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.rag_bm25 import rank_bm25, retrieval_tokens
from app.services.rag_evaluation import (
    RagChunk,
    RagCorpus,
    RagCorpusRegistry,
    prepare_rag_execution,
)


def corpus(*chunks):
    return RagCorpus("test", "1", "Test", "Test", "ko", tuple(chunks), "test-hash")


def chunk(id, text, title=""):
    return RagChunk(id, f"doc-{id}", title, text)


def test_partial_korean_token_match():
    source = corpus(chunk("a", "배포 승인 절차"), chunk("b", "다른 정보"))
    result = rank_bm25(corpus=source, query="배포를 승인하려면?", top_k=5)
    assert [item.chunk_id for item in result] == ["a"]
    assert result[0].score > 0


def test_normalized_technical_tokens():
    assert retrieval_tokens("ＤＩＧＥＳＴ burn-rate AND the") == ["digest", "burn", "rate"]


def test_title_weight_and_stable_tie_order():
    source = corpus(chunk("z", "same token"), chunk("a", "same token"))
    assert [c.chunk_id for c in rank_bm25(corpus=source, query="token")] == ["a", "z"]
    source = corpus(chunk("body", "digest unrelated"), chunk("title", "unrelated", "digest"))
    assert rank_bm25(corpus=source, query="digest")[0].chunk_id == "title"


@pytest.mark.parametrize("query", ["", "?!", "없는키워드", "a the and"])
def test_no_match_never_pads_irrelevant_chunks(query):
    assert rank_bm25(corpus=corpus(chunk("a", "publisher provenance")), query=query) == []


def test_empty_corpus():
    assert rank_bm25(corpus=corpus(), query="publisher") == []


def test_fts_and_sql_operators_are_not_executed():
    source = corpus(chunk("a", "digest"), chunk("b", "publisher"))
    result = rank_bm25(corpus=source, query='"digest" OR (publisher*); DROP TABLE chunks; --')
    assert {c.chunk_id for c in result} == {"a", "b"}
    assert rank_bm25(corpus=source, query="digest")[0].chunk_id == "a"


@pytest.mark.parametrize("top_k", [True, 0, -1, 1001, 2.5, "5"])
def test_invalid_top_k(top_k):
    with pytest.raises(ValueError, match="top_k"):
        rank_bm25(corpus=corpus(), query="digest", top_k=top_k)


@pytest.mark.parametrize("query", [None, 2, "a" * 4097, " ".join(f"term{i}" for i in range(257))])
def test_query_budget(query):
    with pytest.raises(ValueError, match="query"):
        rank_bm25(corpus=corpus(), query=query)


def test_duplicate_chunk_ids_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        rank_bm25(corpus=corpus(chunk("a", "digest"), chunk("a", "other")), query="digest")


SOURCES = [{"chunk_id": "a", "text": "The publisher evidence must be verified before deployment."}]
QUOTE = "publisher evidence must be verified"


def paired(answer="Verification is required.", evidence=None):
    return json.dumps(
        {
            "answer": answer,
            "evidence": evidence if evidence is not None else [{"chunk_id": "a", "quote": QUOTE}],
        }
    )


def test_exact_quote_mapping_does_not_repair_or_claim_entailment():
    result = validate_paired_output(paired(), SOURCES)
    assert result["valid"]
    assert not result["verifies_answer_entailment"]
    assert not result["output_repair"]
    assert json.loads(result["normalized_output"]) == {
        "answer": "Verification is required.",
        "citations": ["a"],
        "claims": [QUOTE],
    }


@pytest.mark.parametrize(
    "output",
    [
        "not json",
        "null",
        "[]",
        "{}",
        paired(answer=" "),
        paired(answer=42),
        paired(evidence=[]),
        paired(evidence="bad"),
        paired(evidence=[None]),
        paired(evidence=[{"chunk_id": "a"}]),
        paired(evidence=[{"chunk_id": "unknown", "quote": QUOTE}]),
        paired(evidence=[{"chunk_id": ["a"], "quote": QUOTE}]),
        paired(evidence=[{"chunk_id": "a", "quote": 42}]),
        paired(evidence=[{"chunk_id": "a", "quote": "publisher"}]),
        paired(evidence=[{"chunk_id": "a", "quote": "Never verify publisher evidence."}]),
        paired(evidence=[{"chunk_id": "a", "quote": "  " + QUOTE}]),
        paired(evidence=[{"chunk_id": "a", "quote": "a" * 481}]),
        paired(evidence=[{"chunk_id": "a", "quote": QUOTE}] * 2),
        paired(evidence=[{"chunk_id": "a", "quote": QUOTE}] * 4),
        json.dumps({"answer": "ok", "evidence": [], "extra": "bad"}),
        '{"answer":"first","answer":"second","evidence":[]}',
    ],
)
def test_invalid_pairs_fail_without_fabricating_output(output):
    result = validate_paired_output(output, SOURCES)
    assert not result["valid"]
    assert result["errors"]
    assert result["normalized_output"] is None


def test_quote_must_be_in_the_paired_source_not_another_source():
    sources = SOURCES + [{"chunk_id": "b", "text": "A completely different document."}]
    assert not validate_paired_output(
        paired(evidence=[{"chunk_id": "b", "quote": QUOTE}]), sources
    )["valid"]


def test_multiple_quotes_from_one_source_keep_one_citation():
    output = paired(
        evidence=[
            {"chunk_id": "a", "quote": QUOTE},
            {"chunk_id": "a", "quote": "before deployment."},
        ]
    )
    result = validate_paired_output(output, SOURCES)
    assert result["valid"]
    assert json.loads(result["normalized_output"])["citations"] == ["a"]


@pytest.fixture
def preparation():
    source = corpus(chunk("a", SOURCES[0]["text"]))
    case = SimpleNamespace(
        external_case_id="test-case",
        category="rag_single_document",
        title="Question",
        input_payload_json={"query": "publisher evidence"},
        reference_context_json={
            "rag": {
                "query": "publisher evidence",
                "corpus_id": "test",
                "relevant_chunk_ids": ["a"],
            }
        },
        expected_output_json={"required_facts": ["private expected label"]},
        expected_tool_schema_json=None,
    )
    config = SimpleNamespace(
        retrieval_config_json={"top_k": 5, "min_score": 0},
        runtime_config_json={},
        generation_config_json={"max_tokens": 768},
    )
    baseline = prepare_rag_execution(config, case, RagCorpusRegistry({"test": source}))
    return baseline, source, case, config


def test_labels_never_enter_candidate_context_or_request(preparation):
    baseline, source, case, config = preparation
    changed = replace(
        baseline,
        retrieval_trace=replace(
            baseline.retrieval_trace,
            expected_relevant_chunk_ids=["secret-label-id"],
            acceptable_evidence_groups=[["secret-label-id"]],
        ),
    )
    a = prepare_candidate(baseline, corpus=source, category=case.category)
    b = prepare_candidate(changed, corpus=source, category=case.category)
    assert a.adapter_input_payload == b.adapter_input_payload
    public = public_case(case, b)
    assert public.expected_output_json == {}
    for adapter in (OpenAICompatibleAdapter(), CitedRagAdapter()):
        assert adapter._expects_json(public)
        request = json.dumps(adapter._user_message_payload(public, configuration=config))
        assert "secret-label" not in request
        assert "private expected" not in request
    assert not b.retrieval_trace.retrieval_contract_satisfied


@pytest.mark.parametrize(
    "category",
    [
        "rag_version_or_scope",
        "insufficient_evidence_refusal",
        "rag_tool_combined",
    ],
)
def test_fallback_preparation_and_requests_are_identical(preparation, category):
    baseline, source, case, config = preparation
    case.category = category
    assert prepare_candidate(baseline, corpus=source, category=category) is baseline
    public = public_case(case, baseline)
    old, new = OpenAICompatibleAdapter(), CitedRagAdapter()
    assert old._system_prompt(config, public) == new._system_prompt(config, public)
    assert old._user_message_payload(public) == new._user_message_payload(public)
    assert old._response_format(public) == new._response_format(public)


def test_candidate_rejects_incomparable_minimum_score(preparation):
    baseline, source, case, _ = preparation
    baseline = replace(baseline, retrieval_trace=replace(baseline.retrieval_trace, min_score=0.05))
    with pytest.raises(ValueError, match="score scales"):
        prepare_candidate(baseline, corpus=source, category=case.category)


def test_candidate_adapter_preserves_raw_output_and_marks_failure(preparation, monkeypatch):
    baseline, source, case, config = preparation
    prepared = prepare_candidate(baseline, corpus=source, category=case.category)
    public = public_case(case, prepared)
    bad = paired(evidence=[{"chunk_id": "a", "quote": "This is fabricated source text."}])
    monkeypatch.setattr(CitedRagAdapter, "_resolve_base_url", lambda *a, **k: "http://local")
    monkeypatch.setattr(CitedRagAdapter, "_model_name", lambda *a, **k: "test-model")
    monkeypatch.setattr(
        CitedRagAdapter,
        "_post_json",
        lambda *a, **k: {
            "choices": [{"message": {"content": bad}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10},
        },
    )
    result = CitedRagAdapter().run_case(configuration=config, evaluation_case=public)
    assert result.raw_output == bad
    assert result.normalized_output == bad
    assert result.error_type == "paired_quote_contract_failed"


def test_diagnostic_errors_are_counted_not_dropped(preparation, monkeypatch):
    baseline, _, case, config = preparation
    monkeypatch.setattr(OpenAICompatibleAdapter, "run_case", lambda **kwargs: None)
    row = observe(case, config, baseline, variant="baseline", seed=42)
    assert not row["passed"]
    assert row["error"]
    summary = summarize_observations([row])
    assert summary["baseline"]["count"] == summary["baseline"]["errors"] == 1
    with pytest.raises(ValueError, match="variant"):
        observe(case, config, baseline, variant="unknown", seed=42)


@pytest.mark.parametrize("variant", ["baseline", "bm25", "paired", "bm25_paired"])
def test_actual_request_enables_schema_without_labels(preparation, monkeypatch, variant):
    baseline, _, case, config = preparation
    raw = (
        paired()
        if "paired" in variant
        else json.dumps(
            {
                "answer": "Verification is required.",
                "citations": ["a"],
                "claims": [QUOTE],
            }
        )
    )
    monkeypatch.setattr(
        OpenAICompatibleAdapter, "_resolve_base_url", lambda *a, **k: "http://local"
    )
    monkeypatch.setattr(OpenAICompatibleAdapter, "_model_name", lambda *a, **k: "test-model")
    monkeypatch.setattr(
        OpenAICompatibleAdapter,
        "_post_json",
        lambda *a, **k: {
            "choices": [{"message": {"content": raw}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 10},
        },
    )
    case.expected_output = case.expected_output_json
    row = observe(case, config, baseline, variant=variant, seed=42)
    assert not row.get("error")
    assert row["request_contract_valid"]
    assert row["requests"][0]["body"]["response_format"]["type"] == "json_schema"
    assert "private expected label" not in json.dumps(row["requests"])
    if "paired" in variant:
        assert row["paired_quote_valid"]


def test_full_approved_pack_comparison_is_read_only():
    root = Path(__file__).resolve().parents[2]
    # Docker uses /workspace for the frozen corpus and /app for installed source/tests.
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    revision = root / "reference_workload/revisions/1.0.4"
    bundle = build_reference_corpus(revision / "manifest.json", repository_root=root)
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=revision / "cases.jsonl",
        review_manifest_path=revision / "review_manifest.jsonl",
    )
    before = copy.deepcopy([c.model_dump() for c in pack.cases])
    config = SimpleNamespace(retrieval_config_json={"top_k": 5, "min_score": 0})
    report, preparations = compare_retrieval(pack, bundle, config)
    assert report["case_count"] == 48
    assert report["applied_count"] == 22
    assert all(
        row["fallback_context_identical"] for row in report["rows"] if not row["candidate_applied"]
    )
    assert set(preparations) == {r["external_case_id"] for r in report["rows"]}
    assert before == [c.model_dump() for c in pack.cases]
    critical = next(c for c in pack.cases if c.external_case_id == "KO-RAG-001")
    assert evaluator_case(critical).expected_output_json == critical.expected_output
