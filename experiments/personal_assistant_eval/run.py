"""Run a synthetic local workload through Model Atlas's adapter and policy engine."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import random
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
from app.services.inference_adapters.openai_compatible import OpenAICompatibleAdapter

from .evaluation import POLICY, RESPONSE_SCHEMA, score, summarize
from .suite import SYSTEM_PROMPT, VERSION, Case, cases

MODELS = ("qwen2.5:1.5b", "qwen3.5:4b", "qwen3.5:9b")
SEEDS = (42, 1729)
GENERATION = {
    "temperature": 0,
    "top_p": 1,
    "max_tokens": 768,
    "presence_penalty": 0,
    "frequency_penalty": 0,
    "reasoning_effort": "none",
}


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def write_json(path: Path, value):
    with path.open("x", encoding="utf-8") as output:
        json.dump(value, output, indent=2, ensure_ascii=False)
        output.write("\n")


def validate_target(base_url: str, models: list[str], confirmed: bool):
    url = urlsplit(base_url)
    if not confirmed:
        raise ValueError("--confirm-synthetic-only is required")
    if (
        url.scheme != "http"
        or url.hostname not in {"localhost", "127.0.0.1"}
        or url.port != 11435
        or url.username
        or url.password
        or url.query
        or url.fragment
        or url.path not in {"", "/"}
    ):
        raise ValueError("Use the isolated loopback Ollama runtime on port 11435")
    if not models or len(set(models)) != len(models) or set(models) - set(MODELS):
        raise ValueError("Only the declared locally downloaded candidate models are supported")


def adapter_case(case: Case):
    return SimpleNamespace(
        external_case_id=case.case_id,
        category="personal_assistant_json",
        title="Personal assistant request",
        input_payload_json=case.public_input(),
        expected_output_json=RESPONSE_SCHEMA,
        expected_tool_schema_json=None,
        reference_context_json={},
    )


def gpu_snapshot() -> list[dict]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        {
            "name": row[0].strip(),
            "total_mib": int(row[1]),
            "used_mib": int(row[2]),
            "utilization_percent": int(row[3]),
            "driver_version": row[4].strip(),
        }
        for row in csv.reader(result.stdout.splitlines())
    ]


def hardware_snapshot() -> dict:
    result = {
        "os": platform.system(),
        "os_release": platform.release(),
        "logical_processors": os.cpu_count(),
        "gpu": gpu_snapshot(),
    }
    if os.name == "nt":
        script = """$cpu = Get-CimInstance Win32_Processor
$computer = Get-CimInstance Win32_ComputerSystem
[pscustomobject]@{
cpu=$cpu.Name
physical_cores=$cpu.NumberOfCores
ram_bytes=$computer.TotalPhysicalMemory
} | ConvertTo-Json"""
        data = subprocess.check_output(["powershell.exe", "-NoProfile", "-Command", script])
        result.update(json.loads(data))
    return result


def api(client: httpx.Client, path: str, payload: dict | None = None):
    response = client.get(path) if payload is None else client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


def render_report(results: dict) -> str:
    lines = [
        "# Personal Assistant Evaluation",
        "",
        f"Suite: `{VERSION}`",
        "",
        "Synthetic inputs, real local inference. Plans are NEVER executed.",
        "",
        "| Model | Correct plans | Critical failures | Unsafe plans | Median ms | p95 ms | Gate |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for model, entry in results["models"].items():
        s = entry["summary"]
        m = s["metrics"]
        lines.append(
            f"| {model} | {s['correct_plans']}/{s['observations']} | "
            f"{m['critical_failure_count']} | {m['unsafe_plan_count']} | "
            f"{s['median_latency_ms']:.0f} | {m['p95_latency_ms']:.0f} | {s['gate']} |"
        )
    lines += ["", "## Failed Cases", ""]
    for model, entry in results["models"].items():
        lines += [f"### {model}", "", ", ".join(entry["summary"]["failed_case_ids"]) or "None", ""]
    lines += [
        "## Interpretation",
        "",
        "A pass permits only a proposed supervised pilot, not autonomous execution.",
        "24 authored cases repeated twice are not 48 independent tasks or an external benchmark.",
        "Live calendar, task services, private files, native execution "
        "and long-context use are untested.",
        "Latency is warm non-streaming end-to-end; TTFT and decode-only speed were not measured.",
        "GPU memory snapshots are not sampled peaks; host use includes other applications.",
        "Existing official evaluation records and release decisions were not read or modified.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument("--base-url", default="http://127.0.0.1:11435")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-synthetic-only", action="store_true")
    args = parser.parse_args()
    validate_target(args.base_url, args.models, args.confirm_synthetic_only)
    args.output.mkdir(parents=True, exist_ok=False)
    suite = cases()
    protocol = {
        "schema_version": VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "seeds": SEEDS,
        "generation": GENERATION,
        "context_length": 8192,
        "concurrency": 1,
        "case_timeout_ms": 30000,
        "system_prompt": SYSTEM_PROMPT,
        "cases": [asdict(case) for case in suite],
        "policy": POLICY,
        "source_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(__file__).parent.glob("*.py")
        },
        "hardware": hardware_snapshot(),
        "data_source": "local_authored_synthetic",
        "inference_source": "actual_local_runtime",
        "side_effects": "none",
        "human_review": "pending",
        "production_readiness": "not_production_ready",
    }
    protocol["content_sha256"] = digest(protocol)
    write_json(args.output / "protocol.json", protocol)
    results = {"protocol_sha256": protocol["content_sha256"], "models": {}}
    adapter = OpenAICompatibleAdapter()
    with httpx.Client(base_url=args.base_url, timeout=180, trust_env=False) as client:
        inventory = api(client, "/api/tags")
        local = {item["name"]: item for item in inventory["models"]}
        if set(args.models) - local.keys():
            raise ValueError("Download every declared model before starting the scored campaign")
        write_json(
            args.output / "runtime.json",
            {"version": api(client, "/api/version"), "models": inventory},
        )
        for model in args.models:
            metadata = api(client, "/api/show", {"model": model})
            cold_start = time.perf_counter()
            warmup = api(
                client,
                "/api/generate",
                {
                    "model": model,
                    "prompt": "Return OK.",
                    "think": False,
                    "stream": False,
                    "options": {"num_ctx": 8192, "num_predict": 8, "temperature": 0},
                    "keep_alive": "10m",
                },
            )
            cold_ms = (time.perf_counter() - cold_start) * 1000
            resident = api(client, "/api/ps")
            loaded = next(item for item in resident["models"] if item["name"] == model)
            if loaded.get("size_vram", 0) <= 0 or loaded.get("context_length") != 8192:
                raise RuntimeError("Required GPU residency/context length was not confirmed")
            configuration = SimpleNamespace(
                runtime_name="ollama",
                context_length=8192,
                runtime_config_json={
                    "base_url": args.base_url,
                    "model": model,
                    "api_key_env": "PERSONAL_EVAL_UNUSED_API_KEY",
                    "_case_timeout_ms": 30000,
                    "prompt_bundle": {"system_prompt": SYSTEM_PROMPT},
                },
                generation_config_json=GENERATION,
                configuration_hash=digest(
                    {
                        "model": local[model],
                        "generation": GENERATION,
                        "protocol": protocol["content_sha256"],
                    }
                ),
                model_artifact=SimpleNamespace(artifact_name=model),
            )
            rows = []
            name = model.replace(":", "-")
            with (args.output / f"{name}.jsonl").open("x", encoding="utf-8") as output:
                for seed in SEEDS:
                    order = list(suite)
                    random.Random(seed).shuffle(order)
                    for case in order:
                        started = time.perf_counter()
                        try:
                            result = adapter.run_case(
                                configuration=configuration,
                                evaluation_case=adapter_case(case),
                                seed=seed,
                            )
                            raw = result.raw_output
                            row = {
                                "raw_output": raw,
                                "adapter_metadata": result.metadata,
                                "latency_ms": result.end_to_end_latency_ms,
                                "prompt_tokens": result.prompt_tokens,
                                "completion_tokens": result.completion_tokens,
                                "runtime_error": None,
                                "score": score(case, raw),
                            }
                        except Exception as exc:
                            row = {
                                "raw_output": "",
                                "latency_ms": (time.perf_counter() - started) * 1000,
                                "runtime_error": f"{type(exc).__name__}: {exc}",
                                "score": score(case, ""),
                            }
                        row.update(
                            case_id=case.case_id,
                            domain=case.domain,
                            critical=case.critical,
                            seed=seed,
                            resident=api(client, "/api/ps"),
                            gpu_after=gpu_snapshot(),
                        )
                        output.write(json.dumps(row, ensure_ascii=False) + "\n")
                        output.flush()
                        rows.append(row)
                        print(
                            json.dumps(
                                {
                                    "model": model,
                                    "done": len(rows),
                                    "case": case.case_id,
                                    "pass": row["score"]["exact_plan"],
                                    "ms": round(row["latency_ms"]),
                                }
                            ),
                            flush=True,
                        )
            entry = {
                "model_identity": local[model],
                "model_details": metadata,
                "warmup_ms": cold_ms,
                "warmup": warmup,
                "resident_after_warmup": resident,
                "configuration_hash": configuration.configuration_hash,
                "summary": summarize(rows),
            }
            results["models"][model] = entry
            write_json(args.output / f"{name}.summary.json", entry)
            api(client, "/api/generate", {"model": model, "keep_alive": 0})
    write_json(args.output / "comparison.json", results)
    with (args.output / "comparison.md").open("x", encoding="utf-8") as output:
        output.write(render_report(results))
    print(json.dumps({"output": str(args.output), "status": "complete"}), flush=True)


if __name__ == "__main__":
    main()
