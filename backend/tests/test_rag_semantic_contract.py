import pytest

from app.services.rag_semantic_contract import (
    ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
    LEGACY_RAG_SEMANTIC_CONTRACT_VERSION,
    parse_rag_semantic_expectation,
)


def test_legacy_semantic_contract_maps_required_facts_to_one_group() -> None:
    expectation = parse_rag_semantic_expectation(
        {
            "must_refuse": False,
            "required_facts": ["fact-a", "fact-b"],
            "forbidden_claims": ["forbidden-a"],
        }
    )

    assert expectation.contract_version == LEGACY_RAG_SEMANTIC_CONTRACT_VERSION
    assert expectation.primary_required_facts == ("fact-a", "fact-b")
    assert expectation.acceptable_required_fact_groups == (("fact-a", "fact-b"),)


def test_any_of_semantic_contract_preserves_primary_and_alternative_groups() -> None:
    expectation = parse_rag_semantic_expectation(
        {
            "semantic_contract_version": ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
            "required_facts": ["primary-a"],
            "acceptable_required_fact_groups": [
                ["primary-a"],
                ["alternative-b"],
            ],
            "forbidden_claims": [],
        }
    )

    assert expectation.contract_version == ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION
    assert expectation.acceptable_required_fact_groups[1] == ("alternative-b",)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "semantic_contract_version": ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
            "required_facts": ["primary-a"],
        },
        {
            "semantic_contract_version": ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
            "required_facts": ["primary-a"],
            "acceptable_required_fact_groups": [["different-primary"]],
        },
        {
            "semantic_contract_version": ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
            "required_facts": ["primary-a"],
            "acceptable_required_fact_groups": [["primary-a"], ["primary-a"]],
        },
    ],
)
def test_invalid_any_of_semantic_contract_is_rejected(payload: dict) -> None:
    with pytest.raises(ValueError):
        parse_rag_semantic_expectation(payload)
