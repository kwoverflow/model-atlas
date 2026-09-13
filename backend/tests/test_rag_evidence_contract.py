import pytest

from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    LEGACY_RAG_EVIDENCE_CONTRACT_VERSION,
    parse_rag_evidence_expectation,
)


def test_legacy_contract_becomes_one_required_group() -> None:
    expectation = parse_rag_evidence_expectation(
        {"relevant_chunk_ids": ["primary-a", "primary-b"]}
    )

    assert expectation.contract_version == LEGACY_RAG_EVIDENCE_CONTRACT_VERSION
    assert expectation.acceptable_groups == (("primary-a", "primary-b"),)
    assert expectation.match(["primary-a"]).coverage == 0.5
    assert expectation.match(["primary-a", "primary-b"]).satisfied is True


def test_any_of_contract_accepts_one_complete_alternative_group() -> None:
    expectation = parse_rag_evidence_expectation(
        {
            "evidence_contract_version": ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
            "relevant_chunk_ids": ["primary"],
            "acceptable_evidence_groups": [
                ["primary"],
                ["alternative-a", "alternative-b"],
            ],
        }
    )

    partial = expectation.match(["alternative-a"])
    complete = expectation.match(["alternative-a", "alternative-b"])

    assert expectation.acceptable_chunk_ids == (
        "primary",
        "alternative-a",
        "alternative-b",
    )
    assert partial.satisfied is False
    assert partial.coverage == 0.5
    assert complete.satisfied is True
    assert complete.group_index == 1


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "relevant_chunk_ids": ["primary"],
                "acceptable_evidence_groups": [["primary"], ["alternative"]],
            },
            "require evidence_contract_version",
        ),
        (
            {
                "evidence_contract_version": ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
                "relevant_chunk_ids": ["primary"],
                "acceptable_evidence_groups": [["alternative"], ["primary"]],
            },
            "first acceptable evidence group",
        ),
    ],
)
def test_any_of_contract_rejects_ambiguous_declarations(
    payload: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_rag_evidence_expectation(payload)
