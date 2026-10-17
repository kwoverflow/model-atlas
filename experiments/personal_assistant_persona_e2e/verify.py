"""No new model calls: check hashes, public transport and deterministic replays."""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.services.personal_assistant.contracts import canonical  # noqa: E402

from .protocol import CASES, PERSONAS, VARIANTS  # noqa: E402
from .run import sha, summarize, write  # noqa: E402
from .workflow import make_service, raw_score, run_case  # noqa: E402


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify(source, output, browser=None):
    output.mkdir()
    plan, summary = read(source / "protocol.json"), read(source / "summary.json")
    rows, transport = read(source / "observations.json"), read(source / "transport.json")
    assert sha((source / "protocol.json").read_bytes()) == summary["protocol_sha256"]
    assert (source / "protocol.sha256").read_text() == summary["protocol_sha256"]
    for name in ("observations", "transport", "faults"):
        assert sha((source / f"{name}.json").read_bytes()) == summary[f"{name}_sha256"]
    for relative, expected in plan["sources"].items():
        assert sha((source / "sources" / relative).read_bytes()) == expected
        assert sha((REPO / relative).read_bytes()) == expected, f"Replay source drift: {relative}"
    assert len(rows) == len(transport) == 34
    assert len({(r["persona"], r["case_id"]) for r in rows}) == 34
    expected_jobs = {(p.name, c.id) for p in PERSONAS for c in CASES}
    expected_jobs |= {(PERSONAS[0].name, c.id) for c in VARIANTS}
    assert {(r["persona"], r["case_id"]) for r in rows} == expected_jobs
    assert len(read(source / "faults.json")) == 6
    for row in rows:
        entry = transport[row["transport_index"]]
        assert entry["url"] == "http://127.0.0.1:11435/v1/chat/completions"
        body = entry["body"]
        assert body["model"] == "qwen3.5:9b"
        assert body["temperature"] == 0 and body["seed"] == 42
        assert body["max_tokens"] == 768 and body["reasoning_effort"] == "none"
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        public = json.loads(body["messages"][1]["content"])["input"]
        assert set(public) == {
            "request",
            "now",
            "timezone",
            "intent_contract",
            "draft_contract",
            "events",
            "tasks",
            "inventory",
        }
        assert public["request"] == row["request"]
        assert public["tasks"] == row["before"]["tasks"]
        assert public["events"] == row["before"]["events"]
        assert "goal_fields" not in public and "expected_fields" not in public
        assert (
            entry["response"]["choices"][0]["message"]["content"]
            == row["initial_record"]["raw_output"]
        )
        case = next(c for c in (*CASES, *VARIANTS) if c.id == row["case_id"])
        case = replace(case, request=row["request"], fields=row["goal_fields"], setup=None)
        persona = next(p for p in PERSONAS if p.name == row["persona"])
        service = make_service(output / f"{persona.name}-{case.id}")
        # Captured public state is replay setup only; it never becomes target-model input.
        with service.sandbox.connect() as db:
            for task in row["before"]["tasks"]:
                db.execute("INSERT INTO tasks VALUES(?,?)", (task["task_id"], canonical(task)))
            for event in row["before"]["events"]:
                db.execute("INSERT INTO events VALUES(?,?)", (event["event_id"], canonical(event)))
        assert service.state() == row["before"]
        captured = row["initial_record"]
        replay = run_case(
            service,
            case,
            persona,
            lambda *_, c=captured: {**c["metadata"], "raw_output": c["raw_output"]},
        )
        for key in (
            "raw_score",
            "completed",
            "completed_without_correction",
            "edit_keys",
            "planned_user_changes",
            "outcome",
            "expiry_mode",
        ):
            assert replay[key] == row[key], (case.id, key)
    recomputed = summarize(rows)
    for key, value in recomputed.items():
        assert summary[key] == value
    result = {
        "status": "passed",
        "model_calls": 0,
        "replayed_cases": len(rows),
        "source_archives_verified": len(plan["sources"]),
        "transport_entries_verified": len(transport),
        "summary": recomputed,
    }
    if browser:
        evidence = read(browser / "browser-e2e.json")
        assert evidence["status"] == "passed" and evidence["browser_flows"] == 10
        assert sha((browser / "protocol.json").read_bytes()) == evidence["protocol_sha256"]
        assert (
            sha((browser / "browser-source.mjs").read_bytes()) == evidence["browser_source_sha256"]
        )
        assert (
            not evidence["independent_human_attestation"] and evidence["reviewer_uses_goal_oracle"]
        )
        assert not evidence["page_errors"]
        observations = evidence["observations"]
        assert {o["case_id"] for o in observations} == {c.id for c in CASES}
        assert len(observations) == 10 and all(o["preapproval_unchanged"] for o in observations)
        scores = []
        for observation in observations:
            case = next(c for c in CASES if c.id == observation["case_id"])
            case = replace(case, fields=observation["goal_fields"])
            score = raw_score(observation["initial_record"]["raw_output"], case)
            scores.append({"case_id": case.id, **score})
        expiry = next(o for o in observations if o["case_id"] == "M10")
        assert expiry["elapsed_ms"] >= 300000 and expiry["expiry_mode"] == "real_wall_clock"
        assert expiry["before_approval_attempt"] == expiry["after"]
        assert expiry["rejection"] == {
            "status": 409,
            "data": {"detail": "approval_expired_or_state_changed"},
        }
        result["browser"] = {
            "flows": 10,
            "real_expiry_seconds": expiry["elapsed_ms"] / 1000,
            "strict_valid": sum(s["strict_valid"] for s in scores),
            "original_model_correct": sum(s["correct"] for s in scores),
            "raw_scores": scores,
        }
    write(output / "verification.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--browser", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.source.resolve(),
                args.output.resolve(),
                args.browser.resolve() if args.browser else None,
            ),
            ensure_ascii=False,
        )
    )
