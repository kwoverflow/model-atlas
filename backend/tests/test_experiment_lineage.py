from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.seed.demo import seed_demo_data


def test_lineage_report_materializes_existing_seed_data(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    response = client.get("/api/v1/experiment-lineage/report")

    assert response.status_code == 200
    payload = response.json()
    event_types = {event["event_type"] for event in payload["events"]}
    assert payload["event_count"] >= 10
    assert "prompt_version_created" in event_types
    assert "benchmark_run_completed" in event_types
    assert "gate_evaluation_completed" in event_types


def test_lineage_materialize_is_idempotent(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_data(db_session)

    first = client.post("/api/v1/experiment-lineage/materialize")
    second = client.post("/api/v1/experiment-lineage/materialize")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["created_count"] > 0
    assert second.json()["created_count"] == 0
    assert second.json()["event_count"] == first.json()["event_count"]
