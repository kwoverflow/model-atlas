from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from app.db.session import SessionLocal
from app.reference_workload.bootstrap import (
    ReferenceBootstrapConflict,
    ReferenceWorkloadApprovalRequired,
    bootstrap_reference_workload,
)
from app.reference_workload.case_revision import (
    CasePackRevisionError,
    create_case_pack_revision,
)
from app.reference_workload.case_revision_review import (
    finalize_case_pack_revision,
    write_case_revision_review_html,
)
from app.reference_workload.cases import (
    CasePackValidationError,
    default_cases_path,
    default_review_manifest_path,
    load_reference_case_pack,
    write_review_worksheet,
)
from app.reference_workload.contract_audit import (
    RetrievalContractAuditError,
    build_retrieval_contract_audit,
    write_retrieval_contract_audit,
)
from app.reference_workload.corpus import build_reference_corpus
from app.reference_workload.draft_cases import write_draft_cases
from app.reference_workload.manifest import (
    ManifestValidationError,
    default_manifest_path,
    default_repository_root,
    lock_reference_manifest,
)
from app.reference_workload.reporting import (
    build_reference_workload_report,
    run_reference_workload_gates,
    write_reference_workload_artifacts,
)
from app.reference_workload.review_assistance import (
    ReviewAssistanceError,
    build_review_assistance_report,
    finalize_assisted_review,
    write_review_assistance_artifacts,
)
from app.reference_workload.review_ui import write_review_assistance_html
from app.reference_workload.runtime_matrix import (
    RuntimeMatrixError,
    build_stored_runtime_comparison,
    execute_runtime_matrix,
    load_runtime_matrix,
    write_runtime_matrix_result,
)


def _print(payload: dict[str, Any], *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str), file=stream)


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path, Path]:
    root = (
        Path(args.repository_root).resolve() if args.repository_root else default_repository_root()
    )
    manifest = Path(args.manifest).resolve() if args.manifest else default_manifest_path(root)
    cases = Path(args.cases).resolve() if args.cases else default_cases_path(root)
    reviews = Path(args.reviews).resolve() if args.reviews else default_review_manifest_path(root)
    return root, manifest, cases, reviews


def _validated_inputs(args: argparse.Namespace) -> tuple[Any, Any]:
    root, manifest, cases, reviews = _paths(args)
    bundle = build_reference_corpus(manifest, repository_root=root)
    case_pack = load_reference_case_pack(
        corpus_bundle=bundle,
        cases_path=cases,
        review_manifest_path=reviews,
    )
    return bundle, case_pack


def _command_lock(args: argparse.Namespace) -> int:
    root, manifest, _, _ = _paths(args)
    validated = lock_reference_manifest(manifest, repository_root=root)
    _print(
        {
            "status": "locked",
            "manifest_path": str(validated.manifest_path),
            "manifest_hash": validated.manifest_hash,
            "file_count": len(validated.files),
        }
    )
    return 0


def _command_draft(args: argparse.Namespace) -> int:
    root, manifest, cases, _ = _paths(args)
    bundle = build_reference_corpus(manifest, repository_root=root)
    generated = write_draft_cases(
        cases,
        corpus_bundle=bundle,
        force=args.force,
    )
    _print(
        {
            "status": "draft_cases_written",
            "cases_path": str(cases),
            "case_count": len(generated),
            "critical_case_count": sum(case.criticality == "critical" for case in generated),
            "approved_case_count": 0,
        }
    )
    return 0


def _command_validate(args: argparse.Namespace) -> int:
    bundle, case_pack = _validated_inputs(args)
    payload = {
        "status": "ready" if case_pack.portfolio_ready else "incomplete",
        "manifest_hash": bundle.manifest.manifest_hash,
        "corpus_hash": bundle.corpus.corpus_hash,
        "corpus_file_count": len(bundle.manifest.files),
        "corpus_chunk_count": len(bundle.corpus.chunks),
        "case_pack": case_pack.summary(),
        "production_readiness": "not_production_ready",
    }
    _print(payload, error=not case_pack.portfolio_ready)
    return 0 if case_pack.portfolio_ready else 2


def _command_review_worksheet(args: argparse.Namespace) -> int:
    bundle, case_pack = _validated_inputs(args)
    root, _, _, _ = _paths(args)
    output_path = (
        Path(args.output).resolve()
        if args.output
        else root / "reference_workload" / "review_worksheet.csv"
    )
    write_review_worksheet(
        output_path,
        case_pack=case_pack,
        corpus_bundle=bundle,
    )
    _print(
        {
            "status": "review_worksheet_written",
            "output_path": str(output_path),
            "case_count": len(case_pack.cases),
            "approved_case_count": case_pack.approved_case_count,
            "approval_fields_populated": False,
        }
    )
    return 0


def _assistance_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    root, _, _, _ = _paths(args)
    directory = root / "reference_workload"
    return (
        Path(args.output_json).resolve()
        if args.output_json
        else directory / "review_assistance.json",
        Path(args.output_csv).resolve() if args.output_csv else directory / "review_assistance.csv",
        Path(args.attestation).resolve()
        if args.attestation
        else directory / "review_attestation.json",
    )


def _command_review_assist(args: argparse.Namespace) -> int:
    bundle, case_pack = _validated_inputs(args)
    report = build_review_assistance_report(
        case_pack=case_pack,
        corpus_bundle=bundle,
    )
    output_json, output_csv, attestation = _assistance_paths(args)
    write_review_assistance_artifacts(
        report=report,
        json_path=output_json,
        csv_path=output_csv,
        attestation_path=attestation,
    )
    root, _, _, _ = _paths(args)
    output_html = (
        Path(args.output_html).resolve()
        if args.output_html
        else root / "reference_workload" / "review_assistance.html"
    )
    write_review_assistance_html(output_html, report=report)
    _print(
        {
            "status": "machine_review_assistance_written",
            "report_sha256": report["report_sha256"],
            "summary": report["summary"],
            "output_json": str(output_json),
            "output_csv": str(output_csv),
            "output_html": str(output_html),
            "attestation": str(attestation),
            "human_approval_recorded": False,
            "production_readiness": "not_production_ready",
        }
    )
    return 0


def _command_finalize_assisted_review(args: argparse.Namespace) -> int:
    bundle, case_pack = _validated_inputs(args)
    current_report = build_review_assistance_report(
        case_pack=case_pack,
        corpus_bundle=bundle,
    )
    root, _, _, reviews = _paths(args)
    report_path = (
        Path(args.report).resolve()
        if args.report
        else root / "reference_workload" / "review_assistance.json"
    )
    attestation_path = (
        Path(args.attestation).resolve()
        if args.attestation
        else root / "reference_workload" / "review_attestation.json"
    )
    summary = finalize_assisted_review(
        current_report=current_report,
        report_path=report_path,
        attestation_path=attestation_path,
        output_path=reviews,
    )
    _print(summary)
    return 0


def _command_bootstrap(args: argparse.Namespace) -> int:
    bundle, case_pack = _validated_inputs(args)
    with SessionLocal() as db:
        summary = bootstrap_reference_workload(
            db,
            corpus_bundle=bundle,
            case_pack=case_pack,
        )
    _print(summary)
    return 0


def _command_retrieval_audit(args: argparse.Namespace) -> int:
    bundle, case_pack = _validated_inputs(args)
    root, _, _, _ = _paths(args)
    output_path = (
        Path(args.output).resolve()
        if args.output
        else root / "artifacts" / "reference-workload" / "retrieval-contract-audit.json"
    )
    report = build_retrieval_contract_audit(
        case_pack=case_pack,
        corpus_bundle=bundle,
        case_ids=args.case_id,
    )
    write_retrieval_contract_audit(output_path, report)
    payload = {**report, "output_path": str(output_path)}
    blocked = report["summary"]["blocked_case_count"] > 0
    _print(payload, error=blocked)
    return 2 if blocked else 0


def _command_create_case_revision(args: argparse.Namespace) -> int:
    root, _, _, _ = _paths(args)
    report = create_case_pack_revision(
        repository_root=root,
        spec_path=Path(args.spec),
        output_directory=Path(args.output_directory),
    )
    blocked = report["summary"]["retrieval_contract_status"] != "pass"
    _print(report, error=blocked)
    return 2 if blocked else 0


def _command_case_revision_review(args: argparse.Namespace) -> int:
    write_case_revision_review_html(Path(args.report), Path(args.output))
    _print(
        {
            "status": "case_revision_review_written",
            "report": str(Path(args.report).resolve()),
            "output": str(Path(args.output).resolve()),
            "production_readiness": "not_production_ready",
        }
    )
    return 0


def _command_finalize_case_revision(args: argparse.Namespace) -> int:
    root, _, _, _ = _paths(args)
    report = finalize_case_pack_revision(
        repository_root=root,
        output_directory=Path(args.output_directory),
        attestation_path=Path(args.attestation),
    )
    _print(report, error=not report["case_pack"]["portfolio_ready"])
    return 0 if report["case_pack"]["portfolio_ready"] else 2


def _command_run(args: argparse.Namespace) -> int:
    bundle, case_pack = _validated_inputs(args)
    root, _, _, _ = _paths(args)
    matrix_path = Path(args.matrix).resolve()
    matrix = load_runtime_matrix(matrix_path)
    environment = dict(os.environ)
    if args.base_url:
        environment["REFERENCE_RUNTIME_BASE_URL"] = args.base_url
    if args.small_model:
        environment["REFERENCE_MODEL_SMALL"] = args.small_model
    if args.medium_model:
        environment["REFERENCE_MODEL_MEDIUM"] = args.medium_model
    output_path = (
        Path(args.output).resolve()
        if args.output
        else root / "artifacts" / "reference-workload" / f"runtime-matrix-{args.mode}.json"
    )
    with SessionLocal() as db:
        bootstrap = bootstrap_reference_workload(
            db,
            corpus_bundle=bundle,
            case_pack=case_pack,
        )
        result = execute_runtime_matrix(
            db,
            matrix=matrix,
            workload_profile_id=UUID(bootstrap["workload_profile_id"]),
            evaluation_suite_id=UUID(bootstrap["evaluation_suite_id"]),
            corpus_bundle=bundle,
            mode=args.mode,
            environment=environment,
            max_cases=args.max_cases,
            case_ids=args.case_id,
            case_timeout_ms=args.case_timeout_ms,
        )
    write_runtime_matrix_result(output_path, result)
    payload = {**result, "output_path": str(output_path)}
    _print(payload, error=result["summary"]["completed_entry_count"] == 0)
    return 0 if result["summary"]["completed_entry_count"] > 0 else 2


def _command_compare_runtime(args: argparse.Namespace) -> int:
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve() if args.output else input_path
    try:
        matrix_result = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeMatrixError(f"runtime matrix result could not be read: {exc}") from exc
    with SessionLocal() as db:
        result = build_stored_runtime_comparison(db, matrix_result)
    write_runtime_matrix_result(output_path, result)
    _print(
        {
            "status": "stored_runtime_comparison_written",
            "output_path": str(output_path),
            "comparison": result["stored_comparison"],
            "production_readiness": "not_production_ready",
        }
    )
    return 0


def _command_gate(args: argparse.Namespace) -> int:
    with SessionLocal() as db:
        summary = run_reference_workload_gates(db)
    _print(summary.model_dump(mode="json"), error=summary.blocked_count > 0)
    return 0 if summary.blocked_count == 0 else 2


def _command_report(args: argparse.Namespace) -> int:
    root, _, _, _ = _paths(args)
    output_directory = (
        Path(args.output_directory).resolve()
        if args.output_directory
        else root / "artifacts" / "reference-workload"
    )
    with SessionLocal() as db:
        report = build_reference_workload_report(db)
    summary = write_reference_workload_artifacts(report, output_directory)
    _print(summary.model_dump(mode="json"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Model Atlas Sprint 6A reference workload")
    parser.add_argument("--repository-root")
    parser.add_argument("--manifest")
    parser.add_argument("--cases")
    parser.add_argument("--reviews")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("lock-manifest")
    draft = commands.add_parser("draft-cases")
    draft.add_argument("--force", action="store_true")
    worksheet = commands.add_parser("review-worksheet")
    worksheet.add_argument("--output")
    assistance = commands.add_parser("review-assist")
    assistance.add_argument("--output-json")
    assistance.add_argument("--output-csv")
    assistance.add_argument("--output-html")
    assistance.add_argument("--attestation")
    finalize = commands.add_parser("finalize-assisted-review")
    finalize.add_argument("--report")
    finalize.add_argument("--attestation")
    commands.add_parser("validate")
    commands.add_parser("bootstrap")
    case_revision = commands.add_parser("create-case-revision")
    case_revision.add_argument("--spec", required=True)
    case_revision.add_argument("--output-directory", required=True)
    case_revision_review = commands.add_parser("case-revision-review")
    case_revision_review.add_argument("--report", required=True)
    case_revision_review.add_argument("--output", required=True)
    finalize_revision = commands.add_parser("finalize-case-revision")
    finalize_revision.add_argument("--output-directory", required=True)
    finalize_revision.add_argument("--attestation", required=True)
    retrieval_audit = commands.add_parser("audit-retrieval-contracts")
    retrieval_audit.add_argument("--case-id", action="append")
    retrieval_audit.add_argument("--output")
    run = commands.add_parser("run")
    run.add_argument(
        "--mode",
        choices=("smoke", "portfolio", "diagnostic"),
        required=True,
    )
    run.add_argument("--matrix", required=True)
    run.add_argument("--output")
    run.add_argument("--base-url")
    run.add_argument("--small-model")
    run.add_argument("--medium-model")
    run.add_argument("--max-cases", type=int)
    run.add_argument(
        "--case-id",
        action="append",
        help="Explicit active reference case ID; repeat in diagnostic mode.",
    )
    run.add_argument("--case-timeout-ms", type=int, default=120_000)
    compare_runtime = commands.add_parser("compare-runtime")
    compare_runtime.add_argument("--input", required=True)
    compare_runtime.add_argument("--output")
    commands.add_parser("gate")
    report = commands.add_parser("report")
    report.add_argument("--output-directory")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    commands = {
        "lock-manifest": _command_lock,
        "draft-cases": _command_draft,
        "review-worksheet": _command_review_worksheet,
        "review-assist": _command_review_assist,
        "finalize-assisted-review": _command_finalize_assisted_review,
        "validate": _command_validate,
        "bootstrap": _command_bootstrap,
        "create-case-revision": _command_create_case_revision,
        "case-revision-review": _command_case_revision_review,
        "finalize-case-revision": _command_finalize_case_revision,
        "audit-retrieval-contracts": _command_retrieval_audit,
        "run": _command_run,
        "compare-runtime": _command_compare_runtime,
        "gate": _command_gate,
        "report": _command_report,
    }
    try:
        status = commands[args.command](args)
    except ReferenceWorkloadApprovalRequired as exc:
        _print(
            {
                "status": "blocked_human_review_required",
                "message": str(exc),
                "case_pack": exc.case_pack.summary(),
                "production_readiness": "not_production_ready",
            },
            error=True,
        )
        status = 2
    except (
        CasePackValidationError,
        CasePackRevisionError,
        ManifestValidationError,
        ReferenceBootstrapConflict,
        RetrievalContractAuditError,
        ReviewAssistanceError,
        RuntimeMatrixError,
    ) as exc:
        _print({"status": "invalid", "message": str(exc)}, error=True)
        status = 2
    raise SystemExit(status)


if __name__ == "__main__":
    main()
