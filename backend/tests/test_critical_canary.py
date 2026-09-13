from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models import BenchmarkResult
from app.reference_workload import critical_canary as canary


def inputs():
    state = canary._seal(
        {
            "schema_version": canary.VERSION,
            "kind": "snapshot",
            "official": {"protected_run_ids": [str(uuid4())], "failure_count": 110},
            "source_sha256": {"app/example.py": "abc"},
            "expected_case_ids": ["CASE-1", "CASE-2"],
            "expected_entry_names": ["small"],
            "matrix_hash": "matrix-hash",
        }
    )
    matrix = {
        "schema_version": canary.RUNTIME_MATRIX_RESULT_VERSION,
        "mode": "diagnostic",
        "matrix_hash": "matrix-hash",
        "evaluation_suite_id": str(uuid4()),
        "suite_hash": "suite-hash",
        "production_readiness": "not_production_ready",
        "diagnostic_scope": {
            "case_ids": ["CASE-1", "CASE-2"],
            "gate_evidence": False,
            "authoritative_portfolio_evidence": False,
        },
        "entries": [
            {
                "name": "small",
                "enabled": True,
                "status": "completed",
                "trials": 1,
                "benchmark_run_id": str(uuid4()),
                "deployment_configuration_id": str(uuid4()),
                "configuration_hash": "config-hash",
                "result_count": 2,
                "metric_count": 2,
            }
        ],
    }
    return state, copy.deepcopy(state), matrix


def test_valid_scope_and_hash_roundtrip():
    before, after, matrix = inputs()
    canary._verify(json.loads(json.dumps(before)))
    assert len(canary.validate_scope(before, after, matrix)) == 1


def test_tampered_snapshot_rejected():
    before, after, matrix = inputs()
    after["official"]["failure_count"] = 0
    with pytest.raises(ValueError, match="hash mismatch"):
        canary.validate_scope(before, after, matrix)


@pytest.mark.parametrize("key", ["official", "source_sha256", "matrix_hash"])
def test_protected_change_rejected_even_when_resealed(key):
    before, after, matrix = inputs()
    after.pop("content_sha256")
    after[key] = "changed"
    with pytest.raises(ValueError, match="protected state changed"):
        canary.validate_scope(before, canary._seal(after), matrix)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mode", "portfolio"),
        ("matrix_hash", "other"),
        ("production_readiness", "production_ready"),
        ("schema_version", "unknown"),
    ],
)
def test_non_diagnostic_input_rejected(field, value):
    before, after, matrix = inputs()
    matrix[field] = value
    with pytest.raises(ValueError, match="isolated diagnostic"):
        canary.validate_scope(before, after, matrix)


@pytest.mark.parametrize("flag", ["gate_evidence", "authoritative_portfolio_evidence"])
@pytest.mark.parametrize("value", [True, None, 0])
def test_evidence_boundary_requires_explicit_false(flag, value):
    before, after, matrix = inputs()
    matrix["diagnostic_scope"][flag] = value
    with pytest.raises(ValueError, match="isolated diagnostic"):
        canary.validate_scope(before, after, matrix)


@pytest.mark.parametrize("case_ids", [[], ["CASE-1"], ["CASE-1", "CASE-1"], ["CASE-1", "NEW"]])
def test_case_coverage_rejected(case_ids):
    before, after, matrix = inputs()
    matrix["diagnostic_scope"]["case_ids"] = case_ids
    with pytest.raises(ValueError, match="case coverage"):
        canary.validate_scope(before, after, matrix)


@pytest.mark.parametrize("change", ["missing", "duplicate", "failed", "trials", "official"])
def test_entry_coverage_and_identity_rejected(change):
    before, after, matrix = inputs()
    entry = matrix["entries"][0]
    if change == "missing":
        matrix["entries"] = []
    elif change == "duplicate":
        matrix["entries"].append(copy.deepcopy(entry))
    elif change == "failed":
        entry["status"] = "failed"
    elif change == "trials":
        entry["trials"] = 2
    else:
        entry["benchmark_run_id"] = before["official"]["protected_run_ids"][0]
    with pytest.raises(ValueError):
        canary.validate_scope(before, after, matrix)


def rows():
    return [
        {
            "entry": "small",
            "external_case_id": f"CASE-{index}",
            "benchmark_result_id": str(uuid4()),
            "category": "tool_single_step",
            "status": status,
        }
        for index, status in enumerate(("pass", "fail"), start=1)
    ]


def test_summary_keeps_failure_and_uses_observation_denominator():
    summary = canary.summarize_rows(rows(), case_ids=["CASE-1", "CASE-2"], entry_names=["small"])
    assert summary["observation_count"] == 2
    assert summary["pass_count"] == summary["failure_count"] == 1
    assert summary["remaining_case_ids"] == ["CASE-2"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "foreign", "result_id", "status"])
def test_invalid_observation_coverage_rejected(change):
    data = rows()
    if change == "missing":
        data.pop()
    elif change == "duplicate":
        data.append(data[0])
    elif change == "foreign":
        data[0]["entry"] = "other"
    elif change == "result_id":
        data[1]["benchmark_result_id"] = data[0]["benchmark_result_id"]
    else:
        data[0]["status"] = "unknown"
    with pytest.raises(ValueError):
        canary.summarize_rows(data, case_ids=["CASE-1", "CASE-2"], entry_names=["small"])


@pytest.mark.parametrize(
    "change", [None, "source", "metric_missing", "noncritical", "foreign_suite"]
)
def test_audit_reuses_evaluator_and_checks_stored_scope(monkeypatch, change):
    before, after, matrix = inputs()
    entry = matrix["entries"][0]
    suite_id = matrix["evaluation_suite_id"]
    configuration = SimpleNamespace(
        configuration_hash="config-hash",
        runtime_config_json={"reference_workload_mode": "diagnostic"},
    )
    run = SimpleNamespace(
        id=entry["benchmark_run_id"],
        status="completed",
        data_source=canary.DIAGNOSTIC_RUNTIME_DATA_SOURCE,
        deployment_configuration_id=entry["deployment_configuration_id"],
        deployment_configuration=configuration,
        evaluation_suite_id=suite_id,
        evaluation_suite=SimpleNamespace(suite_hash="suite-hash"),
    )
    cases = [
        SimpleNamespace(
            id=uuid4(),
            external_case_id=f"CASE-{i}",
            evaluation_suite_id=suite_id,
            criticality="critical",
            category="agent_multi_step",
            title=f"Case {i}",
            expected_output_json=None,
            expected_tool_schema_json=None,
        )
        for i in (1, 2)
    ]
    results = [
        BenchmarkResult(
            id=uuid4(),
            benchmark_run_id=run.id,
            evaluation_case_id=case.id,
            sample_id=f"sample-{i}",
            quality_score=1.0 if i == 0 else 0.0,
            data_source=canary.DIAGNOSTIC_RUNTIME_DATA_SOURCE,
        )
        for i, case in enumerate(cases)
    ]
    metrics = [
        SimpleNamespace(sample_id=item.sample_id, data_source=item.data_source) for item in results
    ]
    if change == "source":
        results[0].data_source = "local_actual_runtime"
    elif change == "metric_missing":
        metrics.pop()
    elif change == "noncritical":
        cases[0].criticality = "normal"
    elif change == "foreign_suite":
        cases[0].evaluation_suite_id = "other"
    responses = iter((results, metrics, cases))
    db = SimpleNamespace(get=lambda *args: run, scalars=lambda *args: next(responses))
    monkeypatch.setattr(
        canary, "_record", lambda entity: {"sample_id": getattr(entity, "sample_id", None)}
    )
    if change:
        with pytest.raises(ValueError):
            canary.audit(db, before=before, after=after, matrix=matrix)
    else:
        report = canary.audit(db, before=before, after=after, matrix=matrix)
        canary._verify(report)
        assert report["gate_evidence"] is False
        assert report["human_reviewed"] is False
        assert report["summary"]["pass_count"] == 1
        assert report["summary"]["failure_count"] == 1
