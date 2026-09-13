from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    BenchmarkExecutionLog,
    BenchmarkResult,
    BenchmarkRun,
    EvaluationCase,
    EvaluationSuite,
    GateEvaluation,
    GateRuleResult,
    InferenceMetric,
    WorkloadProfile,
)
from app.seed.demo import WORKLOAD_SLUG, seed_demo_data
from app.services.deployment_gate.evidence import stable_hash
from app.validators import DomainValidationError

PRODUCTION_CAPTURED_SOURCE = "production_captured"
IMPORT_FORMAT_VERSION = "production-captured-case-import-v1"
VALID_CRITICALITIES = {"critical", "standard", "exploratory"}


@dataclass(frozen=True)
class CapturedCaseImportOptions:
    suite_name: str
    suite_version: str
    workload_slug: str = WORKLOAD_SLUG
    data_source: str = PRODUCTION_CAPTURED_SOURCE
    description: str | None = None
    replace_existing: bool = False
    seed_demo_if_missing: bool = False


@dataclass(frozen=True)
class CapturedCaseImportSummary:
    evaluation_suite_id: str
    evaluation_suite_name: str
    evaluation_suite_version: str
    workload_slug: str
    case_count: int
    critical_case_count: int
    json_case_count: int
    tool_case_count: int
    grounded_case_count: int
    judge_label_case_count: int
    data_source: str
    import_format_version: str = IMPORT_FORMAT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def import_captured_cases(
    db: Session,
    *,
    path: Path,
    options: CapturedCaseImportOptions,
) -> CapturedCaseImportSummary:
    rows = _read_rows(path)
    if not rows:
        raise DomainValidationError("captured case import file did not contain any rows")

    workload = db.scalar(
        select(WorkloadProfile).where(WorkloadProfile.slug == options.workload_slug)
    )
    if workload is None and options.seed_demo_if_missing:
        seed_demo_data(db)
        workload = db.scalar(
            select(WorkloadProfile).where(WorkloadProfile.slug == options.workload_slug)
        )
    if workload is None:
        raise DomainValidationError(f"workload '{options.workload_slug}' was not found")

    case_payloads = [
        _normalize_case(row, index, options) for index, row in enumerate(rows, start=1)
    ]
    _validate_unique_external_ids(case_payloads)

    existing_suite_ids = list(
        db.scalars(
            select(EvaluationSuite.id)
            .where(EvaluationSuite.workload_profile_id == workload.id)
            .where(EvaluationSuite.name == options.suite_name)
            .where(EvaluationSuite.version_label == options.suite_version)
        )
    )
    if existing_suite_ids and not options.replace_existing:
        raise DomainValidationError(
            "evaluation suite already exists; pass replace_existing to overwrite it"
        )
    _delete_suites(db, existing_suite_ids)

    suite_payload = {
        "workload_profile_id": workload.id,
        "name": options.suite_name,
        "version_label": options.suite_version,
        "description": options.description
        or "Production-captured evaluation cases imported from local reviewed artifacts.",
        "status": "active",
        "dataset_source": options.data_source,
        "is_synthetic": False,
    }
    suite_hash_seed = {
        **suite_payload,
        "case_hashes": [
            stable_hash(
                {key: value for key, value in payload.items() if key != "evaluation_suite_id"}
            )
            for payload in case_payloads
        ],
        "import_format_version": IMPORT_FORMAT_VERSION,
    }
    suite = EvaluationSuite(**suite_payload, suite_hash=stable_hash(suite_hash_seed))
    db.add(suite)
    db.flush()

    for payload in case_payloads:
        payload["evaluation_suite_id"] = suite.id
    db.add_all(EvaluationCase(**payload) for payload in case_payloads)
    db.commit()

    return CapturedCaseImportSummary(
        evaluation_suite_id=str(suite.id),
        evaluation_suite_name=suite.name,
        evaluation_suite_version=suite.version_label,
        workload_slug=options.workload_slug,
        case_count=len(case_payloads),
        critical_case_count=sum(1 for case in case_payloads if case["criticality"] == "critical"),
        json_case_count=sum(1 for case in case_payloads if _is_json_case(case)),
        tool_case_count=sum(1 for case in case_payloads if _is_tool_case(case)),
        grounded_case_count=sum(1 for case in case_payloads if _is_grounded_case(case)),
        judge_label_case_count=sum(1 for case in case_payloads if _has_judge_labels(case)),
        data_source=options.data_source,
    )


def _read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise DomainValidationError(f"captured case import file was not found: {path}")
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise DomainValidationError(f"line {line_number} must be a JSON object")
            rows.append(row)
        return rows
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("cases", [])
        if not isinstance(payload, list):
            raise DomainValidationError("JSON import file must contain a list or a cases list")
        if not all(isinstance(row, dict) for row in payload):
            raise DomainValidationError("every JSON import row must be an object")
        return list(payload)
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    raise DomainValidationError("captured case import supports .jsonl, .json, and .csv files")


def _normalize_case(
    row: dict[str, Any],
    row_number: int,
    options: CapturedCaseImportOptions,
) -> dict[str, Any]:
    external_case_id = _required_text(row, "external_case_id", row_number)
    category = _required_text(row, "category", row_number)
    title = _text_value(row, "title") or external_case_id
    input_payload = _json_field(row, "input_payload_json", "input", required=True)
    expected_output = _json_field(row, "expected_output_json", "expected_output")
    reference_context = _json_field(row, "reference_context_json", "reference_context")
    expected_tool = _json_field(row, "expected_tool_schema_json", "expected_tool_schema")
    tags = _tags(row.get("tags_json", row.get("tags")))
    criticality = _text_value(row, "criticality") or "standard"
    if criticality not in VALID_CRITICALITIES:
        raise DomainValidationError(
            f"row {row_number} has invalid criticality '{criticality}'"
        )
    judge_labels = _judge_labels(row)
    if judge_labels:
        reference_context = dict(reference_context or {})
        reference_context["judge_labels"] = judge_labels
    data_source = _text_value(row, "data_source") or options.data_source
    if data_source == "synthetic_demo":
        raise DomainValidationError("production-captured import rows cannot use synthetic_demo")
    if options.data_source not in tags:
        tags.append(options.data_source)
    if data_source not in tags:
        tags.append(data_source)
    return {
        "evaluation_suite_id": None,
        "external_case_id": external_case_id,
        "category": category,
        "title": title,
        "input_payload_json": input_payload,
        "expected_output_json": expected_output,
        "reference_context_json": reference_context,
        "expected_tool_schema_json": expected_tool,
        "tags_json": tags,
        "criticality": criticality,
        "weight": _float_value(row.get("weight"), default=1.0),
        "is_active": _bool_value(row.get("is_active"), default=True),
        "data_source": data_source,
    }


def _delete_suites(db: Session, suite_ids: list[Any]) -> None:
    if not suite_ids:
        return
    gate_ids = list(
        db.scalars(select(GateEvaluation.id).where(GateEvaluation.evaluation_suite_id.in_(suite_ids)))
    )
    run_ids = list(
        db.scalars(select(BenchmarkRun.id).where(BenchmarkRun.evaluation_suite_id.in_(suite_ids)))
    )
    if gate_ids:
        db.execute(delete(GateRuleResult).where(GateRuleResult.gate_evaluation_id.in_(gate_ids)))
        db.execute(delete(GateEvaluation).where(GateEvaluation.id.in_(gate_ids)))
    if run_ids:
        db.execute(
            delete(BenchmarkExecutionLog).where(BenchmarkExecutionLog.benchmark_run_id.in_(run_ids))
        )
        db.execute(delete(InferenceMetric).where(InferenceMetric.benchmark_run_id.in_(run_ids)))
        db.execute(delete(BenchmarkResult).where(BenchmarkResult.benchmark_run_id.in_(run_ids)))
        db.execute(delete(BenchmarkRun).where(BenchmarkRun.id.in_(run_ids)))
    db.execute(delete(EvaluationCase).where(EvaluationCase.evaluation_suite_id.in_(suite_ids)))
    db.execute(delete(EvaluationSuite).where(EvaluationSuite.id.in_(suite_ids)))


def _validate_unique_external_ids(case_payloads: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for payload in case_payloads:
        external_case_id = payload["external_case_id"]
        if external_case_id in seen:
            duplicates.append(external_case_id)
        seen.add(external_case_id)
    if duplicates:
        raise DomainValidationError(
            f"duplicate external_case_id values: {', '.join(sorted(set(duplicates)))}"
        )


def _required_text(row: dict[str, Any], key: str, row_number: int) -> str:
    value = _text_value(row, key)
    if not value:
        raise DomainValidationError(f"row {row_number} is missing required field '{key}'")
    return value


def _text_value(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _json_field(row: dict[str, Any], *keys: str, required: bool = False) -> Any:
    for key in keys:
        if key not in row or _is_blank(row[key]):
            continue
        return _parse_jsonish(row[key], key)
    if required:
        raise DomainValidationError(f"missing required JSON field '{keys[0]}'")
    return None


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value == "")


def _parse_jsonish(value: Any, field_name: str) -> Any:
    if isinstance(value, dict | list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise DomainValidationError(f"field '{field_name}' must be valid JSON") from exc
    raise DomainValidationError(f"field '{field_name}' must be a JSON object or array")


def _tags(value: Any) -> list[str]:
    if _is_blank(value):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        if value.strip().startswith("["):
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise DomainValidationError("tags_json must decode to a list")
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [item.strip() for item in value.split(",") if item.strip()]
    raise DomainValidationError("tags must be a list or comma-separated string")


def _judge_labels(row: dict[str, Any]) -> dict[str, Any]:
    labels = _json_field(row, "judge_labels_json", "judge_labels") or {}
    if not isinstance(labels, dict):
        raise DomainValidationError("judge_labels must be a JSON object")
    labels = dict(labels)
    for key in ("quality_score", "groundedness_score", "faithfulness_score"):
        if key in row and row[key] not in {None, ""}:
            labels[key] = _score_value(row[key], key)
        elif key in labels:
            labels[key] = _score_value(labels[key], key)
    for key in ("human_label", "judge_source", "judge_model", "reviewer_id"):
        if key in row and row[key] not in {None, ""}:
            labels[key] = str(row[key])
    return labels


def _score_value(value: Any, field_name: str) -> float:
    score = float(value)
    if score < 0 or score > 1:
        raise DomainValidationError(f"{field_name} must be between 0 and 1")
    return score


def _float_value(value: Any, *, default: float) -> float:
    if value in {None, ""}:
        return default
    parsed = float(value)
    if parsed <= 0:
        raise DomainValidationError("weight must be positive")
    return parsed


def _bool_value(value: Any, *, default: bool) -> bool:
    if value in {None, ""}:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _is_json_case(case: dict[str, Any]) -> bool:
    return case["expected_output_json"] is not None or "json" in case["category"].lower()


def _is_tool_case(case: dict[str, Any]) -> bool:
    return case["expected_tool_schema_json"] is not None or "tool" in case["category"].lower()


def _is_grounded_case(case: dict[str, Any]) -> bool:
    return "ground" in case["category"].lower()


def _has_judge_labels(case: dict[str, Any]) -> bool:
    reference_context = case.get("reference_context_json")
    return isinstance(reference_context, dict) and bool(reference_context.get("judge_labels"))
