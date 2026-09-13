from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkResult
from app.services.operator_identity import SignerIdentity
from app.validators import DomainValidationError

JUDGE_LABEL_IMPORT_VERSION = "judge-label-import-v1"


@dataclass(frozen=True)
class JudgeLabelImportSummary:
    benchmark_run_id: str
    label_count: int
    matched_label_count: int
    missing_result_count: int
    applied: bool
    quality_label_count: int
    average_abs_quality_delta: float | None
    import_format_version: str = JUDGE_LABEL_IMPORT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def import_judge_labels(
    db: Session,
    *,
    benchmark_run_id: UUID,
    path: Path,
    apply_labels: bool,
) -> JudgeLabelImportSummary:
    rows = _read_rows(path)
    return import_judge_label_rows(
        db,
        benchmark_run_id=benchmark_run_id,
        rows=rows,
        apply_labels=apply_labels,
    )


def import_judge_label_content(
    db: Session,
    *,
    benchmark_run_id: UUID,
    filename: str,
    content: str,
    apply_labels: bool,
    reviewer_identity: SignerIdentity | None = None,
) -> JudgeLabelImportSummary:
    rows = _read_rows_from_text(content, Path(filename).suffix.lower())
    return import_judge_label_rows(
        db,
        benchmark_run_id=benchmark_run_id,
        rows=rows,
        apply_labels=apply_labels,
        reviewer_identity=reviewer_identity,
    )


def import_judge_label_rows(
    db: Session,
    *,
    benchmark_run_id: UUID,
    rows: list[dict[str, Any]],
    apply_labels: bool,
    reviewer_identity: SignerIdentity | None = None,
) -> JudgeLabelImportSummary:
    labels = [_normalize_label(row, index) for index, row in enumerate(rows, start=1)]
    _validate_unique_sample_ids(labels)

    results = list(
        db.scalars(
            select(BenchmarkResult).where(BenchmarkResult.benchmark_run_id == benchmark_run_id)
        )
    )
    result_by_sample = {result.sample_id: result for result in results}
    matched = 0
    missing = 0
    quality_deltas: list[float] = []

    for label in labels:
        result = result_by_sample.get(label["sample_id"])
        if result is None:
            missing += 1
            continue
        matched += 1
        if label.get("quality_score") is not None and result.quality_score is not None:
            quality_deltas.append(abs(float(label["quality_score"]) - result.quality_score))
        if apply_labels:
            _apply_label(
                result,
                label,
                reviewer_identity=reviewer_identity,
            )
            db.add(result)
    if apply_labels:
        db.commit()

    return JudgeLabelImportSummary(
        benchmark_run_id=str(benchmark_run_id),
        label_count=len(labels),
        matched_label_count=matched,
        missing_result_count=missing,
        applied=apply_labels,
        quality_label_count=sum(1 for label in labels if label.get("quality_score") is not None),
        average_abs_quality_delta=(
            sum(quality_deltas) / len(quality_deltas) if quality_deltas else None
        ),
    )


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise DomainValidationError(f"judge label file was not found: {path}")
    return _read_rows_from_text(path.read_text(encoding="utf-8-sig"), path.suffix.lower())


def _read_rows_from_text(content: str, suffix: str) -> list[dict[str, Any]]:
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise DomainValidationError(f"line {line_number} must be a JSON object")
            rows.append(row)
        return rows
    if suffix == ".json":
        payload = json.loads(content)
        if isinstance(payload, dict):
            payload = payload.get("labels", [])
        if not isinstance(payload, list):
            raise DomainValidationError("JSON judge label file must contain a list or labels list")
        if not all(isinstance(row, dict) for row in payload):
            raise DomainValidationError("every judge label row must be an object")
        return list(payload)
    if suffix == ".csv":
        return [dict(row) for row in csv.DictReader(content.splitlines())]
    raise DomainValidationError("judge label import supports .jsonl, .json, and .csv files")


def _normalize_label(row: dict[str, Any], row_number: int) -> dict[str, Any]:
    sample_id = row.get("sample_id") or row.get("external_case_id")
    if sample_id in {None, ""}:
        raise DomainValidationError(f"row {row_number} is missing sample_id")
    label = {
        "sample_id": str(sample_id),
        "quality_score": _optional_score(row, "quality_score"),
        "groundedness_score": _optional_score(row, "groundedness_score"),
        "faithfulness_score": _optional_score(row, "faithfulness_score"),
        "human_label": _optional_text(row, "human_label"),
        "judge_source": _optional_text(row, "judge_source") or "imported",
        "judge_model": _optional_text(row, "judge_model"),
    }
    if not any(
        label[key] is not None
        for key in ("quality_score", "groundedness_score", "faithfulness_score", "human_label")
    ):
        raise DomainValidationError(f"row {row_number} does not contain any judge label values")
    return label


def _apply_label(
    result: BenchmarkResult,
    label: dict[str, Any],
    *,
    reviewer_identity: SignerIdentity | None = None,
) -> None:
    if label["quality_score"] is not None:
        result.quality_score = label["quality_score"]
    if label["groundedness_score"] is not None:
        result.groundedness_score = label["groundedness_score"]
    if label["faithfulness_score"] is not None:
        result.faithfulness_score = label["faithfulness_score"]
    if label["human_label"] is not None:
        result.human_label = label["human_label"]
    metadata = dict(result.metadata_json or {})
    metadata["judge_label"] = {
        "version": JUDGE_LABEL_IMPORT_VERSION,
        "source": label["judge_source"],
        "judge_model": label["judge_model"],
        "applied": True,
        **(
            {
                "human_reviewed": True,
                "reviewer_type": "human",
                "reviewer_identity": reviewer_identity.to_json(),
            }
            if reviewer_identity is not None
            else {}
        ),
    }
    if reviewer_identity is not None:
        metadata["human_reviewed"] = True
    result.metadata_json = metadata


def _validate_unique_sample_ids(labels: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for label in labels:
        sample_id = label["sample_id"]
        if sample_id in seen:
            duplicates.append(sample_id)
        seen.add(sample_id)
    if duplicates:
        raise DomainValidationError(
            f"duplicate sample_id values: {', '.join(sorted(set(duplicates)))}"
        )


def _optional_score(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value in {None, ""}:
        return None
    score = float(value)
    if score < 0 or score > 1:
        raise DomainValidationError(f"{key} must be between 0 and 1")
    return score


def _optional_text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value in {None, ""}:
        return None
    return str(value)
