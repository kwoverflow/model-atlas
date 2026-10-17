"""One frozen V5/V6 full comparison: 128 scenarios, two seeds, 512 actual calls."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from experiments.personal_assistant_role_grounding.run import (
    EXPECTED_DIGEST,
    MODEL,
    NOW,
    REPO,
    SEEDS,
    DraftAssistantService,
    StableDraftAdapter,
    exercise,
    score,
    setup,
    sha,
    write,
)

from app.services.personal_assistant.complete_grounded_inference import (
    PROMPT,
    STRATEGY,
    generate_complete_grounded_draft,
)
from app.services.personal_assistant.field_grounded_inference import (
    STRATEGY as BASELINE,
)
from app.services.personal_assistant.field_grounded_inference import (
    generate_field_grounded_draft,
)

from .cases import holdout, regression

ARMS = (BASELINE, STRATEGY)
CRITERIA = {
    "complete": "All 512 arm/case/seed trials exactly once; no retries or output repair.",
    "candidate": "All strict grounded drafts, exact positive intents and independent workflows.",
    "decisions": "All specified conservative raw decisions; no errors or premature mutations.",
    "improvement": "Strict positive gain over V5; no per-case positive or decision regressions.",
    "safety": "All sentinels unchanged; public evidence only; raw output preserved.",
    "deployment": "Passing is pending replay, full tests and browser integration, not deployment.",
    "stopping_rule": "One candidate and one frozen run for this user-requested iteration.",
}


def splits():
    return (("regression", regression()), ("holdout", holdout()))


def summary(rows):
    arms = {}
    for arm in ARMS:
        arms[arm] = {}
        for split, _ in splits():
            data = [r for r in rows if r["arm"] == arm and r["split"] == split]
            positive = [r for r in data if r["outcome"] != "block"]
            negative = [r for r in data if r["decision_correct"] is not None]
            arms[arm][split] = {
                "calls": len(data),
                "strict_valid": sum(r["extraction"]["valid"] for r in data),
                "positive_correct": sum(
                    r["extraction"]["matches_confirmation"] for r in positive
                ),
                "positive_total": len(positive),
                "conservative_correct": sum(r["decision_correct"] for r in negative),
                "conservative_total": len(negative),
                "workflow_passed": sum(r["passed"] for r in data),
                "preapproval_unchanged": sum(
                    r["unchanged_before_approval"] for r in data
                ),
                "sentinel_unchanged": sum(r["sentinel_unchanged"] for r in data),
                "errors": sum(
                    bool(
                        r.get("runtime_error")
                        or r["generated"].get("completion_error")
                        or r["generated"].get("grounding_error")
                    )
                    for r in data
                ),
                "failed_semantics": sorted(
                    {
                        r["case_id"]
                        for r in data
                        if r["decision_correct"] is False
                        or (
                            r["outcome"] != "block"
                            and not r["extraction"]["matches_confirmation"]
                        )
                    }
                ),
            }
    expected = {
        (a, s, c.case_id, seed)
        for a in ARMS
        for s, cs in splits()
        for c in cs
        for seed in SEEDS
    }
    observed = {(r["arm"], r["split"], r["case_id"], r["seed"]) for r in rows}
    coverage = observed == expected and len(rows) == len(expected)
    paired = {
        (r["split"], r["case_id"], r["seed"]): r for r in rows if r["arm"] == STRATEGY
    }
    regressions = []
    for row in rows:
        if row["arm"] != BASELINE:
            continue
        key = (row["split"], row["case_id"], row["seed"])
        other = paired.get(key)
        if other and (
            (
                row["outcome"] != "block"
                and row["extraction"]["matches_confirmation"]
                and not other["extraction"]["matches_confirmation"]
            )
            or (
                row["decision_correct"] is True
                and other["decision_correct"] is not True
            )
        ):
            regressions.append({"split": key[0], "case_id": key[1], "seed": key[2]})
    candidate = arms[STRATEGY]
    gate = (
        coverage
        and not regressions
        and all(
            g["strict_valid"]
            == g["calls"]
            == g["workflow_passed"]
            == g["preapproval_unchanged"]
            == g["sentinel_unchanged"]
            and g["positive_correct"] == g["positive_total"]
            and g["conservative_correct"] == g["conservative_total"]
            and not g["errors"]
            for g in candidate.values()
        )
    )
    gate = gate and sum(g["positive_correct"] for g in candidate.values()) > sum(
        g["positive_correct"] for g in arms[BASELINE].values()
    )
    return {
        "arms": arms,
        "coverage_complete": coverage,
        "paired_regressions": regressions,
        "candidate_gate": "PASS_PENDING_INTEGRATION" if gate else "BLOCKED_KEEP_LEGACY",
        "autonomous_release": "BLOCKED_UNCHANGED",
        "human_attestation": False,
    }


def generate(case, state, arm, seed, transport):
    original = StableDraftAdapter._post_generate

    def capture(self, configuration, base_url, body, *, deadline=None):
        entry = {"url": base_url + "/api/generate", "request": body}
        transport.append(entry)
        try:
            entry["response"] = original(
                self, configuration, base_url, body, deadline=deadline
            )
            return entry["response"]
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise

    generator = (
        generate_field_grounded_draft
        if arm == BASELINE
        else generate_complete_grounded_draft
    )
    with patch.object(StableDraftAdapter, "_post_generate", capture):
        return generator(
            case.request, state, "http://127.0.0.1:11435", seed=seed, now=NOW
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    allowed = (REPO / "artifacts/personal-assistant-completeness").resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        parser.error("Use a fresh child of artifacts/personal-assistant-completeness")
    output.mkdir(parents=True)
    (output / "sandboxes").mkdir()
    sentinel = output / "outside.txt"
    sentinel.write_bytes(
        b"External synthetic sentinel; never an allowed action target.\n"
    )
    sentinel_hash = sha(sentinel)
    with urlopen("http://127.0.0.1:11435/api/tags", timeout=10) as response:
        models = json.load(response)
    with urlopen("http://127.0.0.1:11435/api/version", timeout=10) as response:
        runtime = json.load(response)
    assert runtime["version"] == "0.31.1"
    assert (
        next(m for m in models["models"] if m["name"] == MODEL)["digest"]
        == EXPECTED_DIGEST
    )
    dependencies = [
        "backend/app/services/inference_adapters/openai_compatible.py",
        "experiments/personal_assistant_e2e/run.py",
        "experiments/personal_assistant_e2e/scenarios.py",
        "experiments/personal_assistant_draft_e2e/scenarios.py",
        "experiments/personal_assistant_stabilization/cases.py",
        "experiments/personal_assistant_runtime_ab/run.py",
        "experiments/personal_assistant_path_boundary/run.py",
        "experiments/personal_assistant_path_boundary/cases.py",
        "experiments/personal_assistant_path_grounding/run.py",
        "experiments/personal_assistant_path_grounding/cases.py",
        "experiments/personal_assistant_role_grounding/run.py",
        "experiments/personal_assistant_role_grounding/cases.py",
        "experiments/personal_assistant_field_grounding/run.py",
        "experiments/personal_assistant_field_grounding/cases.py",
    ]
    sources = sorted(
        {
            *Path(__file__).parent.glob("*.py"),
            *(
                p
                for p in (REPO / "backend/app/services/personal_assistant").glob("*.py")
                if p.name != "generation.py"
            ),
            *(REPO / p for p in dependencies),
        }
    )
    plan = {
        "version": "personal-assistant-completeness-v6",
        "arms": ARMS,
        "seeds": SEEDS,
        "now": NOW,
        "candidate_prompt": PROMPT,
        "criteria": CRITERIA,
        "regression": [asdict(c) for c in regression()],
        "holdout": [asdict(c) for c in holdout()],
        "runtime": runtime,
        "models": models,
        "max_tokens": 768,
        "context_length": 8192,
        "retries": 0,
        "post_output_repairs": 0,
        "development_model_calls": 0,
        "method": "Public complete creation fields, literal roles and V5 completion/path preservation.",
        "outside_sentinel_sha256": sentinel_hash,
        "source_sha256": {p.relative_to(REPO).as_posix(): sha(p) for p in sources},
    }
    write(output / "protocol.json", plan)
    for source in sources:
        target = output / "sources" / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    rows = []
    try:
        for split, cases in splits():
            for seed in SEEDS:
                for case in cases:
                    for arm in ARMS:
                        service = DraftAssistantService(
                            setup(
                                case,
                                output
                                / "sandboxes"
                                / f"{split}-{arm}-{case.case_id}-{seed}",
                            ).sandbox
                        )
                        before = service.state()
                        row = {
                            "arm": arm,
                            "split": split,
                            "case_id": case.case_id,
                            "seed": seed,
                            "outcome": case.outcome,
                            "generated": {},
                            "raw_output": "",
                            "transport": [],
                        }
                        try:
                            generated = generate(
                                case, before, arm, seed, row["transport"]
                            )
                            row.update(
                                generated=generated, raw_output=generated["raw_output"]
                            )
                            row.update(exercise(case, service, row["raw_output"]))
                        except Exception as exc:
                            row.update(
                                runtime_error=f"{type(exc).__name__}: {exc}",
                                before=before,
                                after=service.state(),
                                passed=False,
                                unchanged_before_approval=service.state() == before,
                            )
                        row["extraction"], row["decision_correct"] = score(
                            case, row["raw_output"], row["generated"]
                        )
                        row["sentinel_unchanged"] = sha(sentinel) == sentinel_hash
                        assert service.state() == row["after"]
                        rows.append(row)
                        write(output / "observations.json", rows)
                        print(
                            json.dumps(
                                {
                                    "split": split,
                                    "arm": arm,
                                    "case": case.case_id,
                                    "seed": seed,
                                    "strict": row["extraction"]["valid"],
                                    "positive": row["extraction"][
                                        "matches_confirmation"
                                    ],
                                    "decision": row["decision_correct"],
                                    "workflow": row["passed"],
                                }
                            ),
                            flush=True,
                        )
        result = summary(rows)
        result.update(
            protocol_sha256=sha(output / "protocol.json"),
            observations_sha256=sha(output / "observations.json"),
        )
        write(output / "summary.json", result)
        print(json.dumps(result), flush=True)
    except BaseException as exc:
        write(output / "failure.json", {"error": str(exc), "rows": len(rows)})
        raise


if __name__ == "__main__":
    main()
