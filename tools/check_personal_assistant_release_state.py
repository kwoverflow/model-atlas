"""Read-only snapshots for explicit rollback/roll-forward and workspace preservation."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def check(api, expected_strategy, compare=None, expected_version=None):
    url = urlsplit(api)
    if (
        url.scheme != "http"
        or url.hostname not in {"localhost", "127.0.0.1"}
        or url.port not in {18000, 18001}
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path != "/api/v1/personal-assistant"
    ):
        raise ValueError("Only the two explicitly designated local assistant APIs are allowed")
    opener = build_opener(ProxyHandler({}))
    with opener.open(api + "/workspace", timeout=10) as response:
        workspace = json.load(response)
    with opener.open(api + "/reviews", timeout=10) as response:
        reviews = json.load(response)
    if workspace["draft_strategy"] != expected_strategy:
        raise ValueError("Unexpected active draft strategy")
    if expected_version and workspace.get("application_version") != expected_version:
        raise ValueError("Unexpected application version")
    state_hash, reviews_hash = digest(workspace["state"]), digest(reviews)
    if compare:
        previous = json.loads(compare.read_text(encoding="utf-8"))
        if previous["state_sha256"] != state_hash or previous["reviews_sha256"] != reviews_hash:
            raise ValueError("Workspace or persisted review records changed")
    return {
        "status": "passed",
        "model_calls": 0,
        "read_only": True,
        "draft_strategy": expected_strategy,
        "application_version": workspace.get("application_version"),
        "state_sha256": state_hash,
        "reviews_sha256": reviews_hash,
        "compared_to": str(compare) if compare else None,
        "workspace": workspace,
        "review_count": len(reviews),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--expect-strategy", required=True)
    parser.add_argument("--expect-version")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = check(args.api, args.expect_strategy, args.compare, args.expect_version)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != "workspace"}))
