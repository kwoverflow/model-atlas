from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from app.db.session import SessionLocal
from app.schemas import ModelValidationCampaignCreate
from app.services.agent_jobs import system_worker_identity
from app.services.benchmark_execution import run_benchmark_execution
from app.services.model_validation import (
    ALLOWED_API_KEY_ENV,
    build_model_validation_report,
    render_model_validation_markdown,
    validate_model_validation_campaign,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run and export a Model Atlas local model validation campaign."
    )
    parser.add_argument("--deployment-configuration-id", required=True)
    parser.add_argument("--evaluation-suite-id", required=True)
    parser.add_argument("--benchmark-task-id", required=True)
    parser.add_argument("--prompt-version-id", required=True)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--api-key-env", default=None)
    parser.add_argument("--max-cases", type=int, default=10)
    parser.add_argument("--trials-per-case", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--case-timeout-ms", type=int, default=120_000)
    parser.add_argument(
        "--data-source",
        choices=(
            "local_authored",
            "production_captured",
            "external_benchmark",
            "synthetic_demo",
        ),
        default="local_authored",
    )
    parser.add_argument("--mock", action="store_true")
    parser.add_argument(
        "--output-dir",
        default="artifacts/model-validation",
    )
    args = parser.parse_args()
    adapter_config = {
        key: value
        for key, value in {
            "base_url": args.base_url,
            "model": args.model,
            "api_key_env": args.api_key_env,
        }.items()
        if value
    }
    if args.api_key_env and args.api_key_env != ALLOWED_API_KEY_ENV:
        parser.error(f"--api-key-env must be {ALLOWED_API_KEY_ENV}")
    payload = ModelValidationCampaignCreate(
        deployment_configuration_id=UUID(args.deployment_configuration_id),
        evaluation_suite_id=UUID(args.evaluation_suite_id),
        benchmark_task_id=UUID(args.benchmark_task_id),
        prompt_version_id=UUID(args.prompt_version_id),
        adapter_name="mock" if args.mock else "openai_compatible",
        adapter_config_json=adapter_config,
        data_source=args.data_source,
        max_cases=args.max_cases,
        reliability_mode=args.trials_per_case > 1 or args.concurrency > 1,
        trials_per_case=args.trials_per_case,
        concurrency=args.concurrency,
        case_timeout_ms=args.case_timeout_ms,
    )
    validate_model_validation_campaign(payload)
    with SessionLocal() as db:
        outcome = run_benchmark_execution(
            db,
            payload,
            requester_identity=system_worker_identity("local-model-validation-cli"),
        )
        report = build_model_validation_report(
            db,
            deployment_configuration_id=payload.deployment_configuration_id,
            evaluation_suite_id=payload.evaluation_suite_id,
            focus_benchmark_run_id=outcome.run.id,
        )
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{outcome.run.id}.json"
    markdown_path = output_dir / f"{outcome.run.id}.md"
    json_path.write_text(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_model_validation_markdown(report),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "benchmark_run_id": str(outcome.run.id),
                "status": report.status,
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
