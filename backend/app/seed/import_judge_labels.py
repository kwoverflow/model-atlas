from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from app.db.session import SessionLocal
from app.services.judge_label_import import import_judge_labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Import human or LLM judge labels for a run.")
    parser.add_argument("--benchmark-run-id", required=True, type=UUID)
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        summary = import_judge_labels(
            db,
            benchmark_run_id=args.benchmark_run_id,
            path=args.path,
            apply_labels=args.apply,
        )
    print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
