"""Shared deterministic tokenization, semantic normalization, and refusal detection."""

from __future__ import annotations

import re


def _tokens(value: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "at",
        "before",
        "for",
        "from",
        "in",
        "is",
        "of",
        "on",
        "the",
        "to",
        "what",
        "which",
        "who",
    }
    return [
        token
        for token in re.findall(r"[a-z0-9_]+|[\uac00-\ud7a3]+", value.lower())
        if len(token) > 1 and token not in stopwords
    ]


def _semantic_tokens(value: str) -> list[str]:
    suffixes = (
        "입니다",
        "합니다",
        "됩니다",
        "습니다",
        "으로",
        "에서",
        "에게",
        "까지",
        "부터",
        "처럼",
        "보다",
        "이라는",
        "라고",
        "에는",
        "이나",
        "거나",
        "한",
        "된",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "도",
        "만",
    )
    aliases = {
        "없음": "없",
        "없다": "없",
        "없는": "없",
        "없습니다": "없",
        "않음": "않",
        "않다": "않",
        "않습니다": "않",
        "부족함": "부족",
        "부족합니다": "부족",
    }
    particles = {"은", "는", "이", "가", "을", "를", "의", "에", "도", "만"}
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+|[\uac00-\ud7a3]+", value.lower()):
        normalized = aliases.get(token, token)
        if re.fullmatch(r"[\uac00-\ud7a3]+", token):
            for suffix in suffixes:
                minimum_stem_length = 1 if len(suffix) > 1 else 2
                if (
                    normalized.endswith(suffix)
                    and len(normalized) - len(suffix) >= minimum_stem_length
                ):
                    normalized = normalized[: -len(suffix)]
                    break
        if normalized and normalized not in particles:
            tokens.append(normalized)
    return tokens


def _contains_negation(value: str) -> bool:
    lowered = value.lower().replace("_", " ")
    patterns = (
        r"아니",
        r"않",
        r"없",
        r"부족",
        r"금지",
        r"불가",
        r"별도",
        r"분리",
        r"비구속",
        r"\b(?:not|no|never|cannot|can't|without|insufficient)\b",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def _detect_refusal(candidate_texts: list[str]) -> bool:
    text = " ".join(candidate_texts).lower()
    patterns = (
        r"(?:확인|단정|제공|답변|식별)(?:하|할|해)?\s*수\s*없",
        r"알려\s*드릴\s*수\s*없",
        r"(?:근거|정보|데이터|기록|연결)(?:가|이|은|는)?[^.!?\n]{0,24}(?:없|부족|않)",
        r"요청(?:을)?[^.!?\n]{0,20}(?:거절|수행할\s*수\s*없|처리할\s*수\s*없)",
        (
            r"\b(?:cannot|can't|unable to)\s+"
            r"(?:verify|confirm|determine|provide|identify|name|answer)\b"
        ),
        r"\b(?:insufficient evidence|no evidence|not available|not connected|do not have)\b",
    )
    return any(re.search(pattern, text) for pattern in patterns)
