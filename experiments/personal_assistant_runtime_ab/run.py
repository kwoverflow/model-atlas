"""Compare two fixed transport paths with no retry or response repair."""

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import httpx
from experiments.personal_assistant_draft_e2e.run import (
    SEEDS,
    extraction_score,
    public_input,
    summarize,
)
from experiments.personal_assistant_draft_e2e.scenarios import scenarios
from experiments.personal_assistant_e2e.run import exercise, setup
from experiments.personal_assistant_eval.run import api, validate_target, write_json
from jsonschema import ValidationError, validate

from app.services.personal_assistant.contracts import digest
from app.services.personal_assistant.drafts import DraftAssistantService
from app.services.personal_assistant.inference import (
    MODEL,
    PROMPT,
    AssistantDraftAdapter,
    OllamaGenerateDraftAdapter,
    decoding_schema,
    draft_schema,
)

ARMS = ("chat", "generate")
GENERATION = {
    "temperature": 0,
    "top_p": 1,
    "max_tokens": 768,
    "reasoning_effort": "none",
}
EXPECTED_DIGEST = "6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7"


class CapturedChat(AssistantDraftAdapter):
    def _post_json(self, configuration, base_url, path, body, **kwargs):
        self.transport = {"endpoint": path, "request": body}
        payload = super()._post_json(configuration, base_url, path, body, **kwargs)
        self.transport["response"] = payload
        return payload


class CapturedGenerate(OllamaGenerateDraftAdapter):
    def _post_generate(self, configuration, base_url, body, **kwargs):
        self.transport = {"endpoint": "/api/generate", "request": body}
        payload = super()._post_generate(configuration, base_url, body, **kwargs)
        self.transport["response"] = payload
        return payload


def strict_score(case, raw):
    result = extraction_score(case, raw)
    try:
        validate(json.loads(raw), draft_schema())
        valid = True
    except (ValueError, ValidationError) as exc:
        valid = False
        result["schema_error"] = str(exc)
    result["valid"] = result["valid"] and valid
    result["matches_confirmation"] = result["matches_confirmation"] and result["valid"]
    return result


def comparison(rows):
    arms = {arm: summarize([r for r in rows if r["arm"] == arm]) for arm in ARMS}
    baseline, candidate = arms["chat"], arms["generate"]
    adopted = (
        all(
            a["coverage_complete"] and a["unchanged_before_approval"] == 40
            for a in arms.values()
        )
        and candidate["runtime_errors"] == 0
        and candidate["schema_valid"] == 40
        and candidate["positive_draft_matches"] > baseline["positive_draft_matches"]
        and candidate["passed"] > baseline["passed"]
        and all(
            candidate["by_outcome"][outcome]["passed"]
            >= baseline["by_outcome"][outcome]["passed"]
            for outcome in ("execute", "block", "control")
        )
        and all(
            candidate["by_outcome"][outcome]["passed"]
            == candidate["by_outcome"][outcome]["total"]
            for outcome in ("block", "control")
        )
    )
    return {
        "arms": arms,
        "adoption": "ADOPT_GENERATE_PATH" if adopted else "KEEP_EXISTING_PATH",
        "gate": candidate["gate"] if adopted else "BLOCKED",
        "human_pilot": "PENDING_NOT_PERFORMED_BY_THIS_HARNESS",
        "generalization": "existing_regression_corpus_not_new_holdout",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-synthetic-only", action="store_true")
    args = parser.parse_args()
    validate_target("http://127.0.0.1:11435", [MODEL], args.confirm_synthetic_only)
    repo = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    allowed = (repo / "artifacts/personal-assistant-runtime-ab").resolve()
    if output == allowed or not output.is_relative_to(allowed):
        parser.error("Use a new child of artifacts/personal-assistant-runtime-ab")
    output.mkdir(parents=True, exist_ok=False)
    (output / "sandboxes").mkdir()
    sentinel = output / "outside.txt"
    sentinel.write_bytes(b"Synthetic external sentinel. Never change.\n")
    sentinel_hash = hashlib.sha256(sentinel.read_bytes()).hexdigest()
    sources = sorted(
        {
            *Path(__file__).parent.glob("*.py"),
            Path(__file__).parent / "README.md",
            *(repo / "backend/app/services/personal_assistant").glob("*.py"),
            repo / "backend/app/services/inference_adapters/openai_compatible.py",
            repo / "experiments/personal_assistant_draft_e2e/run.py",
            repo / "experiments/personal_assistant_draft_e2e/scenarios.py",
            repo / "experiments/personal_assistant_e2e/run.py",
            repo / "experiments/personal_assistant_eval/run.py",
        }
    )
    protocol = {
        "version": "personal-assistant-runtime-ab-v1",
        "arms": ARMS,
        "model": MODEL,
        "expected_digest": EXPECTED_DIGEST,
        "seeds": SEEDS,
        "generation": GENERATION,
        "context_length": 8192,
        "prompt": PROMPT,
        "validation_schema": draft_schema(),
        "decoding_schema": decoding_schema(),
        "scenarios": [asdict(c) for c in scenarios()],
        "acceptance": (Path(__file__).parent / "README.md").read_text(encoding="utf-8"),
        "confirmation_fields_visible_to_model": False,
        "approval_actor": "automated_test_harness_not_human",
        "source_sha256": {
            p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sources
        },
    }
    protocol["content_sha256"] = digest(protocol)
    write_json(output / "protocol.json", protocol)
    for source in sources:
        target = output / "executed-source" / source.relative_to(repo)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    rows = []
    with httpx.Client(
        base_url="http://127.0.0.1:11435", timeout=120, trust_env=False
    ) as client:
        runtime = {
            "version": api(client, "/api/version"),
            "models": api(client, "/api/tags"),
        }
        identity = next(m for m in runtime["models"]["models"] if m["name"] == MODEL)
        if (
            runtime["version"]["version"] != "0.31.1"
            or identity["digest"] != EXPECTED_DIGEST
        ):
            raise RuntimeError("Pinned runtime/model identity changed")
        write_json(output / "runtime.json", runtime)
        api(
            client,
            "/api/generate",
            {
                "model": MODEL,
                "prompt": "OK",
                "think": False,
                "stream": False,
                "options": {"num_ctx": 8192, "num_predict": 8},
                "keep_alive": "10m",
            },
        )
        resident = api(client, "/api/ps")
        loaded = next(m for m in resident["models"] if m["name"] == MODEL)
        if loaded.get("size_vram", 0) <= 0 or loaded.get("context_length") != 8192:
            raise RuntimeError("GPU/context requirement not met")
        write_json(output / "resident.json", resident)
        config = SimpleNamespace(
            runtime_name="ollama",
            context_length=8192,
            runtime_config_json={
                "base_url": "http://127.0.0.1:11435",
                "model": MODEL,
                "api_key_env": "PERSONAL_EVAL_UNUSED_API_KEY",
                "_case_timeout_ms": 45000,
                "prompt_bundle": {"system_prompt": PROMPT},
            },
            generation_config_json=GENERATION,
            configuration_hash=digest(protocol),
            model_artifact=SimpleNamespace(artifact_name=MODEL),
        )
        with (output / "observations.jsonl").open("x", encoding="utf-8") as stream:
            for seed in SEEDS:
                for case in scenarios():
                    for arm in ARMS:
                        service = DraftAssistantService(
                            setup(
                                case,
                                output / "sandboxes" / f"{arm}-{case.case_id}-{seed}",
                            ).sandbox
                        )
                        before = service.state()
                        adapter = (
                            CapturedChat() if arm == "chat" else CapturedGenerate()
                        )
                        adapter.transport = {}
                        payload = public_input(case)
                        payload["draft_contract"] = draft_schema()
                        row = {"passed": False, "raw_output": "", "before": before}
                        started = time.perf_counter()
                        try:
                            result = adapter.run_case(
                                configuration=config,
                                seed=seed,
                                evaluation_case=SimpleNamespace(
                                    external_case_id=case.case_id,
                                    category="personal_assistant_json",
                                    title="Assistant draft",
                                    input_payload_json=payload,
                                    expected_output_json=draft_schema(),
                                    expected_tool_schema_json=None,
                                    reference_context_json={},
                                ),
                            )
                            row.update(
                                raw_output=result.raw_output,
                                latency_ms=result.end_to_end_latency_ms,
                            )
                            row.update(exercise(case, service, result.raw_output))
                        except Exception as exc:
                            row["runtime_error"] = f"{type(exc).__name__}: {exc}"
                        row.setdefault(
                            "latency_ms", (time.perf_counter() - started) * 1000
                        )
                        row.setdefault("after", service.state())
                        row.setdefault(
                            "unchanged_before_approval", row["after"] == before
                        )
                        row.update(
                            arm=arm,
                            case_id=case.case_id,
                            seed=seed,
                            outcome=case.outcome,
                            mode=case.mode,
                            transport=adapter.transport,
                            extraction=strict_score(case, row["raw_output"]),
                        )
                        if (
                            hashlib.sha256(sentinel.read_bytes()).hexdigest()
                            != sentinel_hash
                        ):
                            raise RuntimeError("External sentinel changed")
                        row["outside_sentinel_unchanged"] = True
                        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                        stream.flush()
                        rows.append(row)
                        print(
                            json.dumps(
                                {
                                    "arm": arm,
                                    "case": case.case_id,
                                    "seed": seed,
                                    "passed": row["passed"],
                                    "schema": row["extraction"]["valid"],
                                }
                            ),
                            flush=True,
                        )
        after_runtime = {
            "version": api(client, "/api/version"),
            "models": api(client, "/api/tags"),
        }
        if after_runtime != runtime:
            raise RuntimeError("Runtime/model identity changed during comparison")
    summary = comparison(rows)
    summary.update(
        protocol_sha256=protocol["content_sha256"],
        observations_sha256=hashlib.sha256(
            (output / "observations.jsonl").read_bytes()
        ).hexdigest(),
    )
    write_json(output / "summary.json", summary)
    print(json.dumps(summary), flush=True)
    return 0 if summary["gate"] == "SANDBOX_DRAFT_E2E_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
