"""Replay archived/new raw outputs and verify actual decoding and split evidence."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.decision_grounded_inference import (
    configuration_hash as baseline_hash,
)
from app.services.personal_assistant.decision_grounded_inference import decision_schema
from app.services.personal_assistant.semantic_grounded_inference import (
    configuration_hash,
    semantic_schema,
)
from jsonschema import validate

from experiments.personal_assistant_decision_grounding.verify import verify_spans

from .run import (
    BASELINE,
    BASELINE_OBSERVATIONS_SHA,
    CRITERIA,
    NOW,
    PROMPT,
    REPO,
    STRATEGY,
    DraftAssistantService,
    assess_meaning,
    baseline_data,
    exercise,
    holdout,
    regression,
    score,
    setup,
    sha,
    summary,
    write,
)


def decoding(public, arm, seed):
    if arm == BASELINE:
        return decision_schema(public), baseline_hash(public, seed)
    assert arm == STRATEGY
    return semantic_schema(public), configuration_hash(public, seed)


def verify(source, output):
    output.mkdir(parents=True)
    plan = json.loads((source / "protocol.json").read_text(encoding="utf-8"))
    rows = json.loads((source / "observations.json").read_text(encoding="utf-8"))
    result = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    assert sha(source / "protocol.json") == result["protocol_sha256"]
    assert sha(source / "observations.json") == result["observations_sha256"]
    assert plan["criteria"] == CRITERIA and plan["candidate_prompt"] == PROMPT
    assert plan["regression"] == [asdict(c) for c in regression()]
    assert plan["holdout"] == [asdict(c) for c in holdout()]
    for relative, expected in plan["source_sha256"].items():
        assert sha(source / "sources" / relative) == sha(REPO / relative) == expected, (
            relative
        )
    assert sha(source / "outside.txt") == plan["outside_sentinel_sha256"]
    _previous, baseline = baseline_data()
    cases = {c.case_id: c for c in [*regression(), *holdout()]}
    archived = 0
    for row in rows:
        case = cases[row["case_id"]]
        if "baseline_origin" in row:
            index, original = baseline[row["case_id"], row["seed"]]
            assert row["arm"] == BASELINE and row["split"] == "regression"
            assert row["baseline_origin"] == {
                "index": index,
                "split": original["split"],
                "observations_sha256": BASELINE_OBSERVATIONS_SHA,
            }
            assert {
                k: v
                for k, v in row.items()
                if k not in {"baseline_origin", "meaning_assessment", "split"}
            } == {k: v for k, v in original.items() if k != "split"}
            archived += 1
        assert len(row["transport"]) == 1 and not row.get("runtime_error")
        entry = row["transport"][0]
        body, generated = entry["request"], row["generated"]
        public = json.loads(body["prompt"])
        assert entry["url"] == "http://127.0.0.1:11435/api/generate"
        assert body["system"] == PROMPT and set(public) == {
            "request",
            "now",
            "timezone",
            "events",
            "tasks",
            "inventory",
        }
        assert public["request"] == case.request and public["now"] == NOW
        assert public["timezone"] == "Asia/Tokyo"
        assert (
            public["events"] == row["before"]["events"]
            and public["tasks"] == row["before"]["tasks"]
        )
        assert public["inventory"] == [
            p.removeprefix("files/")
            for p in row["before"]["files"]
            if p.startswith("files/")
        ]
        constraints, expected_hash = decoding(public, row["arm"], row["seed"])
        hints, title, path, role, fields, evidence = constraints
        key = "semantic_evidence" if row["arm"] == STRATEGY else "decision_evidence"
        assert generated[key] == evidence and generated[f"{key}_sha256"] == digest(
            evidence
        )
        assert evidence["public_input_sha256"] == digest(public)
        verify_spans(evidence, case.request)
        assert (
            body["format"] == hints and generated["configuration_hash"] == expected_hash
        )
        assert generated["decoding_schema_sha256"] == digest(hints)
        assert (
            generated["title_grounding"] == title
            and generated["path_grounding"] == path
        )
        assert (
            generated["role_grounding"] == role
            and generated["field_evidence"] == fields
        )
        verify_spans(fields, case.request)
        assert generated["strategy"] == row["arm"]
        assert body["options"] == {
            "num_ctx": 8192,
            "num_predict": 768,
            "temperature": 0,
            "top_p": 1,
            "seed": row["seed"],
        }
        assert (
            body["think"] is False
            and body["stream"] is False
            and body["truncate"] is False
        )
        assert entry["response"]["response"] == row["raw_output"]
        if generated["schema_valid"]:
            validate(json.loads(row["raw_output"]), hints)
        service = DraftAssistantService(
            setup(
                case,
                output / f"{row['split']}-{row['arm']}-{case.case_id}-{row['seed']}",
            ).sandbox
        )
        replay = exercise(case, service, row["raw_output"])
        assert (
            replay["passed"] == row["passed"]
            and replay["unchanged_before_approval"] == row["unchanged_before_approval"]
        )
        assert score(case, row["raw_output"], generated) == (
            row["extraction"],
            row["decision_correct"],
        )
        assert row["meaning_assessment"] == assess_meaning(
            case, generated, row["raw_output"]
        )
        assert row["sentinel_unchanged"]
    for key, expected in summary(rows).items():
        assert result[key] == expected
    value = {
        "status": "passed",
        "replayed": len(rows),
        "model_calls": 0,
        "archived_observations": archived,
        "new_scored_requests": len(rows) - archived,
        "sources_verified": len(plan["source_sha256"]),
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
