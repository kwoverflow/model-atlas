"""Independently replay effects and validate the actual frozen decoding transport."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from jsonschema import validate

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.path_grounded_inference import (
    configuration_hash,
    grounded_schema,
)
from app.services.personal_assistant.stable_inference import stable_decoding_schema

from .run import (
    ARMS,
    BASELINE,
    CRITERIA,
    NOW,
    PROMPT,
    REPO,
    SEEDS,
    DraftAssistantService,
    exercise,
    holdout,
    regression,
    score,
    setup,
    sha,
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
    assert plan["criteria"] == CRITERIA
    assert plan["arms"] == list(ARMS) and plan["seeds"] == list(SEEDS)
    assert plan["regression"] == [asdict(c) for c in regression()]
    assert plan["holdout"] == [asdict(c) for c in holdout()]
    assert plan["candidate_prompt"] == PROMPT
    for relative, expected in plan["source_sha256"].items():
        assert sha(source / "sources" / relative) == sha(REPO / relative) == expected, relative
    assert sha(source / "outside.txt") == plan["outside_sentinel_sha256"]
    for row in rows:
        case = next(
            c
            for c in (regression() if row["split"] == "regression" else holdout())
            if c.case_id == row["case_id"]
        )
        assert len(row["transport"]) == 1 and not row.get("runtime_error")
        entry = row["transport"][0]
        assert entry["url"] == "http://127.0.0.1:11435/api/generate"
        body = entry["request"]
        public = json.loads(body["prompt"])
        assert body["system"] == PROMPT
        assert set(public) == {"request", "now", "timezone", "events", "tasks", "inventory"}
        assert public["request"] == case.request and public["now"] == NOW
        assert public["events"] == row["before"]["events"]
        assert public["tasks"] == row["before"]["tasks"]
        inventory = [
            p.removeprefix("files/") for p in row["before"]["files"] if p.startswith("files/")
        ]
        assert public["inventory"] == inventory
        if row["arm"] == BASELINE:
            hints, title = stable_decoding_schema(case.request)
        else:
            hints, title, path = grounded_schema(case.request, inventory)
            assert row["generated"]["path_grounding"] == path
            assert row["generated"]["configuration_hash"] == configuration_hash(
                case.request, inventory, row["seed"]
            )
        assert body["format"] == hints
        assert row["generated"]["title_grounding"] == title
        assert row["generated"]["decoding_schema_sha256"] == digest(hints)
        assert row["generated"]["strategy"] == row["arm"]
        assert body["options"] == {
            "num_ctx": 8192,
            "num_predict": 768,
            "temperature": 0,
            "top_p": 1,
            "seed": row["seed"],
        }
        assert body["think"] is False and body["stream"] is False and body["truncate"] is False
        assert entry["response"]["response"] == row["raw_output"]
        if row["generated"]["schema_valid"]:
            validate(json.loads(row["raw_output"]), hints)
        service = DraftAssistantService(
            setup(
                case, output / f"{row['split']}-{row['arm']}-{case.case_id}-{row['seed']}"
            ).sandbox
        )
        replay = exercise(case, service, row["raw_output"])
        assert replay["passed"] == row["passed"]
        assert replay["unchanged_before_approval"] == row["unchanged_before_approval"]
        assert score(case, row["raw_output"], row["generated"]) == (
            row["extraction"],
            row["decision_correct"],
        )
        assert row["sentinel_unchanged"]
    for key, expected in summary(rows).items():
        assert result[key] == expected
    verification = {
        "status": "passed",
        "replayed": len(rows),
        "model_calls": 0,
        "sources_verified": len(plan["source_sha256"]),
        "transports_verified": len(rows),
        "candidate_gate": result["candidate_gate"],
    }
    write(output / "verification.json", verification)
    return verification


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source.resolve(), args.output.resolve())))
