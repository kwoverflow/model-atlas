"""Create a fresh, disposable review workspace without adopting personal folders."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.operator_identity import local_operator_identity  # noqa: E402
from app.services.personal_assistant.reviews import ReviewService  # noqa: E402
from app.services.personal_assistant.sandbox import Sandbox  # noqa: E402
from app.services.structured_requests import owner_key  # noqa: E402


def initialize(base):
    base = base.absolute()
    if base.parent.resolve() != base.parent:
        raise ValueError("Workspace parent must not be linked")
    base.mkdir(exist_ok=False)
    sandbox = Sandbox.create(base / owner_key(local_operator_identity()))
    (sandbox.root / "files" / "Inbox").mkdir()
    (sandbox.root / "files" / "Archive").mkdir()
    (sandbox.root / "files" / "Inbox" / "review-demo.txt").write_bytes(
        b"Synthetic personal assistant review fixture. No personal data.\n"
    )
    service = ReviewService(sandbox)
    return {"workspace": str(base), "operator_root": str(sandbox.root), "state": service.state()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(initialize(args.workspace), ensure_ascii=True, indent=2))
