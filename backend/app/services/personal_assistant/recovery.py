"""Reconcile only the two recorded names of an interrupted same-volume file operation."""

import hashlib
import os

from .contracts import LOGICAL_ROOT, GuardError, canonical


def _path(sandbox, relative, area):
    try:
        return sandbox.file_path(relative, area=area)
    except GuardError as exc:
        if str(exc) != "hardlinked_file":
            raise
        # file_path checked all ancestors and path syntax before the hardlink check.
        return sandbox.root / area / relative


def reconcile_file(sandbox, db, proposal, before_files, action):
    tool, args = action["tool"], action["arguments"]
    if tool == "files.restore":
        source, source_area = args["source"], args["source_area"]
        destination, destination_area = args["destination"], "files"
    elif tool == "files.move":
        source = args["source"].removeprefix(LOGICAL_ROOT + "/")
        destination = args["destination"].removeprefix(LOGICAL_ROOT + "/")
        source_area, destination_area = "files", "files"
    elif tool == "files.trash":
        source = args["path"].removeprefix(LOGICAL_ROOT + "/")
        source_area, destination_area, destination = "files", "trash", proposal["id"]
    else:
        raise GuardError("file_recovery_only")
    expected = before_files.get(f"{source_area}/{source}", {}).get("sha256")
    if not expected:
        raise GuardError("recovery_evidence_missing")
    src, dst = _path(sandbox, source, source_area), _path(sandbox, destination, destination_area)
    for path in (src, dst):
        if path.exists() and (
            not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise GuardError("recovery_state_ambiguous")
    if src.exists() and dst.exists():
        if not os.path.samefile(src, dst) or src.stat().st_nlink != 2:
            raise GuardError("recovery_state_ambiguous")
        dst.unlink()
        outcome = "rolled_back_link"
    elif src.exists():
        if src.stat().st_nlink != 1:
            raise GuardError("recovery_state_ambiguous")
        outcome = "no_effect"
    elif dst.exists():
        if dst.stat().st_nlink != 1:
            raise GuardError("recovery_state_ambiguous")
        receipt = {
            "proposal_id": proposal["id"],
            "status": "executed",
            "replayed": False,
            "recovered": True,
            "file_change": {
                "source": source,
                "source_area": source_area,
                "destination": destination,
                "destination_area": destination_area,
                "sha256": expected,
            },
        }
        db.execute(
            "UPDATE proposals SET status='executed',receipt=? WHERE id=?",
            (canonical(receipt), proposal["id"]),
        )
        return "completed_effect_recorded"
    else:
        raise GuardError("recovery_state_ambiguous")
    db.execute("UPDATE proposals SET status='cancelled' WHERE id=?", (proposal["id"],))
    return outcome
