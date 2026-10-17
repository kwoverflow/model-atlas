"""Recalculate a saved campaign without calling any model or executing any action."""

import argparse
import ast
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .evaluation import score, summarize
from .run import SEEDS, digest, write_json
from .suite import cases


def verify(directory: Path) -> dict:
    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8"))
    recorded_digest = protocol.pop("content_sha256")
    if digest(protocol) != recorded_digest:
        raise ValueError("Protocol hash mismatch")
    suite = {case.case_id: case for case in cases()}
    if [asdict(case) for case in suite.values()] != protocol["cases"]:
        raise ValueError("Current suite differs from the recorded protocol")
    source_checks = {}
    for name, expected in protocol["source_sha256"].items():
        snapshot = directory / "executed-source" / name
        content = snapshot.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"Executed-source snapshot mismatch: {name}")
        current = (Path(__file__).parent / name).read_bytes()
        unchanged_ast = ast.dump(ast.parse(current)) == ast.dump(ast.parse(content))
        if not unchanged_ast:
            raise ValueError(f"Current source AST differs from executed source: {name}")
        source_checks[name] = {
            "recorded_bytes_verified": True,
            "current_ast_unchanged": True,
            "current_bytes_unchanged": current == content,
        }
    comparison = json.loads((directory / "comparison.json").read_text(encoding="utf-8"))
    if comparison["protocol_sha256"] != recorded_digest:
        raise ValueError("Comparison does not reference this protocol")
    expected_trials = Counter((case_id, seed) for case_id in suite for seed in SEEDS)
    models = {}
    for model, entry in comparison["models"].items():
        path = directory / (model.replace(":", "-") + ".jsonl")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if Counter((row["case_id"], row["seed"]) for row in rows) != expected_trials:
            raise ValueError(f"Missing or duplicated observations: {model}")
        for row in rows:
            case = suite[row["case_id"]]
            if row["critical"] != case.critical or row["domain"] != case.domain:
                raise ValueError("Case metadata mismatch")
            if score(case, row["raw_output"]) != row["score"]:
                raise ValueError("Recorded score differs from recalculated score")
            resident = row["resident"]["models"]
            if len(resident) != 1 or resident[0]["digest"] != entry["model_identity"]["digest"]:
                raise ValueError("Model residency identity mismatch")
            if resident[0]["size_vram"] <= 0 or resident[0]["context_length"] != 8192:
                raise ValueError("GPU/context residency mismatch")
        if summarize(rows) != entry["summary"]:
            raise ValueError("Recorded summary differs from recalculated policy evaluation")
        models[model] = {
            "observations": len(rows),
            "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "recomputed_scores_match": True,
            "recomputed_gate": entry["summary"]["gate"],
        }
    return {
        "status": "verified",
        "protocol_sha256": recorded_digest,
        "models": models,
        "source_checks": source_checks,
        "scope": "Local data integrity and score recomputation, not external attestation.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.directory)
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
