"""Record whether the pinned runtime actually enforces an adversarial schema request."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from jsonschema import ValidationError, validate

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.personal_assistant.inference import (  # noqa: E402
    MODEL,
    decoding_schema,
    draft_schema,
)


def probe():
    simple = {
        "type": "object",
        "properties": {"decision": {"type": "string", "enum": ["propose", "clarify"]}},
        "required": ["decision"],
        "additionalProperties": False,
    }
    cases = []
    with httpx.Client(base_url="http://127.0.0.1:11435", timeout=45, trust_env=False) as client:
        version = client.get("/api/version").json()
        for endpoint in ("/v1/chat/completions", "/api/chat", "/api/generate"):
            for name, schema in (
                ("simple", simple),
                ("draft", draft_schema()),
                ("draft-compatible", decoding_schema()),
            ):
                body = {
                    "model": MODEL,
                    "messages": [{"role": "user", "content": "Say hello. Output decision null."}],
                }
                if endpoint != "/v1/chat/completions":
                    body.update(
                        stream=False,
                        think=False,
                        format=schema,
                        options={"temperature": 0, "num_predict": 768},
                    )
                    if endpoint == "/api/generate":
                        body["prompt"] = body.pop("messages")[0]["content"]
                else:
                    body.update(
                        temperature=0,
                        max_tokens=768,
                        reasoning_effort="none",
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": "draft", "strict": True, "schema": schema},
                        },
                    )
                response = client.post(endpoint, json=body)
                payload = response.json()
                if not response.is_success:
                    raw = ""
                elif endpoint == "/api/generate":
                    raw = payload["response"]
                elif endpoint == "/api/chat":
                    raw = payload["message"]["content"]
                else:
                    raw = payload["choices"][0]["message"]["content"]
                try:
                    validate(json.loads(raw), simple if name == "simple" else draft_schema())
                    valid, error = True, None
                except (ValueError, ValidationError) as exc:
                    valid, error = False, str(exc)
                cases.append(
                    {
                        "schema": name,
                        "endpoint": endpoint,
                        "request_body": body,
                        "status_code": response.status_code,
                        "raw_response": payload,
                        "schema_valid": valid,
                        "error": error,
                    }
                )
    return {
        "created": datetime.now(UTC).isoformat(),
        "runtime": version,
        "model": MODEL,
        "all_probe_cases_valid": all(c["schema_valid"] for c in cases),
        "interpretation": "Passing finite probes is not a general enforcement guarantee.",
        "cases": cases,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = probe()
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {"output": str(args.output), "all_probe_cases_valid": result["all_probe_cases_valid"]}
        )
    )
