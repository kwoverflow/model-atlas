"""Freeze and audit the existing ten browser flows under the successor strategy."""

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backend"))

from experiments.personal_assistant_persona_e2e.protocol import CASES, protocol  # noqa: E402
from experiments.personal_assistant_persona_e2e.workflow import (  # noqa: E402
    corrections,
    raw_score,
)

from app.services.personal_assistant.stable_inference import STRATEGY  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def freeze(comparison, output):
    result = json.loads((comparison / "summary.json").read_text(encoding="utf-8"))
    assert result["adoption"] in {"ADOPT_HUMAN_REVIEW_DRAFT_PATH", "KEEP_LEGACY_DEFAULT"}
    output.mkdir()
    sources = [
        *sorted((REPO / "backend/app/services/personal_assistant").glob("*.py")),
        REPO / "backend/app/core/config.py",
        REPO / "backend/app/api/v1/routes/personal_assistant.py",
        REPO / "tools/verify_personal_assistant_personas.mjs",
        Path(__file__),
    ]
    plan = protocol()
    plan.update(
        runtime_adapter=STRATEGY,
        draft_strategy=STRATEGY,
        adoption=result["adoption"],
        default_strategy="legacy",
        activation="Explicit candidate opt-in in a disposable synthetic workspace only.",
        purpose="Successor integration regression; not a new unseen benchmark.",
        comparison_protocol_sha256=sha(comparison / "protocol.json"),
        comparison_summary_sha256=sha(comparison / "summary.json"),
        acceptance="10 raw correct drafts; 10 unchanged-before-approval flows; real 300s expiry.",
        source_sha256={p.relative_to(REPO).as_posix(): sha(p) for p in sources},
    )
    for source in sources:
        target = output / "sources" / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    write(output / "protocol.json", plan)
    return {"status": "frozen", "protocol": str(output / "protocol.json")}


def verify(source, evidence_path, output):
    plan = json.loads((source / "protocol.json").read_text(encoding="utf-8"))
    evidence = json.loads((evidence_path / "browser-e2e.json").read_text(encoding="utf-8"))
    assert plan["draft_strategy"] == STRATEGY
    assert sha(evidence_path / "protocol.json") == sha(source / "protocol.json")
    assert evidence["protocol_sha256"] == sha(source / "protocol.json")
    script_hash = plan["source_sha256"]["tools/verify_personal_assistant_personas.mjs"]
    assert evidence["browser_source_sha256"] == script_hash
    assert sha(evidence_path / "browser-source.mjs") == script_hash
    for relative, expected in plan["source_sha256"].items():
        assert sha(source / "sources" / relative) == sha(REPO / relative) == expected, relative
    rows = evidence["observations"]
    assert len(rows) == 10 and {r["case_id"] for r in rows} == {c.id for c in CASES}
    assert evidence["status"] == "passed" and not evidence["page_errors"]
    scores = []
    for row in rows:
        record = row["initial_record"]
        assert record["metadata"]["strategy"] == STRATEGY
        assert record["metadata"]["schema_valid"] and not record["metadata"]["completion_error"]
        assert row["preapproval_unchanged"]
        case = replace(next(c for c in CASES if c.id == row["case_id"]), fields=row["goal_fields"])
        score = raw_score(record["raw_output"], case)
        keys = [] if case.accepted_decisions else corrections(record["initial_fields"], case.fields)
        if row.get("saved_record"):
            assert row["saved_record"]["raw_output"] == record["raw_output"]
        scores.append({"case_id": case.id, **score, "model_correction_keys": keys})
    expiry = next(r for r in rows if r["case_id"] == "M10")
    assert expiry["elapsed_ms"] >= 300000
    assert expiry["before"] == expiry["before_approval_attempt"] == expiry["after"]
    assert expiry["rejection"] == {
        "status": 409,
        "data": {"detail": "approval_expired_or_state_changed"},
    }
    result = {
        "status": "passed" if all(s["correct"] for s in scores) else "raw_accuracy_failed",
        "browser_flows_passed": 10,
        "strict_valid": sum(s["strict_valid"] for s in scores),
        "original_drafts_correct": sum(s["correct"] for s in scores),
        "model_correction_keys": sum(len(s["model_correction_keys"]) for s in scores),
        "planned_user_changes": sum(r.get("planned_user_changes", 0) for r in rows),
        "real_expiry_seconds": expiry["elapsed_ms"] / 1000,
        "source_archives_verified": len(plan["source_sha256"]),
        "model_calls_during_verification": 0,
        "human_attestation": False,
        "scores": scores,
        "protocol_sha256": sha(source / "protocol.json"),
        "evidence_sha256": sha(evidence_path / "browser-e2e.json"),
    }
    write(output, result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["freeze", "verify"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.mode == "freeze":
        result = freeze(args.source.resolve(), args.output.resolve())
    else:
        if not args.evidence:
            parser.error("--evidence is required for verify")
        result = verify(args.source.resolve(), args.evidence.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=True))
