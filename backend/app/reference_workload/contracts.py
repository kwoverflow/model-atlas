from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.rag_evidence_contract import parse_rag_evidence_expectation
from app.services.rag_semantic_contract import parse_rag_semantic_expectation

REFERENCE_MANIFEST_SCHEMA_VERSION = "model-atlas-reference-workload-manifest-v1"
REFERENCE_CASE_SCHEMA_VERSION = "model-atlas-reference-case-v1"
REFERENCE_REVIEW_SCHEMA_VERSION = "model-atlas-reference-review-v1"
REFERENCE_WORKLOAD_SLUG = "model-atlas-operator-assistant-ko"
REFERENCE_CORPUS_ID = "model-atlas-operator-handbook-ko"
REFERENCE_CASE_CONTRACT_VERSION = "reference-case-v1"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpusFileContract(StrictContract):
    path: str = Field(min_length=1, max_length=500)
    sha256: str | None = None
    included: bool = True

    @field_validator("path")
    @classmethod
    def validate_repository_relative_path(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "\\" in normalized:
            raise ValueError("corpus paths must be non-empty POSIX-style relative paths")
        if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
            raise ValueError("absolute corpus paths are not allowed")
        parts = normalized.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError("corpus paths may not contain empty, dot, or parent segments")
        return normalized

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized):
            raise ValueError("sha256 must be a lowercase 64-character digest")
        return normalized


class CorpusManifestContract(StrictContract):
    corpus_id: Literal["model-atlas-operator-handbook-ko"]
    corpus_version: str = Field(min_length=1, max_length=80)
    chunking_version: Literal["markdown-section-chunker-v1"]
    files: list[CorpusFileContract] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> CorpusManifestContract:
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("corpus file paths must be unique")
        if not any(item.included for item in self.files):
            raise ValueError("at least one corpus file must be included")
        return self


class ReferenceWorkloadManifestContract(StrictContract):
    schema_version: Literal["model-atlas-reference-workload-manifest-v1"]
    workload_slug: Literal["model-atlas-operator-assistant-ko"]
    workload_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    language: Literal["ko"]
    corpus: CorpusManifestContract
    case_contract_version: Literal["reference-case-v1"]
    minimum_active_cases: int = Field(ge=60)
    minimum_critical_cases: int = Field(ge=20)


class CaseReviewContract(StrictContract):
    status: Literal["draft", "approved", "rejected"]
    reviewer: str | None = Field(default=None, min_length=1, max_length=160)
    reviewed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_review_provenance(self) -> CaseReviewContract:
        if self.status in {"approved", "rejected"}:
            if not self.reviewer or self.reviewed_at is None or not self.notes:
                raise ValueError(
                    "reviewed cases require reviewer, timezone-aware reviewed_at, and notes"
                )
            if self.reviewed_at.utcoffset() is None:
                raise ValueError("reviewed_at must be timezone-aware")
        elif self.reviewer is not None or self.reviewed_at is not None:
            raise ValueError("draft cases may not claim reviewer metadata")
        return self


class ReferenceCaseContract(StrictContract):
    schema_version: Literal["model-atlas-reference-case-v1"]
    external_case_id: str = Field(pattern=r"^KO-[A-Z0-9-]+-\d{3}$", max_length=120)
    category: Literal[
        "rag_single_document",
        "rag_multi_document",
        "rag_version_or_scope",
        "insufficient_evidence_refusal",
        "tool_single_step",
        "tool_failure_recovery",
        "rag_tool_combined",
        "agent_multi_step",
    ]
    title: str = Field(min_length=1, max_length=240)
    input_payload: dict[str, Any]
    expected_output: dict[str, Any] | None = None
    reference_context: dict[str, Any] | None = None
    expected_tool_schema: dict[str, Any] | None = None
    criticality: Literal["critical", "standard", "exploratory"]
    weight: float = Field(gt=0)
    review: CaseReviewContract
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case_shape(self) -> ReferenceCaseContract:
        if not any(
            isinstance(self.input_payload.get(key), str)
            and str(self.input_payload[key]).strip()
            for key in ("query", "request", "question")
        ):
            raise ValueError("a reference case requires a non-empty query, request, or question")
        if self.category.startswith("rag_"):
            rag = self.reference_context.get("rag") if self.reference_context else None
            if not isinstance(rag, dict):
                raise ValueError("RAG cases require reference_context.rag")
            relevant = rag.get("relevant_chunk_ids")
            if not isinstance(relevant, list) or not relevant:
                raise ValueError("RAG cases require at least one relevant chunk ID")
            try:
                parse_rag_evidence_expectation(rag)
            except ValueError as exc:
                raise ValueError(f"invalid RAG evidence contract: {exc}") from exc
        if isinstance(self.expected_output, dict):
            try:
                parse_rag_semantic_expectation(self.expected_output)
            except ValueError as exc:
                raise ValueError(f"invalid RAG semantic contract: {exc}") from exc
        if self.category.startswith("tool_") and self.expected_tool_schema is None:
            raise ValueError("Tool cases require expected_tool_schema")
        return self


class CaseReviewDecisionContract(StrictContract):
    schema_version: Literal["model-atlas-reference-review-v1"]
    external_case_id: str = Field(pattern=r"^KO-[A-Z0-9-]+-\d{3}$", max_length=120)
    case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    notes: str = Field(min_length=1, max_length=2000)

    @field_validator("reviewed_at")
    @classmethod
    def validate_review_time(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        return value
