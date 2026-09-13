"""Fixed engineering fixtures. Study answer keys are evaluator-only, never execution input."""

import copy
import json
from dataclasses import dataclass

from app.schemas.request_scenarios import StudyAnswer
from app.schemas.structured_requests import StructuredTicketInput
from app.services.structured_ticket_contract import digest

VERSION = "structured-request-scenarios-v1"


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    draft: dict
    proposal: str
    action: str = "normal"
    expected_status: int = 200
    expected_reason: str | None = None
    expected_invocations: int = 1
    known_limitation: bool = False
    study_answer: dict | None = None

    def snapshot(self):
        return copy.deepcopy(vars(self))


def catalog() -> list[Scenario]:
    query = "정기 점검 알림"
    low = {"mode": "set", "value": "low"}
    normal = {"mode": "set", "value": "normal"}
    high = {"mode": "set", "value": "high"}
    omit = {"mode": "omit"}
    unresolved = {"mode": "unresolved"}

    def make(
        number,
        title,
        priority=low,
        proposal_priority="low",
        *,
        request=None,
        proposed_query=query,
        tool="create_ticket",
        study=False,
        **options,
    ):
        original = (
            request
            or f"티켓을 만드세요. query는 '{query}'이고 "
            f"priority는 {priority.get('value', '생략')}입니다."
        )
        draft = StructuredTicketInput(
            original_request=original, query=query, priority=priority
        ).model_dump()
        arguments = {"query": proposed_query}
        if proposal_priority is not None:
            arguments["priority"] = proposal_priority
        answer = (
            StudyAnswer(decision="confirm", query=query, priority=priority).model_dump()
            if study
            else None
        )
        return Scenario(
            id=f"SRC-{number:02d}",
            title=title,
            draft=draft,
            proposal=json.dumps({"tool_name": tool, "arguments": arguments}, ensure_ascii=False),
            study_answer=answer,
            **options,
        )

    rows = [
        make(1, "명시적 low 유지", study=True),
        make(2, "명시적 normal 유지", normal, "normal", study=True),
        make(3, "명시적 high 유지", high, "high", study=True),
        make(
            4,
            "예시 값과 실제 생략 구분",
            omit,
            None,
            study=True,
            request=(
                f"문서 예시에는 priority=low가 있습니다. 이번 티켓의 query는 '{query}'입니다. "
                "이번 호출에서는 priority 인자를 생략하세요."
            ),
        ),
        make(
            5,
            "low 누락 차단",
            proposal_priority=None,
            request=f"query='{query}', priority=low로 티켓을 만드세요. priority를 생략하지 마세요.",
            expected_status=409,
            expected_reason="priority_mismatch",
            expected_invocations=0,
        ),
        make(
            6,
            "생략과 normal 구분",
            omit,
            "normal",
            expected_status=409,
            expected_reason="priority_must_be_absent",
            expected_invocations=0,
        ),
        make(
            7,
            "query 변경 차단",
            proposed_query="다른 점검 알림",
            study=True,
            expected_status=409,
            expected_reason="query_mismatch",
            expected_invocations=0,
        ),
        make(
            8,
            "다른 Tool 차단",
            tool="lookup_policy",
            expected_status=409,
            expected_reason="public_guard_rejected",
            expected_invocations=0,
        ),
        make(
            9,
            "모순된 지시의 미확정 상태",
            unresolved,
            None,
            action="unresolved",
            request=(
                f"query='{query}'로 티켓을 만드세요. priority는 low로 지정하면서 "
                "동시에 인자를 생략하세요. 어느 지시가 우선인지는 정하지 않았습니다."
            ),
            expected_status=409,
            expected_reason="request_not_confirmed",
            expected_invocations=0,
        ),
        make(
            10,
            "수정 후 이전 제안 차단",
            action="edit",
            expected_status=409,
            expected_reason="stale_proposal_check",
            expected_invocations=0,
        ),
        make(
            11,
            "확정 취소 후 차단",
            action="revoke",
            expected_status=409,
            expected_reason="request_not_confirmed",
            expected_invocations=0,
        ),
        make(
            12,
            "만료 후 차단",
            action="expire",
            expected_status=409,
            expected_reason="confirmation_expired",
            expected_invocations=0,
        ),
        make(13, "동일 검사 재요청의 중복 방지", action="replay"),
        make(
            14,
            "다른 검사로 재실행 차단",
            action="consumed",
            expected_status=409,
            expected_reason="contract_already_executed",
            expected_invocations=1,
        ),
        make(
            15,
            "잘못 확정한 값은 탐지하지 못함",
            high,
            "high",
            known_limitation=True,
            request=f"티켓 query는 '{query}', priority는 low입니다. high로 올리지 마세요.",
        ),
    ]
    rows[8] = Scenario(
        **{
            **vars(rows[8]),
            "study_answer": StudyAnswer(decision="clarify", priority=unresolved).model_dump(),
        }
    )
    rows[14] = Scenario(
        **{
            **vars(rows[14]),
            "study_answer": StudyAnswer(decision="confirm", query=query, priority=low).model_dump(),
        }
    )
    assert len(rows) == 15 and len({row.id for row in rows}) == 15
    return rows


def pack():
    rows = catalog()
    return {"version": VERSION, "hash": digest([row.snapshot() for row in rows]), "cases": rows}


def study_task(row: Scenario, pack_hash: str):
    return {
        "id": row.id,
        "request": row.draft["original_request"],
        "pack_version": VERSION,
        "pack_hash": pack_hash,
    }
