"""Freeze one candidate; compare 20 regression and 16 unseen requests twice."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from experiments.personal_assistant_draft_e2e.scenarios import scenarios  # noqa: E402
from experiments.personal_assistant_e2e.run import exercise, setup  # noqa: E402
from experiments.personal_assistant_runtime_ab.run import (  # noqa: E402
    EXPECTED_DIGEST,
    strict_score,
)

from app.services.personal_assistant.drafts import DraftAssistantService, parse_draft  # noqa: E402
from app.services.personal_assistant.inference import (  # noqa: E402
    MODEL,
    AssistantDraftAdapter,
    generate_draft,
)
from app.services.personal_assistant.stable_inference import (  # noqa: E402
    PROMPT,
    STRATEGY,
    StableDraftAdapter,
    generate_stable_draft,
)

from .cases import holdout  # noqa: E402

SEEDS = (42, 1729)
NOW = "2026-10-11T09:00:00+09:00"
ARMS = ("legacy", STRATEGY)


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summary(rows):
    groups = {}
    for arm in ARMS:
        groups[arm] = {}
        for split in ("regression", "holdout"):
            data = [r for r in rows if r["arm"] == arm and r["split"] == split]
            positive = [r for r in data if r["outcome"] != "block"]
            negative = [r for r in data if r["outcome"] == "block"]
            groups[arm][split] = {
                "cases": len(data),
                "strict_valid": sum(r["extraction"]["valid"] for r in data),
                "positive_correct": sum(r["extraction"]["matches_confirmation"] for r in positive),
                "positive_total": len(positive),
                "workflow_passed": sum(r["passed"] for r in data),
                "block_workflows_passed": sum(r["passed"] for r in negative),
                "block_total": len(negative),
                "holdout_negative_decisions_correct": sum(
                    r.get("negative_decision_correct", False) for r in negative
                ),
                "preapproval_unchanged": sum(r["unchanged_before_approval"] for r in data),
                "runtime_errors": sum(bool(r.get("runtime_error")) for r in data),
                "completion_errors": sum(
                    bool(r["generated"].get("completion_error")) for r in data
                ),
                "failed_cases": sorted({r["case_id"] for r in data if not r["passed"]}),
            }
    candidate = groups[STRATEGY]
    expected = {
        (a, s, c.case_id, seed)
        for a in ARMS
        for s, cases in (("regression", scenarios()), ("holdout", holdout()))
        for c in cases
        for seed in SEEDS
    }
    observed = {(r["arm"], r["split"], r["case_id"], r["seed"]) for r in rows}
    coverage = observed == expected and len(rows) == len(expected)
    adopted = coverage and all(
        g["strict_valid"] == g["cases"] == g["workflow_passed"] == g["preapproval_unchanged"]
        and g["positive_correct"] == g["positive_total"]
        and not g["runtime_errors"]
        and not g["completion_errors"]
        for g in candidate.values()
    )
    adopted = (
        adopted
        and candidate["holdout"]["holdout_negative_decisions_correct"]
        == candidate["holdout"]["block_total"]
    )
    adopted = adopted and all(
        candidate[s]["positive_correct"] > groups["legacy"][s]["positive_correct"]
        for s in candidate
    )
    return {
        "arms": groups,
        "coverage_complete": coverage,
        "adoption": "ADOPT_HUMAN_REVIEW_DRAFT_PATH" if adopted else "KEEP_LEGACY_DEFAULT",
        "autonomous_release": "BLOCKED_UNCHANGED",
        "human_attestation": False,
        "interpretation": "A hybrid request-grounded pipeline, not standalone LLM accuracy.",
    }


def captured_generate(adapter_class, call):
    transport = []
    if adapter_class is StableDraftAdapter:
        method = "_post_generate"
    else:
        method = "_post_json"
    original = getattr(adapter_class, method)

    def capture(self, configuration, base_url, *args, **kwargs):
        entry = {
            "url": base_url + ("/api/generate" if method == "_post_generate" else args[0]),
            "request": args[-1],
        }
        transport.append(entry)
        result = original(self, configuration, base_url, *args, **kwargs)
        entry["response"] = result
        return result

    with patch.object(adapter_class, method, capture):
        result = call()
    return result, transport


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    allowed = (REPO / "artifacts/personal-assistant-stabilization").resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        parser.error("Use a fresh child of artifacts/personal-assistant-stabilization")
    output.mkdir(parents=True)
    (output / "sandboxes").mkdir()
    with urlopen("http://127.0.0.1:11435/api/tags", timeout=10) as response:
        models = json.load(response)
    with urlopen("http://127.0.0.1:11435/api/version", timeout=10) as response:
        runtime = json.load(response)
    assert runtime["version"] == "0.31.1"
    assert next(m for m in models["models"] if m["name"] == MODEL)["digest"] == EXPECTED_DIGEST
    sources = sorted(
        {
            *Path(__file__).parent.glob("*.py"),
            *(REPO / "backend/app/services/personal_assistant").glob("*.py"),
            REPO / "backend/app/services/inference_adapters/openai_compatible.py",
            REPO / "experiments/personal_assistant_e2e/run.py",
            REPO / "experiments/personal_assistant_draft_e2e/scenarios.py",
            REPO / "experiments/personal_assistant_runtime_ab/run.py",
        }
    )
    plan = {
        "version": "personal-assistant-stabilization-v1",
        "arms": ARMS,
        "seeds": SEEDS,
        "now": NOW,
        "candidate_prompt": PROMPT,
        "retries": 0,
        "post_output_repairs": 0,
        "max_tokens": 768,
        "context_length": 8192,
        "runtime": runtime,
        "models": models,
        "regression": [asdict(c) for c in scenarios()],
        "holdout": [asdict(c) for c in holdout()],
        "acceptance": (
            "All candidate schema/workflow checks; all positive exact intents; "
            "all holdout conservative decisions; improve over baseline; "
            "no mutation before approval."
        ),
        "title_constraint_source": (
            "Public unambiguous quoted creation target, never evaluation goals."
        ),
        "source_sha256": {p.relative_to(REPO).as_posix(): sha(p) for p in sources},
    }
    write(output / "protocol.json", plan)
    for source in sources:
        target = output / "sources" / source.relative_to(REPO)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    rows = []

    class FixedDateTime:
        @staticmethod
        def now(_zone):
            return datetime.fromisoformat(NOW)

    try:
        for split, cases in (("regression", scenarios()), ("holdout", holdout())):
            for seed in SEEDS:
                for case in cases:
                    for arm in ARMS:
                        service = DraftAssistantService(
                            setup(
                                case, output / "sandboxes" / f"{split}-{arm}-{case.case_id}-{seed}"
                            ).sandbox
                        )
                        before = service.state()
                        row = {
                            "arm": arm,
                            "split": split,
                            "case_id": case.case_id,
                            "seed": seed,
                            "outcome": case.outcome,
                            "raw_output": "",
                            "generated": {},
                            "transport": [],
                        }
                        try:
                            if arm == "legacy":
                                with patch(
                                    "app.services.personal_assistant.inference.datetime",
                                    FixedDateTime,
                                ):
                                    generated, transport = captured_generate(
                                        AssistantDraftAdapter,
                                        lambda c=case, s=service, seed=seed: generate_draft(
                                            c.request,
                                            s.state(),
                                            "http://127.0.0.1:11435",
                                            seed=seed,
                                        ),
                                    )
                            else:
                                generated, transport = captured_generate(
                                    StableDraftAdapter,
                                    lambda c=case, s=service, seed=seed: generate_stable_draft(
                                        c.request,
                                        s.state(),
                                        "http://127.0.0.1:11435",
                                        seed=seed,
                                        now=NOW,
                                    ),
                                )
                            row.update(
                                generated=generated,
                                raw_output=generated["raw_output"],
                                transport=transport,
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
                        row["extraction"] = strict_score(case, row["raw_output"])
                        if row["generated"].get("completion_error"):
                            row["extraction"].update(valid=False, matches_confirmation=False)
                        if "decisions" in case.expected:
                            try:
                                draft = parse_draft(row["raw_output"])
                                row["negative_decision_correct"] = (
                                    row["extraction"]["valid"]
                                    and draft.intent is None
                                    and draft.decision in case.expected["decisions"]
                                )
                            except ValueError:
                                row["negative_decision_correct"] = False
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
                                    "schema": row["extraction"]["valid"],
                                    "matched": row["extraction"]["matches_confirmation"],
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
