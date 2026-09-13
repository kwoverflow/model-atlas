from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


DEFAULT_MODEL = "fixture-korean-document-assistant"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("content-type", "application/json; charset=utf-8")
    handler.send_header("content-length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class FixtureHandler(BaseHTTPRequestHandler):
    server_version = "ModelAtlasFixture/0.1"
    model_name = DEFAULT_MODEL

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            _json_response(
                self,
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": self.model_name,
                            "object": "model",
                            "created": 1_804_032_000,
                            "owned_by": "model-atlas-fixture",
                        }
                    ],
                },
            )
            return
        _json_response(self, 404, {"error": {"message": "Not found"}})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            _json_response(self, 404, {"error": {"message": "Not found"}})
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": {"message": "Invalid JSON"}})
            return

        user_content = ""
        for message in body.get("messages", []):
            if isinstance(message, dict) and message.get("role") == "user":
                user_content = str(message.get("content", ""))

        answer = "fixture-response"
        try:
            case_payload = json.loads(user_content)
            case_id = case_payload.get("case_id", "unknown")
            input_payload = case_payload.get("input", {})
            question = input_payload.get("question") if isinstance(input_payload, dict) else None
            answer = f"{case_id}: {question or '요청 내용을 확인했습니다.'}"
        except json.JSONDecodeError:
            pass

        created = int(time.time())
        _json_response(
            self,
            200,
            {
                "id": f"chatcmpl-fixture-{created}",
                "object": "chat.completion",
                "created": created,
                "model": body.get("model") or self.model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": max(1, len(user_content) // 4),
                    "completion_tokens": max(1, len(answer) // 4),
                    "total_tokens": max(2, (len(user_content) + len(answer)) // 4),
                },
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a tiny OpenAI-compatible fixture server for Model Atlas development."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=1234)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    FixtureHandler.model_name = args.model
    server = ThreadingHTTPServer((args.host, args.port), FixtureHandler)
    print(
        f"Model Atlas OpenAI-compatible fixture listening on "
        f"http://{args.host}:{args.port}/v1"
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
