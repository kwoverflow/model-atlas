"""Zero-model release replay, including native schema and truthful explanation policy."""

import argparse
import json
from pathlib import Path

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.release_generation import (
    configuration_hash,
    release_schema,
)
from app.services.personal_assistant.stable_inference import PROMPT
from jsonschema import validate

from experiments.personal_assistant_decision_grounding.verify import verify_spans

from .run import (
    CRITERIA,
    NOW,
    REPO,
    DraftAssistantService,
    assess_meaning,
    assess_policy,
    baseline,
    exercise,
    score,
    setup,
    sha,
    splits,
    summary,
    write,
)


def verify(source, output):
    output.mkdir(parents=True)
    plan = json.loads((source / "protocol.json").read_text(encoding="utf-8"))
    rows = json.loads((source / "observations.json").read_text(encoding="utf-8"))
    result = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    assert plan["criteria"] == CRITERIA
    assert sha(source / "protocol.json") == result["protocol_sha256"]
    assert sha(source / "observations.json") == result["observations_sha256"]
    for relative, expected in plan["source_sha256"].items():
        assert sha(source / "sources" / relative) == sha(REPO / relative) == expected, (
            relative
        )
    baseline()
    cases = {(s, c.case_id): c for s, items in splits() for c in items}
    for row in rows:
        case = cases[row["split"], row["case_id"]]
        assert len(row["transport"]) == 1 and not row.get("runtime_error")
        entry = row["transport"][0]
        body, generated = entry["request"], row["generated"]
        public = json.loads(body["prompt"])
        assert entry["url"] == "http://127.0.0.1:11435/api/generate"
        assert set(public) == {
            "request",
            "now",
            "timezone",
            "events",
            "tasks",
            "inventory",
        }
        assert (
            body["system"] == PROMPT
            and public["request"] == case.request
            and public["now"] == NOW
        )
        assert (
            public["events"] == row["before"]["events"]
            and public["tasks"] == row["before"]["tasks"]
        )
        assert public["inventory"] == [
            p.removeprefix("files/")
            for p in row["before"]["files"]
            if p.startswith("files/")
        ]
        hints, title, path, role, fields, evidence, policy = release_schema(public)
        assert body["format"] == hints and generated[
            "configuration_hash"
        ] == configuration_hash(public, row["seed"])
        assert generated["decoding_schema_sha256"] == digest(hints)
        assert (
            generated["title_grounding"] == title
            and generated["path_grounding"] == path
        )
        assert (
            generated["role_grounding"] == role
            and generated["field_evidence"] == fields
        )
        assert generated["semantic_evidence"] == evidence and generated[
            "semantic_evidence_sha256"
        ] == digest(evidence)
        assert generated["release_explanation"] == policy
        verify_spans(fields, case.request)
        verify_spans(evidence, case.request)
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
            setup(case, output / f"{row['split']}-{case.case_id}-{row['seed']}").sandbox
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
        assert row["explanation_policy_correct"] == assess_policy(
            generated, row["raw_output"]
        )
        assert row["sentinel_unchanged"]
    assert sha(source / "outside.txt") == plan["outside_sentinel_sha256"]
    assert {k: v for k, v in result.items() if not k.endswith("_sha256")} == summary(
        rows
    )
    value = {
        "status": "passed",
        "model_calls": 0,
        "replayed": len(rows),
        "sources_verified": len(plan["source_sha256"]),
        "regression_gate": result["regression_gate"],
    }
    write(output / "verification.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.source.resolve(), args.output.resolve())))
