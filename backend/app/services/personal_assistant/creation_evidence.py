"""Bounded creation evidence; domain, literal roles and field completeness are separate."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .request_evidence import priority_evidence, request_context, source, timezone_evidence

DATE = re.compile(r"(?:(?P<year>\d{4})\s*년\s*)?(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일")
ISO_DATE = re.compile(r"(?<!\d)(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})(?!\d)")
TIME = re.compile(
    r"(?P<period>오전|오후)?\s*(?P<hour>\d{1,2})\s*시(?:\s*(?P<minute>\d{1,2})\s*분)?"
)
ISO_TIME = re.compile(r"(?<=T)(?P<hour>\d{2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?")
DURATION = re.compile(r"(?P<minutes>\d+)\s*분\s*(?:간|동안)")
DUE_OMISSION = re.compile(
    r"(?:기한|마감)(?:과\s*우선순위)?\s*(?:은|는|을|를)?\s*(?:없이|생략|넣지\s*마)"
)
WITHDRAWAL = re.compile(r"철회|아니\s*취소|아무것도|추가하지|등록하지|만들지")
DOCUMENT_FRAME = re.compile(
    r"(?:문서|인용문|비신뢰\s*데이터)(?:\s*안|\s*속|\s*내용|에).*?(?:지시|명령|적혀|써\s*있)|"
    r"(?:문서|인용문).*?(?:따라|실행)|<\s*/?\s*(?:system|instruction)\b"
)


def temporal_evidence(public, context, zone, operation):
    request = public["request"]
    dates, times, durations, invalid = [], [], [], []
    omissions = [source(request, *m.span(), None) for m in DUE_OMISSION.finditer(context)]
    now = datetime.fromisoformat(public["now"])
    local_now = now.astimezone(ZoneInfo(zone["value"] or public["timezone"]))
    year_from_public = False
    for pattern in (DATE, ISO_DATE):
        for match in pattern.finditer(context):
            year = int(match["year"]) if match["year"] else local_now.year
            year_from_public |= not bool(match["year"])
            try:
                value = datetime(year, int(match["month"]), int(match["day"])).date().isoformat()
                dates.append(source(request, *match.span(), value))
            except ValueError:
                invalid.append(source(request, *match.span(), None))
    for match in re.finditer(r"오늘|내일|모레", context):
        offset = {"오늘": 0, "내일": 1, "모레": 2}[match[0]]
        value = (local_now.date() + timedelta(days=offset)).isoformat()
        dates.append(source(request, *match.span(), value))
        year_from_public = True
    for pattern in (TIME, ISO_TIME):
        for match in pattern.finditer(context):
            groups = match.groupdict()
            hour, minute = int(match["hour"]), int(match["minute"] or 0)
            period = groups.get("period")
            if period and not 1 <= hour <= 12:
                invalid.append(source(request, *match.span(), None))
                continue
            if period:
                hour = hour % 12 + (12 if period == "오후" else 0)
            try:
                value = datetime(2000, 1, 1, hour, minute, int(groups.get("second") or 0))
                times.append(source(request, *match.span(), value.time().isoformat()))
            except ValueError:
                invalid.append(source(request, *match.span(), None))
    for match in DURATION.finditer(context):
        minutes = int(match["minutes"])
        durations.append(source(request, *match.span(), minutes))
        if not 1 <= minutes <= 1440:
            invalid.append(source(request, *match.span(), None))
    date_values, time_values = {s["value"] for s in dates}, {s["value"] for s in times}
    mentioned = bool(dates or times or invalid or re.search(r"기한|마감", context))
    if invalid or len(date_values) > 1 or len(time_values) > 1 or (omissions and (dates or times)):
        mode, value = "ambiguous", None
    elif len(date_values) == len(time_values) == 1:
        mode, value = "specified", f"{next(iter(date_values))}T{next(iter(time_values))}"
    elif dates or times or (mentioned and not omissions) or operation == "calendar.create":
        mode, value = "ambiguous", None
    else:
        mode, value = "omitted", None
    length_values = {s["value"] for s in durations}
    length_mode = "specified" if len(length_values) == 1 and not invalid else "ambiguous"
    return {
        "local_time": {
            "mode": mode,
            "value": value,
            "sources": [*dates, *times],
            "omissions": omissions,
            "invalid": invalid,
            "calendar_source": "public.now in source_timezone" if year_from_public else None,
        },
        "duration_minutes": {
            "mode": length_mode,
            "value": next(iter(length_values)) if length_mode == "specified" else None,
            "sources": durations,
        },
    }


def creation_evidence(public):
    request = public["request"]
    context, literals = request_context(request)
    trust = "document_frame" if DOCUMENT_FRAME.search(context) else "direct_request"
    withdrawn = bool(WITHDRAWAL.search(context))
    create = bool(re.search(r"추가|만들|넣어|등록|잡아", context))
    file_command = bool(re.search(r"이동|옮겨|휴지통|영구\s*삭제", context))
    todo = bool(re.search(r"할\s*일|기한|마감|우선순위|priority", context, re.I))
    calendar = bool(re.search(r"일정|잡아|부터|\d+\s*분\s*(?:간|동안)", context))
    operation = None
    if create and todo != calendar and not (file_command or withdrawn or trust == "document_frame"):
        operation = "todo.create" if todo else "calendar.create"
    titles = [
        item
        for item in literals
        if re.match(r"\s*(?:을|를|일정|할\s*일)", request[item["end"] + 1 :])
        or re.search(r"제목은\s*$", request[: item["start"]])
    ]
    title = titles[0] if len(titles) == 1 and 0 < len(titles[0]["value"]) <= 200 else None
    zone = timezone_evidence(request, context, public["timezone"])
    return {
        "operation": operation,
        "scope": {"trust": trust, "withdrawn": withdrawn, "file_command": file_command},
        "title": title,
        "title_candidates": titles,
        "literal_spans": literals,
        "source_timezone": zone,
        "priority": priority_evidence(request, context),
        **temporal_evidence(public, context, zone, operation),
    }
