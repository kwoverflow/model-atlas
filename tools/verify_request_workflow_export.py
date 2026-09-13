"""Verify workflow JSON downloads without trusting their claimed integrity flag."""

import argparse
import hashlib
import json
from pathlib import Path


def same_json(left, right):
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            same_json(left[k], right[k]) for k in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            same_json(a, b) for a, b in zip(left, right)
        )
    return left == right


def verify(document):
    attempts = document.get("attempts", [document])
    if not isinstance(attempts, list) or not attempts:
        raise ValueError("no completed workflow attempts")
    hashes = []
    for row in attempts:
        if (
            row.get("gate_evidence") is not False
            or row.get("human_review_verified") is not False
        ):
            raise ValueError(
                "workflow evidence must not claim official or human approval"
            )
        result, envelope = row.get("result"), row.get("evidence")
        if (
            not result
            or not envelope
            or not isinstance(envelope.get("canonical_json"), str)
        ):
            raise ValueError(
                "canonical evidence missing; re-download this record from the current API"
            )
        actual = hashlib.sha256(envelope["canonical_json"].encode("utf-8")).hexdigest()
        if actual != envelope.get("sha256") or actual != result.get("evidence_hash"):
            raise ValueError("canonical evidence hash mismatch")
        decoded = json.loads(envelope["canonical_json"])
        if not same_json(
            decoded, {k: v for k, v in result.items() if k != "evidence_hash"}
        ):
            raise ValueError("displayed result differs from canonical evidence")
        if decoded.get("attempt_id") != row.get("id") or decoded.get(
            "source"
        ) != row.get("source"):
            raise ValueError("attempt identity or provenance mismatch")
        if (
            decoded.get("gate_evidence") is not False
            or decoded.get("human_review_verified") is not False
        ):
            raise ValueError("canonical evidence claims forbidden approval")
        hashes.append({"id": row["id"], "sha256": actual})
    return {
        "status": "verified",
        "attempt_count": len(hashes),
        "hashes": hashes,
        "scope": "content_integrity_not_identity_authenticity_or_independent_review",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        result = verify(json.loads(args.file.read_text(encoding="utf-8-sig")))
    except (ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
