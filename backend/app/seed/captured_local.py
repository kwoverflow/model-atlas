from __future__ import annotations

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import (
    AcceptancePolicy,
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

CAPTURED_SUITE_NAME = "Korean Operations Assistant Captured Local Suite"
CAPTURED_SUITE_VERSION = "v1-captured-local"
CAPTURED_DATA_SOURCE = "captured_local"
STRICT_POLICY_NAME = "Strict Local Release Policy"


def _json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["answer", "confidence", "evidence"],
        "properties": {
            "answer": {"type": "string"},
            "confidence": {"type": "number"},
            "evidence": {"type": "string"},
        },
    }


def _tool_schema(tool_name: str) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "arguments": {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        },
    }


def _case_payloads(suite_id: Any) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for index in range(1, 13):
        critical = index <= 4
        payloads.append(
            {
                "evaluation_suite_id": suite_id,
                "external_case_id": f"captured-json-{index:03d}",
                "category": "json_extraction",
                "title": f"Captured JSON extraction case {index:02d}",
                "input_payload_json": {
                    "document": (
                        f"운영 메모 {index}: 담당자는 Ops-{index % 5 + 1}팀이고, "
                        f"마감일은 2026-07-{10 + index:02d}입니다. "
                        "요청 사항은 장애 원인 기록, 고객 안내 초안 작성, "
                        "재발 방지 조치 등록입니다."
                    ),
                    "instruction": (
                        "Return one JSON object with keys answer, confidence, evidence. "
                        "Use a short Korean answer string."
                    ),
                },
                "expected_output_json": _json_schema(),
                "reference_context_json": {
                    "source": "operator-authored-local-case",
                    "required_keys": ["answer", "confidence", "evidence"],
                },
                "expected_tool_schema_json": None,
                "tags_json": ["captured_local", "json", "operations"],
                "criticality": "critical" if critical else "standard",
                "weight": 1.0,
                "is_active": True,
                "data_source": CAPTURED_DATA_SOURCE,
            }
        )

    tools = [
        ("lookup_policy", "휴가 승인 규정 확인"),
        ("search_incidents", "장애 이력 조회"),
        ("create_ticket", "후속 작업 티켓 생성"),
        ("lookup_customer", "고객 계약 상태 확인"),
        ("summarize_thread", "대화 스레드 요약"),
    ]
    for index in range(1, 11):
        tool_name, request = tools[(index - 1) % len(tools)]
        critical = index <= 3
        payloads.append(
            {
                "evaluation_suite_id": suite_id,
                "external_case_id": f"captured-tool-{index:03d}",
                "category": "tool_selection",
                "title": f"Captured tool selection case {index:02d}",
                "input_payload_json": {
                    "request": request,
                    "available_tools": [name for name, _ in tools],
                    "instruction": (
                        "Return one JSON object with keys tool_name and arguments. "
                        f"Use tool_name={tool_name} and arguments.query as a Korean search phrase."
                    ),
                },
                "expected_output_json": None,
                "reference_context_json": {
                    "source": "operator-authored-local-case",
                    "expected_tool": tool_name,
                },
                "expected_tool_schema_json": _tool_schema(tool_name),
                "tags_json": ["captured_local", "tool", "operations"],
                "criticality": "critical" if critical else "standard",
                "weight": 1.0,
                "is_active": True,
                "data_source": CAPTURED_DATA_SOURCE,
            }
        )

    for index in range(1, 19):
        critical = index <= 3
        payloads.append(
            {
                "evaluation_suite_id": suite_id,
                "external_case_id": f"captured-qa-{index:03d}",
                "category": "grounded_answer",
                "title": f"Captured grounded answer case {index:02d}",
                "input_payload_json": {
                    "document": (
                        f"내부 공지 {index}: 배포 창은 금요일 22:00-23:30이며, "
                        "영향 범위는 관리자 콘솔입니다. 롤백 담당자는 플랫폼 온콜입니다."
                    ),
                    "question": "배포 영향 범위와 롤백 담당자를 한 문장으로 답하세요.",
                },
                "expected_output_json": None,
                "reference_context_json": {
                    "source": "operator-authored-local-case",
                    "facts": ["관리자 콘솔", "플랫폼 온콜"],
                },
                "expected_tool_schema_json": None,
                "tags_json": ["captured_local", "qa", "operations"],
                "criticality": "critical" if critical else "standard",
                "weight": 1.0,
                "is_active": True,
                "data_source": CAPTURED_DATA_SOURCE,
            }
        )
    return payloads


def _delete_existing_suite(db: Session, suite_ids: list[Any]) -> None:
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


def seed_captured_local_suite(db: Session) -> dict[str, Any]:
    workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
    strict_policy = db.scalar(
        select(AcceptancePolicy).where(AcceptancePolicy.name == STRICT_POLICY_NAME)
    )
    if workload is None or strict_policy is None:
        seed_demo_data(db)
        workload = db.scalar(select(WorkloadProfile).where(WorkloadProfile.slug == WORKLOAD_SLUG))
        strict_policy = db.scalar(
            select(AcceptancePolicy).where(AcceptancePolicy.name == STRICT_POLICY_NAME)
        )
    if workload is None or strict_policy is None:
        raise RuntimeError("Demo workload and strict policy are required before captured seeding.")

    existing_suite_ids = list(
        db.scalars(select(EvaluationSuite.id).where(EvaluationSuite.name == CAPTURED_SUITE_NAME))
    )
    _delete_existing_suite(db, existing_suite_ids)
    db.flush()

    suite_payload = {
        "workload_profile_id": workload.id,
        "name": CAPTURED_SUITE_NAME,
        "version_label": CAPTURED_SUITE_VERSION,
        "description": (
            "Operator-authored local acceptance cases for validating real runtime execution. "
            "These cases are non-synthetic for gate mechanics, but should be replaced with "
            "production-captured examples before real deployment approval."
        ),
        "status": "active",
        "dataset_source": CAPTURED_DATA_SOURCE,
        "is_synthetic": False,
    }
    suite_hash_seed = {
        **suite_payload,
        "case_external_ids": [
            payload["external_case_id"] for payload in _case_payloads("pending")
        ],
    }
    suite = EvaluationSuite(**suite_payload, suite_hash=stable_hash(suite_hash_seed))
    db.add(suite)
    db.flush()

    case_payloads = _case_payloads(suite.id)
    db.add_all(EvaluationCase(**payload) for payload in case_payloads)
    db.commit()
    return {
        "evaluation_suite_id": str(suite.id),
        "evaluation_suite_name": suite.name,
        "evaluation_suite_version": suite.version_label,
        "acceptance_policy_id": str(strict_policy.id),
        "case_count": len(case_payloads),
        "critical_case_count": sum(
            1 for case in case_payloads if case["criticality"] == "critical"
        ),
        "json_case_count": sum(
            1 for case in case_payloads if case["category"] == "json_extraction"
        ),
        "tool_case_count": sum(1 for case in case_payloads if case["category"] == "tool_selection"),
        "data_source": CAPTURED_DATA_SOURCE,
    }


def main() -> None:
    with SessionLocal() as db:
        summary = seed_captured_local_suite(db)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
