from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.reference_workload.contracts import (
    CaseReviewContract,
    CaseReviewDecisionContract,
    ReferenceCaseContract,
)
from app.reference_workload.corpus import ReferenceCorpusBundle
from app.reference_workload.manifest import (
    canonical_json,
    default_repository_root,
    stable_hash,
)
from app.services.rag_evidence_contract import parse_rag_evidence_expectation

REQUIRED_CATEGORY_COUNTS = {
    "rag_single_document": 12,
    "rag_multi_document": 10,
    "rag_version_or_scope": 6,
    "insufficient_evidence_refusal": 8,
    "tool_single_step": 10,
    "tool_failure_recovery": 6,
    "rag_tool_combined": 6,
    "agent_multi_step": 6,
}

REQUIRED_CRITICAL_CATEGORY_COUNTS = {
    "rag_single_document": 2,
    "rag_multi_document": 3,
    "rag_version_or_scope": 3,
    "insufficient_evidence_refusal": 4,
    "tool_single_step": 2,
    "tool_failure_recovery": 2,
    "rag_tool_combined": 3,
    "agent_multi_step": 1,
}


class CasePackValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ReferenceCasePack:
    cases: tuple[ReferenceCaseContract, ...]
    case_hashes: dict[str, str]
    category_counts: dict[str, int]
    critical_category_counts: dict[str, int]
    approved_case_count: int
    approved_critical_case_count: int
    draft_case_count: int
    rejected_case_count: int
    portfolio_ready: bool
    checks: tuple[dict[str, Any], ...]
    shortfalls: tuple[str, ...]

    @property
    def approved_cases(self) -> tuple[ReferenceCaseContract, ...]:
        return tuple(case for case in self.cases if case.review.status == "approved")

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": "model-atlas-reference-case-pack-summary-v1",
            "case_count": len(self.cases),
            "approved_case_count": self.approved_case_count,
            "approved_critical_case_count": self.approved_critical_case_count,
            "draft_case_count": self.draft_case_count,
            "rejected_case_count": self.rejected_case_count,
            "category_counts": self.category_counts,
            "critical_category_counts": self.critical_category_counts,
            "portfolio_ready": self.portfolio_ready,
            "checks": list(self.checks),
            "shortfalls": list(self.shortfalls),
        }


def default_cases_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or default_repository_root()).resolve()
    return root / "reference_workload" / "cases.jsonl"


def default_review_manifest_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or default_repository_root()).resolve()
    return root / "reference_workload" / "review_manifest.jsonl"


def reference_case_hash(case: ReferenceCaseContract) -> str:
    payload = case.model_dump(mode="json", exclude={"review"})
    return stable_hash(payload)


def _load_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise CasePackValidationError(f"reference JSONL file is missing: {path}") from exc
    except UnicodeDecodeError as exc:
        raise CasePackValidationError(f"reference JSONL file must be UTF-8: {path}") from exc
    records: list[tuple[int, dict[str, Any]]] = []
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise CasePackValidationError(
                f"invalid JSON at {path}:{line_number}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise CasePackValidationError(f"JSONL record must be an object at {path}:{line_number}")
        records.append((line_number, payload))
    return records


def load_case_contracts(path: Path) -> tuple[ReferenceCaseContract, ...]:
    cases: list[ReferenceCaseContract] = []
    for line_number, payload in _load_jsonl(path):
        try:
            cases.append(ReferenceCaseContract.model_validate(payload))
        except ValidationError as exc:
            raise CasePackValidationError(
                f"invalid reference case at {path}:{line_number}: {exc}"
            ) from exc
    identifiers = [case.external_case_id for case in cases]
    duplicates = sorted(
        identifier for identifier, count in Counter(identifiers).items() if count > 1
    )
    if duplicates:
        raise CasePackValidationError(f"duplicate reference case IDs: {', '.join(duplicates)}")
    return tuple(cases)


def load_review_decisions(path: Path) -> tuple[CaseReviewDecisionContract, ...]:
    decisions: list[CaseReviewDecisionContract] = []
    for line_number, payload in _load_jsonl(path):
        try:
            decisions.append(CaseReviewDecisionContract.model_validate(payload))
        except ValidationError as exc:
            raise CasePackValidationError(
                f"invalid case review at {path}:{line_number}: {exc}"
            ) from exc
    identifiers = [decision.external_case_id for decision in decisions]
    duplicates = sorted(
        identifier for identifier, count in Counter(identifiers).items() if count > 1
    )
    if duplicates:
        raise CasePackValidationError(f"duplicate case review IDs: {', '.join(duplicates)}")
    return tuple(decisions)


def _apply_review_decisions(
    cases: tuple[ReferenceCaseContract, ...],
    decisions: tuple[CaseReviewDecisionContract, ...],
) -> tuple[ReferenceCaseContract, ...]:
    case_map = {case.external_case_id: case for case in cases}
    unknown = sorted(
        decision.external_case_id
        for decision in decisions
        if decision.external_case_id not in case_map
    )
    if unknown:
        raise CasePackValidationError(f"reviews reference unknown case IDs: {', '.join(unknown)}")
    decision_map = {decision.external_case_id: decision for decision in decisions}
    reviewed: list[ReferenceCaseContract] = []
    for case in cases:
        decision = decision_map.get(case.external_case_id)
        if decision is None:
            reviewed.append(case)
            continue
        observed_hash = reference_case_hash(case)
        if decision.case_sha256 != observed_hash:
            raise CasePackValidationError(
                f"review hash mismatch for {case.external_case_id}: "
                f"expected {decision.case_sha256}, observed {observed_hash}"
            )
        review = CaseReviewContract(
            status=decision.decision,
            reviewer=decision.reviewer,
            reviewed_at=decision.reviewed_at,
            notes=decision.notes,
        )
        reviewed.append(case.model_copy(update={"review": review}))
    return tuple(reviewed)


def validate_case_pack(
    cases: tuple[ReferenceCaseContract, ...],
    *,
    corpus_bundle: ReferenceCorpusBundle,
) -> ReferenceCasePack:
    known_chunk_ids = {chunk.chunk_id for chunk in corpus_bundle.corpus.chunks}
    for case in cases:
        reference = case.reference_context or {}
        rag = reference.get("rag")
        if not isinstance(rag, dict):
            continue
        try:
            expectation = parse_rag_evidence_expectation(rag)
        except ValueError as exc:
            raise CasePackValidationError(
                f"case {case.external_case_id} has an invalid RAG evidence contract: {exc}"
            ) from exc
        requested_ids = list(expectation.acceptable_chunk_ids)
        missing = sorted(set(requested_ids) - known_chunk_ids)
        if missing:
            raise CasePackValidationError(
                f"case {case.external_case_id} references unknown chunks: {', '.join(missing)}"
            )
        if rag.get("corpus_id") != corpus_bundle.corpus.corpus_id:
            raise CasePackValidationError(
                f"case {case.external_case_id} references a different corpus ID"
            )
        if rag.get("corpus_version") != corpus_bundle.corpus.corpus_version:
            raise CasePackValidationError(
                f"case {case.external_case_id} references a different corpus version"
            )

    category_counts = dict(Counter(case.category for case in cases))
    critical_counts = dict(
        Counter(case.category for case in cases if case.criticality == "critical")
    )
    approved = [case for case in cases if case.review.status == "approved"]
    approved_critical = [case for case in approved if case.criticality == "critical"]
    approved_category_counts = Counter(case.category for case in approved)
    approved_critical_counts = Counter(
        case.category for case in approved if case.criticality == "critical"
    )

    checks: list[dict[str, Any]] = []
    shortfalls: list[str] = []

    def add_check(check_id: str, passed: bool, observed: Any, required: Any) -> None:
        checks.append(
            {
                "check_id": check_id,
                "passed": passed,
                "observed": observed,
                "required": required,
            }
        )
        if not passed:
            shortfalls.append(f"{check_id}: observed {observed}, required {required}")

    minimum_active = corpus_bundle.manifest.contract.minimum_active_cases
    minimum_critical = corpus_bundle.manifest.contract.minimum_critical_cases
    add_check(
        "approved_active_cases", len(approved) >= minimum_active, len(approved), minimum_active
    )
    add_check(
        "approved_critical_cases",
        len(approved_critical) >= minimum_critical,
        len(approved_critical),
        minimum_critical,
    )
    for category, minimum in REQUIRED_CATEGORY_COUNTS.items():
        add_check(
            f"approved_category:{category}",
            approved_category_counts[category] >= minimum,
            approved_category_counts[category],
            minimum,
        )
    for category, minimum in REQUIRED_CRITICAL_CATEGORY_COUNTS.items():
        add_check(
            f"approved_critical_category:{category}",
            approved_critical_counts[category] >= minimum,
            approved_critical_counts[category],
            minimum,
        )

    return ReferenceCasePack(
        cases=cases,
        case_hashes={case.external_case_id: reference_case_hash(case) for case in cases},
        category_counts=category_counts,
        critical_category_counts=critical_counts,
        approved_case_count=len(approved),
        approved_critical_case_count=len(approved_critical),
        draft_case_count=sum(1 for case in cases if case.review.status == "draft"),
        rejected_case_count=sum(1 for case in cases if case.review.status == "rejected"),
        portfolio_ready=all(bool(check["passed"]) for check in checks),
        checks=tuple(checks),
        shortfalls=tuple(shortfalls),
    )


def load_reference_case_pack(
    *,
    corpus_bundle: ReferenceCorpusBundle,
    cases_path: Path | None = None,
    review_manifest_path: Path | None = None,
) -> ReferenceCasePack:
    root = corpus_bundle.manifest.repository_root
    resolved_cases = (cases_path or default_cases_path(root)).resolve()
    resolved_reviews = (review_manifest_path or default_review_manifest_path(root)).resolve()
    cases = load_case_contracts(resolved_cases)
    decisions = load_review_decisions(resolved_reviews)
    reviewed_cases = _apply_review_decisions(cases, decisions)
    return validate_case_pack(reviewed_cases, corpus_bundle=corpus_bundle)


def serialize_case(case: ReferenceCaseContract) -> str:
    return canonical_json(case.model_dump(mode="json"))


def write_review_worksheet(
    output_path: Path,
    *,
    case_pack: ReferenceCasePack,
    corpus_bundle: ReferenceCorpusBundle,
) -> None:
    chunk_sources = {chunk.chunk_id: chunk.document_id for chunk in corpus_bundle.corpus.chunks}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "external_case_id",
                "category",
                "criticality",
                "title",
                "query_or_request",
                "source_paths",
                "expected_contract_json",
                "case_sha256",
                "decision",
                "reviewer",
                "reviewed_at",
                "notes",
            ],
        )
        writer.writeheader()
        for case in case_pack.cases:
            reference = case.reference_context or {}
            rag = reference.get("rag") if isinstance(reference.get("rag"), dict) else {}
            relevant_ids = (
                list(parse_rag_evidence_expectation(rag).acceptable_chunk_ids) if rag else []
            )
            source_paths = sorted(
                {
                    chunk_sources[str(chunk_id)]
                    for chunk_id in relevant_ids
                    if str(chunk_id) in chunk_sources
                }
            )
            query = next(
                (
                    str(case.input_payload[key])
                    for key in ("query", "request", "question")
                    if case.input_payload.get(key)
                ),
                "",
            )
            writer.writerow(
                {
                    "external_case_id": case.external_case_id,
                    "category": case.category,
                    "criticality": case.criticality,
                    "title": case.title,
                    "query_or_request": query,
                    "source_paths": " | ".join(source_paths),
                    "expected_contract_json": canonical_json(
                        {
                            "expected_output": case.expected_output,
                            "expected_tool_schema": case.expected_tool_schema,
                            "agent": reference.get("agent"),
                        }
                    ),
                    "case_sha256": case_pack.case_hashes[case.external_case_id],
                    "decision": "",
                    "reviewer": "",
                    "reviewed_at": "",
                    "notes": "",
                }
            )
    temporary_path.replace(output_path)
