from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

RAG_BOUNDED_ANSWER_CONTRACT_VERSION = "rag-bounded-answer-contract-v1"


@dataclass(frozen=True)
class BoundedRagAnswerContract:
    contract_version: str
    strategy: str
    answer: str
    source_claim: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def compile_bounded_rag_answer(
    *,
    category: str,
    query: str,
    claims: list[str],
) -> BoundedRagAnswerContract | None:
    normalized_category = category.strip().lower()
    normalized_query = " ".join(query.split())
    normalized_claims = [" ".join(claim.split()) for claim in claims if claim.strip()]
    if not normalized_query or not normalized_claims:
        return None

    bounded_claim = normalized_claims[0][:180].strip()
    if normalized_category == "insufficient_evidence_refusal":
        bounded_query = normalized_query[:120].strip()
        answer = (
            f"저장된 비교 근거가 없거나 부족해 '{bounded_query}'를 확인하거나 "
            f"제공할 수 없습니다. 근거: {bounded_claim}"
        )
        strategy = "insufficient-evidence-refusal-v1"
    elif normalized_category == "rag_version_or_scope":
        answer = (
            f"선택된 근거가 직접 밝히는 범위: {bounded_claim} "
            "이 범위를 다른 성능, 승인, 신원 또는 운영 상태로 확대해 해석하지 않습니다."
        )
        strategy = "scope-boundary-v1"
    else:
        return None

    return BoundedRagAnswerContract(
        contract_version=RAG_BOUNDED_ANSWER_CONTRACT_VERSION,
        strategy=strategy,
        answer=answer,
        source_claim=bounded_claim,
    )


def rag_answer_contract_descriptor() -> dict[str, Any]:
    return {
        "contract_version": RAG_BOUNDED_ANSWER_CONTRACT_VERSION,
        "input_schema_version": "selected-source-claim-v1",
        "output_schema_version": "bounded-rag-answer-v1",
        "categories": ["insufficient_evidence_refusal", "rag_version_or_scope"],
        "ground_truth_inputs": [],
    }
