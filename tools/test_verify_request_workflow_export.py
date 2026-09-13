import hashlib
import json

import pytest

from verify_request_workflow_export import same_json, verify


def fixture():
    result = {
        "attempt_id": "test",
        "source": "automated_qa",
        "number": 0.0,
        "gate_evidence": False,
        "human_review_verified": False,
    }
    canonical = json.dumps(result)
    sha = hashlib.sha256(canonical.encode()).hexdigest()
    return {
        "id": "test",
        "source": "automated_qa",
        "gate_evidence": False,
        "human_review_verified": False,
        "result": {**result, "evidence_hash": sha},
        "evidence": {"canonical_json": canonical, "sha256": sha, "verified": True},
    }


def test_browser_numeric_roundtrip_and_bundle():
    row = fixture()
    row["result"]["number"] = 0
    assert verify(row)["status"] == "verified"
    assert verify({"attempts": [row]})["attempt_count"] == 1


@pytest.mark.parametrize(
    "change",
    ["hash", "display", "identity", "source", "approval", "missing", "typed_value"],
)
def test_tampering_is_not_hidden_by_claimed_verified_flag(change):
    row = fixture()
    if change == "hash":
        row["evidence"]["sha256"] = "0" * 64
    elif change == "display":
        row["result"]["number"] = 42
    elif change == "identity":
        row["id"] = "other"
    elif change == "source":
        row["source"] = "participant_self_report"
    elif change == "approval":
        row["gate_evidence"] = True
    elif change == "missing":
        row["evidence"] = None
    else:
        row["result"]["number"] = False
    with pytest.raises(ValueError):
        verify(row)


def test_json_boolean_and_numeric_types_are_distinct():
    assert same_json({"x": [0.0, 1]}, {"x": [0, 1.0]})
    assert not same_json({"x": [False]}, {"x": [0]})
    assert not same_json({"x": 1}, {"x": "1"})
