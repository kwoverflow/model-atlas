"""Freeze one V8 candidate; 360 new calls plus 296 hash-verified V7 observations."""

import argparse
import copy
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from app.services.personal_assistant.decision_grounded_inference import (
    STRATEGY as BASELINE,
)
from app.services.personal_assistant.decision_grounded_inference import (
    generate_decision_grounded_draft,
)
from app.services.personal_assistant.semantic_grounded_inference import (
    PROMPT,
    STRATEGY,
    generate_semantic_grounded_draft,
)

from experiments.personal_assistant_decision_grounding.run import (
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

from .cases import GOLD, assess_meaning, holdout, regression

ARMS = (BASELINE, STRATEGY)
BASELINE_SOURCE = (
    REPO / "artifacts/personal-assistant-decision-grounding/2026-10-16/comparison-v1"
)
BASELINE_PROTOCOL_SHA = (
    "e727fc4dc087db22ae0b9bb4995cffac18f6efb4e79211ea783cce3e503befff"
)
BASELINE_OBSERVATIONS_SHA = (
    "a12632c8aa0b9d62fc0d0be256cb9cf59ff944502beb2adc2d2ec6ff1a653888"
)
CRITERIA = {
    "coverage": "656 observations: 296 archived V7, 296 new V8 regression, 32 new per arm.",
    "regression": "All exact intents, specified conservative decisions, workflows and sentinels.",
    "meaning": "All 24 supported meaning trials and 8 explicit unverified trials, separately.",
    "improvement": "More faithful fresh explanations; no per-case decision or intent regression.",
    "transport": "One actual request per new trial, no retries, no raw output repair.",
    "limit": "Only the declared small document grammar; not general semantic understanding.",
    "deployment": "Passing remains pending integration; keep legacy and approval requirements.",
    "stop": "One frozen candidate/run. Any post-freeze counterexample is reported, not retuned.",
}


def splits():
    return (("regression", regression()), ("holdout", holdout()))


def baseline_data():
    assert sha(BASELINE_SOURCE / "protocol.json") == BASELINE_PROTOCOL_SHA
    assert sha(BASELINE_SOURCE / "observations.json") == BASELINE_OBSERVATIONS_SHA
    plan = json.loads((BASELINE_SOURCE / "protocol.json").read_text(encoding="utf-8"))
    for relative, expected in plan["source_sha256"].items():
        assert (
            sha(BASELINE_SOURCE / "sources" / relative)
            == sha(REPO / relative)
            == expected
        )
    rows = json.loads(
        (BASELINE_SOURCE / "observations.json").read_text(encoding="utf-8")
    )
    data = {
        (r["case_id"], r["seed"]): (i, r)
        for i, r in enumerate(rows)
        if r["arm"] == BASELINE
    }
    assert len(data) == 296
    return plan, data


def summary(rows):
    arms = {}
    for arm in ARMS:
        arms[arm] = {}
        for split, _cases in splits():
            data = [r for r in rows if r["arm"] == arm and r["split"] == split]
            positive = [r for r in data if r["outcome"] != "block"]
            negative = [r for r in data if r["decision_correct"] is not None]
            meaning = [
                r["meaning_assessment"] for r in data if r.get("meaning_assessment")
            ]
            supported = [
                r
                for r in data
                if r["case_id"] in GOLD and GOLD[r["case_id"]] is not None
            ]
            unknown = [
                r for r in data if r["case_id"] in GOLD and GOLD[r["case_id"]] is None
            ]
            proofs = [r["generated"].get("semantic_evidence", {}) for r in data]
            arms[arm][split] = {
                "observations": len(data),
                "new_model_calls": sum("baseline_origin" not in r for r in data),
                "strict_valid": sum(r["extraction"]["valid"] for r in data),
                "positive_correct": sum(
                    r["extraction"]["matches_confirmation"] for r in positive
                ),
                "positive_total": len(positive),
                "conservative_correct": sum(
                    r["decision_correct"] is True for r in negative
                ),
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
                "faithful_explanations": sum(
                    m["faithful_explanation"] for m in meaning
                ),
                "meaning_checks": len(meaning),
                "evidence_checks_passed": sum(
                    m["evidence_correct"] is True for m in meaning
                ),
                "supported_interpretations": sum(
                    r["meaning_assessment"]["interpretation_success"] for r in supported
                ),
                "supported_total": len(supported),
                "safe_abstentions": sum(
                    r["meaning_assessment"]["faithful_explanation"] for r in unknown
                ),
                "unsupported_total": len(unknown),
                "unsupported_counted_as_interpreted": sum(
                    r["meaning_assessment"]["interpretation_success"] for r in unknown
                ),
                "action_grounded": sum(
                    p.get("action_evidence", {}).get("status") == "grounded"
                    for p in proofs
                ),
                "unverified_explanations": sum(
                    p.get("explanation_evidence", {}).get("status") == "unverified"
                    for p in proofs
                ),
                "failed_cases": sorted(
                    {
                        r["case_id"]
                        for r in data
                        if not r["passed"]
                        or r["decision_correct"] is False
                        or (
                            r["outcome"] != "block"
                            and not r["extraction"]["matches_confirmation"]
                        )
                        or (
                            r.get("meaning_assessment")
                            and not r["meaning_assessment"]["faithful_explanation"]
                        )
                    }
                ),
            }
    expected = {
        (arm, split, case.case_id, seed)
        for arm in ARMS
        for split, cases in splits()
        for case in cases
        for seed in SEEDS
    }
    observed = {(r["arm"], r["split"], r["case_id"], r["seed"]) for r in rows}
    coverage = expected == observed and len(rows) == len(expected)
    paired = {
        (r["split"], r["case_id"], r["seed"]): r for r in rows if r["arm"] == STRATEGY
    }
    regressions = []
    for row in rows:
        if row["arm"] != BASELINE:
            continue
        key = row["split"], row["case_id"], row["seed"]
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
    fresh = arms[STRATEGY]["holdout"]
    gate = (
        coverage
        and not regressions
        and all(
            g["observations"]
            == g["strict_valid"]
            == g["workflow_passed"]
            == g["preapproval_unchanged"]
            == g["sentinel_unchanged"]
            and g["positive_correct"] == g["positive_total"]
            and g["conservative_correct"] == g["conservative_total"]
            and not g["errors"]
            for g in arms[STRATEGY].values()
        )
        and fresh["meaning_checks"]
        == fresh["evidence_checks_passed"]
        == fresh["faithful_explanations"]
        == 32
        and fresh["supported_interpretations"] == fresh["supported_total"] == 24
        and fresh["safe_abstentions"] == fresh["unsupported_total"] == 8
        and fresh["unsupported_counted_as_interpreted"] == 0
        and fresh["faithful_explanations"]
        > arms[BASELINE]["holdout"]["faithful_explanations"]
        and not any(r.get("runtime_error") for r in rows)
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

    assert arm in ARMS
    generator = (
        generate_decision_grounded_draft
        if arm == BASELINE
        else generate_semantic_grounded_draft
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
    allowed = (REPO / "artifacts/personal-assistant-semantic-grounding").resolve()
    if not output.is_relative_to(allowed) or output == allowed:
        parser.error(
            "Use a fresh child of artifacts/personal-assistant-semantic-grounding"
        )
    previous, baseline = baseline_data()
    output.mkdir(parents=True)
    (output / "sandboxes").mkdir()
    sentinel = output / "outside.txt"
    sentinel.write_bytes(
        b"Synthetic external sentinel; never an allowed action target.\n"
    )
    with urlopen("http://127.0.0.1:11435/api/tags", timeout=10) as response:
        models = json.load(response)
    with urlopen("http://127.0.0.1:11435/api/version", timeout=10) as response:
        runtime = json.load(response)
    assert runtime["version"] == "0.31.1"
    assert (
        next(m for m in models["models"] if m["name"] == MODEL)["digest"]
        == EXPECTED_DIGEST
    )
    with urlopen("http://127.0.0.1:11435/api/ps", timeout=10) as response:
        resident = json.load(response)
    preparation = {"model_requests": 0, "resident_before": resident}
    if not any(
        m["digest"] == EXPECTED_DIGEST and m["context_length"] == 8192
        for m in resident["models"]
    ):
        load = {"model": MODEL, "keep_alive": "30m"}
        request = Request(
            "http://127.0.0.1:11435/api/generate",
            data=json.dumps(load).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=180) as response:
            loaded = json.load(response)
        assert loaded.get("done") is True and loaded.get("response", "") == ""
        preparation.update(model_requests=1, request=load, response=loaded)
    sources = sorted(
        {
            *(REPO / relative for relative in previous["source_sha256"]),
            *Path(__file__).parent.glob("*.py"),
            REPO / "backend/app/services/personal_assistant/semantic_evidence.py",
            REPO
            / "backend/app/services/personal_assistant/semantic_grounded_inference.py",
            REPO / "backend/app/services/personal_assistant/generation.py",
            REPO
            / "backend/tests/test_personal_assistant_semantic_grounded_inference.py",
        }
    )
    plan = {
        "version": "personal-assistant-semantic-grounding-v8",
        "arms": ARMS,
        "seeds": SEEDS,
        "now": NOW,
        "criteria": CRITERIA,
        "candidate_prompt": PROMPT,
        "regression": [asdict(c) for c in regression()],
        "holdout": [asdict(c) for c in holdout()],
        "gold": GOLD,
        "gold_authorship": "local_agent_authored_not_independent_human_review",
        "baseline_protocol_sha256": BASELINE_PROTOCOL_SHA,
        "baseline_observations_sha256": BASELINE_OBSERVATIONS_SHA,
        "runtime": runtime,
        "models": models,
        "preparation": preparation,
        "max_tokens": 768,
        "context_length": 8192,
        "retries": 0,
        "post_output_repairs": 0,
        "development_model_calls": 0,
        "new_scored_requests": 360,
        "archived_observations": 296,
        "outside_sentinel_sha256": sha(sentinel),
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
                        if split == "regression" and arm == BASELINE:
                            index, original = baseline[case.case_id, seed]
                            row = copy.deepcopy(original)
                            row.update(
                                split=split,
                                meaning_assessment=None,
                                baseline_origin={
                                    "index": index,
                                    "split": original["split"],
                                    "observations_sha256": BASELINE_OBSERVATIONS_SHA,
                                },
                            )
                        else:
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
                                    generated=generated,
                                    raw_output=generated["raw_output"],
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
                            row["meaning_assessment"] = assess_meaning(
                                case, row["generated"], row["raw_output"]
                            )
                            row["sentinel_unchanged"] = (
                                sha(sentinel) == plan["outside_sentinel_sha256"]
                            )
                            assert service.state() == row["after"]
                        rows.append(row)
                        write(output / "observations.json", rows)
                        if "baseline_origin" not in row:
                            print(
                                json.dumps(
                                    {
                                        "n": len(rows),
                                        "arm": arm,
                                        "split": split,
                                        "case": case.case_id,
                                        "seed": seed,
                                        "workflow": row["passed"],
                                        "meaning": row["meaning_assessment"],
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
