from app.services.rag_answer_contract import (
    RAG_BOUNDED_ANSWER_CONTRACT_VERSION,
    compile_bounded_rag_answer,
)


def test_scope_answer_is_compiled_from_public_claim_without_query_echo() -> None:
    query = "development root가 외부 신원을 증명하나요?"
    claim = "Managed publisher root, development tier."

    contract = compile_bounded_rag_answer(
        category="rag_version_or_scope",
        query=query,
        claims=[claim],
    )

    assert contract is not None
    assert contract.contract_version == RAG_BOUNDED_ANSWER_CONTRACT_VERSION
    assert contract.strategy == "scope-boundary-v1"
    assert claim in contract.answer
    assert query not in contract.answer
    assert "확대해 해석하지 않습니다" in contract.answer


def test_refusal_answer_retains_bounded_query_and_claim() -> None:
    query = "현재 최고 모델을 단정해 주세요."
    claim = "비교 근거가 없으면 최고 모델을 단정할 수 없다."

    contract = compile_bounded_rag_answer(
        category="insufficient_evidence_refusal",
        query=query,
        claims=[claim],
    )

    assert contract is not None
    assert contract.strategy == "insufficient-evidence-refusal-v1"
    assert query in contract.answer
    assert claim in contract.answer


def test_answer_contract_is_not_applied_without_selected_claims() -> None:
    assert (
        compile_bounded_rag_answer(
            category="rag_version_or_scope",
            query="scope query",
            claims=[],
        )
        is None
    )
