from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationCase
from app.seed.demo import seed_demo_data
from app.seed.rag_evaluation import seed_rag_evaluation_pack


def _task_and_prompt(client: TestClient) -> tuple[dict, dict]:
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    task = next(item for item in tasks if item["name"] == "Korean document QA")
    prompt = next(item for item in prompts if item["benchmark_task_id"] == task["id"])
    return task, prompt


def _execute_pack(client: TestClient, seeded: dict) -> dict:
    task, prompt = _task_and_prompt(client)
    response = client.post(
        "/api/v1/benchmark-executions",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 20,
            "seed": 9,
            "isolation_policy_id": "rag-readonly-internal",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_rag_pack_runs_and_passes_its_policy(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_rag_evaluation_pack(db_session)

    execution = _execute_pack(client, seeded)
    summary = execution["rag_evaluation_summary"]
    isolation = execution["benchmark_run"]["runtime_config_json"]["isolation_preflights"]
    selector = execution["benchmark_run"]["runtime_config_json"]["evidence_selector_descriptor"]
    assert len(isolation) == 1
    assert isolation[0]["policy"]["policy_id"] == "rag-readonly-internal"
    assert selector["selector_version"] == "lexical-sentence-selector-v1"
    assert summary["rag_case_count"] == 10
    assert summary["successful_case_count"] == 10
    assert summary["failed_case_count"] == 0
    assert summary["average_retrieval_recall"] == 1.0
    assert summary["average_citation_precision"] == 1.0
    assert summary["average_citation_recall"] == 1.0
    assert summary["average_groundedness_score"] == 1.0
    assert summary["average_unsupported_claim_rate"] == 0.0
    assert summary["corpus_versions"] == ["ops-handbook-v1"]
    assert summary["retriever_versions"] == ["lexical-overlap-v1"]

    run_id = execution["benchmark_run"]["id"]
    detail_response = client.get(f"/api/v1/benchmark-executions/{run_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["rag_evaluation_summary"] == summary
    assert len(detail["rag_traces"]) == 10
    assert detail["rag_traces"][0]["trace"]["retrieval"]["retrieved_chunks"]

    corpus_registry_response = client.get("/api/v1/rag/corpora")
    assert corpus_registry_response.status_code == 200
    corpus_registry = corpus_registry_response.json()
    assert corpus_registry["registry_version"] == "rag-corpus-registry-v1"
    assert corpus_registry["corpora"][0]["chunk_count"] == 12
    corpus_id = corpus_registry["corpora"][0]["corpus_id"]
    corpus_response = client.get(f"/api/v1/rag/corpora/{corpus_id}")
    assert corpus_response.status_code == 200
    assert len(corpus_response.json()["chunks"]) == 12
    retriever_response = client.get("/api/v1/rag/retriever")
    assert retriever_response.status_code == 200
    assert retriever_response.json()["retriever_version"] == "lexical-overlap-v1"

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "APPROVED"
    assert len(gate["rule_results"]) == 5
    assert all(rule["status"] == "pass" for rule in gate["rule_results"])
    metrics = gate["scorecard_json"]["metrics"]
    assert metrics["rag_retrieval_recall"]["value"] == 1.0
    assert metrics["rag_citation_precision"]["value"] == 1.0
    assert metrics["rag_unsupported_claim_rate"]["value"] == 0.0
    snapshot = gate["evidence_snapshot_json"]
    assert snapshot["schema_version"] == "gate-evidence-snapshot-v8"
    assert snapshot["rag_corpus_versions"] == ["ops-handbook-v1"]
    assert snapshot["retriever_versions"] == ["lexical-overlap-v1"]
    assert snapshot["rag_evaluation_versions"] == ["rag-evaluation-trace-v5"]


def test_rag_pack_seed_is_idempotent(db_session: Session) -> None:
    seed_demo_data(db_session)
    first = seed_rag_evaluation_pack(db_session)
    second = seed_rag_evaluation_pack(db_session)

    assert first["created"] is True
    assert second["created"] is False
    assert second["deployment_configuration_id"] == first["deployment_configuration_id"]
    assert second["evaluation_suite_id"] == first["evaluation_suite_id"]
    assert second["acceptance_policy_id"] == first["acceptance_policy_id"]
    assert second["case_count"] == 10


def test_unsupported_critical_rag_answer_blocks_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    seeded = seed_rag_evaluation_pack(db_session)
    critical_case = db_session.scalar(
        select(EvaluationCase).where(EvaluationCase.external_case_id == "rag-eval-001")
    )
    assert critical_case is not None
    critical_case.input_payload_json = {
        **critical_case.input_payload_json,
        "mock_rag_output": {
            "answer": "Every release can skip the deployment gate.",
            "citations": ["missing-chunk"],
            "claims": ["Every release can skip the deployment gate."],
        },
    }
    db_session.commit()

    execution = _execute_pack(client, seeded)
    summary = execution["rag_evaluation_summary"]
    assert summary["failed_case_count"] == 1
    assert summary["average_citation_precision"] < 1.0
    assert summary["average_unsupported_claim_rate"] > 0.0

    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201
    gate = gate_response.json()
    assert gate["verdict"] == "BLOCKED"
    critical_outcome = next(
        outcome
        for outcome in gate["scorecard_json"]["critical_case_outcomes"]
        if outcome["external_case_id"] == "rag-eval-001"
    )
    assert critical_outcome["status"] == "fail"
    assert critical_outcome["rag_evaluation_status"] == "failed"
