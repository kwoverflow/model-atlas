"""Recompute the fixed comparison without inference or response correction."""

import argparse
import json
from pathlib import Path

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.drafts import parse_draft
from app.services.personal_assistant.stable_inference import stable_decoding_schema

from .run import (
    ARMS,
    NOW,
    REPO,
    SEEDS,
    DraftAssistantService,
    exercise,
    holdout,
    scenarios,
    setup,
    sha,
    strict_score,
    summary,
    write,
)


def verify(source, output):
    output.mkdir()
    plan = json.loads((source / "protocol.json").read_text(encoding="utf-8"))
    rows = json.loads((source / "observations.json").read_text(encoding="utf-8"))
    result = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    assert sha(source / "protocol.json") == result["protocol_sha256"]
    assert sha(source / "observations.json") == result["observations_sha256"]
    assert plan["seeds"] == list(SEEDS) and plan["arms"] == list(ARMS)
    for relative, expected in plan["source_sha256"].items():
        assert sha(source / "sources" / relative) == expected
        assert sha(REPO / relative) == expected, relative
    for row in rows:
        case = next(
            c
            for c in (scenarios() if row["split"] == "regression" else holdout())
            if c.case_id == row["case_id"]
        )
        assert len(row["transport"]) == 1
        entry = row["transport"][0]
        native = row["arm"] == ARMS[1]
        if native:
            assert entry["url"] == "http://127.0.0.1:11435/api/generate"
            body = entry["request"]
            public = json.loads(body["prompt"])
            hints, grounded = stable_decoding_schema(case.request)
            assert body["format"] == hints
            assert row["generated"]["title_grounding"] == grounded
            assert row["generated"]["decoding_schema_sha256"] == digest(hints)
            assert body["options"]["seed"] == row["seed"] and body["options"]["num_predict"] == 768
            assert body["options"]["num_ctx"] == 8192 and body["think"] is False
            assert body["truncate"] is False and body["stream"] is False
            assert entry["response"]["response"] == row["raw_output"]
        else:
            assert entry["url"] == "http://127.0.0.1:11435/v1/chat/completions"
            body = entry["request"]
            assert body["seed"] == row["seed"] and body["max_tokens"] == 768
            public = json.loads(body["messages"][1]["content"])["input"]
            assert entry["response"]["choices"][0]["message"]["content"] == row["raw_output"]
        assert public["request"] == case.request and public["now"] == NOW
        assert public["tasks"] == row["before"]["tasks"]
        assert public["events"] == row["before"]["events"]
        assert public["inventory"] == [p.removeprefix("files/") for p in row["before"]["files"]]
        assert not {"confirmed_fields", "expected_fields", "goal_fields"} & public.keys()
        if native:
            assert set(public) == {"request", "now", "timezone", "events", "tasks", "inventory"}
        service = DraftAssistantService(
            setup(
                case, output / f"{row['split']}-{row['arm']}-{case.case_id}-{row['seed']}"
            ).sandbox
        )
        replay = exercise(case, service, row["raw_output"])
        assert replay["passed"] == row["passed"]
        assert replay["unchanged_before_approval"] == row["unchanged_before_approval"]
        score = strict_score(case, row["raw_output"])
        if row["generated"].get("completion_error"):
            score.update(valid=False, matches_confirmation=False)
        assert score == row["extraction"]
        if "decisions" in case.expected:
            try:
                draft = parse_draft(row["raw_output"])
                decision = (
                    score["valid"]
                    and draft.intent is None
                    and draft.decision in case.expected["decisions"]
                )
            except ValueError:
                decision = False
            assert decision == row["negative_decision_correct"]
    for key, expected in summary(rows).items():
        assert result[key] == expected
    verification = {
        "status": "passed",
        "replayed": len(rows),
        "source_archives_verified": len(plan["source_sha256"]),
        "transport_entries_verified": len(rows),
        "model_calls": 0,
        "adoption": result["adoption"],
    }
    write(output / "verification.json", verification)
    return verification


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source.resolve(), args.output.resolve())))
