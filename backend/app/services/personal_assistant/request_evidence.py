"""Public request evidence, preserving source offsets and excluding literal data."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .stable_inference import QUOTED

PRIORITIES = {
    "low": "low",
    "normal": "normal",
    "high": "high",
    "낮음": "low",
    "낮은": "low",
    "보통": "normal",
    "높음": "high",
    "높은": "high",
}
PRIORITY_VALUE = "|".join(PRIORITIES)
PRIORITY_PATTERNS = (
    re.compile(
        rf"(?:우선순위|priority)\s*(?:는|를|은|을|=|:)?\s*['\"]?"
        rf"(?P<value>{PRIORITY_VALUE})(?![A-Za-z])",
        re.I,
    ),
    re.compile(rf"(?<![A-Za-z])(?P<value>{PRIORITY_VALUE})['\"]?\s*우선순위", re.I),
)
OMISSION = re.compile(
    r"(?:우선순위|priority)\s*(?:(?:인자|필드)\s*)?(?:는|를|은|을)?\s*"
    r"(?:없이|생략|넣지\s*마|정하지\s*마|지정하지\s*마|설정하지\s*마)",
    re.I,
)
ZONES = {
    "뉴욕": "America/New_York",
    "도쿄": "Asia/Tokyo",
    "일본": "Asia/Tokyo",
    "서울": "Asia/Seoul",
    "한국": "Asia/Seoul",
    "JST": "Asia/Tokyo",
    "KST": "Asia/Seoul",
    "UTC": "UTC",
}
ZONE_TOKEN = re.compile(
    r"뉴욕|도쿄|일본|서울|한국|(?<![A-Za-z0-9_])(?:JST|KST|UTC)(?![A-Za-z0-9_])"
)
IANA = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z][A-Za-z0-9_+-]*/)+[A-Za-z0-9_+-]+")
ZONE_LABEL = re.compile(r"source_timezone|timezone|시간대", re.I)
ZONE_OMISSION = re.compile(
    r"(?:source_timezone|timezone|시간대)\s*(?:는|를|=|:)?\s*"
    r"(?:생략|없이|넣지\s*마|지정하지\s*마)",
    re.I,
)
ZONE_DEFAULT = re.compile(
    r"(?:사용자|내|기본)\s*시간대(?:를|로)?\s*(?:사용|적용)|시간대는\s*기본값"
)


def source(request, start, end, value):
    return {"start": start, "end": end, "text": request[start:end], "value": value}


def request_context(request):
    spans = []
    for match in QUOTED.finditer(request):
        before, after = request[: match.start()], request[match.end() :]
        slot_quote = re.search(
            r"(?:우선순위|priority|source_timezone|timezone|시간대)\s*(?:는|를|=|:)?\s*$",
            before,
            re.I,
        ) or re.match(r"\s*(?:우선순위|현지|시간대|시간|시각)", after)
        if not slot_quote:
            group = next(i for i in range(1, 5) if match.group(i) is not None)
            spans.append(source(request, match.start(group), match.end(group), match.group(group)))
    for match in re.finditer(r"제목은\s*(?P<title>[^.!?\r\n]+?)(?:이야|야)(?=[.!]|$)", request):
        spans.append(source(request, match.start("title"), match.end("title"), match["title"]))
    chars = list(request)
    for span in spans:
        chars[span["start"] : span["end"]] = " " * (span["end"] - span["start"])
    return "".join(chars), spans


def priority_evidence(request, context):
    evidence = {}
    for pattern in PRIORITY_PATTERNS:
        for match in pattern.finditer(context):
            start, end = match.span("value")
            evidence[start, end] = source(request, start, end, PRIORITIES[match["value"].lower()])
    omissions = [source(request, m.start(), m.end(), None) for m in OMISSION.finditer(context)]
    unknown = []
    for match in re.finditer(
        r"(?:우선순위|priority)\s*(?:는|은|=|:)\s*['\"]?(?P<raw>[A-Za-z]+|[가-힣]+)",
        context,
        re.I,
    ):
        start, end = match.span("raw")
        known = any(a == start for a, _ in evidence)
        omitted = any(m["start"] <= start < m["end"] for m in omissions)
        if not known and not omitted:
            unknown.append(source(request, start, end, match["raw"]))
    values = {item["value"] for item in evidence.values()}
    mentions = bool(re.search(r"우선순위|priority", context, re.I))
    if (
        unknown
        or len(values) > 1
        or (values and omissions)
        or (mentions and not values and not omissions)
    ):
        mode, value = "ambiguous", None
    elif values:
        mode, value = "specified", next(iter(values))
    else:
        mode, value = "omitted", None
    return {
        "mode": mode,
        "value": value,
        "sources": list(evidence.values()),
        "omissions": omissions,
        "unknown": unknown,
    }


def timezone_evidence(request, context, default):
    evidence, unknown = [], []
    iana_spans = []
    for match in IANA.finditer(context):
        try:
            ZoneInfo(match[0])
            evidence.append(source(request, match.start(), match.end(), match[0]))
            iana_spans.append(match.span())
        except (ZoneInfoNotFoundError, ValueError):
            if ZONE_LABEL.search(context):
                unknown.append(source(request, match.start(), match.end(), match[0]))
    for match in ZONE_TOKEN.finditer(context):
        if any(a <= match.start() < b for a, b in iana_spans):
            continue
        raw = match[0]
        qualified = raw in {"JST", "KST", "UTC"} or bool(
            re.match(r"\s*(?:현지|시간|시각|기준)", context[match.end() :])
            or re.search(
                r"(?:source_timezone|timezone|시간대)\s*(?:는|=|:)?\s*['\"]?$",
                context[: match.start()],
                re.I,
            )
        )
        target = source(request, match.start(), match.end(), ZONES[raw])
        (evidence if qualified else unknown).append(target)
    for match in re.finditer(r"(?<![A-Za-z])(?:CST|EST|PST|MST|IST|BST)(?![A-Za-z])", context):
        unknown.append(source(request, match.start(), match.end(), match[0]))
    values = {item["value"] for item in evidence}
    omitted = [source(request, m.start(), m.end(), None) for m in ZONE_OMISSION.finditer(context)]
    defaults = [
        source(request, m.start(), m.end(), default) for m in ZONE_DEFAULT.finditer(context)
    ]
    local_words = list(re.finditer(r"([가-힣A-Za-z]+)\s+현지", context))
    if any(m[1] not in ZONES for m in local_words):
        unknown.extend(
            source(request, m.start(1), m.end(1), m[1]) for m in local_words if m[1] not in ZONES
        )
    if len(values) > 1 or unknown or (values and (omitted or defaults)):
        mode, value = "ambiguous", None
    elif values:
        mode, value = "specified", next(iter(values))
    elif ZONE_LABEL.search(context) and not (omitted or defaults):
        mode, value = "ambiguous", None
    else:
        mode, value = "default", default
    return {
        "mode": mode,
        "value": value,
        "sources": evidence,
        "unknown": unknown,
        "omissions": omitted,
        "defaults": defaults,
        "default_source": "public.timezone" if mode == "default" else None,
    }


def creation_evidence(public):
    request = public["request"]
    context, literals = request_context(request)
    create = bool(re.search(r"추가|만들|넣어|등록|잡아", context))
    todo = create and bool(re.search(r"할\s*일|기한|마감|우선순위|priority", context, re.I))
    calendar = create and bool(re.search(r"일정|잡아", context))
    untrusted = bool(re.search(r"문서|비신뢰|인용|지시", context))
    file_command = bool(re.search(r"이동|옮겨|휴지통|영구\s*삭제", context))
    kind = (
        None
        if todo == calendar or untrusted or file_command
        else "todo.create"
        if todo
        else "calendar.create"
    )
    return {
        "operation": kind,
        "literal_spans": literals,
        "untrusted_context": untrusted,
        "source_timezone": timezone_evidence(request, context, public["timezone"]),
        "priority": priority_evidence(request, context),
    }
