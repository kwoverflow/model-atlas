"""Finite real-model review experiment with archived protocol and transport inputs."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.services.personal_assistant.inference import (  # noqa: E402
    MODEL,
    AssistantDraftAdapter,
    generate_draft,
)

from .faults import run_faults  # noqa: E402
from .protocol import CASES, PERSONAS, VARIANTS, protocol  # noqa: E402
from .workflow import make_service, run_case  # noqa: E402


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def summarize(rows):
    groups = {}
    for name in sorted({r["persona"] for r in rows}):
        values = [r for r in rows if r["persona"] == name]
        groups[name] = {
            "cases": len(values),
            "strict_draft_valid": sum(r["raw_score"]["strict_valid"] for r in values),
            "original_model_correct": sum(r["raw_score"]["correct"] for r in values),
            "completed_without_correction": sum(r["completed_without_correction"] for r in values),
            "completed_after_correction": sum(
                r["completed"] and bool(r["edit_keys"]) for r in values
            ),
            "completed": sum(r["completed"] for r in values),
            "corrected_field_keys": sum(len(r["edit_keys"]) for r in values),
            "planned_user_changes": sum(r["planned_user_changes"] for r in values),
            "abandoned": sum(not r["completed"] for r in values),
            "outcomes": dict(Counter(r["outcome"] for r in values)),
        }
    return {
        "groups": groups,
        "preapproval_unchanged": sum(r["preapproval_unchanged"] for r in rows),
        "checked_cases": len(rows),
        "independent_human_attestation": False,
        "reviewer_uses_goal_oracle": True,
        "model_release_gate": "BLOCKED_UNCHANGED",
        "safety_claim": (
            "No assertion failed under idealized synthetic review; not a real-user error rate."
        ),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir()  # Exclusive: no overwrite, reset, or reused evidence directory.
    (output / "sources").mkdir()
    source_paths = sorted((REPO / "experiments/personal_assistant_persona_e2e").glob("*.py"))
    source_paths += sorted((REPO / "backend/app/services/personal_assistant").glob("*.py"))
    source_paths += [REPO / "backend/app/services/inference_adapters/openai_compatible.py"]
    sources = {}
    for source in source_paths:
        relative = source.relative_to(REPO).as_posix()
        data = source.read_bytes()
        archived = output / "sources" / relative
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.write_bytes(data)
        sources[relative] = sha(data)
    with urlopen("http://127.0.0.1:11435/api/tags", timeout=10) as response:
        models = json.load(response)["models"]
    model = next(m for m in models if m["name"] == MODEL)
    with urlopen("http://127.0.0.1:11435/api/version", timeout=10) as response:
        runtime = json.load(response)
    plan = {**protocol(), "sources": sources, "model": model, "runtime": runtime}
    write(output / "protocol.json", plan)
    protocol_hash = sha((output / "protocol.json").read_bytes())
    (output / "protocol.sha256").write_text(protocol_hash, encoding="ascii")
    rows = []
    transport = []
    post = AssistantDraftAdapter._post_json

    def captured(self, configuration, base_url, path, body, **kwargs):
        entry = {"url": base_url + path, "body": body}
        transport.append(entry)
        try:
            response = post(self, configuration, base_url, path, body, **kwargs)
            entry["response"] = response
            return response
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise

    def generator(request, state):
        return generate_draft(request, state, "http://127.0.0.1:11435", seed=42)

    try:
        with patch.object(AssistantDraftAdapter, "_post_json", captured):
            jobs = [(p, c) for p in PERSONAS for c in CASES]
            jobs += [(PERSONAS[0], c) for c in VARIANTS]
            for persona, case in jobs:
                service = make_service(output / f"{persona.name}-{case.id}")
                row = run_case(service, case, persona, generator)
                row["transport_index"] = len(transport) - 1
                rows.append(row)
                write(output / "observations.json", rows)
                write(output / "transport.json", transport)
                print(
                    json.dumps(
                        {
                            "persona": persona.name,
                            "case": case.id,
                            "model_correct": row["raw_score"]["correct"],
                            "outcome": row["outcome"],
                        }
                    ),
                    flush=True,
                )
        faults = run_faults(output / "faults")
        write(output / "faults.json", faults)
        summary = summarize(rows)
        summary.update(
            protocol_sha256=protocol_hash,
            fault_checks=len(faults),
            observations_sha256=sha((output / "observations.json").read_bytes()),
            transport_sha256=sha((output / "transport.json").read_bytes()),
            faults_sha256=sha((output / "faults.json").read_bytes()),
        )
        write(output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    except BaseException as exc:
        write(
            output / "failure.json",
            {"error": f"{type(exc).__name__}: {exc}", "completed_rows": len(rows)},
        )
        write(output / "observations.json", rows)
        write(output / "transport.json", transport)
        raise


if __name__ == "__main__":
    main()
