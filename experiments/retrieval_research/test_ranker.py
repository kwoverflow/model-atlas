from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

from experiments.retrieval_research.ranker import (
    OnnxRanker,
    RedundancyIndex,
    select_mmr,
    select_top,
    validate_scores,
)
from experiments.retrieval_research.run import (
    CANDIDATES,
    decision,
    public_inputs,
    summarize,
)


def chunks():
    return [
        {"chunk_id": "a", "title": "Release", "text": "Signed release approval provenance"},
        {"chunk_id": "b", "title": "Release", "text": "Signed release approval provenance"},
        {"chunk_id": "c", "title": "Incident", "text": "Paging retries restore failed delivery"},
    ]


def test_score_ties_and_input_order_invariance():
    data = chunks()
    assert select_top(data, [1.0, 1.0, 2.0]) == [2, 0, 1]
    rev = list(reversed(data))
    assert [rev[i]["chunk_id"] for i in select_top(rev, [2.0, 1.0, 1.0])] == ["c", "a", "b"]


@pytest.mark.parametrize(
    "scores", [[1.0], [float("nan"), 1.0, 2.0], [float("inf"), 1.0, 2.0], [True, 1, 2]]
)
def test_invalid_scores(scores):
    with pytest.raises(ValueError):
        validate_scores(chunks(), scores)


def test_duplicate_source_rejected():
    with pytest.raises(ValueError):
        validate_scores([chunks()[0]] * 2, [1.0, 1.0])


@pytest.mark.parametrize("k", [0, 6, True, 1.5])
def test_selection_budget(k):
    with pytest.raises(ValueError):
        select_top(chunks(), [1, 2, 3], k)


def test_mmr_penalizes_duplicate_and_keeps_relevance_first():
    data = chunks()
    matrix = RedundancyIndex(data).similarities(data)
    assert matrix[0][1] == pytest.approx(1)
    assert matrix[0][2] == pytest.approx(0)
    assert select_top(data, [3.0, 2.9, 2.0], 2) == [0, 1]
    assert select_mmr(data, [3.0, 2.9, 2.0], matrix, 2) == [0, 2]
    assert select_mmr(data, [3.0, 2.9, 2.0], matrix, 2, 1.0) == [0, 1]


@pytest.mark.parametrize("matrix", [[], [[1]], [[float("nan")] * 3] * 3, [[2] * 3] * 3])
def test_invalid_mmr_matrix(matrix):
    with pytest.raises(ValueError):
        select_mmr(chunks(), [1, 2, 3], matrix)


def test_empty_candidates():
    assert select_top([], []) == []
    assert select_mmr([], [], []) == []


@pytest.fixture
def local_ranker():
    location = os.environ.get("RAG_RESEARCH_MODEL_DIR")
    if not location:
        pytest.skip("local pinned model not supplied; tests never download")
    return OnnxRanker(Path(location))


def test_native_model_relevance_sanity(local_ranker):
    data = [
        {"chunk_id": "a", "title": "Mars", "text": "Mars is called the Red Planet."},
        {"chunk_id": "b", "title": "Wood", "text": "Oak is used in furniture construction."},
    ]
    result = local_ranker.score("Which planet is called the Red Planet?", data)
    assert result["scores"][0] > result["scores"][1]
    assert result["window_counts"] == [1, 1]


def test_long_passage_uses_complete_overlapping_windows(local_ranker):
    windows = local_ranker.windows("What restores paging?", "paging delivery " * 700)
    assert len(windows) > 1
    assert all(len(w.ids) <= 512 for w in windows)
    assert local_ranker.tokenizer.truncation is None


@pytest.mark.parametrize(
    "query,text",
    [
        ("", "source"),
        ("query", ""),
        ("word " * 130, "text"),
        ("query", "word " * 5000),
        ("\ud55c\uad6d\uc5b4", "source"),
    ],
)
def test_model_input_budgets(local_ranker, query, text):
    with pytest.raises(ValueError):
        local_ranker.windows(query, text)


def test_wrong_model_hash_rejected(tmp_path):
    (tmp_path / "onnx").mkdir()
    (tmp_path / "onnx/model.onnx").write_bytes(b"not a model")
    with pytest.raises(ValueError, match="weight hash"):
        OnnxRanker(tmp_path)


def metrics(ordinary=12, critical=3, regression=False):
    return {
        name: {
            "ordinary_reachable": ordinary,
            "critical_reachable": critical,
            "regressions": {"baseline": ["case"] if regression else [], "guarded_rrf": []},
        }
        for name in CANDIDATES
    }


def test_promising_is_not_adoption_or_answer_readiness():
    result = decision(metrics(), 0, 1.0)
    assert all(v["promising_development_candidate"] for v in result.values())
    assert all(
        not v["answer_diagnostic_eligible"] and not v["default_adoption"] for v in result.values()
    )


@pytest.mark.parametrize(
    "summary,failures,seconds",
    [
        (metrics(ordinary=11), 0, 1),
        (metrics(critical=2), 0, 1),
        (metrics(regression=True), 0, 1),
        (metrics(), 1, 1),
        (metrics(), 0, 10),
    ],
)
def test_frozen_thresholds(summary, failures, seconds):
    assert not any(
        v["promising_development_candidate"] for v in decision(summary, failures, seconds).values()
    )


@pytest.fixture(scope="module")
def evidence():
    from app.reference_workload.rag_bilingual_diagnostic import load_inputs
    from app.reference_workload.rag_complementary_diagnostic import load_replay

    from experiments.retrieval_research.run import PREVIOUS_HASH

    root = Path(__file__).resolve().parents[2]
    previous = load_replay(root / "artifacts/rag-complementary/2026-09-12/live.json", PREVIOUS_HASH)
    pack, bundle = load_inputs(root)
    return previous, pack, bundle.corpus


def test_public_inputs_cover_pack_without_evaluation_fields(evidence):
    previous, pack, corpus = evidence
    cases, inputs, sources = public_inputs(previous, pack, corpus)
    assert len(cases) == 48 and len(inputs) == 22
    assert sum(len(v["chunks"]) for v in inputs.values()) == 1100
    assert sources
    for payload in inputs.values():
        assert set(payload) == {"query", "chunks"}
        assert all(
            set(c) == {"chunk_id", "document_id", "title", "text"} for c in payload["chunks"]
        )


def test_label_mutation_does_not_change_scorer_inputs(evidence):
    previous, pack, corpus = evidence
    expected = public_inputs(previous, pack, corpus)[1:]
    changed = copy.deepcopy(pack)
    for case in changed.approved_cases:
        rag = (case.reference_context or {}).get("rag")
        if rag:
            rag["relevant_chunk_ids"] = ["deliberately-not-a-source"]
    assert public_inputs(previous, changed, corpus)[1:] == expected


def test_changed_public_source_is_rejected(evidence):
    previous, pack, corpus = evidence
    changed = copy.deepcopy(previous)
    row = next(r for r in changed["retrieval"]["rows"] if r["in_scope"])
    row["candidate_pool"][0]["text"] = "changed source"
    with pytest.raises(ValueError, match="source does not match"):
        public_inputs(changed, pack, corpus)


def test_fallbacks_counted_without_claiming_scoring():
    variants = {name: {"reachable": True} for name in ("baseline", "guarded_rrf", *CANDIDATES)}
    row = {
        "external_case_id": "fallback",
        "in_scope": False,
        "criticality": "critical",
        "variants": variants,
    }
    result = summarize([row])
    assert result["cross_encoder"]["all_reachable"] == 1
    assert result["cross_encoder"]["ordinary_reachable"] == 0
    assert result["cross_encoder"]["critical_reachable"] == 0
