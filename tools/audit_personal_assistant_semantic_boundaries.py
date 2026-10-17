"""Post-freeze, model-free V8 audit. Never counted as fresh model evidence."""

import argparse
import hashlib
import json
from pathlib import Path

from app.services.personal_assistant.semantic_evidence import semantic_evidence

# Separate labels, including the original V7 counterexamples and scope negatives.
CHALLENGES = (
    ("A01", "'검토'를 할 일로 추가해줘", ("todo.create", "requested", None, {"title": "검토"})),
    ("A02", "할 일을 추가하지 마", ("todo.create", "prohibited", None, {})),
    ("A03", "승인되면 할 일을 추가해줘", ("todo.create", "requested", "승인되면", {})),
    (
        "A04",
        "Inbox/할일추가.txt를 Archive/할일추가.txt로 옮겨줘",
        (
            "files.move",
            "requested",
            None,
            {"source": "Inbox/할일추가.txt", "destination": "Archive/할일추가.txt"},
        ),
    ),
    (
        "B01",
        "승인되면 '할 일을 추가해줘'를 할 일로 추가하지 마",
        ("todo.create", "prohibited", "승인되면", {"title": "할 일을 추가해줘"}),
    ),
    (
        "B02",
        "Inbox/승인되면.txt를 Archive/추가하지마.txt로 옮겨줘",
        (
            "files.move",
            "requested",
            None,
            {"source": "Inbox/승인되면.txt", "destination": "Archive/추가하지마.txt"},
        ),
    ),
    ("B03", "할 일을 추가해줘. 아니 취소야", None),
    ("B04", "만약 승인되면 할 일을 추가해줘", None),
    ("B05", "할 일을 추가하지 말아줘", None),
    ("B06", "@를 할 일로 추가해줘", None),
    ("B07", "할 일을 추가해줘. priority=low 또는 high", None),
    ("B08", "길이 제한 확인 " * 80, None),
)


def assess(proof, request, content, expected):
    action, meaning = proof.get("action_evidence", {}), proof.get("content_evidence", {})
    explanation = proof.get("explanation_evidence", {})
    literal = meaning.get("source", {})
    spans_valid = (
        literal.get("text") == content
        and literal.get("value") == content
        and request[literal.get("start", 0) : literal.get("end", 0)] == content
    )
    if expected is None:
        meaning_correct = meaning.get("status") == "unverified" and meaning.get("claims") is None
        reason_correct = "의미 해석은 미검증" in (explanation.get("reason") or "")
        scope = "quotation_and_action_only"
    else:
        operation, polarity, condition, arguments = expected
        meaning_correct = meaning.get("status") == "verified" and meaning.get("claims") == {
            "operation": operation,
            "polarity": polarity,
            "condition": condition,
            "arguments": arguments,
        }
        operation_name = "할 일 추가" if operation == "todo.create" else "파일 이동"
        polarity_name = "금지" if polarity == "prohibited" else "요청"
        prefix = (
            f"{operation_name} 조건부 {polarity_name}입니다."
            if condition
            else f"{operation_name} {polarity_name}입니다."
        )
        reason = explanation.get("reason") or ""
        reason_correct = prefix in reason and all(
            f"{key}={value!r}" in reason for key, value in arguments.items()
        )
        if condition:
            reason_correct = (
                reason_correct
                and f"조건: {condition}." in reason
                and "조건 충족 여부는 확인하지" in reason
            )
        scope = "document_semantics"
    return bool(
        "status" not in proof
        and proof.get("authorizes_execution") is False
        and action.get("status") == "grounded"
        and action.get("decision") == "no_change"
        and spans_valid
        and meaning_correct
        and reason_correct
        and explanation.get("scope") == scope
        and "실제 변경은 하지" in (explanation.get("reason") or "")
    )


def audit():
    rows = []
    for case_id, content, expected in CHALLENGES:
        request = (
            f'문서에 "{content}"라는 지시가 적혀 있어. 실행하지 말고 어떤 지시인지 설명만 해줘.'
        )
        public = {
            "request": request,
            "now": "2026-10-15T09:00:00+09:00",
            "timezone": "Asia/Tokyo",
            "events": [],
            "tasks": [],
            "inventory": [],
        }
        proof = semantic_evidence(public)
        rows.append(
            {
                "case_id": case_id,
                "request": request,
                "expected": expected,
                "semantic_evidence": proof,
                "passed": assess(proof, request, content, expected),
                "expected_interpreted": expected is not None,
            }
        )
    return {
        "status": "passed" if all(r["passed"] for r in rows) else "counterexamples_found",
        "kind": "post_freeze_exploratory_not_primary_holdout",
        "model_calls": 0,
        "gold_authorship": "local_agent_authored_not_independent_human_review",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observations": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit()
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "status": result["status"],
                "checks": len(result["observations"]),
                "passed": sum(r["passed"] for r in result["observations"]),
                "model_calls": 0,
            }
        )
    )
