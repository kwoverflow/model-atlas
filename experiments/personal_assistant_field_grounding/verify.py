"""Audit frozen transport, source evidence and replay effects without inference."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from jsonschema import validate

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.field_grounded_inference import (
    configuration_hash,
    evidence_schema,
)
from app.services.personal_assistant.role_grounded_inference import configuration_hash as old_hash
from app.services.personal_assistant.role_grounded_inference import role_schema

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


def verify_spans(value, request):
    if isinstance(value, dict):
        if {"start", "end", "text"} <= value.keys():
            assert request[value["start"] : value["end"]] == value["text"]
        for item in value.values():
            verify_spans(item, request)
    elif isinstance(value, list):
        for item in value:
            verify_spans(item, request)


def verify(source, output):
    output.mkdir()
    plan = json.loads((source / "protocol.json").read_text(encoding="utf-8"))
    rows = json.loads((source / "observations.json").read_text(encoding="utf-8"))
    result = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    assert sha(source / "protocol.json") == result["protocol_sha256"]
    assert sha(source / "observations.json") == result["observations_sha256"]
    assert plan["criteria"] == CRITERIA and plan["candidate_prompt"] == PROMPT
    assert plan["arms"] == list(ARMS) and plan["seeds"] == list(SEEDS)
    assert plan["regression"] == [asdict(c) for c in regression()]
    assert plan["holdout"] == [asdict(c) for c in holdout()]
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
        body, generated = entry["request"], row["generated"]
        public = json.loads(body["prompt"])
        assert body["system"] == PROMPT
        assert set(public) == {"request", "now", "timezone", "events", "tasks", "inventory"}
        assert public["request"] == case.request and public["now"] == NOW
        assert public["timezone"] == "Asia/Tokyo"
        assert public["events"] == row["before"]["events"]
        assert public["tasks"] == row["before"]["tasks"]
        assert public["inventory"] == [
            p.removeprefix("files/") for p in row["before"]["files"] if p.startswith("files/")
        ]
        if row["arm"] == BASELINE:
            hints, title, path, role = role_schema(public)
            expected_hash = old_hash(public, row["seed"])
        else:
            hints, title, path, role, fields = evidence_schema(public)
            assert generated["field_evidence"] == fields
            verify_spans(fields, case.request)
            expected_hash = configuration_hash(public, row["seed"])
        assert body["format"] == hints and generated["title_grounding"] == title
        assert generated["path_grounding"] == path and generated["role_grounding"] == role
        assert generated["configuration_hash"] == expected_hash
        assert generated["decoding_schema_sha256"] == digest(hints)
        assert generated["strategy"] == row["arm"]
        assert body["options"] == {
            "num_ctx": 8192,
            "num_predict": 768,
            "temperature": 0,
            "top_p": 1,
            "seed": row["seed"],
        }
        assert body["think"] is False and body["stream"] is False and body["truncate"] is False
        assert entry["response"]["response"] == row["raw_output"]
        if generated["schema_valid"]:
            validate(json.loads(row["raw_output"]), hints)
        service = DraftAssistantService(
            setup(
                case, output / f"{row['split']}-{row['arm']}-{case.case_id}-{row['seed']}"
            ).sandbox
        )
        replay = exercise(case, service, row["raw_output"])
        assert replay["passed"] == row["passed"]
        assert replay["unchanged_before_approval"] == row["unchanged_before_approval"]
        assert score(case, row["raw_output"], generated) == (
            row["extraction"],
            row["decision_correct"],
        )
        assert row["sentinel_unchanged"]
    for key, expected in summary(rows).items():
        assert result[key] == expected
    value = {
        "status": "passed",
        "replayed": len(rows),
        "model_calls": 0,
        "sources_verified": len(plan["source_sha256"]),
        "transports_verified": len(rows),
        "candidate_gate": result["candidate_gate"],
    }
    write(output / "verification.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source.resolve(), args.output.resolve())))
