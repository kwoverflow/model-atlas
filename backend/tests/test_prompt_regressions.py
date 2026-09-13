from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.seed.demo import seed_demo_data
from app.services.prompt_regressions import build_prompt_regression_report


def test_prompt_regression_report_groups_runs_by_prompt_version(db_session: Session) -> None:
    seed_demo_data(db_session)

    report = build_prompt_regression_report(db_session)

    assert report.row_count > 0
    assert report.rows[0].run_count > 0
    assert report.rows[0].result_count > 0
    assert report.rows[0].mean_quality_score.sample_size > 0


def test_prompt_regression_api_returns_report(client: TestClient, db_session: Session) -> None:
    seed_demo_data(db_session)

    response = client.get("/api/v1/prompt-regressions/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] > 0
    assert payload["rows"][0]["prompt_version_id"]
    assert "risk_flags" in payload["rows"][0]
