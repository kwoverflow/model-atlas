"""Verify captured sources, raw drafts, receipts, persisted state, and fresh replay."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.drafts import DraftAssistantService
from app.services.personal_assistant.sandbox import Sandbox

from experiments.personal_assistant_e2e.run import assert_effect, exercise, setup
from experiments.personal_assistant_eval.run import write_json

from .run import SEEDS, extraction_score, summarize
from .scenarios import scenarios


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(output: Path, replay_output: Path):
    repo = Path(__file__).resolve().parents[2]
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    checksum = protocol.pop("content_sha256")
    require(digest(protocol) == checksum, "protocol_hash_mismatch")
    require(protocol["scenarios"] == [asdict(c) for c in scenarios()], "scenario_drift")
    require(protocol["seeds"] == list(SEEDS), "seed_drift")
    require(
        protocol["confirmation_fields_visible_to_model"] is False, "confirmation_leak"
    )
    for name, expected in protocol["source_sha256"].items():
        relative = Path(name)
        require(
            not relative.is_absolute() and ".." not in relative.parts,
            "invalid_source_path",
        )
        for source in (repo / relative, output / "executed-source" / relative):
            require(
                hashlib.sha256(source.read_bytes()).hexdigest() == expected, str(source)
            )
    data_path = output / "observations.jsonl"
    rows = [
        json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines()
    ]
    saved = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    require(saved["protocol_sha256"] == checksum, "summary_protocol_mismatch")
    require(
        saved["observations_sha256"]
        == hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "observations_hash_mismatch",
    )
    summary = summarize(rows)
    require(summary["coverage_complete"], "coverage_mismatch")
    for key, value in summary.items():
        require(saved[key] == value, f"summary_mismatch:{key}")
    runtime = json.loads((output / "runtime.json").read_text(encoding="utf-8"))
    identity = next(
        m for m in runtime["models"]["models"] if m["name"] == protocol["model"]
    )
    resident = json.loads((output / "resident.json").read_text(encoding="utf-8"))
    loaded = next(m for m in resident["models"] if m["name"] == protocol["model"])
    require(
        loaded["digest"] == identity["digest"]
        and loaded["size_vram"] > 0
        and loaded["context_length"] == 8192,
        "resident_identity_mismatch",
    )
    allowed = (repo / "artifacts/personal-assistant-draft-e2e").resolve()
    require(
        replay_output.resolve().is_relative_to(allowed)
        and replay_output.resolve() != allowed,
        "replay_output_outside_scope",
    )
    require(
        not replay_output.resolve().is_relative_to(output.resolve()),
        "replay_overlaps_run",
    )
    replay_output.mkdir(parents=True, exist_ok=False)
    cases = {c.case_id: c for c in scenarios()}
    for row in rows:
        case = cases[row["case_id"]]
        name = f"{case.case_id}-{row['seed']}"
        require(not row.get("runtime_error"), f"runtime_error:{name}")
        original = DraftAssistantService(Sandbox(output / "sandboxes" / name))
        require(original.state() == row["after"], f"persisted_state_mismatch:{name}")
        require(original.audit() == row["audit"], f"audit_mismatch:{name}")
        require(
            extraction_score(case, row["raw_output"]) == row["extraction"],
            f"extraction_score_mismatch:{name}",
        )
        if "receipt" in row:
            assert_effect(case, row["after_execution"], row["before"], row["receipt"])
        service = DraftAssistantService(setup(case, replay_output / name).sandbox)
        replayed = exercise(case, service, row["raw_output"])
        for key in (
            "passed",
            "preview_created",
            "unchanged_before_approval",
            "guard_error",
        ):
            require(replayed.get(key) == row.get(key), f"replay_mismatch:{name}:{key}")
    require(
        (output / "outside.txt").read_text(encoding="utf-8")
        == "Untouched external synthetic sentinel.",
        "sentinel_changed",
    )
    return {
        "status": "verified",
        "records": len(rows),
        "gate": summary["gate"],
        "passed": summary["passed"],
        "protocol_sha256": checksum,
        "observations_sha256": saved["observations_sha256"],
        "source_snapshots": len(protocol["source_sha256"]),
        "model_digest": identity["digest"],
        "scope": "local_integrity_and_deterministic_replay_not_new_inference_or_external_review",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay-output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.output.absolute(), args.replay_output.absolute())
    write_json(args.replay_output / "verification.json", result)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
