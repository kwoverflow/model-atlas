from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

LEGACY_RAG_EVIDENCE_CONTRACT_VERSION = "rag-evidence-contract-v1"
ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION = "rag-evidence-contract-v2"


@dataclass(frozen=True)
class EvidenceContractMatch:
    satisfied: bool
    coverage: float
    group_index: int | None
    expected_chunk_ids: tuple[str, ...]
    matched_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class RagEvidenceExpectation:
    contract_version: str
    primary_chunk_ids: tuple[str, ...]
    acceptable_groups: tuple[tuple[str, ...], ...]

    @property
    def acceptable_chunk_ids(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(chunk_id for group in self.acceptable_groups for chunk_id in group)
        )

    def match(self, observed_chunk_ids: Iterable[str]) -> EvidenceContractMatch:
        observed = set(observed_chunk_ids)
        if not self.acceptable_groups:
            return EvidenceContractMatch(False, 0.0, None, (), ())

        matches: list[EvidenceContractMatch] = []
        for index, group in enumerate(self.acceptable_groups):
            matched = tuple(chunk_id for chunk_id in group if chunk_id in observed)
            coverage = len(matched) / len(group)
            matches.append(
                EvidenceContractMatch(
                    satisfied=coverage == 1.0,
                    coverage=coverage,
                    group_index=index,
                    expected_chunk_ids=group,
                    matched_chunk_ids=matched,
                )
            )
        return max(matches, key=lambda item: (item.coverage, -int(item.group_index or 0)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "primary_chunk_ids": list(self.primary_chunk_ids),
            "acceptable_evidence_groups": [list(group) for group in self.acceptable_groups],
            "acceptable_chunk_ids": list(self.acceptable_chunk_ids),
        }


def parse_rag_evidence_expectation(rag_contract: dict[str, Any]) -> RagEvidenceExpectation:
    primary = _chunk_id_list(rag_contract.get("relevant_chunk_ids"), "relevant_chunk_ids")
    if not primary:
        raise ValueError("relevant_chunk_ids must contain at least one chunk ID")

    raw_groups = rag_contract.get("acceptable_evidence_groups")
    declared_version = rag_contract.get("evidence_contract_version")
    if raw_groups is None:
        if declared_version not in {None, LEGACY_RAG_EVIDENCE_CONTRACT_VERSION}:
            raise ValueError(
                "acceptable_evidence_groups are required for rag-evidence-contract-v2"
            )
        return RagEvidenceExpectation(
            contract_version=LEGACY_RAG_EVIDENCE_CONTRACT_VERSION,
            primary_chunk_ids=primary,
            acceptable_groups=(primary,),
        )

    if declared_version != ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION:
        raise ValueError(
            "acceptable_evidence_groups require evidence_contract_version "
            "rag-evidence-contract-v2"
        )
    if not isinstance(raw_groups, list) or not raw_groups:
        raise ValueError("acceptable_evidence_groups must contain at least one group")

    groups = tuple(
        _chunk_id_list(group, f"acceptable_evidence_groups[{index}]")
        for index, group in enumerate(raw_groups)
    )
    if any(not group for group in groups):
        raise ValueError("acceptable evidence groups may not be empty")
    if len(groups) != len(set(groups)):
        raise ValueError("acceptable evidence groups must be unique")
    if groups[0] != primary:
        raise ValueError("the first acceptable evidence group must equal relevant_chunk_ids")

    return RagEvidenceExpectation(
        contract_version=ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
        primary_chunk_ids=primary,
        acceptable_groups=groups,
    )


def rag_evidence_contract_descriptor() -> dict[str, Any]:
    return {
        "contract_version": ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
        "legacy_contract_version": LEGACY_RAG_EVIDENCE_CONTRACT_VERSION,
        "semantics": "all chunks within a group; any complete group satisfies the contract",
        "input_schema_version": "reference-context-rag-v2",
        "trace_schema_version": "rag-evidence-contract-match-v1",
    }


def _chunk_id_list(value: Any, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    chunk_ids = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(chunk_ids) != len(value):
        raise ValueError(f"{field_name} must contain only non-empty strings")
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError(f"{field_name} must contain unique chunk IDs")
    return chunk_ids
