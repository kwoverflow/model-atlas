"""Locally authored usability tasks, not an independent model holdout."""

import copy

from app.services.structured_ticket_contract import digest

VERSION = "request-workflow-v1"


def cases():
    rows = [
        (
            "배송 주소 확인",
            "query='배송 주소 확인'으로 티켓을 만들고 priority는 low로 지정하세요.",
            "low",
        ),
        (
            "결제 오류 조사",
            "query='결제 오류 조사' 티켓이 필요합니다. priority=high를 반드시 포함하세요.",
            "high",
        ),
        (
            "계정 정보 갱신",
            "query='계정 정보 갱신'으로 티켓을 만드세요. priority 인자는 보내지 마세요.",
            "omit",
        ),
        (
            "월간 사용량 정리",
            "query='월간 사용량 정리' 티켓을 만들고 priority=normal을 명시하세요.",
            "normal",
        ),
        (
            "보고서  재발행",
            "query='보고서  재발행'을 공백까지 그대로 사용하세요. priority=low인 티켓을 만드세요.",
            "low",
        ),
        (
            "알림 문구 수정",
            "예시의 priority=high는 이번 요청에 적용하지 않습니다. "
            "query='알림 문구 수정', priority=low로 티켓을 만드세요.",
            "low",
        ),
        (
            "접근 권한 회수",
            "query='접근 권한 회수'로 티켓을 만드세요. "
            "priority 인자를 생략하지 말고 high로 지정하세요.",
            "high",
        ),
        (
            "첨부 파일 교체",
            "예전에는 priority=normal을 보냈습니다. "
            "이번 query='첨부 파일 교체' 티켓에서는 priority 인자를 생략하세요.",
            "omit",
        ),
        (
            None,
            "query='백업 일정 조정'으로 티켓을 만드세요. "
            "priority=low를 포함하면서 동시에 priority 인자를 생략하세요. "
            "두 지시의 우선순위는 정하지 않았습니다.",
            "clarify",
        ),
        (
            None,
            "query='접속 기록 조사' 티켓의 priority를 high와 normal로 각각 지정하라는 "
            "두 지시가 있습니다. "
            "하나의 값만 보낼 수 있고 어느 지시가 우선인지는 정하지 않았습니다.",
            "clarify",
        ),
    ]
    return [
        {
            "id": f"WF-{index:02d}",
            "request": request,
            "expected": {
                "decision": "clarify" if priority == "clarify" else "execute",
                "query": query,
                "priority": {"mode": "unresolved"}
                if priority == "clarify"
                else {"mode": "omit"}
                if priority == "omit"
                else {"mode": "set", "value": priority},
            },
        }
        for index, (query, request, priority) in enumerate(rows, 1)
    ]


def catalog():
    rows = cases()
    pack_hash = digest({"version": VERSION, "cases": rows})
    return {
        "version": VERSION,
        "hash": pack_hash,
        "tasks": [
            {
                "id": row["id"],
                "request": row["request"],
                "pack_version": VERSION,
                "pack_hash": pack_hash,
            }
            for row in rows
        ],
        "scope": "local_authored_workflow_usability_not_independent_holdout",
        "gate_evidence": False,
    }


def scenario(task_id):
    public = catalog()
    row = next((row for row in cases() if row["id"] == task_id), None)
    if row is None:
        return None
    return {
        "task": next(t for t in public["tasks"] if t["id"] == task_id),
        "expected": copy.deepcopy(row["expected"]),
    }
