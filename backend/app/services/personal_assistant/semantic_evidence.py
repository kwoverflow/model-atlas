"""Separate action-role evidence from bounded, source-backed document meaning."""

import re

from .decision_evidence import EXPLAIN, decision_evidence
from .request_evidence import request_context, source
from .stable_inference import QUOTED

QUOTE_LIMIT = 240
CONDITION = r"(?:(?P<condition>승인되면)\s+)?"
POLARITY = r"(?P<verb>추가해줘|추가하지\s*마)"
TODO = re.compile(
    CONDITION + r"(?:(?P<title>@)\s*(?:을|를)\s*)?할\s*일(?:로|에|을)?\s*" + POLARITY + r"[.!]?"
)
MOVE = re.compile(
    CONDITION
    + r"(?P<source>@|[\w./-]+)\s*(?:을|를)\s+"
    + r"(?P<destination>@|[\w./-]+)\s*(?:으로|로)\s*"
    + r"(?P<verb>옮겨줘|옮기지\s*마)[.!]?"
)


def content_evidence(request, literal):
    """Full-match a small grammar; unknown remainders never become semantic claims."""
    text = literal["text"]
    unresolved = {
        "status": "unverified",
        "claims": None,
        "source": literal,
        "scope": "bounded_document_clause_v1",
    }
    if len(text) > QUOTE_LIMIT:
        return unresolved
    chars = list(text)
    arguments = {}
    for match in QUOTED.finditer(text):
        group = next(i for i in range(1, 5) if match.group(i) is not None)
        # Keep offsets stable while shielding instruction-like words in arguments.
        start, end = match.span()
        chars[start:end] = "@" + " " * (end - start - 1)
        arguments[start] = source(
            request,
            literal["start"] + match.start(group),
            literal["start"] + match.end(group),
            match[group],
        )
    masked = "".join(chars)
    match = TODO.fullmatch(masked)
    operation = "todo.create"
    if match is None:
        match = MOVE.fullmatch(masked)
        operation = "files.move"
    if match is None:
        return unresolved
    claims = {"operation": operation, "arguments": {}, "condition": None}
    sources = {}
    used_arguments = set()
    for key in ("verb", "condition", "title", "source", "destination"):
        if key not in match.re.groupindex or match[key] is None:
            continue
        start, end = match.span(key)
        if start in arguments:
            item = arguments[start]
            used_arguments.add(start)
        else:
            item = source(request, literal["start"] + start, literal["start"] + end, match[key])
            # A marker is valid only when backed by an actual quoted argument.
            if match[key] == "@":
                return unresolved
        sources[key] = item
        if key == "condition":
            claims["condition"] = item["value"]
        elif key != "verb":
            claims["arguments"][key] = item["value"]
    if used_arguments != set(arguments):
        return unresolved
    claims["polarity"] = "prohibited" if "마" in match["verb"] else "requested"
    return {
        "status": "verified",
        "claims": claims,
        "source": literal,
        "claim_sources": sources,
        "scope": "bounded_document_clause_v1",
    }


def render_content(content):
    """Render only verified claims, or explicitly preserve an unverified quotation."""
    if content["status"] != "verified":
        quotation = (
            f"문서 원문: {content['source']['text']}\n"
            if len(content["source"]["text"]) <= QUOTE_LIMIT
            else "원문이 길어 이 설명에는 인용을 생략합니다.\n"
        )
        return quotation + "문서 내용의 의미 해석은 미검증이며, 동작이나 조건을 단정하지 않습니다."
    claims = content["claims"]
    operation = "할 일 추가" if claims["operation"] == "todo.create" else "파일 이동"
    polarity = "금지" if claims["polarity"] == "prohibited" else "요청"
    condition = (
        f"조건부 {polarity}입니다. 조건: {claims['condition']}. "
        "조건 충족 여부는 확인하지 않았습니다."
        if claims["condition"]
        else f"{polarity}입니다."
    )
    arguments = ", ".join(f"{key}={value!r}" for key, value in claims["arguments"].items())
    return f"문서 내용은 {operation} {condition}" + (f" 인자: {arguments}." if arguments else "")


def semantic_evidence(public):
    previous = decision_evidence(public)
    context, literals = request_context(public["request"])
    action = {
        key: previous[key]
        for key in ("status", "request_role", "decision", "reason_code", "needs", "basis")
    }
    content = {"status": "not_applicable", "claims": None}
    reason = previous["reason"]
    if EXPLAIN.fullmatch(context) and len(literals) == 1:
        content = content_evidence(public["request"], literals[0])
        # The outer request authorizes explanation only, regardless of quoted commands.
        action["basis"] = {"scope": "outer explanation-only frame", "literal_spans": literals}
        reason = render_content(content) + " 설명만 요청했으므로 실제 변경은 하지 않습니다."
    explanation = {
        "status": "bound" if reason is not None else "unverified",
        "scope": "document_semantics"
        if content["status"] == "verified"
        else (
            "quotation_and_action_only" if content["status"] == "unverified" else "decision_only"
        ),
        "reason": reason,
    }
    return {
        "action_evidence": action,
        "content_evidence": content,
        "explanation_evidence": explanation,
        "authorizes_execution": False,
    }
