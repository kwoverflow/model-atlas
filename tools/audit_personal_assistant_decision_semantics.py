"""Exploratory, model-free challenges to explanation certificates; not frozen trial scores."""

import argparse
import hashlib
import json
from pathlib import Path

from app.services.personal_assistant.decision_evidence import decision_evidence

CHALLENGES = (
    ("A01", "'검토'를 할 일로 추가해줘", ("할 일 추가",)),
    ("A02", "할 일을 추가하지 마", ("추가하지", "금지")),
    ("A03", "승인되면 할 일을 추가해줘", ("조건", "승인되면")),
    ("A04", "Inbox/할일추가.txt를 Archive/할일추가.txt로 옮겨줘", ("파일 이동", "파일을 이동")),
)


def audit():
    rows = []
    for case_id, content, facts in CHALLENGES:
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
        proof = decision_evidence(public)
        facts_present = any(fact in (proof["reason"] or "") for fact in facts)
        abstained = proof["status"] == "insufficient"
        rows.append(
            {
                "case_id": case_id,
                "request": request,
                "expected_summary_facts_any": facts,
                "decision_evidence": proof,
                "facts_present": facts_present,
                "false_sufficiency": proof["status"] == "grounded" and not facts_present,
                "passed": facts_present or abstained,
            }
        )
    return {
        "status": "passed" if all(r["passed"] for r in rows) else "counterexamples_found",
        "model_calls": 0,
        "kind": "post_freeze_exploratory_not_primary_holdout",
        "gold_authorship": "local_agent_authored_not_independent_human_review",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "observations": rows,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = audit()
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "status": value["status"],
                "model_calls": 0,
                "false_sufficiency": sum(r["false_sufficiency"] for r in value["observations"]),
            }
        )
    )
