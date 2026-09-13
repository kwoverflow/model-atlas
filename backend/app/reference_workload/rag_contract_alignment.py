"""Build a source-bound review draft without changing questions or scoring contracts."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.reference_workload.case_revision import (
    CASE_REVISION_SPEC_VERSION,
    CasePackRevisionSpec,
    create_case_pack_revision,
)
from app.reference_workload.case_revision_review import write_case_revision_review_html
from app.reference_workload.cases import load_reference_case_pack
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import default_repository_root, file_sha256, stable_hash
from app.services.inference_adapters.cited_rag import ORDINARY_RAG_CATEGORIES
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter
from app.services.rag_evaluation import retrieve
from app.services.rag_evidence_contract import parse_rag_evidence_expectation


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SupportQuote(StrictModel):
    chunk_id: str = Field(min_length=1)
    quote: str = Field(min_length=12)


class QuestionFacet(StrictModel):
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    support: list[SupportQuote] = Field(min_length=1)


class AlignmentCase(StrictModel):
    external_case_id: str = Field(min_length=1)
    assessment: Literal["adequate", "partial", "indirect"]
    reason: str = Field(min_length=1, max_length=2000)
    proposed_chunk_ids: list[str] = Field(min_length=1)
    facets: list[QuestionFacet] = Field(min_length=1)


class AlignmentPlan(StrictModel):
    schema_version: Literal["rag-contract-alignment-plan-v1"]
    source_workload_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    revision_id: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    source_cases_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: list[AlignmentCase] = Field(min_length=1, max_length=20)


def build_alignment(plan, pack, bundle):
    if bundle.corpus.corpus_hash != plan.corpus_sha256:
        raise ValueError("source corpus hash mismatch")
    targets = {
        case.external_case_id: case
        for case in pack.approved_cases
        if case.category in ORDINARY_RAG_CATEGORIES and case.criticality == "critical"
    }
    ids = [case.external_case_id for case in plan.cases]
    if len(ids) != len(set(ids)) or set(ids) != set(targets):
        raise ValueError("plan must cover each ordinary critical RAG case exactly once")
    chunks = {chunk.chunk_id: chunk for chunk in bundle.corpus.chunks}
    rows, changes = [], []
    for item in plan.cases:
        case = targets[item.external_case_id]
        rag = case.reference_context["rag"]
        old = parse_rag_evidence_expectation(rag)
        proposed = item.proposed_chunk_ids
        if len(set(proposed)) != len(proposed) or not set(proposed) <= chunks.keys():
            raise ValueError("proposed source IDs must be known and unique")
        facet_ids = [facet.id for facet in item.facets]
        if len(set(facet_ids)) != len(facet_ids):
            raise ValueError("question facet IDs must be unique within a case")
        supports = [support for facet in item.facets for support in facet.support]
        if {support.chunk_id for support in supports} != set(proposed):
            raise ValueError("every proposed source must support a facet; no extra sources")
        for support in supports:
            if support.quote not in chunks[support.chunk_id].text:
                raise ValueError(f"support quote is not exact: {item.external_case_id}")
        if (
            case.category == "rag_multi_document"
            and len({chunks[chunk_id].document_id for chunk_id in proposed}) < 2
        ):
            raise ValueError("multi-document cases must retain at least two source documents")
        public = SimpleNamespace(
            category=case.category,
            input_payload_json={
                "rag_context": {
                    "retrieved_chunks": [chunks[chunk_id].to_dict() for chunk_id in proposed]
                }
            },
        )
        schema = OpenAICompatibleAdapter()._response_format(public)
        budget = schema["json_schema"]["schema"]["properties"]["citations"]["maxItems"]
        if len(proposed) > budget:
            raise ValueError("proposed AND evidence exceeds the default citation budget")
        query = rag["query"]
        top_k = rag["top_k"]
        if rag["minimum_score"] != 0:
            raise ValueError("alignment audit currently requires minimum_score=0")
        ranking = retrieve(
            corpus=bundle.corpus,
            query=query,
            relevant_chunk_ids=proposed,
            top_k=len(chunks),
            min_score=0.0,
        )
        ranked = {chunk.chunk_id: chunk for chunk in ranking.retrieved_chunks}
        top_ids = {chunk.chunk_id for chunk in ranking.retrieved_chunks[:top_k]}
        changed = old.acceptable_groups != (tuple(proposed),)
        if (item.assessment == "adequate") == changed:
            raise ValueError("adequate sources must be retained; deficiencies need a change")

        def evidence(chunk_id, ranking=ranked):
            return {
                **chunks[chunk_id].to_dict(),
                "text_sha256": stable_hash(chunks[chunk_id].text),
                "rank": ranking[chunk_id].rank,
                "score": ranking[chunk_id].score,
            }

        rows.append(
            {
                **item.model_dump(mode="json"),
                "severity": "high" if changed else "informational",
                "assessment_origin": "assistant_authored_not_human_reviewed",
                "semantic_alignment_automatically_verified": False,
                "question": case.input_payload["query"],
                "retrieval_query": query,
                "source_case_sha256": pack.case_hashes[case.external_case_id],
                "required_output_unchanged": case.expected_output,
                "top_k": top_k,
                "maximum_citations": budget,
                "proposed_change": changed,
                "old_reachable": old.match(top_ids).satisfied,
                "proposed_reachable": set(proposed) <= top_ids,
                "old_evidence": [evidence(i) for i in old.acceptable_chunk_ids],
                "proposed_evidence": [evidence(i) for i in proposed],
                "exact_quote_checks": len(supports),
            }
        )
        if changed:
            first = chunks[proposed[0]]
            changes.append(
                {
                    "external_case_id": item.external_case_id,
                    "retrieval_query": query,
                    "relevant_chunk_ids": proposed,
                    "top_k": top_k,
                    "expected_source_path": first.document_id,
                    "expected_heading": first.title,
                    "rationale": item.reason,
                }
            )
    spec = CasePackRevisionSpec.model_validate(
        {
            "schema_version": CASE_REVISION_SPEC_VERSION,
            "revision_id": plan.revision_id,
            "source_workload_version": plan.source_workload_version,
            "query_strategy": "source-alignment-query-unchanged-v1",
            "changes": changes,
        }
    )
    report = {
        "schema_version": "rag-contract-alignment-audit-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "draft_human_review_required",
        "gate_evidence": False,
        "human_reviewed": False,
        "model_calls": 0,
        "application_database_writes": 0,
        "production_readiness": "not_production_ready",
        "corpus": bundle.corpus.summary(),
        "source_cases_sha256": plan.source_cases_sha256,
        "source_workload_version": plan.source_workload_version,
        "revision_id": plan.revision_id,
        "summary": {
            "case_count": len(rows),
            "proposed_change_count": len(changes),
            "retained_source_count": len(rows) - len(changes),
            "old_reachable": sum(row["old_reachable"] for row in rows),
            "proposed_reachable": sum(row["proposed_reachable"] for row in rows),
            "exact_quote_checks": sum(row["exact_quote_checks"] for row in rows),
        },
        "preserved": [
            "question",
            "retrieval_query",
            "top_k",
            "required_facts",
            "forbidden_claims",
            "must_refuse",
            "criticality",
            "weight",
        ],
        "limitations": [
            "Exact quote checks verify source integrity, not semantic entailment or approval.",
            "Facets and alignment assessments are assistant-authored review proposals.",
            "These five known critical cases are not a random sample or a new model evaluation.",
            "Reachability is a diagnostic, never a reason to weaken expected evidence.",
            "Existing keyword semantic scoring and sparse required facts are unchanged.",
        ],
        "cases": rows,
    }
    return report, spec


def _write_json(path, payload):
    with path.open("x", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
        target.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=default_repository_root())
    parser.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    plan = AlignmentPlan.model_validate_json(args.plan.read_text("utf-8"))
    source = root / "reference_workload/revisions" / plan.source_workload_version
    output = root / "reference_workload/revisions" / plan.revision_id
    if output.exists():
        parser.error("revision output already exists; never overwrite a review draft")
    source_hashes = {p.name: file_sha256(p) for p in source.iterdir() if p.is_file()}
    if source_hashes["cases.jsonl"] != plan.source_cases_sha256:
        raise ValueError("source cases hash mismatch")
    bundle = build_reference_corpus(source / "manifest.json", repository_root=root)
    pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=source / "cases.jsonl",
        review_manifest_path=source / "review_manifest.jsonl",
    )
    report, spec = build_alignment(plan, pack, bundle)
    output.mkdir(parents=True)
    spec_path = output / "revision_spec.json"
    _write_json(spec_path, spec.model_dump(mode="json", exclude_none=True))
    revision = create_case_pack_revision(
        repository_root=root, spec_path=spec_path, output_directory=output
    )
    write_case_revision_review_html(
        output / "revision_report.json", output / "revision_review.html"
    )
    report.update(
        revision_report_sha256=revision["report_sha256"],
        revision_summary=revision["summary"],
        plan_sha256=file_sha256(args.plan),
        implementation_sha256=file_sha256(Path(__file__)),
        source_files_unchanged=source_hashes
        == {p.name: file_sha256(p) for p in source.iterdir() if p.is_file()},
    )
    if not report["source_files_unchanged"]:
        raise ValueError("source revision changed during draft generation")
    report["content_sha256"] = stable_hash(report)
    _write_json(output / "source_alignment_audit.json", report)
    print(
        json.dumps(
            {"output": str(output), "summary": report["summary"], "revision": revision["summary"]}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
