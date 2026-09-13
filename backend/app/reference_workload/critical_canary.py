"""Read-only provenance and coverage audit for a bounded critical-case diagnostic."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import BenchmarkResult, BenchmarkRun, EvaluationCase, InferenceMetric
from app.reference_workload.runtime_matrix import (
    DIAGNOSTIC_RUNTIME_DATA_SOURCE,
    RUNTIME_MATRIX_RESULT_VERSION,
    load_runtime_matrix,
)
from app.services.deployment_gate.evidence import EvidenceBundle, stable_hash
from app.services.deployment_gate.metrics import critical_case_outcomes
from app.services.reference_output_review import build_reference_output_review_plan
from app.services.reference_workload_read_model import build_reference_workload_overview

VERSION = "critical-canary-audit-v1"


def _record(entity) -> dict:
    return {
        column.key: getattr(entity, column.key) for column in inspect(type(entity)).column_attrs
    }


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seal(payload: dict) -> dict:
    return {**payload, "content_sha256": stable_hash(payload)}


def _verify(payload: dict) -> None:
    body = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("content_sha256") != stable_hash(body):
        raise ValueError("snapshot content hash mismatch")
    if payload.get("schema_version") != VERSION:
        raise ValueError("unsupported canary schema")


def snapshot(db: Session, root: Path) -> dict:
    overview = build_reference_workload_overview(db)
    plan = build_reference_output_review_plan(db)
    run_ids = [item.latest_run_id for item in overview.configuration_matrix if item.latest_run_id]
    protected = []
    for run_id in sorted(run_ids, key=str):
        run = db.get(BenchmarkRun, run_id)
        results = list(
            db.scalars(
                select(BenchmarkResult)
                .where(BenchmarkResult.benchmark_run_id == run_id)
                .order_by(BenchmarkResult.id)
            )
        )
        metrics = list(
            db.scalars(
                select(InferenceMetric)
                .where(InferenceMetric.benchmark_run_id == run_id)
                .order_by(InferenceMetric.id)
            )
        )
        case_ids = {item.evaluation_case_id for item in results}
        cases = list(
            db.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.id.in_(case_ids))
                .order_by(EvaluationCase.id)
            )
        )
        protected.append(
            {
                "run": _record(run),
                "configuration": _record(run.deployment_configuration),
                "suite": _record(run.evaluation_suite),
                "results": [_record(item) for item in results],
                "metrics": [_record(item) for item in metrics],
                "cases": [_record(item) for item in cases],
            }
        )
    app_root = Path(__file__).resolve().parents[1]
    sources = {
        f"app/{path.relative_to(app_root).as_posix()}": _file_hash(path)
        for path in sorted(app_root.rglob("*.py"))
    }
    for relative in (
        "reference_workload/runtime_matrix.json",
        "reference_workload/manifest.json",
        "reference_workload/cases.jsonl",
        "reference_workload/review_manifest.jsonl",
        "reference_workload/revisions/1.0.4/manifest.json",
        "reference_workload/revisions/1.0.4/cases.jsonl",
        "reference_workload/revisions/1.0.4/review_manifest.jsonl",
        "reference_workload/revisions/1.0.4/finalization_report.json",
    ):
        sources[relative] = _file_hash(root / relative)
    matrix = load_runtime_matrix(root / "reference_workload/runtime_matrix.json")
    return _seal(
        {
            "schema_version": VERSION,
            "kind": "snapshot",
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "official": {
                "comparison_hash": overview.comparison_hash,
                "gate_verdict": overview.gate_verdict,
                "critical_failure_count": overview.critical_failure_count,
                "actual_runtime_result_count": overview.actual_runtime_result_count,
                "review_coverage": overview.review_coverage.model_dump(mode="json"),
                "production_readiness": overview.production_readiness,
                "protected_records_sha256": stable_hash(protected),
                "protected_run_ids": [str(item) for item in run_ids],
                "review_plan_hash": plan.plan_hash,
            },
            "expected_case_ids": sorted({item.external_case_id for item in plan.clusters}),
            "expected_entry_names": [item.name for item in matrix.entries if item.enabled],
            "matrix_hash": stable_hash(matrix.model_dump(mode="json")),
            "source_sha256": sources,
        }
    )


def validate_scope(before: dict, after: dict, matrix: dict) -> list[dict]:
    for state in (before, after):
        _verify(state)
        if state.get("kind") != "snapshot":
            raise ValueError("expected a canary snapshot")
    for key in (
        "official",
        "source_sha256",
        "expected_case_ids",
        "expected_entry_names",
        "matrix_hash",
    ):
        if before[key] != after[key]:
            raise ValueError(f"protected state changed: {key}")
    scope = matrix.get("diagnostic_scope", {})
    if (
        matrix.get("schema_version") != RUNTIME_MATRIX_RESULT_VERSION
        or matrix.get("mode") != "diagnostic"
        or scope.get("gate_evidence") is not False
        or scope.get("authoritative_portfolio_evidence") is not False
        or matrix.get("production_readiness") != "not_production_ready"
        or matrix.get("matrix_hash") != before["matrix_hash"]
    ):
        raise ValueError("not an isolated diagnostic from the snapshotted matrix")
    expected = before["expected_case_ids"]
    if (
        not expected
        or len(expected) > 20
        or Counter(scope.get("case_ids", [])) != Counter(expected)
    ):
        raise ValueError("diagnostic case coverage differs from the frozen failure plan")
    entries = [item for item in matrix.get("entries", []) if item.get("enabled") is True]
    if Counter(item.get("name") for item in entries) != Counter(before["expected_entry_names"]):
        raise ValueError("diagnostic entry coverage mismatch")
    if any(item.get("status") != "completed" or item.get("trials") != 1 for item in entries):
        raise ValueError("every planned entry must complete exactly one trial")
    run_ids = [item.get("benchmark_run_id") for item in entries]
    if not all(run_ids) or len(set(run_ids)) != len(run_ids):
        raise ValueError("missing or duplicate diagnostic run")
    if set(run_ids) & set(before["official"]["protected_run_ids"]):
        raise ValueError("official runs cannot be used as a diagnostic")
    return entries


def summarize_rows(rows: list[dict], *, case_ids: list[str], entry_names: list[str]) -> dict:
    expected = Counter((entry, case) for entry in entry_names for case in case_ids)
    if Counter((row["entry"], row["external_case_id"]) for row in rows) != expected:
        raise ValueError("missing, duplicate, or unexpected observation")
    result_ids = [row["benchmark_result_id"] for row in rows]
    if len(set(result_ids)) != len(result_ids):
        raise ValueError("duplicate result ID")
    if any(row["status"] not in {"pass", "fail"} for row in rows):
        raise ValueError("unknown critical outcome")
    categories = sorted({row["category"] for row in rows})
    return {
        "observation_count": len(rows),
        "unique_case_count": len(case_ids),
        "pass_count": sum(row["status"] == "pass" for row in rows),
        "failure_count": sum(row["status"] == "fail" for row in rows),
        "remaining_case_ids": sorted(
            {row["external_case_id"] for row in rows if row["status"] == "fail"}
        ),
        "by_category": [
            {
                "category": category,
                "observation_count": sum(row["category"] == category for row in rows),
                "pass_count": sum(
                    row["category"] == category and row["status"] == "pass" for row in rows
                ),
                "failure_count": sum(
                    row["category"] == category and row["status"] == "fail" for row in rows
                ),
            }
            for category in categories
        ],
        "by_entry": [
            {
                "entry": entry,
                "pass_count": sum(
                    row["entry"] == entry and row["status"] == "pass" for row in rows
                ),
                "failure_count": sum(
                    row["entry"] == entry and row["status"] == "fail" for row in rows
                ),
            }
            for entry in entry_names
        ],
    }


def audit(db: Session, *, before: dict, after: dict, matrix: dict) -> dict:
    entries = validate_scope(before, after, matrix)
    rows = []
    stored_runs = []
    for entry in entries:
        run = db.get(BenchmarkRun, UUID(entry["benchmark_run_id"]))
        if (
            run is None
            or run.status != "completed"
            or run.data_source != DIAGNOSTIC_RUNTIME_DATA_SOURCE
            or str(run.deployment_configuration_id) != entry["deployment_configuration_id"]
            or str(run.evaluation_suite_id) != matrix["evaluation_suite_id"]
            or run.evaluation_suite.suite_hash != matrix["suite_hash"]
            or run.deployment_configuration.configuration_hash != entry["configuration_hash"]
            or run.deployment_configuration.runtime_config_json.get("reference_workload_mode")
            != "diagnostic"
        ):
            raise ValueError("stored run does not match diagnostic identity/scope")
        results = list(
            db.scalars(
                select(BenchmarkResult)
                .where(BenchmarkResult.benchmark_run_id == run.id)
                .order_by(BenchmarkResult.sample_id)
            )
        )
        metrics = list(
            db.scalars(
                select(InferenceMetric)
                .where(InferenceMetric.benchmark_run_id == run.id)
                .order_by(InferenceMetric.sample_id)
            )
        )
        if (
            len(results) != entry["result_count"]
            or len(metrics) != entry["metric_count"]
            or Counter(item.sample_id for item in results)
            != Counter(item.sample_id for item in metrics)
            or any(
                item.data_source != DIAGNOSTIC_RUNTIME_DATA_SOURCE for item in [*results, *metrics]
            )
        ):
            raise ValueError("stored result/metric coverage or provenance mismatch")
        cases = {
            item.id: item
            for item in db.scalars(
                select(EvaluationCase).where(
                    EvaluationCase.id.in_({item.evaluation_case_id for item in results})
                )
            )
        }
        if any(
            item.evaluation_case_id not in cases
            or cases[item.evaluation_case_id].evaluation_suite_id != run.evaluation_suite_id
            or cases[item.evaluation_case_id].criticality != "critical"
            for item in results
        ):
            raise ValueError("missing, non-critical, or foreign-suite case")
        bundle = EvidenceBundle(
            deployment_configuration=run.deployment_configuration,
            evaluation_suite=run.evaluation_suite,
            active_cases=list(cases.values()),
            runs=[run],
            results=results,
            metrics=metrics,
            source_distribution={DIAGNOSTIC_RUNTIME_DATA_SOURCE: len(results)},
            result_case_map={item.id: cases[item.evaluation_case_id] for item in results},
        )
        outcomes = {item["sample_id"]: item for item in critical_case_outcomes(bundle)}
        if len(outcomes) != len(results):
            raise ValueError("duplicate sample or incomplete critical outcomes")
        for result in results:
            rows.append(
                {
                    **outcomes[result.sample_id],
                    "entry": entry["name"],
                    "benchmark_result_id": str(result.id),
                    "stored_result": _record(result),
                }
            )
        stored_runs.append(
            {
                "run": _record(run),
                "configuration": _record(run.deployment_configuration),
                "cases": [
                    _record(item)
                    for item in sorted(cases.values(), key=lambda case: case.external_case_id)
                ],
                "metrics": [_record(item) for item in metrics],
            }
        )
    return _seal(
        {
            "schema_version": VERSION,
            "kind": "audit",
            "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            "authority": "non_authoritative_local_diagnostic",
            "gate_evidence": False,
            "human_reviewed": False,
            "production_readiness": "not_production_ready",
            "official_unchanged": True,
            "source_unchanged": True,
            "before_sha256": before["content_sha256"],
            "after_sha256": after["content_sha256"],
            "matrix_result_sha256": stable_hash(matrix),
            "official": after["official"],
            "summary": summarize_rows(
                rows,
                case_ids=before["expected_case_ids"],
                entry_names=before["expected_entry_names"],
            ),
            "rows": rows,
            "stored_runs": stored_runs,
            "limitations": [
                "Twenty known development cases, one trial per entry; not an independent holdout.",
                "Critical outcomes reuse the existing evaluator; they are not human judgments.",
                "Revised labels, adapter, token budget and trial count differ from the official "
                "baseline; no causal gain claim.",
                "Legacy recovery labels with disabled fault injection do not measure "
                "environment-owned retry recovery fairly.",
                "A bounded RAG answer compiler or Agent plan compiler is system behavior, "
                "not raw model accuracy.",
                "Passing this audit proves checked coverage and consistency, not identity "
                "authenticity or production readiness.",
            ],
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("snapshot", "audit"))
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--matrix-result", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new evidence path")
    if args.command == "audit" and not all((args.before, args.after, args.matrix_result)):
        parser.error("audit requires --before, --after and --matrix-result")
    with SessionLocal() as db:
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        if args.command == "snapshot":
            payload = snapshot(db, args.repository_root.resolve())
        else:
            payload = audit(
                db,
                **{
                    key: json.loads(path.read_text(encoding="utf-8"))
                    for key, path in (
                        ("before", args.before),
                        ("after", args.after),
                        ("matrix", args.matrix_result),
                    )
                },
            )
        db.rollback()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2, default=str)
        output.write("\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": _file_hash(args.output),
                "summary": payload.get("summary"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
