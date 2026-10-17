"""Recheck saved effects, protocol, raw response replay and local source integrity."""

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from app.services.personal_assistant.sandbox import Sandbox
from app.services.personal_assistant.service import AssistantService

from experiments.personal_assistant_eval.run import digest, write_json

from .run import SEEDS, assert_effect, exercise, setup, summarize
from .scenarios import scenarios


def verify(output: Path, replay_output: Path) -> dict:
    output = output.absolute()
    repo = Path(__file__).resolve().parents[2]
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    checksum = protocol.pop("content_sha256")
    assert digest(protocol) == checksum, "protocol_hash_mismatch"
    assert protocol["scenarios"] == [asdict(c) for c in scenarios()], "scenario_drift"
    assert protocol["seeds"] == list(SEEDS), "seed_drift"
    for name, expected in protocol["source_sha256"].items():
        relative = Path(name)
        assert not relative.is_absolute() and ".." not in relative.parts
        captured = output / "executed-source" / relative
        assert hashlib.sha256(captured.read_bytes()).hexdigest() == expected, name
        assert hashlib.sha256((repo / relative).read_bytes()).hexdigest() == expected, name
    observations_path = output / "observations.jsonl"
    rows = [json.loads(line) for line in observations_path.read_text(encoding="utf-8").splitlines()]
    saved_summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert saved_summary["protocol_sha256"] == checksum
    assert (
        hashlib.sha256(observations_path.read_bytes()).hexdigest()
        == saved_summary["observations_sha256"]
    )
    calculated = summarize(rows)
    assert calculated["coverage_complete"]
    for key, value in calculated.items():
        assert saved_summary[key] == value, key
    allowed = (repo / "artifacts/personal-assistant-e2e").resolve()
    assert replay_output.resolve().is_relative_to(allowed)
    assert not replay_output.resolve().is_relative_to(output.resolve())
    replay_output.mkdir(parents=True, exist_ok=False)
    cases = {c.case_id: c for c in scenarios()}
    checks = []
    for row in rows:
        assert not row.get("runtime_error"), "runtime failure requires separate investigation"
        case = cases[row["case_id"]]
        name = f"{case.case_id}-{row['seed']}"
        original = AssistantService(Sandbox(output / "sandboxes" / name))
        assert original.state() == row["after"], f"persisted_state_mismatch:{name}"
        assert original.audit() == row["audit"], f"audit_mismatch:{name}"
        if "receipt" in row:
            assert_effect(case, row["after_execution"], row["before"], row["receipt"])
        fresh = setup(case, replay_output / name)
        replayed = exercise(case, fresh, row["raw_output"])
        for key in ("passed", "preview_created", "unchanged_before_approval", "guard_error"):
            assert replayed.get(key) == row.get(key), f"raw_replay_mismatch:{name}:{key}"
        checks.append({"case_id": case.case_id, "seed": row["seed"], "verified": True})
    sentinel = output / "outside.txt"
    assert sentinel.read_text(encoding="utf-8") == "Untouched external synthetic sentinel."
    return {
        "status": "verified",
        "records": len(checks),
        "checks": checks,
        "protocol_sha256": checksum,
        "source_snapshots": len(protocol["source_sha256"]),
        "gate": calculated["gate"],
        "passed": calculated["passed"],
        "scope": "local_integrity_and_deterministic_replay_not_new_inference_or_external_review",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay-output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.output, args.replay_output)
    write_json(args.replay_output / "verification.json", result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
