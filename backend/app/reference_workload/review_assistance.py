from __future__ import annotations

import csv
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.reference_workload.cases import ReferenceCasePack
from app.reference_workload.contracts import (
    REFERENCE_REVIEW_SCHEMA_VERSION,
    REFERENCE_WORKLOAD_SLUG,
    ReferenceCaseContract,
)
from app.reference_workload.corpus import ReferenceCorpusBundle
from app.reference_workload.manifest import canonical_json, stable_hash
from app.services.rag_evidence_contract import parse_rag_evidence_expectation
from app.services.tool_execution import DEFAULT_TOOL_REGISTRY

REVIEW_ASSISTANCE_SCHEMA_VERSION = "model-atlas-review-assistance-v1"
REVIEW_ATTESTATION_SCHEMA_VERSION = "model-atlas-review-attestation-v1"
REVIEW_ATTESTATION_STATEMENT = (
    "I personally reviewed the automated report and every required spot-check case."
)

_HIGH_RISK_CATEGORIES = {
    "insufficient_evidence_refusal",
    "tool_failure_recovery",
    "agent_multi_step",
}
_MACHINE_REVIEWER_PATTERN = re.compile(
    r"(^|[-_ ])(codex|openai|automated|automation|machine|llm|ai[-_ ]?reviewer|test)([-_ ]|$)",
    re.IGNORECASE,
)


class ReviewAssistanceError(ValueError):
    pass


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+|[\uac00-\ud7a3]+", value.lower())
        if len(token) > 1
    }


def _query(case: ReferenceCaseContract) -> str:
    return next(
        (
            str(case.input_payload[key]).strip()
            for key in ("query", "request", "question")
            if isinstance(case.input_payload.get(key), str)
            and str(case.input_payload[key]).strip()
        ),
        "",
    )


def _check(
    check_id: str,
    passed: bool,
    detail: str,
    *,
    severity: str = "blocker",
    observed: Any = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "passed": passed,
        "severity": severity,
        "detail": detail,
        **({"observed": observed} if observed is not None else {}),
    }


def _source_evidence(
    case: ReferenceCaseContract,
    *,
    chunk_map: dict[str, Any],
) -> list[dict[str, Any]]:
    reference = case.reference_context or {}
    rag = reference.get("rag") if isinstance(reference.get("rag"), dict) else {}
    chunk_ids = (
        list(parse_rag_evidence_expectation(rag).acceptable_chunk_ids) if rag else []
    )
    evidence: list[dict[str, Any]] = []
    for chunk_id in chunk_ids:
        chunk = chunk_map.get(str(chunk_id))
        if chunk is None:
            continue
        evidence.append(
            {
                "chunk_id": chunk.chunk_id,
                "source_path": chunk.document_id,
                "heading_path": list(chunk.metadata.get("heading_path", [])),
                "source_sha256": chunk.metadata.get("source_sha256"),
                "chunk_sha256": chunk.metadata.get("chunk_sha256"),
                "excerpt": " ".join(chunk.text.split())[:360],
            }
        )
    return evidence


def _expected_output_checks(case: ReferenceCaseContract) -> list[dict[str, Any]]:
    expected = case.expected_output if isinstance(case.expected_output, dict) else {}
    reference = case.reference_context or {}
    agent = reference.get("agent") if isinstance(reference.get("agent"), dict) else {}
    expected_steps = agent.get("expected_steps", [])
    respond_steps = [
        step
        for step in expected_steps
        if isinstance(step, dict) and step.get("action") == "respond"
    ]
    if case.category in {"agent_multi_step", "rag_tool_combined"}:
        response_contract_valid = bool(respond_steps) and all(
            isinstance(step.get("required_terms"), list) and bool(step["required_terms"])
            for step in respond_steps
        )
        return [
            _check(
                "agent_response_contract",
                response_contract_valid,
                "Agent response steps contain non-empty required terms.",
            )
        ]
    facts = expected.get("required_facts")
    forbidden = expected.get("forbidden_claims")
    must_refuse = expected.get("must_refuse")
    facts_valid = (
        isinstance(facts, list)
        and bool(facts)
        and all(isinstance(value, str) and value.strip() for value in facts)
    )
    forbidden_valid = isinstance(forbidden, list) and all(
        isinstance(value, str) and value.strip() for value in forbidden
    )
    checks = [
        _check(
            "required_facts_contract",
            facts_valid,
            "Required facts are a non-empty list of strings.",
            observed=len(facts) if isinstance(facts, list) else None,
        ),
        _check(
            "forbidden_claims_contract",
            forbidden_valid,
            "Forbidden claims are represented as a list of strings.",
            observed=len(forbidden) if isinstance(forbidden, list) else None,
        ),
    ]
    if case.category == "insufficient_evidence_refusal":
        checks.append(
            _check(
                "refusal_contract",
                must_refuse is True and isinstance(forbidden, list) and bool(forbidden),
                "Refusal cases require must_refuse=true and at least one forbidden claim.",
            )
        )
    else:
        checks.append(
            _check(
                "refusal_contract",
                must_refuse is False,
                "Non-refusal cases explicitly use must_refuse=false.",
            )
        )
    return checks


def _rag_checks(
    case: ReferenceCaseContract,
    *,
    bundle: ReferenceCorpusBundle,
    evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    reference = case.reference_context or {}
    rag = reference.get("rag") if isinstance(reference.get("rag"), dict) else None
    requires_rag = case.category.startswith("rag_")
    if rag is None:
        return [
            _check(
                "rag_reference_integrity",
                not requires_rag,
                "A RAG reference is present when the category requires one.",
            )
        ]
    corpus_matches = (
        rag.get("corpus_id") == bundle.corpus.corpus_id
        and rag.get("corpus_version") == bundle.corpus.corpus_version
        and rag.get("corpus_hash") == bundle.corpus.corpus_hash
        and bool(evidence)
    )
    expected = case.expected_output if isinstance(case.expected_output, dict) else {}
    facts = expected.get("required_facts", [])
    fact_tokens = _tokens(" ".join(str(value) for value in facts))
    evidence_tokens = _tokens(" ".join(item["excerpt"] for item in evidence))
    overlap = sorted(fact_tokens & evidence_tokens)
    overlap_ratio = len(overlap) / len(fact_tokens) if fact_tokens else 0.0
    return [
        _check(
            "rag_reference_integrity",
            corpus_matches,
            "RAG case references the current corpus hash and known source chunks.",
            observed=len(evidence),
        ),
        _check(
            "source_term_overlap",
            not fact_tokens or bool(overlap),
            (
                "Required-fact terms overlap the selected source excerpts. "
                "Agent cases without top-level facts are checked through their step contract. "
                "This lexical signal does not prove semantic correctness."
            ),
            severity="advisory",
            observed={"ratio": round(overlap_ratio, 4), "terms": overlap[:12]},
        ),
    ]


def _tool_checks(case: ReferenceCaseContract) -> list[dict[str, Any]]:
    expected = case.expected_tool_schema
    requires_tool = case.category in {
        "tool_single_step",
        "tool_failure_recovery",
        "rag_tool_combined",
        "agent_multi_step",
    }
    if not isinstance(expected, dict):
        return [
            _check(
                "tool_contract",
                not requires_tool,
                "A Tool contract is present when the category requires one.",
            )
        ]
    tool_name = expected.get("tool_name")
    registered = DEFAULT_TOOL_REGISTRY.get(str(tool_name)) if tool_name else None
    arguments = expected.get("arguments")
    arguments_valid = (
        isinstance(arguments, dict)
        and arguments.get("type") == "object"
        and isinstance(arguments.get("required"), list)
        and isinstance(arguments.get("properties"), dict)
        and arguments.get("additionalProperties") is False
    )
    compatible = False
    if registered is not None and arguments_valid:
        registry_schema = registered.descriptor.argument_schema
        expected_properties = set(arguments["properties"])
        registry_properties = set(registry_schema.get("properties", {}))
        registry_required = set(registry_schema.get("required", []))
        expected_required = set(arguments["required"])
        compatible = (
            expected_properties <= registry_properties
            and registry_required <= expected_required
        )
    checks = [
        _check(
            "tool_registry_membership",
            registered is not None,
            "Expected Tool is present in the bounded local Tool Registry.",
            observed=tool_name,
        ),
        _check(
            "tool_argument_contract",
            arguments_valid and compatible,
            "Expected arguments are closed and compatible with the registered Tool schema.",
        ),
    ]
    if case.category == "tool_failure_recovery":
        required = arguments.get("required", []) if isinstance(arguments, dict) else []
        checks.append(
            _check(
                "bounded_recovery_contract",
                expected.get("max_attempts") == 2 and "simulate_failure" in required,
                "Recovery cases require one bounded retry and an explicit failure fixture.",
            )
        )
    return checks


def _agent_checks(case: ReferenceCaseContract) -> list[dict[str, Any]]:
    if case.category not in {"agent_multi_step", "rag_tool_combined"}:
        return []
    reference = case.reference_context or {}
    agent = reference.get("agent") if isinstance(reference.get("agent"), dict) else {}
    bounded = (
        1 <= int(agent.get("max_steps", 0)) <= 3
        and int(agent.get("max_tool_calls", 0)) <= 1
        and int(agent.get("max_retrievals", 0)) <= 1
        and agent.get("allow_memory_write") is False
        and bool(agent.get("allowed_tools"))
    )
    return [
        _check(
            "bounded_agent_contract",
            bounded,
            "Agent execution is bounded to three steps, one Tool call, and one retrieval.",
        )
    ]


def _case_item(
    case: ReferenceCaseContract,
    *,
    case_hash: str,
    bundle: ReferenceCorpusBundle,
    chunk_map: dict[str, Any],
    duplicate_queries: set[str],
) -> dict[str, Any]:
    evidence = _source_evidence(case, chunk_map=chunk_map)
    checks = [
        _check(
            "draft_provenance",
            case.review.status in {"draft", "approved"},
            "Source case is a draft or has a separate hash-bound approval.",
        ),
        *_expected_output_checks(case),
        *_rag_checks(case, bundle=bundle, evidence=evidence),
        *_tool_checks(case),
        *_agent_checks(case),
        _check(
            "unique_query",
            _query(case) not in duplicate_queries,
            "No other case has the exact same normalized query.",
            severity="advisory",
        ),
    ]
    blockers = [check for check in checks if not check["passed"] and check["severity"] == "blocker"]
    advisories = [
        check for check in checks if not check["passed"] and check["severity"] == "advisory"
    ]
    risk_reasons: list[str] = []
    if case.criticality == "critical":
        risk_reasons.append("critical_case")
    if case.category in _HIGH_RISK_CATEGORIES:
        risk_reasons.append(f"high_risk_category:{case.category}")
    risk_reasons.extend(f"advisory:{check['check_id']}" for check in advisories)
    if blockers:
        recommendation = "repair_required"
        risk_reasons.extend(f"blocker:{check['check_id']}" for check in blockers)
    elif risk_reasons:
        recommendation = "spot_check_required"
    else:
        recommendation = "eligible_for_bulk_review"
    return {
        "external_case_id": case.external_case_id,
        "case_sha256": case_hash,
        "category": case.category,
        "criticality": case.criticality,
        "title": case.title,
        "query_or_request": _query(case),
        "machine_recommendation": recommendation,
        "risk_reasons": risk_reasons,
        "expected_contract": {
            "expected_output": case.expected_output,
            "expected_tool_schema": case.expected_tool_schema,
            "agent": (case.reference_context or {}).get("agent"),
        },
        "checks": checks,
        "source_evidence": evidence,
    }


def review_report_hash(report: dict[str, Any]) -> str:
    return stable_hash(
        {
            key: value
            for key, value in report.items()
            if key not in {"generated_at", "report_sha256"}
        }
    )


def build_review_assistance_report(
    *,
    case_pack: ReferenceCasePack,
    corpus_bundle: ReferenceCorpusBundle,
) -> dict[str, Any]:
    queries = [_query(case).casefold() for case in case_pack.cases]
    duplicate_queries = {value for value in queries if queries.count(value) > 1}
    chunk_map = {chunk.chunk_id: chunk for chunk in corpus_bundle.corpus.chunks}
    items = [
        _case_item(
            case,
            case_hash=case_pack.case_hashes[case.external_case_id],
            bundle=corpus_bundle,
            chunk_map=chunk_map,
            duplicate_queries=duplicate_queries,
        )
        for case in case_pack.cases
    ]
    for category in sorted({item["category"] for item in items}):
        sample_candidates = sorted(
            (
                item
                for item in items
                if item["category"] == category
                and item["criticality"] != "critical"
                and item["machine_recommendation"] == "spot_check_required"
            ),
            key=lambda item: item["external_case_id"],
        )
        for item in sample_candidates[1:]:
            item["machine_recommendation"] = "eligible_for_bulk_review"
            item["sampling_disposition"] = "covered_by_one_noncritical_category_sample"
        if sample_candidates:
            sample_candidates[0]["sampling_disposition"] = "selected_category_risk_sample"
    counts = {
        recommendation: sum(
            item["machine_recommendation"] == recommendation for item in items
        )
        for recommendation in (
            "eligible_for_bulk_review",
            "spot_check_required",
            "repair_required",
        )
    }
    required_case_ids = [
        item["external_case_id"]
        for item in items
        if item["machine_recommendation"] != "eligible_for_bulk_review"
    ]
    report: dict[str, Any] = {
        "schema_version": REVIEW_ASSISTANCE_SCHEMA_VERSION,
        "workload_slug": REFERENCE_WORKLOAD_SLUG,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "manifest_sha256": corpus_bundle.manifest.manifest_hash,
        "corpus_sha256": corpus_bundle.corpus.corpus_hash,
        "case_pack_sha256": stable_hash(
            sorted(case_pack.case_hashes.items(), key=lambda item: item[0])
        ),
        "automation_boundary": {
            "machine_review_only": True,
            "human_approval_required": True,
            "production_readiness": "not_production_ready",
        },
        "summary": {
            "case_count": len(items),
            **counts,
            "required_human_case_count": len(required_case_ids),
            "required_human_case_ids": required_case_ids,
        },
        "items": items,
    }
    report["report_sha256"] = review_report_hash(report)
    return report


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_review_assistance_artifacts(
    *,
    report: dict[str, Any],
    json_path: Path,
    csv_path: Path,
    attestation_path: Path,
) -> None:
    _write_json(json_path, report)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_csv = csv_path.with_suffix(csv_path.suffix + ".tmp")
    with temporary_csv.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "external_case_id",
                "category",
                "criticality",
                "title",
                "machine_recommendation",
                "risk_reasons",
                "failed_checks",
                "source_paths",
                "case_sha256",
            ],
        )
        writer.writeheader()
        for item in report["items"]:
            writer.writerow(
                {
                    "external_case_id": item["external_case_id"],
                    "category": item["category"],
                    "criticality": item["criticality"],
                    "title": item["title"],
                    "machine_recommendation": item["machine_recommendation"],
                    "risk_reasons": " | ".join(item["risk_reasons"]),
                    "failed_checks": " | ".join(
                        check["check_id"] for check in item["checks"] if not check["passed"]
                    ),
                    "source_paths": " | ".join(
                        sorted({evidence["source_path"] for evidence in item["source_evidence"]})
                    ),
                    "case_sha256": item["case_sha256"],
                }
            )
    temporary_csv.replace(csv_path)
    _write_json(
        attestation_path,
        {
            "schema_version": REVIEW_ATTESTATION_SCHEMA_VERSION,
            "review_report_sha256": report["report_sha256"],
            "reviewer": "",
            "attestation": REVIEW_ATTESTATION_STATEMENT,
            "approve_automated_passes": False,
            "required_case_ids": report["summary"]["required_human_case_ids"],
            "confirmed_case_ids": [],
            "notes": "",
        },
    )


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReviewAssistanceError(f"review artifact is missing: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewAssistanceError(f"review artifact is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ReviewAssistanceError(f"review artifact must be a JSON object: {path}")
    return payload


def finalize_assisted_review(
    *,
    current_report: dict[str, Any],
    report_path: Path,
    attestation_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    stored_report = _load_object(report_path)
    observed_report_hash = review_report_hash(stored_report)
    if stored_report.get("report_sha256") != observed_report_hash:
        raise ReviewAssistanceError("stored review report hash is invalid")
    if observed_report_hash != current_report["report_sha256"]:
        raise ReviewAssistanceError("review report is stale relative to the current case pack")
    if int(stored_report.get("summary", {}).get("repair_required", 0)) > 0:
        raise ReviewAssistanceError("repair-required cases must be corrected before approval")

    attestation = _load_object(attestation_path)
    if attestation.get("schema_version") != REVIEW_ATTESTATION_SCHEMA_VERSION:
        raise ReviewAssistanceError("unsupported review attestation schema")
    if attestation.get("review_report_sha256") != observed_report_hash:
        raise ReviewAssistanceError("attestation is not bound to the current review report")
    reviewer = str(attestation.get("reviewer", "")).strip()
    if len(reviewer) < 2 or _MACHINE_REVIEWER_PATTERN.search(reviewer):
        raise ReviewAssistanceError("attestation requires a real human reviewer identity")
    if attestation.get("attestation") != REVIEW_ATTESTATION_STATEMENT:
        raise ReviewAssistanceError("the required personal-review attestation is missing")
    if attestation.get("approve_automated_passes") is not True:
        raise ReviewAssistanceError("automated-pass cases were not explicitly approved")
    notes = str(attestation.get("notes", "")).strip()
    if not notes:
        raise ReviewAssistanceError("attestation notes are required")
    required_ids = sorted(stored_report["summary"]["required_human_case_ids"])
    confirmed_ids = sorted(str(value) for value in attestation.get("confirmed_case_ids", []))
    if confirmed_ids != required_ids:
        raise ReviewAssistanceError(
            "confirmed_case_ids must exactly match every required spot-check case"
        )

    reviewed_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    records = [
        {
            "schema_version": REFERENCE_REVIEW_SCHEMA_VERSION,
            "external_case_id": item["external_case_id"],
            "case_sha256": item["case_sha256"],
            "decision": "approved",
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "notes": (
                f"Human-assisted batch review bound to report {observed_report_hash}. {notes}"
            ),
        }
        for item in stored_report["items"]
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        "".join(canonical_json(record) + "\n" for record in records),
        encoding="utf-8",
    )
    temporary.replace(output_path)
    return {
        "status": "human_attestation_recorded",
        "review_report_sha256": observed_report_hash,
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "approved_case_count": len(records),
        "output_path": str(output_path),
        "production_readiness": "not_production_ready",
    }
