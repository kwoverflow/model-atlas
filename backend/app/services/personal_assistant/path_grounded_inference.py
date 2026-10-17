"""Public literal path constraints; uncertain wording retains the compact baseline."""

import json
import re
from pathlib import PurePosixPath

from jsonschema import ValidationError, validate

from .contracts import digest
from .inference import MODEL, draft_schema
from .stable_inference import (
    PROMPT,
    QUOTED,
    StableDraftAdapter,
    generate_stable_draft,
    literal_title,
    public_payload,
    stable_decoding_schema,
)

STRATEGY = "compact-path-grounded-v3"
ATOM = r"(?:'[^'\r\n]+'|\"[^\"\r\n]+\"|“[^”\r\n]+”|‘[^’\r\n]+’|[^\s'\"“”‘’]+?)"
MOVE = re.compile(
    rf"^\s*(?P<source>{ATOM})\s*(?:을|를)\s*(?P<destination>{ATOM})\s*(?:으로|로)"
    r"\s*(?:이동해|옮겨)\s*(?:줘|주세요)(?P<tail>.*)$"
)
TRASH = re.compile(
    rf"^\s*(?P<path>{ATOM})\s*(?:을|를)\s*(?:휴지통|보관함)(?:으로|로)"
    r"\s*보내\s*(?:줘|주세요)(?P<tail>.*)$"
)
QUOTE_PAIRS = {"'": "'", '"': '"', "“": "”", "‘": "’"}


def lexical_path_allowed(relative):
    # The frozen executor owns filesystem checks; this lexical mirror is parity-tested.
    parts = relative.split("/")
    return (
        bool(relative)
        and not PurePosixPath(relative).is_absolute()
        and not any(
            part in {"", ".", ".."}
            or part.endswith((" ", "."))
            or re.search(r'[\\:*?"<>|\x00-\x1f]', part)
            or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
            for part in parts
        )
    )


def quoted_title(request):
    original = literal_title(request)
    if original:
        return original
    matches = list(QUOTED.finditer(request))
    if len(matches) != 1:
        return None
    match = matches[0]
    group = next(i for i in range(1, 5) if match.group(i) is not None)
    value = match.group(group)
    if not value.strip() or len(value) > 200:
        return None
    # Context words inside the literal title are not external document instructions.
    masked = request[: match.start(group)] + "literal-title" + request[match.end(group) :]
    if literal_title(masked) is None:
        return None
    return {"value": value, "start": match.start(group), "end": match.end(group)}


def literal_file_command(request, inventory):
    match = MOVE.fullmatch(request) or TRASH.fullmatch(request)
    if match is None:
        return None
    names = ("source", "destination") if "source" in match.groupdict() else ("path",)
    context = request
    spans, fields = {}, {"operation": "files.move" if len(names) == 2 else "files.trash"}
    for name in reversed(names):
        start, end = match.span(name)
        token = request[start:end]
        context = context[:start] + "literal-path" + context[end:]
        if token[0] in QUOTE_PAIRS and token[-1] == QUOTE_PAIRS[token[0]]:
            start, end = start + 1, end - 1
        fields[name] = request[start:end]
        spans[name] = {"start": start, "end": end}
    if re.search(r"문서|지시|비신뢰|취소|철회|중단|멈|하지\s*마|이동하지|옮기지|아무것도", context):
        return None
    if re.search(
        r"삭제|보관|휴지통|이동|옮|생성|추가|완료|실행|보내|대신|아니|변경|다른|"
        r"확인|가능|먼저|후에|만약|않|아직",
        match["tail"],
    ):
        return None
    allowed = all(lexical_path_allowed(fields[name]) for name in names)
    decision = "refuse" if not allowed else None
    source = fields[names[0]]
    destination = fields.get("destination")
    if (
        allowed
        and source in inventory
        and (destination is None or (destination not in inventory and destination != source))
    ):
        parents = {str(PurePosixPath(fields[name]).parent) for name in names}
        if parents <= {".", "Inbox", "Archive"}:
            decision = "propose"
    return {"fields": fields, "spans": spans, "lexical_allowed": allowed, "decision": decision}


def grounded_schema(request, inventory):
    hints, _ = stable_decoding_schema(request)
    title = quoted_title(request)
    if title:
        for definition in ("CalendarCreate", "TodoCreate"):
            hints["$defs"][definition]["properties"]["title"]["enum"] = [title["value"]]
    path = literal_file_command(request, inventory)
    if path and path["decision"]:
        reason = hints["oneOf"][0]["properties"]["reason"]
        intent = {"type": "null"}
        if path["decision"] == "propose":
            fields = path["fields"]
            intent = {
                "type": "object",
                "additionalProperties": False,
                "required": list(fields),
                "properties": {key: {"const": value} for key, value in fields.items()},
            }
        hints["oneOf"] = [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["decision", "intent", "reason"],
                "properties": {
                    "decision": {"const": path["decision"]},
                    "intent": intent,
                    "reason": reason,
                },
            }
        ]
    return hints, title, path


def configuration_hash(request, inventory, seed):
    hints, _, _ = grounded_schema(request, inventory)
    return digest(
        {
            "strategy": STRATEGY,
            "model": MODEL,
            "prompt": PROMPT,
            "validation_schema": draft_schema(),
            "decoding_schema": hints,
            "generation": {"seed": seed, "max_tokens": 768, "context": 8192},
        }
    )


class PathGroundedDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    @staticmethod
    def generate_body(configuration, body):
        native = StableDraftAdapter.generate_body(configuration, body)
        public = json.loads(body["messages"][1]["content"])
        native["format"], _, _ = grounded_schema(public["request"], public["inventory"])
        return native


def generate_path_grounded_draft(request_text, state, base_url, *, seed=42, now=None):
    result = generate_stable_draft(
        request_text, state, base_url, seed=seed, now=now, adapter=PathGroundedDraftAdapter()
    )
    inventory = public_payload(request_text, state, now=now)["inventory"]
    hints, title, path = grounded_schema(request_text, inventory)
    grounding_error = None
    if result["schema_valid"]:
        try:
            validate(json.loads(result["raw_output"]), hints)
        except (ValueError, ValidationError):
            result["schema_valid"] = False
            grounding_error = "draft_grounding_mismatch"
    return {
        **result,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(request_text, inventory, seed),
        "decoding_schema_sha256": digest(hints),
        "title_grounding": title,
        "path_grounding": path,
        "path_policy": "public-literal-boundary-v3",
        "grounding_error": grounding_error,
    }
