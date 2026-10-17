"""Independently replay saved raw responses; perform no inference or human actions."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from experiments.personal_assistant_draft_e2e.run import public_input
from experiments.personal_assistant_draft_e2e.scenarios import scenarios
from experiments.personal_assistant_e2e.run import exercise, setup
from experiments.personal_assistant_eval.run import write_json
from experiments.personal_assistant_runtime_ab.run import comparison, strict_score
from jsonschema import ValidationError, validate

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.drafts import DraftAssistantService
from app.services.personal_assistant.inference import (
    AssistantDraftAdapter,
    OllamaGenerateDraftAdapter,
    draft_schema,
)


def verify(root):
    protocol = json.loads((root / "protocol.json").read_text(encoding="utf-8"))
    content_hash = protocol.pop("content_sha256")
    assert digest(protocol) == content_hash, "protocol_hash_mismatch"
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    assert summary["protocol_sha256"] == content_hash
    assert (
        hashlib.sha256((root / "observations.jsonl").read_bytes()).hexdigest()
        == (summary["observations_sha256"])
    ), "observations_hash_mismatch"
    for name, expected in protocol["source_sha256"].items():
        assert hashlib.sha256((root / "executed-source" / name).read_bytes()).hexdigest() == (
            expected
        ), f"source_snapshot_changed:{name}"
    observations = [
        json.loads(line)
        for line in (root / "observations.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    cases = {c.case_id: c for c in scenarios()}
    assert protocol["validation_schema"] == draft_schema()
    assert not protocol["confirmation_fields_visible_to_model"]
    runtime = json.loads((root / "runtime.json").read_text(encoding="utf-8"))
    assert runtime["version"]["version"] == "0.31.1"
    identity = next(m for m in runtime["models"]["models"] if m["name"] == protocol["model"])
    assert identity["digest"] == protocol["expected_digest"]
    resident = json.loads((root / "resident.json").read_text(encoding="utf-8"))
    loaded = next(m for m in resident["models"] if m["name"] == protocol["model"])
    assert loaded["context_length"] == 8192 and loaded["size_vram"] > 0
    shape_valid = {"chat": 0, "generate": 0}
    config = SimpleNamespace(
        context_length=8192,
        runtime_config_json={"prompt_bundle": {"system_prompt": protocol["prompt"]}},
    )
    replayed = 0
    with tempfile.TemporaryDirectory(prefix="atlas-runtime-replay-") as temporary:
        for index, row in enumerate(observations):
            case = cases[row["case_id"]]
            payload = {**public_input(case), "draft_contract": draft_schema()}
            request = row["transport"]["request"]
            evaluation_case = SimpleNamespace(
                category="personal_assistant_json",
                input_payload_json=payload,
                expected_output_json=draft_schema(),
                expected_tool_schema_json=None,
            )
            expected_system = AssistantDraftAdapter()._system_prompt(config, evaluation_case)
            if row["arm"] == "chat":
                assert row["transport"]["endpoint"] == "/v1/chat/completions"
                public_message = request["messages"][1]["content"]
                assert (
                    row["raw_output"]
                    == row["transport"]["response"]["choices"][0]["message"]["content"]
                )
                assert request["seed"] == row["seed"]
                assert [m["role"] for m in request["messages"]] == ["system", "user"]
                assert request["messages"][0]["content"] == expected_system
                assert request["model"] == protocol["model"]
                assert all(request[key] == value for key, value in protocol["generation"].items())
                assert request["response_format"]["json_schema"]["schema"] == draft_schema()
            else:
                assert row["transport"]["endpoint"] == "/api/generate"
                public_message = request["prompt"]
                assert row["raw_output"] == row["transport"]["response"]["response"]
                assert request["format"] == protocol["decoding_schema"]
                assert request["system"] == expected_system
                expected = OllamaGenerateDraftAdapter.generate_body(
                    SimpleNamespace(context_length=8192),
                    {
                        "messages": [
                            {"role": "system", "content": request["system"]},
                            {"role": "user", "content": public_message},
                        ],
                        "model": protocol["model"],
                        "seed": row["seed"],
                        **protocol["generation"],
                    },
                )
                assert request == expected
            public = json.loads(public_message)
            assert set(public) == {"case_id", "category", "title", "input"}
            assert public["input"] == payload, "private_expected_input_leak"
            assert public["case_id"] == row["case_id"]
            try:
                validate(json.loads(row["raw_output"]), protocol["validation_schema"])
                shape_valid[row["arm"]] += 1
            except (ValueError, ValidationError):
                pass
            assert row["extraction"] == strict_score(case, row["raw_output"])
            service = DraftAssistantService(setup(case, Path(temporary) / str(index)).sandbox)
            result = exercise(case, service, row["raw_output"])
            assert result["passed"] == row["passed"], f"workflow_replay_mismatch:{index}"
            assert result["unchanged_before_approval"] == row["unchanged_before_approval"]
            assert row["outside_sentinel_unchanged"]
            replayed += 1
    recalculated = comparison(observations)
    assert all(summary[k] == value for k, value in recalculated.items())
    return {
        "verified": True,
        "replayed_workflows": replayed,
        "source_snapshots_verified": len(protocol["source_sha256"]),
        "protocol_sha256": content_hash,
        "adoption": summary["adoption"],
        "gate": summary["gate"],
        "json_schema_shape_valid": shape_valid,
        "independent_human_attestation": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = verify(args.run)
    write_json(args.output, result)
    print(json.dumps(result))
