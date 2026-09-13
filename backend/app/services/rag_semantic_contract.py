from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LEGACY_RAG_SEMANTIC_CONTRACT_VERSION = "rag-semantic-contract-v1"
ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION = "rag-semantic-contract-v2"


@dataclass(frozen=True)
class RagSemanticExpectation:
    contract_version: str
    must_refuse: bool | None
    primary_required_facts: tuple[str, ...]
    acceptable_required_fact_groups: tuple[tuple[str, ...], ...]
    forbidden_claims: tuple[str, ...]


def _string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    normalized = tuple(item.strip() for item in value)
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{field_name} must be unique")
    return normalized


def parse_rag_semantic_expectation(payload: dict[str, Any]) -> RagSemanticExpectation:
    required_facts = _string_tuple(payload.get("required_facts"), field_name="required_facts")
    forbidden_claims = _string_tuple(
        payload.get("forbidden_claims"),
        field_name="forbidden_claims",
    )
    must_refuse_value = payload.get("must_refuse")
    must_refuse = must_refuse_value if isinstance(must_refuse_value, bool) else None
    declared_version = payload.get("semantic_contract_version")
    groups_payload = payload.get("acceptable_required_fact_groups")

    if groups_payload is None:
        if declared_version not in {None, LEGACY_RAG_SEMANTIC_CONTRACT_VERSION}:
            raise ValueError(
                "acceptable_required_fact_groups are required for rag-semantic-contract-v2"
            )
        groups = (required_facts,) if required_facts else ()
        return RagSemanticExpectation(
            contract_version=LEGACY_RAG_SEMANTIC_CONTRACT_VERSION,
            must_refuse=must_refuse,
            primary_required_facts=required_facts,
            acceptable_required_fact_groups=groups,
            forbidden_claims=forbidden_claims,
        )

    if declared_version != ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION:
        raise ValueError(
            "acceptable_required_fact_groups require semantic_contract_version "
            "rag-semantic-contract-v2"
        )
    if not required_facts:
        raise ValueError("rag-semantic-contract-v2 requires primary required_facts")
    if not isinstance(groups_payload, list) or not groups_payload:
        raise ValueError("acceptable_required_fact_groups must be a non-empty list")

    groups = tuple(
        _string_tuple(group, field_name="acceptable_required_fact_groups item")
        for group in groups_payload
    )
    if any(not group for group in groups):
        raise ValueError("acceptable required-fact groups may not be empty")
    if groups[0] != required_facts:
        raise ValueError("the first acceptable required-fact group must equal required_facts")
    if len(groups) != len(set(groups)):
        raise ValueError("acceptable required-fact groups must be unique")
    return RagSemanticExpectation(
        contract_version=ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
        must_refuse=must_refuse,
        primary_required_facts=required_facts,
        acceptable_required_fact_groups=groups,
        forbidden_claims=forbidden_claims,
    )


def rag_semantic_contract_descriptor() -> dict[str, Any]:
    return {
        "contract_version": ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
        "legacy_contract_version": LEGACY_RAG_SEMANTIC_CONTRACT_VERSION,
        "input_schema_version": "reference-expected-output-v2",
        "trace_schema_version": "rag-semantic-contract-match-v1",
        "semantics": "all facts within a group; any complete group satisfies required facts",
    }
