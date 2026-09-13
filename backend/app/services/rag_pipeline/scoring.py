"""Output validation, citation grounding, and semantic-contract scoring."""

from __future__ import annotations

import json
from typing import Any

from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    parse_rag_evidence_expectation,
)
from app.services.rag_semantic_contract import (
    parse_rag_semantic_expectation,
)

from .contracts import (
    FORBIDDEN_CLAIM_MATCH_THRESHOLD,
    RAG_EVALUATION_TRACE_VERSION,
    SEMANTIC_FACT_MATCH_THRESHOLD,
    RagEvaluationTrace,
    RagRetrievalTrace,
)
from .text import _contains_negation, _detect_refusal, _semantic_tokens, _tokens


def evaluate_rag_output(
    normalized_output: str,
    retrieval: RagRetrievalTrace,
    expected_output: dict[str, Any] | None = None,
    answer_contract: dict[str, Any] | None = None,
) -> RagEvaluationTrace:
    parsed: Any = None
    output_error: str | None = None
    try:
        parsed = json.loads(normalized_output)
    except (json.JSONDecodeError, TypeError):
        output_error = "output is not valid JSON"
    answer = str(parsed.get("answer") or "").strip() if isinstance(parsed, dict) else ""
    citations = _citations(parsed.get("citations")) if isinstance(parsed, dict) else []
    claims = _claims(parsed.get("claims")) if isinstance(parsed, dict) else []
    output_valid = bool(answer and citations and claims)
    if output_error is None and not output_valid:
        output_error = "output requires non-empty answer, citations, and claims"

    retrieved_by_id = {chunk.chunk_id: chunk for chunk in retrieval.retrieved_chunks}
    evidence_expectation = parse_rag_evidence_expectation(
        {
            "evidence_contract_version": retrieval.evidence_contract_version,
            "relevant_chunk_ids": retrieval.expected_relevant_chunk_ids,
            **(
                {"acceptable_evidence_groups": retrieval.acceptable_evidence_groups}
                if retrieval.evidence_contract_version == ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
                else {}
            ),
        }
    )
    acceptable_ids = set(evidence_expectation.acceptable_chunk_ids)
    invalid_citations = [citation for citation in citations if citation not in retrieved_by_id]
    correct_citations = [
        citation
        for citation in citations
        if citation in retrieved_by_id and citation in acceptable_ids
    ]
    citation_precision = len(set(correct_citations)) / len(set(citations)) if citations else 0.0
    citation_match = evidence_expectation.match(correct_citations)
    citation_recall = citation_match.coverage
    cited_texts = [
        retrieved_by_id[citation].text for citation in citations if citation in retrieved_by_id
    ]
    support_scores = [_claim_support_score(claim, cited_texts) for claim in claims]
    unsupported_count = sum(1 for score in support_scores if score < 0.6)
    unsupported_rate = unsupported_count / len(claims) if claims else 1.0
    groundedness = sum(support_scores) / len(support_scores) if support_scores else 0.0
    semantic = _evaluate_semantic_contract(
        expected_output=expected_output,
        answer=answer,
        claims=claims,
    )
    expected_answer = (
        str(answer_contract.get("answer") or "").strip()
        if isinstance(answer_contract, dict)
        else ""
    )
    answer_contract_applied = bool(expected_answer)
    answer_contract_satisfied = not answer_contract_applied or answer == expected_answer
    successful = (
        output_valid
        and retrieval.status == "success"
        and retrieval.retrieval_contract_satisfied
        and citation_precision >= 1.0
        and citation_match.satisfied
        and groundedness >= 0.8
        and unsupported_rate == 0.0
        and not invalid_citations
        and semantic["semantic_contract_satisfied"]
        and answer_contract_satisfied
    )
    return RagEvaluationTrace(
        schema_version=RAG_EVALUATION_TRACE_VERSION,
        status="success" if successful else "failed",
        successful=successful,
        output_valid=output_valid,
        output_error=output_error,
        answer=answer,
        citations=citations,
        claims=claims,
        invalid_citation_ids=sorted(set(invalid_citations)),
        correct_citation_ids=sorted(set(correct_citations)),
        citation_precision=round(citation_precision, 6),
        citation_recall=round(citation_recall, 6),
        citation_contract_satisfied=citation_match.satisfied,
        satisfied_citation_group_index=citation_match.group_index,
        groundedness_score=round(groundedness, 6),
        unsupported_claim_count=unsupported_count,
        unsupported_claim_rate=round(unsupported_rate, 6),
        claim_support_scores=[round(score, 6) for score in support_scores],
        semantic_contract_declared=semantic["semantic_contract_declared"],
        semantic_contract_version=semantic["semantic_contract_version"],
        semantic_contract_satisfied=semantic["semantic_contract_satisfied"],
        must_refuse=semantic["must_refuse"],
        refusal_detected=semantic["refusal_detected"],
        refusal_requirement_satisfied=semantic["refusal_requirement_satisfied"],
        required_facts=semantic["required_facts"],
        acceptable_required_fact_groups=semantic["acceptable_required_fact_groups"],
        required_fact_group_results=semantic["required_fact_group_results"],
        required_fact_results=semantic["required_fact_results"],
        required_fact_coverage=semantic["required_fact_coverage"],
        required_fact_contract_satisfied=semantic["required_fact_contract_satisfied"],
        matched_required_facts=semantic["matched_required_facts"],
        satisfied_required_fact_group_index=semantic["satisfied_required_fact_group_index"],
        forbidden_claims=semantic["forbidden_claims"],
        forbidden_claim_results=semantic["forbidden_claim_results"],
        forbidden_claim_violation_count=semantic["forbidden_claim_violation_count"],
        answer_contract_version=(
            str(answer_contract.get("contract_version"))
            if isinstance(answer_contract, dict) and answer_contract.get("contract_version")
            else None
        ),
        answer_contract_strategy=(
            str(answer_contract.get("strategy"))
            if isinstance(answer_contract, dict) and answer_contract.get("strategy")
            else None
        ),
        answer_contract_applied=answer_contract_applied,
        answer_contract_satisfied=answer_contract_satisfied,
        retrieval=retrieval,
    )


def _citations(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    citations: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            citations.append(item.strip())
        elif isinstance(item, dict):
            citation_id = item.get("chunk_id") or item.get("id")
            if citation_id:
                citations.append(str(citation_id))
    return citations


def _claims(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _evaluate_semantic_contract(
    *,
    expected_output: dict[str, Any] | None,
    answer: str,
    claims: list[str],
) -> dict[str, Any]:
    contract = expected_output if isinstance(expected_output, dict) else {}
    expectation = parse_rag_semantic_expectation(contract)
    must_refuse = expectation.must_refuse
    required_facts = list(expectation.primary_required_facts)
    required_groups = [list(group) for group in expectation.acceptable_required_fact_groups]
    forbidden_claims = list(expectation.forbidden_claims)
    declared = must_refuse is not None or bool(required_groups) or bool(forbidden_claims)
    candidate_texts = [text for text in [answer, *claims] if text]
    refusal_detected = _detect_refusal(candidate_texts)
    refusal_satisfied = (
        True if must_refuse is None else refusal_detected if must_refuse else not refusal_detected
    )

    required_group_results = [
        [
            _semantic_match_result(
                expectation=fact,
                candidate_texts=candidate_texts,
                threshold=SEMANTIC_FACT_MATCH_THRESHOLD,
                reject_negated=False,
            )
            for fact in group
        ]
        for group in required_groups
    ]
    required_coverages = [
        sum(1 for result in results if result["matched"]) / len(results)
        for results in required_group_results
    ]
    if required_coverages:
        best_group_index = max(
            range(len(required_coverages)),
            key=lambda index: (required_coverages[index], -index),
        )
        required_results = required_group_results[best_group_index]
        required_coverage = required_coverages[best_group_index]
        required_contract_satisfied = required_coverage == 1.0
        satisfied_group_index = best_group_index if required_contract_satisfied else None
    else:
        required_results = []
        required_coverage = 1.0
        required_contract_satisfied = True
        satisfied_group_index = None
    matched_required_facts = [
        str(result["expectation"]) for result in required_results if result["matched"]
    ]

    forbidden_results = [
        _semantic_match_result(
            expectation=claim,
            candidate_texts=candidate_texts,
            threshold=FORBIDDEN_CLAIM_MATCH_THRESHOLD,
            reject_negated=True,
        )
        for claim in forbidden_claims
    ]
    forbidden_violation_count = sum(1 for result in forbidden_results if result["matched"])
    satisfied = not declared or (
        refusal_satisfied and required_contract_satisfied and forbidden_violation_count == 0
    )
    return {
        "semantic_contract_declared": declared,
        "semantic_contract_version": expectation.contract_version,
        "semantic_contract_satisfied": satisfied,
        "must_refuse": must_refuse,
        "refusal_detected": refusal_detected,
        "refusal_requirement_satisfied": refusal_satisfied,
        "required_facts": required_facts,
        "acceptable_required_fact_groups": required_groups,
        "required_fact_group_results": required_group_results,
        "required_fact_results": required_results,
        "required_fact_coverage": round(required_coverage, 6),
        "required_fact_contract_satisfied": required_contract_satisfied,
        "matched_required_facts": matched_required_facts,
        "satisfied_required_fact_group_index": satisfied_group_index,
        "forbidden_claims": forbidden_claims,
        "forbidden_claim_results": forbidden_results,
        "forbidden_claim_violation_count": forbidden_violation_count,
    }


def _semantic_match_result(
    *,
    expectation: str,
    candidate_texts: list[str],
    threshold: float,
    reject_negated: bool,
) -> dict[str, Any]:
    best_text = ""
    best_score = 0.0
    for candidate in candidate_texts:
        score = _semantic_match_score(expectation, candidate)
        if score > best_score:
            best_text = candidate
            best_score = score
    negated = bool(best_text and _contains_negation(best_text))
    return {
        "expectation": expectation,
        "matched": best_score >= threshold and not (reject_negated and negated),
        "score": round(best_score, 6),
        "matched_text": best_text,
        "negated": negated,
        "threshold": threshold,
    }


def _semantic_match_score(expectation: str, candidate: str) -> float:
    expected_tokens = set(_semantic_tokens(expectation))
    candidate_tokens = set(_semantic_tokens(candidate))
    if not expected_tokens or not candidate_tokens:
        return 0.0
    return len(expected_tokens & candidate_tokens) / len(expected_tokens)


def _claim_support_score(claim: str, cited_texts: list[str]) -> float:
    if not cited_texts:
        return 0.0
    claim_tokens = set(_tokens(claim))
    if not claim_tokens:
        return 0.0
    scores: list[float] = []
    for text in cited_texts:
        if claim.lower() in text.lower() or text.lower() in claim.lower():
            scores.append(1.0)
            continue
        text_tokens = set(_tokens(text))
        scores.append(len(claim_tokens & text_tokens) / len(claim_tokens))
    return max(scores, default=0.0)
