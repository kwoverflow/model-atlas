from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.rag_contract_alignment import AlignmentPlan, build_alignment
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter


@pytest.fixture(scope="module")
def source():
    root = Path(__file__).resolve().parents[2]
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    revision = root / "reference_workload/revisions/1.0.4"
    bundle = build_reference_corpus(revision / "manifest.json", repository_root=root)
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=revision / "cases.jsonl",
        review_manifest_path=revision / "review_manifest.jsonl",
    )
    payload = json.loads(
        (root / "reference_workload/diagnostics/rag-contract-alignment-v1.json").read_text("utf-8")
    )
    return bundle, pack, payload


def audit(source, mutate=None):
    bundle, pack, payload = source
    changed = copy.deepcopy(payload)
    if mutate:
        mutate(changed)
    return build_alignment(AlignmentPlan.model_validate(changed), pack, bundle)


def test_source_bound_alignment_preserves_difficult_retrieval(source, monkeypatch):
    monkeypatch.setattr(
        OpenAICompatibleAdapter,
        "run_case",
        lambda *a, **k: pytest.fail("alignment must never run inference"),
    )
    report, spec = audit(source)
    assert report["summary"] == {
        "case_count": 5,
        "proposed_change_count": 4,
        "retained_source_count": 1,
        "old_reachable": 3,
        "proposed_reachable": 1,
        "exact_quote_checks": 14,
    }
    assert report["model_calls"] == report["application_database_writes"] == 0
    assert not report["human_reviewed"] and not report["gate_evidence"]
    assert report["status"] == "draft_human_review_required"
    assert all(not row["semantic_alignment_automatically_verified"] for row in report["cases"])
    assert len(spec.changes) == 4
    assert "KO-RAG-002" not in {change.external_case_id for change in spec.changes}
    for change in spec.changes:
        case = next(c for c in source[1].cases if c.external_case_id == change.external_case_id)
        assert change.retrieval_query == case.reference_context["rag"]["query"]
        assert change.top_k == case.reference_context["rag"]["top_k"]
        assert change.required_facts is None
        assert change.acceptable_required_fact_groups is None
        assert change.acceptable_evidence_groups is None


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda p: p.update(corpus_sha256="0" * 64), "corpus hash"),
        (lambda p: p["cases"].pop(), "exactly once"),
        (lambda p: p["cases"].append(copy.deepcopy(p["cases"][0])), "exactly once"),
        (lambda p: p["cases"][0].update(proposed_chunk_ids=["unknown"]), "known and unique"),
        (
            lambda p: p["cases"][0]["proposed_chunk_ids"].append(
                p["cases"][0]["proposed_chunk_ids"][0]
            ),
            "known and unique",
        ),
        (
            lambda p: p["cases"][0]["facets"][0]["support"][0].update(
                quote="fabricated source sentence"
            ),
            "quote is not exact",
        ),
        (
            lambda p: p["cases"][0]["facets"][0]["support"][0].update(chunk_id="unknown"),
            "every proposed source",
        ),
        (lambda p: p["cases"][2]["facets"].pop(), "every proposed source"),
        (
            lambda p: p["cases"][0]["facets"].append(copy.deepcopy(p["cases"][0]["facets"][0])),
            "facet IDs",
        ),
        (lambda p: p["cases"][0].update(assessment="adequate"), "adequate sources"),
        (lambda p: p["cases"][1].update(assessment="partial"), "adequate sources"),
    ],
)
def test_invalid_alignment_fails_closed(source, mutation, match):
    with pytest.raises(ValueError, match=match):
        audit(source, mutation)


@pytest.mark.parametrize("field", ["required_facts", "retrieval_query", "top_k", "human_reviewed"])
def test_plan_cannot_silently_change_other_contracts(source, field):
    with pytest.raises(ValidationError, match="Extra inputs"):
        audit(source, lambda p: p["cases"][0].update({field: "changed"}))


def test_citation_budget_is_enforced(source):
    bundle = source[0]
    extra = next(c for c in bundle.corpus.chunks if c.chunk_id == "ko-ee4c76f916f08531f6551c7d")

    def mutate(p):
        target = p["cases"][-1]
        target["proposed_chunk_ids"].append(extra.chunk_id)
        target["facets"].append(
            {
                "id": "extra",
                "description": "extra source",
                "support": [{"chunk_id": extra.chunk_id, "quote": extra.text}],
            }
        )

    with pytest.raises(ValueError, match="citation budget"):
        audit(source, mutate)


def test_multi_document_obligation_cannot_collapse(source):
    def mutate(p):
        target = p["cases"][2]
        target["proposed_chunk_ids"] = target["proposed_chunk_ids"][:1]
        target["facets"] = target["facets"][:2]

    with pytest.raises(ValueError, match="at least two"):
        audit(source, mutate)


def test_pack_and_plan_are_not_mutated(source):
    before = copy.deepcopy([case.model_dump() for case in source[1].cases])
    plan = copy.deepcopy(source[2])
    audit(source)
    assert source[2] == plan
    assert before == [case.model_dump() for case in source[1].cases]


def test_generated_revision_only_changes_four_evidence_contracts(source):
    root = Path(__file__).resolve().parents[2]
    if not (root / "reference_workload").exists():
        root = Path("/workspace")
    revision = root / "reference_workload/revisions/1.0.5"
    bundle = build_reference_corpus(revision / "manifest.json", repository_root=root)
    revised = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=revision / "cases.jsonl",
        review_manifest_path=revision / "review_manifest.jsonl",
    )
    if not (revision / "finalization_report.json").exists():
        assert revised.approved_case_count == 60
        assert revised.approved_critical_case_count == 16
        assert revised.draft_case_count == 4
        assert not revised.portfolio_ready
    changed_ids = {
        item["external_case_id"] for item in source[2]["cases"] if item["assessment"] != "adequate"
    }
    before = {case.external_case_id: case for case in source[1].cases}
    for case in revised.cases:
        old = before[case.external_case_id]
        assert case.input_payload == old.input_payload
        assert case.expected_output == old.expected_output
        assert case.criticality == old.criticality and case.weight == old.weight
        if case.external_case_id not in changed_ids:
            assert case.model_dump() == old.model_dump()
        else:
            a, b = copy.deepcopy(case.reference_context), copy.deepcopy(old.reference_context)
            for rag in (a["rag"], b["rag"]):
                rag.pop("relevant_chunk_ids")
                rag.pop("query_strategy", None)
            assert a == b
