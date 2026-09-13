from __future__ import annotations

import datetime as dt
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgentApprovalCheckpoint,
    BenchmarkResult,
    BenchmarkRun,
    InferenceMetric,
)
from app.seed.adaptive_agent_operations import seed_adaptive_agent_operations_pack
from app.seed.demo import seed_demo_data
from app.services.agent_jobs import run_agent_worker_once


def _operator_headers(
    subject_id: str,
    *,
    role: str = "ML Ops Lead",
) -> dict[str, str]:
    return {
        "x-model-atlas-operator-id": subject_id,
        "x-model-atlas-operator-name": subject_id.replace("-", " ").title(),
        "x-model-atlas-operator-role": role,
        "x-model-atlas-identity-provider": "pytest-identity",
    }


def _execute_pending_pack(
    client: TestClient,
    db_session: Session,
    *,
    requester_id: str = "requester-1",
) -> tuple[dict, dict]:
    seed_demo_data(db_session)
    seeded = seed_adaptive_agent_operations_pack(db_session)
    tasks = client.get("/api/v1/benchmark-tasks").json()
    prompts = client.get("/api/v1/prompt-versions").json()
    task = next(item for item in tasks if item["name"] == "Korean document QA")
    prompt = next(item for item in prompts if item["benchmark_task_id"] == task["id"])
    response = client.post(
        "/api/v1/benchmark-executions",
        headers=_operator_headers(requester_id),
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "benchmark_task_id": task["id"],
            "prompt_version_id": prompt["id"],
            "adapter_name": "mock",
            "data_source": "local_authored",
            "max_cases": 10,
            "seed": 17,
        },
    )
    assert response.status_code == 201, response.text
    return seeded, response.json()


def _checkpoints(client: TestClient, run_id: str) -> list[dict]:
    response = client.get(
        "/api/v1/agents/checkpoints",
        params={"benchmark_run_id": run_id},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _decide(
    client: TestClient,
    checkpoint: dict,
    *,
    decision: str,
    operator_id: str,
) -> dict:
    response = client.post(
        f"/api/v1/agents/checkpoints/{checkpoint['id']}/decision",
        headers=_operator_headers(operator_id),
        json={
            "decision": decision,
            "reason": f"Pytest {decision} decision for persisted checkpoint.",
            "expected_version": checkpoint["version"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _resume(client: TestClient, checkpoint: dict, *, operator_id: str) -> dict:
    response = client.post(
        f"/api/v1/agents/checkpoints/{checkpoint['id']}/resume",
        headers=_operator_headers(operator_id),
        json={"expected_version": checkpoint["version"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_persisted_checkpoints_require_policy_identity_and_resume_without_duplicates(
    client: TestClient,
    db_session: Session,
) -> None:
    seeded, execution = _execute_pending_pack(client, db_session)
    run_id = execution["benchmark_run"]["id"]
    checkpoints = _checkpoints(client, run_id)

    assert len(checkpoints) == 2
    assert {checkpoint["status"] for checkpoint in checkpoints} == {"pending"}
    assert all(len(checkpoint["request_hash"]) == 64 for checkpoint in checkpoints)
    assert all(
        checkpoint["approval_policy_json"]["policy_version"]
        == "agent-control-approval-rbac-v1"
        for checkpoint in checkpoints
    )
    assert all(
        checkpoint["approval_policy_json"]["separation_of_duties"] is True
        for checkpoint in checkpoints
    )

    unverified = client.post(
        f"/api/v1/agents/checkpoints/{checkpoints[0]['id']}/decision",
        json={
            "decision": "approved",
            "reason": "Self-attested local approval must be rejected.",
            "expected_version": checkpoints[0]["version"],
        },
    )
    assert unverified.status_code == 422
    assert "verified operator identity" in unverified.text

    same_operator = client.post(
        f"/api/v1/agents/checkpoints/{checkpoints[0]['id']}/decision",
        headers=_operator_headers("requester-1"),
        json={
            "decision": "approved",
            "reason": "Requester cannot approve the same checkpoint.",
            "expected_version": checkpoints[0]["version"],
        },
    )
    assert same_operator.status_code == 422
    assert "different operator" in same_operator.text

    resumed_result_ids: list[str] = []
    resumed_run_ids: list[str] = []
    for index, checkpoint in enumerate(checkpoints, start=1):
        approved = _decide(
            client,
            checkpoint,
            decision="approved",
            operator_id=f"approver-{index}",
        )
        assert approved["status"] == "approved"
        assert approved["version"] == 2
        assert approved["identity_verified"] is True
        assert len(approved["decision_hash"]) == 64

        stale = client.post(
            f"/api/v1/agents/checkpoints/{checkpoint['id']}/resume",
            headers=_operator_headers(f"approver-{index}"),
            json={"expected_version": 1},
        )
        assert stale.status_code == 422
        assert "version conflict" in stale.text

        resumed = _resume(
            client,
            approved,
            operator_id=f"approver-{index}",
        )
        assert resumed["checkpoint"]["status"] == "resumed"
        assert resumed["checkpoint"]["version"] == 3
        assert resumed["result_revision"] == 2
        assert resumed["parent_benchmark_run_id"] == run_id
        assert resumed["parent_benchmark_result_id"] == checkpoint["benchmark_result_id"]
        assert resumed["benchmark_result_id"] != checkpoint["benchmark_result_id"]
        assert resumed["trace"]["status"] == "success"
        assert resumed["trace"]["approval_provenance_count"] == 1
        approval_step = resumed["trace"]["steps"][0]
        assert approval_step["output"]["decision_source"] == (
            "persisted_agent_control_plane"
        )
        assert approval_step["output"]["identity_verified"] is True
        assert approval_step["output"]["checkpoint_record_id"] == checkpoint["id"]
        resumed_result_ids.append(resumed["benchmark_result_id"])
        resumed_run_ids.append(resumed["benchmark_run_id"])

        idempotent = client.post(
            f"/api/v1/agents/checkpoints/{checkpoint['id']}/resume",
            headers=_operator_headers(f"approver-{index}"),
            json={"expected_version": 1},
        )
        assert idempotent.status_code == 200
        assert idempotent.json()["result_revision"] == 2

    detail = client.get(f"/api/v1/benchmark-executions/{run_id}").json()
    assert detail["result_count"] == 5
    assert detail["metric_count"] == 5
    assert detail["agent_execution_summary"]["successful_case_count"] == 3
    assert detail["agent_execution_summary"]["pending_checkpoint_count"] == 2
    assert {checkpoint["status"] for checkpoint in _checkpoints(client, run_id)} == {
        "resumed"
    }

    for child_run_id in resumed_run_ids:
        child_detail = client.get(
            f"/api/v1/benchmark-executions/{child_run_id}"
        ).json()
        assert child_detail["benchmark_run"]["parent_benchmark_run_id"] == run_id
        assert child_detail["benchmark_run"]["revision_number"] == 2
        assert child_detail["result_count"] == 1
        assert child_detail["metric_count"] == 1
        assert child_detail["agent_execution_summary"]["successful_case_count"] == 1
        assert child_detail["agent_execution_summary"]["approval_provenance_rate"] == 1.0

    lineage_run_ids = [UUID(run_id), *(UUID(value) for value in resumed_run_ids)]
    assert len(
        db_session.scalars(
            select(BenchmarkRun).where(BenchmarkRun.id.in_(lineage_run_ids))
        ).all()
    ) == 3
    assert len(
        db_session.scalars(
            select(BenchmarkResult).where(
                BenchmarkResult.benchmark_run_id.in_(lineage_run_ids)
            )
        ).all()
    ) == 7
    assert len(
        db_session.scalars(
            select(InferenceMetric).where(
                InferenceMetric.benchmark_run_id.in_(lineage_run_ids)
            )
        ).all()
    ) == 7

    for result_id in resumed_result_ids:
        replay = client.post(f"/api/v1/agents/replay/{result_id}")
        assert replay.status_code == 200, replay.text
        assert replay.json()["deterministic_match"] is True

    gate = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate.status_code == 201, gate.text
    assert gate.json()["verdict"] == "APPROVED"
    assert gate.json()["evidence_snapshot_json"]["result_count"] == 5
    revisions = gate.json()["evidence_snapshot_json"]["evidence_revision_manifest"]
    assert sum(item["revision_number"] == 2 for item in revisions) == 2


def test_checkpoint_expiry_and_revocation_are_terminal(
    client: TestClient,
    db_session: Session,
) -> None:
    _, execution = _execute_pending_pack(client, db_session)
    checkpoints = _checkpoints(client, execution["benchmark_run"]["id"])

    expiring = db_session.get(AgentApprovalCheckpoint, checkpoints[0]["id"])
    assert expiring is not None
    expiring.expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    db_session.commit()
    expired_response = client.get(
        f"/api/v1/agents/checkpoints/{checkpoints[0]['id']}"
    )
    assert expired_response.status_code == 200
    expired = expired_response.json()
    assert expired["status"] == "expired"
    assert expired["version"] == 2

    expired_decision = client.post(
        f"/api/v1/agents/checkpoints/{expired['id']}/decision",
        headers=_operator_headers("approver-expiry"),
        json={
            "decision": "approved",
            "reason": "Expired approvals cannot be revived.",
            "expected_version": expired["version"],
        },
    )
    assert expired_decision.status_code == 422
    assert "cannot be decided from expired" in expired_decision.text

    approved = _decide(
        client,
        checkpoints[1],
        decision="approved",
        operator_id="approver-revoke",
    )
    revoked_response = client.post(
        f"/api/v1/agents/checkpoints/{approved['id']}/revoke",
        headers=_operator_headers("governance-revoker", role="Model Governance"),
        json={
            "reason": "Risk context changed before execution resume.",
            "expected_version": approved["version"],
        },
    )
    assert revoked_response.status_code == 200, revoked_response.text
    revoked = revoked_response.json()
    assert revoked["status"] == "revoked"
    assert revoked["version"] == 3
    assert len(revoked["revocation_hash"]) == 64

    resume_response = client.post(
        f"/api/v1/agents/checkpoints/{revoked['id']}/resume",
        headers=_operator_headers("approver-revoke"),
        json={"expected_version": revoked["version"]},
    )
    assert resume_response.status_code == 422
    assert "cannot resume from revoked" in resume_response.text


def test_denied_checkpoint_updates_trace_and_replay_evidence(
    client: TestClient,
    db_session: Session,
) -> None:
    _, execution = _execute_pending_pack(client, db_session)
    checkpoint = _checkpoints(client, execution["benchmark_run"]["id"])[0]

    denied = _decide(
        client,
        checkpoint,
        decision="denied",
        operator_id="risk-reviewer",
    )
    assert denied["status"] == "denied"
    assert denied["version"] == 2

    assert denied["transition_benchmark_result_id"] != denied["benchmark_result_id"]
    detail = client.get(
        f"/api/v1/benchmark-executions/{denied['transition_benchmark_run_id']}"
    ).json()
    denied_trace = next(
        record
        for record in detail["agent_traces"]
        if record["benchmark_result_id"] == denied["transition_benchmark_result_id"]
    )
    assert denied_trace["trace"]["status"] == "approval_denied"
    assert denied_trace["trace"]["denied_checkpoint_count"] == 1
    assert denied_trace["trace"]["approval_provenance_count"] == 1

    replay = client.post(
        f"/api/v1/agents/replay/{denied['transition_benchmark_result_id']}"
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["deterministic_match"] is True

    stored = db_session.scalar(
        select(AgentApprovalCheckpoint).where(
            AgentApprovalCheckpoint.id == denied["id"]
        )
    )
    assert stored is not None
    assert stored.approver_identity_json["subject_id"] == "risk-reviewer"


def test_durable_resume_job_creates_child_revision_and_stales_gate(
    client: TestClient,
    db_session: Session,
) -> None:
    seeded, execution = _execute_pending_pack(client, db_session)
    run_id = execution["benchmark_run"]["id"]
    gate_response = client.post(
        "/api/v1/deployment-gates/evaluations",
        json={
            "deployment_configuration_id": seeded["deployment_configuration_id"],
            "evaluation_suite_id": seeded["evaluation_suite_id"],
            "acceptance_policy_id": seeded["acceptance_policy_id"],
        },
    )
    assert gate_response.status_code == 201, gate_response.text
    gate_id = gate_response.json()["id"]

    checkpoint = _checkpoints(client, run_id)[0]
    approved = _decide(
        client,
        checkpoint,
        decision="approved",
        operator_id="async-approver",
    )
    queued_response = client.post(
        f"/api/v1/agents/checkpoints/{approved['id']}/resume-jobs",
        headers=_operator_headers("async-approver"),
        json={"expected_version": approved["version"]},
    )
    assert queued_response.status_code == 202, queued_response.text
    queued = queued_response.json()
    assert queued["status"] == "queued"
    assert queued["attempt_count"] == 0

    completed = run_agent_worker_once(
        db_session,
        worker_id="pytest-agent-worker",
        lease_seconds=30,
    )
    assert completed is not None
    assert completed.id == UUID(queued["id"])
    assert completed.status == "completed"
    assert completed.attempt_count == 1
    assert completed.result_json is not None
    assert completed.result_json["parent_benchmark_run_id"] == run_id
    child_run_id = str(completed.result_json["benchmark_run_id"])

    child = client.get(f"/api/v1/benchmark-executions/{child_run_id}")
    assert child.status_code == 200, child.text
    assert child.json()["benchmark_run"]["revision_number"] == 2
    assert child.json()["benchmark_run"]["parent_benchmark_run_id"] == run_id

    stale_gate = client.get(
        f"/api/v1/deployment-gates/evaluations/{gate_id}"
    ).json()
    assert stale_gate["status"] == "stale"
    assert stale_gate["stale_at"] is not None
    assert "append-only" in stale_gate["stale_reason"]
    readiness = client.get(
        "/api/v1/release-readiness/snapshot",
        params={"gate_evaluation_id": gate_id},
    )
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["status"] == "BLOCKED"
    assert readiness.json()["gate"]["status"] == "stale"
