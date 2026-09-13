from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BenchmarkResult
from app.schemas import GateEvaluationCreate
from app.seed.demo import seed_demo_data
from app.services.deployment_gate.evaluator import create_gate_evaluation
from app.services.deployment_gate.staleness import mark_scope_gates_stale
from app.services.judge_label_import import import_judge_label_rows
from tests.test_deployment_gate import _build_gate_graph


def test_release_decision_can_sign_approvable_snapshot(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="release-decision")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    response = client.post(
        "/api/v1/release-decisions",
        headers={
            "x-model-atlas-operator-id": "release-manager-1",
            "x-model-atlas-operator-name": "Release Manager One",
            "x-model-atlas-operator-role": "Release Manager",
            "x-model-atlas-identity-provider": "test-proxy",
        },
        json={
            "gate_evaluation_id": str(gate.id),
            "decision": "APPROVE_RELEASE",
            "decided_by": "release-manager",
            "signer_role": "Release Manager",
            "ticket_reference": "REL-100",
            "decision_reason": "Gate passed and is ready for baseline promotion.",
            "signature_statement": "I reviewed and approve this local release decision.",
            "notes": "Proceed after operational handoff.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["decision"] == "APPROVE_RELEASE"
    assert payload["release_readiness_status"] == "READY_TO_PROMOTE"
    assert payload["gate_evaluation_id"] == str(gate.id)
    assert payload["deployment_configuration_id"] == str(ids["deployment_configuration_id"])
    assert payload["snapshot_json"]["gate"]["gate_evaluation_id"] == str(gate.id)
    assert payload["snapshot_hash"]
    assert payload["decision_hash"]
    assert payload["signature_hash"]
    assert payload["identity_verified"] is True
    assert payload["decided_by"] == "Release Manager One"
    assert payload["signer_identity_json"]["display_name"] == "Release Manager One"
    assert payload["signer_identity_json"]["role"] == "Release Manager"
    assert payload["signer_identity_json"]["ticket_reference"] == "REL-100"
    assert payload["approval_policy_json"]["allowed"] is True
    assert payload["approval_policy_json"]["policy_version"] == "release-approval-rbac-v1"

    list_response = client.get(f"/api/v1/release-decisions?gate_evaluation_id={gate.id}")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [payload["id"]]

    lineage_response = client.get(
        "/api/v1/experiment-lineage/report?event_type=release_decision_signed"
    )
    assert lineage_response.status_code == 200
    lineage_payload = lineage_response.json()
    assert lineage_payload["release_decision_event_count"] == 1
    assert lineage_payload["events"][0]["release_decision_id"] == payload["id"]
    assert lineage_payload["events"][0]["event_type"] == "release_decision_signed"
    assert (
        lineage_payload["events"][0]["metadata_json"]["signature_hash"]
        == payload["signature_hash"]
    )


def test_release_decision_records_trusted_header_identity(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="trusted-release-decision")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    response = client.post(
        "/api/v1/release-decisions",
        headers={
            "x-model-atlas-operator-id": "ops-123",
            "x-model-atlas-operator-name": "Ops Lead",
            "x-model-atlas-operator-role": "Release Manager",
            "x-model-atlas-identity-provider": "local-dev-proxy",
        },
        json={
            "gate_evaluation_id": str(gate.id),
            "decision": "REQUEST_CHANGES",
            "decided_by": "fallback-name",
            "decision_reason": "Record a reviewed change request with trusted identity.",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["decided_by"] == "Ops Lead"
    assert payload["identity_verified"] is True
    assert payload["signer_identity_json"]["subject_id"] == "ops-123"
    assert payload["signer_identity_json"]["identity_provider"] == "local-dev-proxy"
    assert payload["signature_hash"]
    assert payload["approval_policy_json"]["allowed"] is True


def test_stale_release_review_revoke_and_replacement_workflow(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="release-operations")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    headers = {
        "x-model-atlas-operator-id": "release-manager-ops",
        "x-model-atlas-operator-name": "Release Manager Ops",
        "x-model-atlas-operator-role": "Release Manager",
        "x-model-atlas-identity-provider": "test-proxy",
    }
    created = client.post(
        "/api/v1/release-decisions",
        headers=headers,
        json={
            "gate_evaluation_id": str(gate.id),
            "decision": "APPROVE_RELEASE",
            "decided_by": "fallback",
            "decision_reason": "Approve the initial release evidence.",
        },
    )
    assert created.status_code == 201, created.text
    original = created.json()
    assert original["operational_status"] == "active"

    stale = mark_scope_gates_stale(
        db_session,
        deployment_configuration_id=gate.deployment_configuration_id,
        evaluation_suite_id=gate.evaluation_suite_id,
        current_revision_hash="f" * 64,
        reason="New production evidence requires release review.",
    )
    assert [item.id for item in stale] == [gate.id]
    db_session.commit()

    stale_read = client.get(
        f"/api/v1/release-decisions/{original['id']}"
    )
    assert stale_read.status_code == 200
    assert stale_read.json()["operational_status"] == "needs_review"
    assert stale_read.json()["stale_warning"] is True
    assert stale_read.json()["action_count"] == 1

    acknowledged = client.post(
        f"/api/v1/release-decisions/{original['id']}/actions",
        headers=headers,
        json={
            "action_type": "acknowledged",
            "reason": "Release owner acknowledged the stale Gate warning.",
        },
    )
    assert acknowledged.status_code == 201, acknowledged.text
    revoked = client.post(
        f"/api/v1/release-decisions/{original['id']}/actions",
        headers=headers,
        json={
            "action_type": "revoked",
            "reason": "Revoke operational use until replacement evidence is signed.",
        },
    )
    assert revoked.status_code == 201, revoked.text
    revoked_read = client.get(
        f"/api/v1/release-decisions/{original['id']}"
    ).json()
    assert revoked_read["operational_status"] == "revoked"

    replacement_gate = create_gate_evaluation(
        db_session,
        GateEvaluationCreate(**ids),
    )
    replacement = client.post(
        "/api/v1/release-decisions",
        headers=headers,
        json={
            "gate_evaluation_id": str(replacement_gate.id),
            "decision": "APPROVE_RELEASE",
            "decided_by": "fallback",
            "decision_reason": "Replace the revoked release with a fresh Gate.",
            "replaces_release_decision_id": original["id"],
        },
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["replaces_release_decision_id"] == original["id"]
    assert replacement.json()["operational_status"] == "active"

    replaced_read = client.get(
        f"/api/v1/release-decisions/{original['id']}"
    ).json()
    assert replaced_read["operational_status"] == "replaced"
    actions = client.get(
        f"/api/v1/release-decisions/{original['id']}/actions"
    )
    assert actions.status_code == 200
    assert [item["action_type"] for item in actions.json()] == [
        "stale_detected",
        "acknowledged",
        "revoked",
        "replaced",
    ]
    assert (
        actions.json()[-1]["replacement_release_decision_id"]
        == replacement.json()["id"]
    )


def test_release_decision_rejects_self_attested_release_approval(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="self-attested-release-decision")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    response = client.post(
        "/api/v1/release-decisions",
        json={
            "gate_evaluation_id": str(gate.id),
            "decision": "APPROVE_RELEASE",
            "decided_by": "release-manager",
            "signer_role": "Release Manager",
            "decision_reason": "Trying to approve with local self-attested identity.",
        },
    )

    assert response.status_code == 422
    assert "requires verified operator identity" in response.text


def test_release_decision_rejects_unapproved_trusted_role(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(db_session, config_name="unauthorized-release-decision")
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))

    response = client.post(
        "/api/v1/release-decisions",
        headers={
            "x-model-atlas-operator-id": "ml-engineer-1",
            "x-model-atlas-operator-name": "ML Engineer One",
            "x-model-atlas-operator-role": "ML Engineer",
            "x-model-atlas-identity-provider": "test-proxy",
        },
        json={
            "gate_evaluation_id": str(gate.id),
            "decision": "APPROVE_RELEASE",
            "decided_by": "fallback-name",
            "decision_reason": "Trying to approve with a reviewer-only role.",
        },
    )

    assert response.status_code == 422
    assert "requires one of these roles" in response.text


def test_operator_identity_endpoint_reports_release_permissions(
    client: TestClient,
) -> None:
    local_response = client.get("/api/v1/operator-identity/me")
    assert local_response.status_code == 200
    local_payload = local_response.json()
    assert local_payload["identity_verified"] is False
    assert (
        local_payload["release_permissions"]["decisions"]["APPROVE_RELEASE"]["allowed"]
        is False
    )

    trusted_response = client.get(
        "/api/v1/operator-identity/me",
        headers={
            "x-model-atlas-operator-id": "ops-123",
            "x-model-atlas-operator-name": "Ops Lead",
            "x-model-atlas-operator-role": "Release Manager",
            "x-model-atlas-identity-provider": "local-dev-proxy",
        },
    )
    assert trusted_response.status_code == 200
    trusted_payload = trusted_response.json()
    assert trusted_payload["identity_verified"] is True
    assert (
        trusted_payload["release_permissions"]["decisions"]["APPROVE_RELEASE"]["allowed"]
        is True
    )


def test_release_decision_rejects_approval_when_readiness_is_not_approvable(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    gate = client.get("/api/v1/deployment-gates/evaluations").json()[0]

    response = client.post(
        "/api/v1/release-decisions",
        json={
            "gate_evaluation_id": gate["id"],
            "decision": "APPROVE_RELEASE",
            "decided_by": "release-manager",
            "decision_reason": "Trying to approve without sufficient evidence.",
        },
    )

    assert response.status_code == 422
    assert "APPROVE_RELEASE requires readiness status" in response.text


def test_release_decision_request_changes_and_markdown_export(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)
    gate = client.get("/api/v1/deployment-gates/evaluations").json()[0]
    create_response = client.post(
        "/api/v1/release-decisions",
        json={
            "gate_evaluation_id": gate["id"],
            "decision": "REQUEST_CHANGES",
            "decided_by": "release-manager",
            "decision_reason": "Replace synthetic evidence with reviewed local cases.",
        },
    )
    release_decision = create_response.json()

    response = client.get(f"/api/v1/release-decisions/{release_decision['id']}/report.md")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Model Atlas Release Decision Record" in response.text
    assert release_decision["decision_hash"] in response.text
    assert "release-approval-rbac-v1" in response.text
    assert gate["id"] in response.text

    snapshot_response = client.get(
        f"/api/v1/release-decisions/{release_decision['id']}/snapshot.json"
    )
    assert snapshot_response.status_code == 200
    assert snapshot_response.headers["content-type"].startswith("application/json")
    assert "model-atlas-release-snapshot.json" in snapshot_response.headers[
        "content-disposition"
    ]
    assert snapshot_response.json()["gate"]["gate_evaluation_id"] == gate["id"]

    diff_response = client.get(
        f"/api/v1/release-decisions/{release_decision['id']}/snapshot-diff"
    )
    assert diff_response.status_code == 200
    diff_payload = diff_response.json()
    assert diff_payload["release_decision_id"] == release_decision["id"]
    assert diff_payload["gate_evaluation_id"] == gate["id"]
    assert diff_payload["frozen_snapshot_hash"] == release_decision["snapshot_hash"]
    assert diff_payload["current_snapshot_hash"]
    assert diff_payload["ignored_paths"] == ["generated_at"]
    assert diff_payload["diff_count"] >= len(diff_payload["diffs"])


def test_snapshot_diff_detects_evidence_trust_change_after_judge_labels(
    client: TestClient,
    db_session: Session,
) -> None:
    ids = _build_gate_graph(
        db_session,
        config_name="trust-diff",
        reviewed_evidence=False,
    )
    gate = create_gate_evaluation(db_session, GateEvaluationCreate(**ids))
    create_response = client.post(
        "/api/v1/release-decisions",
        json={
            "gate_evaluation_id": str(gate.id),
            "decision": "REQUEST_CHANGES",
            "decided_by": "reviewer",
            "decision_reason": "Freeze the heuristic-only evidence state.",
        },
    )
    assert create_response.status_code == 201
    release_decision = create_response.json()
    assert release_decision["snapshot_json"]["evidence_trust"]["trust_status"] == (
        "needs_judge_review"
    )

    results = list(
        db_session.scalars(
            select(BenchmarkResult).where(
                BenchmarkResult.benchmark_run_id.in_(
                    gate.evidence_snapshot_json["benchmark_run_ids"]
                )
            )
        )
    )
    import_judge_label_rows(
        db_session,
        benchmark_run_id=results[0].benchmark_run_id,
        rows=[
            {
                "sample_id": result.sample_id,
                "quality_score": result.quality_score,
                "human_label": "reviewed-pass",
                "judge_source": "human_review",
            }
            for result in results
        ],
        apply_labels=True,
    )

    diff_response = client.get(
        f"/api/v1/release-decisions/{release_decision['id']}/snapshot-diff"
    )
    assert diff_response.status_code == 200
    paths = {item["path"] for item in diff_response.json()["diffs"]}
    assert "evidence_trust.trust_status" in paths
    assert "production_readiness" in paths or "evidence_trust.score_distribution.heuristic" in paths
