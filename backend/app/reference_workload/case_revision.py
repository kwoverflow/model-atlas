from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.reference_workload.cases import (
    default_cases_path,
    default_review_manifest_path,
    load_case_contracts,
    load_reference_case_pack,
    load_review_decisions,
    reference_case_hash,
    serialize_case,
)
from app.reference_workload.contract_audit import (
    build_retrieval_contract_audit,
    write_retrieval_contract_audit,
)
from app.reference_workload.contracts import ReferenceCaseContract
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.manifest import (
    canonical_json,
    default_manifest_path,
    file_sha256,
    stable_hash,
)
from app.services.rag_evaluation import retrieve
from app.services.rag_evidence_contract import (
    ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
    parse_rag_evidence_expectation,
)
from app.services.rag_semantic_contract import (
    ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
    parse_rag_semantic_expectation,
)

LEGACY_CASE_REVISION_SPEC_VERSION = "model-atlas-reference-case-pack-revision-spec-v1"
EVIDENCE_CASE_REVISION_SPEC_VERSION = "model-atlas-reference-case-pack-revision-spec-v2"
CASE_REVISION_SPEC_VERSION = "model-atlas-reference-case-pack-revision-spec-v3"
LEGACY_CASE_REVISION_REPORT_VERSION = "model-atlas-reference-case-pack-revision-report-v1"
EVIDENCE_CASE_REVISION_REPORT_VERSION = "model-atlas-reference-case-pack-revision-report-v2"
CASE_REVISION_REPORT_VERSION = "model-atlas-reference-case-pack-revision-report-v3"
_CASE_REVISION_FINALIZATION_VERSION = (
    "model-atlas-reference-case-pack-revision-finalization-v1"
)


class CasePackRevisionError(ValueError):
    pass


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseRevisionChange(_StrictModel):
    external_case_id: str = Field(pattern=r"^KO-[A-Z0-9-]+-\d{3}$")
    retrieval_query: str = Field(min_length=1, max_length=1000)
    relevant_chunk_ids: list[str] = Field(min_length=1)
    acceptable_evidence_groups: list[list[str]] | None = None
    required_facts: list[str] | None = None
    acceptable_required_fact_groups: list[list[str]] | None = None
    top_k: int = Field(ge=1, le=10)
    expected_source_path: str = Field(min_length=1, max_length=500)
    expected_heading: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=2000)

    @field_validator("relevant_chunk_ids")
    @classmethod
    def validate_unique_chunk_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("relevant_chunk_ids must be unique")
        return value

    @model_validator(mode="after")
    def validate_acceptable_evidence_groups(self) -> CaseRevisionChange:
        if self.acceptable_evidence_groups is None:
            return self
        try:
            parse_rag_evidence_expectation(
                {
                    "evidence_contract_version": ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
                    "relevant_chunk_ids": self.relevant_chunk_ids,
                    "acceptable_evidence_groups": self.acceptable_evidence_groups,
                }
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self

    @model_validator(mode="after")
    def validate_acceptable_required_fact_groups(self) -> CaseRevisionChange:
        semantic_values = (
            self.required_facts,
            self.acceptable_required_fact_groups,
        )
        if all(value is None for value in semantic_values):
            return self
        if any(value is None for value in semantic_values):
            raise ValueError(
                "required_facts and acceptable_required_fact_groups must be provided together"
            )
        try:
            parse_rag_semantic_expectation(
                {
                    "semantic_contract_version": ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
                    "required_facts": self.required_facts,
                    "acceptable_required_fact_groups": (
                        self.acceptable_required_fact_groups
                    ),
                }
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self


class CasePackRevisionSpec(_StrictModel):
    schema_version: str
    revision_id: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    source_workload_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    query_strategy: str = Field(pattern=r"^[a-z0-9-]+-v\d+$")
    changes: list[CaseRevisionChange] = Field(min_length=1, max_length=20)

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value not in {
            LEGACY_CASE_REVISION_SPEC_VERSION,
            EVIDENCE_CASE_REVISION_SPEC_VERSION,
            CASE_REVISION_SPEC_VERSION,
        }:
            raise ValueError(f"unsupported revision spec version: {value}")
        return value

    @model_validator(mode="after")
    def validate_versioned_features(self) -> CasePackRevisionSpec:
        if self.schema_version == LEGACY_CASE_REVISION_SPEC_VERSION and any(
            change.acceptable_evidence_groups is not None for change in self.changes
        ):
            raise ValueError(
                "acceptable_evidence_groups require case-pack revision spec v2"
            )
        if self.schema_version != CASE_REVISION_SPEC_VERSION and any(
            change.acceptable_required_fact_groups is not None for change in self.changes
        ):
            raise ValueError(
                "acceptable_required_fact_groups require case-pack revision spec v3"
            )
        return self

    @field_validator("changes")
    @classmethod
    def validate_unique_case_ids(
        cls,
        value: list[CaseRevisionChange],
    ) -> list[CaseRevisionChange]:
        identifiers = [change.external_case_id for change in value]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("revision case IDs must be unique")
        return value


def load_case_pack_revision_spec(path: Path) -> CasePackRevisionSpec:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CasePackRevisionSpec.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise CasePackRevisionError(f"case-pack revision spec is invalid: {exc}") from exc


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CasePackRevisionError(f"{label} is invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise CasePackRevisionError(f"{label} must contain a JSON object")
    return payload


def _resolve_revision_source(
    *,
    root: Path,
    canonical_directory: Path,
    spec: CasePackRevisionSpec,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    canonical_manifest = default_manifest_path(root)
    canonical_payload = _load_json_object(
        canonical_manifest,
        label="canonical reference manifest",
    )
    if canonical_payload.get("workload_version") == spec.source_workload_version:
        return (
            canonical_manifest,
            default_cases_path(root),
            default_review_manifest_path(root),
            {
                "kind": "canonical",
                "directory": "reference_workload",
                "finalization_report_sha256": None,
            },
        )

    source_directory = (
        canonical_directory / "revisions" / spec.source_workload_version
    ).resolve()
    if not source_directory.is_relative_to(canonical_directory):
        raise CasePackRevisionError("revision source must remain under reference_workload")
    source_manifest = source_directory / "manifest.json"
    source_cases = source_directory / "cases.jsonl"
    source_reviews = source_directory / "review_manifest.jsonl"
    source_report_path = source_directory / "revision_report.json"
    finalization_path = source_directory / "finalization_report.json"
    source_payload = _load_json_object(
        source_manifest,
        label="source revision manifest",
    )
    if source_payload.get("workload_version") != spec.source_workload_version:
        raise CasePackRevisionError("source revision manifest version does not match the spec")

    source_report = _load_json_object(
        source_report_path,
        label="source revision report",
    )
    observed_source_report_hash = stable_hash(
        {
            key: value
            for key, value in source_report.items()
            if key not in {"generated_at", "report_sha256"}
        }
    )
    if (
        source_report.get("revision_id") != spec.source_workload_version
        or source_report.get("report_sha256") != observed_source_report_hash
    ):
        raise CasePackRevisionError("source revision report identity does not match")

    finalization = _load_json_object(
        finalization_path,
        label="source revision finalization report",
    )
    observed_finalization_hash = stable_hash(
        {key: value for key, value in finalization.items() if key != "report_sha256"}
    )
    if (
        finalization.get("schema_version") != _CASE_REVISION_FINALIZATION_VERSION
        or finalization.get("revision_id") != spec.source_workload_version
        or finalization.get("revision_report_sha256") != source_report["report_sha256"]
        or finalization.get("report_sha256") != observed_finalization_hash
        or not bool((finalization.get("case_pack") or {}).get("portfolio_ready"))
    ):
        raise CasePackRevisionError("source revision is not validly finalized")

    source_identity = source_report.get("artifact_identity")
    if not isinstance(source_identity, dict):
        raise CasePackRevisionError("source revision artifact identity is missing")
    expected_hashes = {
        source_manifest: source_identity.get("manifest_sha256"),
        source_cases: source_identity.get("cases_sha256"),
        source_reviews: finalization.get("review_manifest_sha256"),
    }
    for path, expected_hash in expected_hashes.items():
        if not isinstance(expected_hash, str) or file_sha256(path) != expected_hash:
            raise CasePackRevisionError(
                f"finalized source revision artifact changed: {path.name}"
            )
    return (
        source_manifest,
        source_cases,
        source_reviews,
        {
            "kind": "finalized_revision",
            "directory": source_directory.relative_to(root).as_posix(),
            "revision_report_sha256": source_report["report_sha256"],
            "finalization_report_sha256": finalization["report_sha256"],
        },
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _chunk_evidence(chunk: Any) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "source_path": chunk.document_id,
        "heading": chunk.title,
        "chunk_sha256": chunk.metadata.get("chunk_sha256"),
        "excerpt": " ".join(chunk.text.split())[:500],
    }


def _expected_ranks(
    *,
    corpus: Any,
    query: str,
    expected_chunk_ids: list[str],
) -> dict[str, int | None]:
    trace = retrieve(
        corpus=corpus,
        query=query,
        relevant_chunk_ids=expected_chunk_ids,
        top_k=len(corpus.chunks),
        min_score=0.0,
    )
    return {
        chunk_id: next(
            (chunk.rank for chunk in trace.retrieved_chunks if chunk.chunk_id == chunk_id),
            None,
        )
        for chunk_id in expected_chunk_ids
    }


def _revise_case(
    case: ReferenceCaseContract,
    change: CaseRevisionChange,
    *,
    query_strategy: str,
) -> ReferenceCaseContract:
    payload = case.model_dump(mode="json")
    reference = deepcopy(payload.get("reference_context") or {})
    rag = reference.get("rag")
    agent = reference.get("agent")
    if not isinstance(rag, dict):
        raise CasePackRevisionError(
            f"revision case {case.external_case_id} requires a RAG contract"
        )
    rag.update(
        {
            "query": change.retrieval_query,
            "query_strategy": query_strategy,
            "relevant_chunk_ids": list(change.relevant_chunk_ids),
            "top_k": change.top_k,
        }
    )
    if change.acceptable_evidence_groups is not None:
        rag.update(
            {
                "evidence_contract_version": ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
                "acceptable_evidence_groups": deepcopy(change.acceptable_evidence_groups),
            }
        )
    else:
        rag.pop("evidence_contract_version", None)
        rag.pop("acceptable_evidence_groups", None)
    reference["rag"] = rag
    if agent is not None:
        if not isinstance(agent, dict):
            raise CasePackRevisionError(
                f"revision case {case.external_case_id} has an invalid Agent contract"
            )
        expected_steps = agent.get("expected_steps")
        if not isinstance(expected_steps, list):
            raise CasePackRevisionError(
                f"revision case {case.external_case_id} has no Agent expected_steps"
            )
        revised_steps = deepcopy(expected_steps)
        retrieval_steps = [
            step
            for step in revised_steps
            if isinstance(step, dict) and step.get("action") == "retrieve"
        ]
        if len(retrieval_steps) != 1:
            raise CasePackRevisionError(
                f"revision case {case.external_case_id} must have exactly one retrieval step"
            )
        retrieval_steps[0]["relevant_chunk_ids"] = list(change.relevant_chunk_ids)
        if change.acceptable_evidence_groups is not None:
            retrieval_steps[0]["evidence_contract_version"] = (
                ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION
            )
            retrieval_steps[0]["acceptable_evidence_groups"] = deepcopy(
                change.acceptable_evidence_groups
            )
        else:
            retrieval_steps[0].pop("evidence_contract_version", None)
            retrieval_steps[0].pop("acceptable_evidence_groups", None)
        agent["expected_steps"] = revised_steps
        reference["agent"] = agent
    payload["reference_context"] = reference
    if change.acceptable_required_fact_groups is not None:
        expected_output = deepcopy(payload.get("expected_output") or {})
        expected_output.update(
            {
                "semantic_contract_version": ANY_OF_RAG_SEMANTIC_CONTRACT_VERSION,
                "required_facts": list(change.required_facts or []),
                "acceptable_required_fact_groups": deepcopy(
                    change.acceptable_required_fact_groups
                ),
            }
        )
        payload["expected_output"] = expected_output
    return ReferenceCaseContract.model_validate(payload)


def create_case_pack_revision(
    *,
    repository_root: Path,
    spec_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    root = repository_root.resolve()
    output = output_directory.resolve()
    canonical_directory = (root / "reference_workload").resolve()
    if output == canonical_directory:
        raise CasePackRevisionError("revision output cannot replace the canonical case pack")
    if not output.is_relative_to(canonical_directory):
        raise CasePackRevisionError("revision output must remain under reference_workload")
    if (output / "finalization_report.json").exists():
        raise CasePackRevisionError(
            "finalized revision cannot be regenerated; create a new revision version"
        )
    spec = load_case_pack_revision_spec(spec_path.resolve())
    if tuple(map(int, spec.revision_id.split("."))) <= tuple(
        map(int, spec.source_workload_version.split("."))
    ):
        raise CasePackRevisionError("revision_id must be newer than source_workload_version")
    (
        source_manifest_path,
        source_cases_path,
        source_reviews_path,
        source_provenance,
    ) = _resolve_revision_source(
        root=root,
        canonical_directory=canonical_directory,
        spec=spec,
    )
    source_manifest = _load_json_object(
        source_manifest_path,
        label="source reference manifest",
    )

    source_bundle = build_reference_corpus(
        source_manifest_path,
        repository_root=root,
    )
    source_cases = load_case_contracts(source_cases_path)
    source_reviews = load_review_decisions(source_reviews_path)
    case_map = {case.external_case_id: case for case in source_cases}
    chunk_map = {chunk.chunk_id: chunk for chunk in source_bundle.corpus.chunks}
    change_map = {change.external_case_id: change for change in spec.changes}
    missing_cases = sorted(set(change_map) - set(case_map))
    if missing_cases:
        raise CasePackRevisionError(
            "revision references unknown cases: " + ", ".join(missing_cases)
        )

    revised_cases: list[ReferenceCaseContract] = []
    change_rows: list[dict[str, Any]] = []
    for source_case in source_cases:
        change = change_map.get(source_case.external_case_id)
        if change is None:
            revised_cases.append(source_case)
            continue
        revised_expectation = parse_rag_evidence_expectation(
            {
                "relevant_chunk_ids": change.relevant_chunk_ids,
                **(
                    {
                        "evidence_contract_version": ANY_OF_RAG_EVIDENCE_CONTRACT_VERSION,
                        "acceptable_evidence_groups": change.acceptable_evidence_groups,
                    }
                    if change.acceptable_evidence_groups is not None
                    else {}
                ),
            }
        )
        expected_chunks = []
        for chunk_id in revised_expectation.acceptable_chunk_ids:
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                raise CasePackRevisionError(
                    f"revision case {change.external_case_id} references unknown chunk {chunk_id}"
                )
            expected_chunks.append(chunk)
        primary_chunk = expected_chunks[0]
        if (
            primary_chunk.document_id != change.expected_source_path
            or primary_chunk.title != change.expected_heading
        ):
            raise CasePackRevisionError(
                f"revision evidence identity changed for {change.external_case_id}"
            )
        revised_case = _revise_case(
            source_case,
            change,
            query_strategy=spec.query_strategy,
        )
        revised_cases.append(revised_case)
        source_rag = (source_case.reference_context or {}).get("rag", {})
        source_expectation = parse_rag_evidence_expectation(source_rag)
        old_query = str(source_rag.get("query") or "")
        old_ids = list(source_expectation.primary_chunk_ids)
        change_rows.append(
            {
                "external_case_id": source_case.external_case_id,
                "criticality": source_case.criticality,
                "title": source_case.title,
                "request": (
                    source_case.input_payload.get("request")
                    or source_case.input_payload.get("query")
                ),
                "semantic_contract": deepcopy(revised_case.expected_output),
                "old_semantic_contract": deepcopy(source_case.expected_output),
                "revised_semantic_contract": deepcopy(revised_case.expected_output),
                "semantic_contract_changed": (
                    source_case.expected_output != revised_case.expected_output
                ),
                "source_case_sha256": reference_case_hash(source_case),
                "revised_case_sha256": reference_case_hash(revised_case),
                "old_contract": {
                    "query": old_query,
                    "relevant_chunk_ids": old_ids,
                    "evidence_contract_version": source_expectation.contract_version,
                    "acceptable_evidence_groups": [
                        list(group) for group in source_expectation.acceptable_groups
                    ],
                    "expected_chunk_ranks": _expected_ranks(
                        corpus=source_bundle.corpus,
                        query=old_query,
                        expected_chunk_ids=list(source_expectation.acceptable_chunk_ids),
                    ),
                    "evidence": [
                        _chunk_evidence(chunk_map[chunk_id])
                        for chunk_id in source_expectation.acceptable_chunk_ids
                        if chunk_id in chunk_map
                    ],
                },
                "revised_contract": {
                    "query": change.retrieval_query,
                    "query_strategy": spec.query_strategy,
                    "top_k": change.top_k,
                    "relevant_chunk_ids": list(change.relevant_chunk_ids),
                    "evidence_contract_version": revised_expectation.contract_version,
                    "acceptable_evidence_groups": [
                        list(group) for group in revised_expectation.acceptable_groups
                    ],
                    "expected_chunk_ranks": _expected_ranks(
                        corpus=source_bundle.corpus,
                        query=change.retrieval_query,
                        expected_chunk_ids=list(revised_expectation.acceptable_chunk_ids),
                    ),
                    "evidence": [_chunk_evidence(chunk) for chunk in expected_chunks],
                },
                "rationale": change.rationale,
                "review_status": "draft_human_review_required",
            }
        )

    changed_ids = set(change_map)
    retained_reviews = [
        decision for decision in source_reviews if decision.external_case_id not in changed_ids
    ]
    revised_manifest = {**source_manifest, "workload_version": spec.revision_id}
    manifest_path = output / "manifest.json"
    cases_path = output / "cases.jsonl"
    reviews_path = output / "review_manifest.jsonl"
    audit_path = output / "retrieval_contract_audit.json"
    report_path = output / "revision_report.json"
    _write_text(manifest_path, f"{canonical_json(revised_manifest)}\n")
    _write_text(
        cases_path,
        "".join(f"{serialize_case(case)}\n" for case in revised_cases),
    )
    _write_text(
        reviews_path,
        "".join(
            f"{canonical_json(decision.model_dump(mode='json'))}\n" for decision in retained_reviews
        ),
    )

    revised_bundle = build_reference_corpus(manifest_path, repository_root=root)
    revised_pack = load_reference_case_pack(
        corpus_bundle=revised_bundle,
        cases_path=cases_path,
        review_manifest_path=reviews_path,
    )
    audit = build_retrieval_contract_audit(
        case_pack=revised_pack,
        corpus_bundle=revised_bundle,
        case_ids=sorted(changed_ids),
    )
    write_retrieval_contract_audit(audit_path, audit)
    audit_rows = {row["external_case_id"]: row for row in audit["cases"]}
    for row in change_rows:
        audit_row = audit_rows[row["external_case_id"]]
        row["revised_contract"]["retrieval_recall"] = audit_row["retrieval_recall"]
        row["revised_contract"]["contract_reachable"] = audit_row["contract_reachable"]
        row["revised_contract"]["satisfied_evidence_group_index"] = audit_row[
            "satisfied_evidence_group_index"
        ]
        row["revised_contract"]["matched_acceptable_chunk_ids"] = audit_row[
            "matched_acceptable_chunk_ids"
        ]

    report: dict[str, Any] = {
        "schema_version": CASE_REVISION_REPORT_VERSION,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "revision_id": spec.revision_id,
        "source_workload_version": spec.source_workload_version,
        "source_provenance": source_provenance,
        "query_strategy": spec.query_strategy,
        "summary": {
            "case_count": len(revised_cases),
            "changed_case_count": len(change_rows),
            "retained_approval_count": len(retained_reviews),
            "pending_review_count": len(change_rows),
            "approved_case_count": revised_pack.approved_case_count,
            "approved_critical_case_count": revised_pack.approved_critical_case_count,
            "portfolio_ready": revised_pack.portfolio_ready,
            "retrieval_contract_status": audit["summary"]["status"],
        },
        "changes": change_rows,
        "artifact_identity": {
            "source_manifest_sha256": file_sha256(source_manifest_path),
            "source_cases_sha256": file_sha256(source_cases_path),
            "source_reviews_sha256": file_sha256(source_reviews_path),
            "manifest_sha256": file_sha256(manifest_path),
            "cases_sha256": file_sha256(cases_path),
            "reviews_sha256": file_sha256(reviews_path),
            "retrieval_contract_audit_report_sha256": audit["report_sha256"],
        },
        "evidence_boundary": {
            "canonical_case_pack_mutated": False,
            "historical_results_mutated": False,
            "changed_cases_approved": False,
            "bootstrap_allowed": revised_pack.portfolio_ready,
            "authoritative_portfolio_evidence": False,
            "production_readiness": "not_production_ready",
        },
    }
    report["report_sha256"] = stable_hash(
        {key: value for key, value in report.items() if key != "generated_at"}
    )
    _write_text(report_path, f"{canonical_json(report)}\n")
    return {**report, "output_directory": str(output)}
