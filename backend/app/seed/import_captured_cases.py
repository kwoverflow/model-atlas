from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.seed.demo import WORKLOAD_SLUG
from app.services.captured_case_import import (
    PRODUCTION_CAPTURED_SOURCE,
    CapturedCaseImportOptions,
    import_captured_cases,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import production-captured evaluation cases.")
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--suite-name", required=True)
    parser.add_argument("--suite-version", required=True)
    parser.add_argument("--workload-slug", default=WORKLOAD_SLUG)
    parser.add_argument("--data-source", default=PRODUCTION_CAPTURED_SOURCE)
    parser.add_argument("--description")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--seed-demo-if-missing", action="store_true")
    args = parser.parse_args()

    options = CapturedCaseImportOptions(
        suite_name=args.suite_name,
        suite_version=args.suite_version,
        workload_slug=args.workload_slug,
        data_source=args.data_source,
        description=args.description,
        replace_existing=args.replace,
        seed_demo_if_missing=args.seed_demo_if_missing,
    )
    with SessionLocal() as db:
        summary = import_captured_cases(db, path=args.path, options=options)
    print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
