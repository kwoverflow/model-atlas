"""Real subprocess termination and overlapping approvals in synthetic workspaces."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from app.services.personal_assistant.contracts import GuardError
from app.services.personal_assistant.reviews import ReviewService
from app.services.personal_assistant.sandbox import Sandbox

from .workflow import approve, binding, confirm, make_service, rejected

REPO = Path(__file__).resolve().parents[2]
MOVE = {
    "operation": "files.move",
    "source": "Inbox/review-demo.txt",
    "destination": "Archive/review-demo.txt",
}


def wait_file(path, process, timeout=20):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise AssertionError(f"Worker did not reach checkpoint: {process.poll()}")
        time.sleep(0.02)


def worker(root, record_id, mode):
    service = ReviewService(Sandbox(root))
    record = service.get(record_id)
    if mode != "competing":

        def interrupted(src, dst):
            if mode in {"linked", "moved", "modified"}:
                os.link(src, dst)
            if mode in {"moved", "modified"}:
                src.unlink()
            if mode == "modified":
                dst.write_bytes(b"Modified after file effect; recovery must block.\n")
            if mode == "independent_copy":
                dst.write_bytes(src.read_bytes())
            (root / "checkpoint").write_text(mode, encoding="utf-8")
            while not (root / "release").exists():
                time.sleep(0.02)
            # Concurrent test continues; killed tests never reach this point.
            if mode == "before":
                Sandbox.move_exclusive(src, dst)

        service.sandbox.move_exclusive = interrupted
    try:
        record = approve(service, record)
        result = {"status": record["status"], "replayed": record["receipt"]["replayed"]}
    except GuardError as exc:
        result = {"rejection": str(exc)}
    (root / f"worker-{mode}.json").write_text(json.dumps(result), encoding="utf-8")


def spawn(root, record, mode):
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "experiments.personal_assistant_persona_e2e.faults",
            "--worker",
            str(root),
            "--record",
            record["id"],
            "--mode",
            mode,
        ],
        cwd=REPO,
        env={**os.environ, "PYTHONPATH": str(REPO / "backend")},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def pending_move(root):
    service = make_service(root)
    before = service.state()
    record = service.create(
        "Synthetic fault test",
        lambda *_: {
            "raw_output": json.dumps({"decision": "propose", "intent": MOVE, "reason": "Fixture"})
        },
    )
    return service, before, confirm(service, record)


def effect_snapshot(root):
    # An interrupted hardlink intentionally cannot be read through normal inventory.
    result = {}
    for name in ("Inbox/review-demo.txt", "Archive/review-demo.txt"):
        path = root / "files" / name
        result[name] = {"exists": path.exists()}
        if path.exists():
            result[name].update(
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(), links=path.stat().st_nlink
            )
    return result


def run_faults(base):
    base.mkdir()
    observations = []
    for mode in ("before", "linked", "moved", "modified", "independent_copy"):
        root = base / mode
        service, before, record = pending_move(root)
        process = spawn(root, record, mode)
        try:
            wait_file(root / "checkpoint", process)
            assert service.get(record["id"])["status"] == "executing"
            rejected(
                lambda s=service, r=record: s.recover(r["id"], **binding(r)),
                "workspace_execution_in_progress",
            )
            process.kill()
            process.communicate(timeout=10)
            assert process.returncode is not None and process.returncode != 0
            crashed = service.get(record["id"])
            effect = effect_snapshot(root)
            if mode in {"modified", "independent_copy"}:
                reason = rejected(
                    lambda s=service, r=crashed: s.recover(r["id"], **binding(r)),
                    "recovery_state_ambiguous",
                )
                assert effect_snapshot(root) == effect
                outcome = {"rejection": reason}
            else:
                recovered = service.recover(record["id"], **binding(crashed))
                assert recovered["status"] == ("executed" if mode == "moved" else "cancelled")
                if mode == "moved":
                    assert service.state()["files"] == {
                        "files/Archive/review-demo.txt": before["files"][
                            "files/Inbox/review-demo.txt"
                        ]
                    }
                    assert (
                        approve(service, recovered)["events"][-1]["event"] == "execution_replayed"
                    )
                else:
                    assert service.state() == before
                outcome = {"status": recovered["status"]}
            observations.append(
                {
                    "mode": mode,
                    "process_terminated": True,
                    "exit_code": process.returncode,
                    "lock_released": True,
                    "outcome": outcome,
                    "before": before,
                    "interrupted_effect": effect,
                    "after": effect_snapshot(root),
                }
            )
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    root = base / "concurrent"
    service, before, record = pending_move(root)
    first = spawn(root, record, "before")
    second = None
    try:
        wait_file(root / "checkpoint", first)
        second = spawn(root, record, "competing")
        _, stderr = second.communicate(timeout=20)
        assert second.returncode == 0, stderr.decode(errors="replace")
        competitor = json.loads((root / "worker-competing.json").read_text())
        assert competitor == {"rejection": "workspace_execution_in_progress"}
        (root / "release").write_text("continue", encoding="utf-8")
        _, stderr = first.communicate(timeout=20)
        assert first.returncode == 0, stderr.decode(errors="replace")
        after = service.state()
        assert after["files"] == {
            "files/Archive/review-demo.txt": before["files"]["files/Inbox/review-demo.txt"]
        }
        assert (
            approve(service, service.get(record["id"]))["events"][-1]["event"]
            == "execution_replayed"
        )
        assert service.state() == after
        assert sum(e["event"] == "executed" for e in service.get(record["id"])["events"]) == 1
        observations.append(
            {
                "mode": "concurrent",
                "overlapping_processes": True,
                "competitor": competitor,
                "executions": 1,
                "replay_unchanged": True,
                "before": before,
                "after": after,
            }
        )
    finally:
        for process in (first, second):
            if process and process.poll() is None:
                process.kill()
                process.communicate(timeout=10)
    return observations


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--mode", required=True)
    args = parser.parse_args()
    worker(args.worker.resolve(), args.record, args.mode)
