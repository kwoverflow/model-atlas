"""Public, bounded decision certificates, distinct from execution authorization."""

import re
from datetime import datetime, timedelta

from .creation_evidence import creation_evidence
from .field_grounded_inference import completion_role
from .path_grounded_inference import QUOTE_PAIRS, literal_file_command
from .planning import GuardError, local_instant
from .request_evidence import request_context

CREATE = r"(?:추가해(?:줘|주세요)?|추가할|추가하는|만들어줘|넣어줘|등록해줘|잡아줘)"
EXPLAIN = re.compile(
    r"\s*문서(?:에|에는)\s*[\"“‘']\s*[\"”’'](?:라는|라고\s*하는)?\s*"
    r"(?:지시|명령)(?:가|이)\s*적혀\s*있어[.!]?\s*실행하지\s*말고\s*"
    r"(?:어떤\s*(?:지시|명령)인지|내용을)\s*설명만\s*해줘[.!]?\s*"
)
CONDITIONAL = re.compile(r"만약|가능하면|승인되면|조건(?:이|을|에|부)|검토\s*후")
FRAGMENTS = re.compile(
    rf"{CREATE}|TITLE|DATE|TIME|DURATION|"
    r"(?:source_timezone|timezone|시간대)(?:는|를|=|:)?ZONE|"
    r"ZONE(?:현지|시간|시각|기준)?|"
    r"(?:priority|우선순위)(?:는|를|은|을|=|:)?VALUE|VALUE우선순위|"
    r"OMIT(?:해줘|해|할게)?|DEFAULT(?:해)?|"
    r"할일(?:로|에|만)?|일정(?:에|을|로)?|제목은|이야|"
    r"(?:기한|마감)(?:으로|은|는)?|부터|까지|으로|을|를|로|T|[.,\s]"
)
CONFLICT_WORDS = re.compile(
    r"로지정하면서|로설정하면서|로지정하고|로넣어줘|로해|"
    r"동시에요구하며|동시에|우선하는지시는없어|어느지시도우선하지않아|"
    r"(?:어느값|어느쪽|어느지시|어떤지시)(?:이|가)?우선인지(?:는)?정하지않았어"
)
LABELS = {
    "priority": "우선순위",
    "source_timezone": "시간대",
    "local_due": "마감 시각",
    "local_start": "시작 시각",
    "duration_minutes": "일정 길이",
}


def command_shape(public, fields):
    request = public["request"]
    spans = []
    title = fields["title"]
    if not title:
        return None
    start, end = title["start"], title["end"]
    if start and request[start - 1] in QUOTE_PAIRS:
        if end >= len(request) or request[end] != QUOTE_PAIRS[request[start - 1]]:
            return None
        start, end = start - 1, end + 1
    spans.append((start, end, "TITLE"))
    for name, token in (("priority", "VALUE"), ("source_timezone", "ZONE")):
        for key in ("sources", "unknown"):
            spans.extend((s["start"], s["end"], token) for s in fields[name][key])
        spans.extend((s["start"], s["end"], "OMIT") for s in fields[name]["omissions"])
    spans.extend((s["start"], s["end"], "DEFAULT") for s in fields["source_timezone"]["defaults"])
    time = fields["local_time"]
    for item in time["sources"]:
        token = "TIME" if ":" in item["value"] else "DATE"
        spans.append((item["start"], item["end"], token))
    spans.extend((s["start"], s["end"], "OMIT") for s in time["omissions"])
    spans.extend((s["start"], s["end"], "DURATION") for s in fields["duration_minutes"]["sources"])
    accepted = []
    for span in sorted(spans, key=lambda s: (s[0], -s[1])):
        if accepted and span[0] < accepted[-1][1]:
            if span[1] <= accepted[-1][1]:
                continue
            return None
        accepted.append(span)
    shape = request
    for start, end, token in reversed(accepted):
        shape = shape[:start] + token + shape[end:]
    shape = re.sub(r"['\"“‘](VALUE|ZONE)['\"”’]", r"\1", shape)
    shape = re.sub(r"\s+", "", shape)
    if len(re.findall(CREATE, shape)) != 1 or shape.count("TITLE") != 1:
        return None
    if fields["priority"]["mode"] == "ambiguous":
        shape = CONFLICT_WORDS.sub("", shape)
    return shape if not FRAGMENTS.sub("", shape) else None


def certificate(role, decision, code, reason, *, needs=(), basis=None):
    return {
        "status": "grounded",
        "request_role": role,
        "decision": decision,
        "reason_code": code,
        "reason": reason,
        "needs": list(needs),
        "basis": basis or {},
        "authorizes_execution": False,
    }


def decision_evidence(public):
    context, literals = request_context(public["request"])
    if EXPLAIN.fullmatch(context):
        quoted = " ".join(s["value"] for s in literals)
        operation = "할 일 추가" if re.search(r"할\s*일.*추가", quoted) else "작업"
        return certificate(
            "explain_only",
            "no_change",
            "explanation_only",
            f"문서에 적힌 {operation} 지시를 설명하는 요청입니다. "
            "실행 요청이 아니므로 변경하지 않습니다.",
            basis={"literal_spans": literals, "scope": "complete explanation-only frame"},
        )
    complete = completion_role(public)
    if complete:
        decision = complete["decision"]
        code = {
            "propose": "open_task",
            "no_change": "already_complete",
            "clarify": "task_target_unresolved",
        }[decision]
        reasons = {
            "propose": "공개 목록에서 ID와 미완료 상태를 확인한 완료 처리 초안입니다. "
            "승인 전에는 실행하지 않습니다.",
            "no_change": "해당 ID의 할 일은 이미 완료 상태이므로 변경하지 않습니다.",
            "clarify": "공개 목록에서 해당 ID의 유일한 미완료 대상을 확인할 수 없습니다. "
            "대상을 확인해 주세요.",
        }
        return certificate(
            "complete",
            decision,
            code,
            reasons[decision],
            basis=complete,
            needs=["task_id"] if decision == "clarify" else [],
        )
    path = literal_file_command(public["request"], public["inventory"])
    if path and path["decision"]:
        blocked = path["decision"] == "refuse"
        return certificate(
            "file",
            path["decision"],
            "forbidden_path" if blocked else "file_draft",
            "요청한 작업 대상 경로가 허용 정책에 맞지 않아 거절합니다. 파일은 변경하지 않습니다."
            if blocked
            else "공개 파일 목록을 기준으로 만든 파일 작업 초안입니다. "
            "승인 시 경로와 상태를 다시 검사합니다.",
            basis=path,
        )
    fields = creation_evidence(public)
    if fields["operation"] and CONDITIONAL.search(context):
        return {
            **certificate(
                "conditional",
                "clarify",
                "unsupported_condition",
                "요청의 실행 조건을 현재 지원 범위에서 확인할 수 없습니다. "
                "조건과 실행 여부를 확인해 주세요.",
                basis={"scope": "condition detected, not established"},
            ),
            "status": "insufficient",
        }
    shape = command_shape(public, fields) if fields["operation"] else None
    if not shape:
        return {
            "status": "insufficient",
            "request_role": "unresolved",
            "decision": None,
            "reason_code": None,
            "reason": None,
            "needs": [],
            "basis": {"scope": "unsupported or incomplete command frame"},
            "authorizes_execution": False,
        }
    todo = fields["operation"] == "todo.create"
    time_name = "local_due" if todo else "local_start"
    required = [
        ("source_timezone", "source_timezone"),
        ("local_time", time_name),
        ("priority", "priority") if todo else ("duration_minutes", "duration_minutes"),
    ]
    needs = [name for key, name in required if fields[key]["mode"] == "ambiguous"]
    basis = {"command_shape": shape, "fields": fields, "state_source": "public.tasks/events"}
    if needs:
        labels = ", ".join(LABELS[name] for name in needs)
        return certificate(
            "create",
            "clarify",
            "field_confirmation",
            f"확인이 필요한 항목은 {labels}입니다. "
            "해당 항목의 값이나 상충하는 지시를 확인해 주세요.",
            needs=needs,
            basis=basis,
        )
    title = fields["title"]["value"]
    if todo and any(t["title"] == title and t["status"] == "open" for t in public["tasks"]):
        return certificate(
            "create",
            "clarify",
            "duplicate_task",
            "동일 제목의 미완료 할 일이 있습니다. 기존 항목과의 중복 여부를 확인해 주세요.",
            basis=basis,
        )
    if not todo:
        try:
            start = local_instant(fields["local_time"]["value"], fields["source_timezone"]["value"])
            end = start + timedelta(minutes=fields["duration_minutes"]["value"])
        except GuardError:
            return certificate(
                "create",
                "clarify",
                "ambiguous_instant",
                "해당 시간대에서 현지 시각을 하나의 시점으로 확정할 수 없습니다. "
                "시각을 확인해 주세요.",
                needs=["local_start"],
                basis=basis,
            )
        if any(
            start < datetime.fromisoformat(e["end_at"])
            and end > datetime.fromisoformat(e["start_at"])
            for e in public["events"]
        ):
            return certificate(
                "create",
                "clarify",
                "calendar_conflict",
                "공개 일정과 시간이 겹칩니다. 시작 시각을 확인해 주세요.",
                needs=["local_start"],
                basis=basis,
            )
    zone = fields["source_timezone"]
    timezone = (
        f"사용자 기본 시간대 {zone['value']}를 적용합니다."
        if zone["mode"] == "default"
        else (f"요청에 지정된 시간대 {zone['value']}를 적용합니다.")
    )
    time = fields["local_time"]
    details = (
        (f"마감은 {time['value']}입니다." if time["mode"] == "specified" else "마감은 생략합니다.")
        if todo
        else f"시작은 {time['value']}, 길이는 {fields['duration_minutes']['value']}분입니다."
    )
    if todo:
        priority = fields["priority"]
        details += (
            f"우선순위는 요청한 {priority['value']}입니다."
            if priority["mode"] == "specified"
            else ("우선순위는 생략합니다.")
        )
    return certificate(
        "create",
        "propose",
        "complete_creation",
        f"{'할 일' if todo else '일정'} 추가 초안입니다. {details} {timezone} "
        "승인 전에는 실행하지 않습니다.",
        basis=basis,
    )
