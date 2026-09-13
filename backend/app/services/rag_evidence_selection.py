from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict, dataclass

RAG_EVIDENCE_SELECTOR_ID = "lexical_sentence_selector"
RAG_EVIDENCE_SELECTOR_VERSION = "lexical-sentence-selector-v1"
MAX_SELECTED_CLAIM_LENGTH = 320


@dataclass(frozen=True)
class EvidenceCandidate:
    rank: int
    chunk_id: str
    document_id: str
    title: str
    text: str
    retrieval_score: float


@dataclass(frozen=True)
class SelectedEvidence:
    selection_rank: int
    source_rank: int
    chunk_id: str
    document_id: str
    title: str
    text: str
    claim: str
    score: float
    confidence: str
    query_coverage: float
    boundary_signal: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceSelectionTrace:
    schema_version: str
    selector_id: str
    selector_version: str
    candidate_count: int
    selected_count: int
    selected_chunk_ids: list[str]
    confidence: str
    abstain_recommended: bool
    selections: list[SelectedEvidence]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def selector_descriptor() -> dict[str, object]:
    return {
        "selector_id": RAG_EVIDENCE_SELECTOR_ID,
        "selector_version": RAG_EVIDENCE_SELECTOR_VERSION,
        "display_name": "Deterministic Lexical Sentence Selector",
        "capabilities": [
            "query_only_selection",
            "sentence_extraction",
            "boundary_signal",
            "confidence_classification",
        ],
        "input_schema_version": "retrieved-evidence-candidates-v1",
        "output_schema_version": "rag-evidence-selection-v1",
    }


def select_evidence(
    *,
    query: str,
    candidates: list[EvidenceCandidate],
    category: str = "",
    max_selected: int = 1,
) -> EvidenceSelectionTrace:
    if not candidates or max_selected <= 0:
        return EvidenceSelectionTrace(
            schema_version="rag-evidence-selection-v1",
            selector_id=RAG_EVIDENCE_SELECTOR_ID,
            selector_version=RAG_EVIDENCE_SELECTOR_VERSION,
            candidate_count=len(candidates),
            selected_count=0,
            selected_chunk_ids=[],
            confidence="none",
            abstain_recommended=True,
            selections=[],
        )

    query_tokens = _semantic_tokens(query)
    document_frequency = Counter(
        token
        for candidate in candidates
        for token in set(_semantic_tokens(f"{candidate.title} {candidate.text}"))
    )
    boundary_preferred = _boundary_preferred(query, category)
    scored: list[tuple[float, EvidenceCandidate, str, float, bool]] = []
    for candidate in candidates:
        claim, claim_score, query_coverage, boundary_signal = _best_claim(
            query_tokens=query_tokens,
            candidate=candidate,
            document_frequency=document_frequency,
            document_count=len(candidates),
            boundary_preferred=boundary_preferred,
        )
        retrieval_prior = max(0.0, min(1.0, candidate.retrieval_score))
        score = round(0.94 * claim_score + 0.06 * retrieval_prior, 6)
        scored.append((score, candidate, claim, query_coverage, boundary_signal))

    scored.sort(key=lambda item: (-item[0], item[1].rank, item[1].chunk_id))
    if scored and _confidence(scored[0][0], scored[0][3]) == "low":
        retrieval_first = min(scored, key=lambda item: (item[1].rank, item[1].chunk_id))
        scored = [retrieval_first, *[item for item in scored if item is not retrieval_first]]
    selections: list[SelectedEvidence] = []
    for selection_rank, item in enumerate(scored[:max_selected], start=1):
        score, candidate, claim, query_coverage, boundary_signal = item
        confidence = _confidence(score, query_coverage)
        selections.append(
            SelectedEvidence(
                selection_rank=selection_rank,
                source_rank=candidate.rank,
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                title=candidate.title,
                text=candidate.text,
                claim=claim,
                score=score,
                confidence=confidence,
                query_coverage=round(query_coverage, 6),
                boundary_signal=boundary_signal,
            )
        )

    overall_confidence = selections[0].confidence if selections else "none"
    return EvidenceSelectionTrace(
        schema_version="rag-evidence-selection-v1",
        selector_id=RAG_EVIDENCE_SELECTOR_ID,
        selector_version=RAG_EVIDENCE_SELECTOR_VERSION,
        candidate_count=len(candidates),
        selected_count=len(selections),
        selected_chunk_ids=[selection.chunk_id for selection in selections],
        confidence=overall_confidence,
        abstain_recommended=overall_confidence in {"low", "none"},
        selections=selections,
    )


def _best_claim(
    *,
    query_tokens: list[str],
    candidate: EvidenceCandidate,
    document_frequency: Counter[str],
    document_count: int,
    boundary_preferred: bool,
) -> tuple[str, float, float, bool]:
    title_tokens = set(_semantic_tokens(candidate.title))
    title_overlap = _weighted_coverage(
        query_tokens,
        title_tokens,
        document_frequency,
        document_count,
    )
    best: tuple[float, str, float, bool] | None = None
    for sentence in _sentences(candidate.text):
        if _is_structural_fragment(sentence):
            continue
        sentence_tokens = _semantic_tokens(sentence)
        sentence_token_set = set(sentence_tokens)
        query_coverage = _weighted_coverage(
            query_tokens,
            sentence_token_set,
            document_frequency,
            document_count,
        )
        density = len(set(query_tokens) & sentence_token_set) / max(1, len(sentence_token_set))
        phrase_score = _ordered_pair_coverage(query_tokens, sentence_tokens)
        boundary_signal = _has_boundary_signal(sentence)
        boundary_score = 1.0 if boundary_preferred and boundary_signal else 0.0
        score = (
            0.61 * query_coverage
            + 0.12 * min(1.0, density * 3)
            + 0.10 * title_overlap
            + 0.09 * phrase_score
            + 0.08 * boundary_score
        )
        value = (score, sentence, query_coverage, boundary_signal)
        if (
            best is None
            or value[0] > best[0]
            or (value[0] == best[0] and len(value[1]) < len(best[1]))
        ):
            best = value

    if best is None:
        fallback = _compact_claim(candidate.text)
        return fallback, 0.0, 0.0, _has_boundary_signal(fallback)
    return _compact_claim(best[1]), best[0], best[2], best[3]


def _weighted_coverage(
    query_tokens: list[str],
    candidate_tokens: set[str],
    document_frequency: Counter[str],
    document_count: int,
) -> float:
    unique_query = set(query_tokens)
    if not unique_query:
        return 0.0
    weights = {
        token: math.log((document_count + 1) / (document_frequency[token] + 0.5)) + 1
        for token in unique_query
    }
    total = sum(weights.values())
    matched = sum(weight for token, weight in weights.items() if token in candidate_tokens)
    return matched / total if total else 0.0


def _ordered_pair_coverage(query_tokens: list[str], candidate_tokens: list[str]) -> float:
    query_pairs = set(zip(query_tokens, query_tokens[1:], strict=False))
    if not query_pairs:
        return 0.0
    candidate_pairs = set(zip(candidate_tokens, candidate_tokens[1:], strict=False))
    return len(query_pairs & candidate_pairs) / len(query_pairs)


def _boundary_preferred(query: str, category: str) -> bool:
    lowered = f"{category} {query}".lower()
    return bool(
        re.search(
            r"refus|scope|단정|확인|알려|되나요|해도|인가요|있나요|\b(?:can|may|is|are|verify)\b",
            lowered,
        )
    )


def _has_boundary_signal(value: str) -> bool:
    lowered = value.lower().replace("_", " ")
    return bool(
        re.search(
            r"아니|않|없|못|별도|분리|비주장|제한|범위|"
            r"\b(?:not|no|never|cannot|can't|does not|must not|without|separate|only)\b",
            lowered,
        )
    )


def _sentences(value: str) -> list[str]:
    normalized = re.sub(r"```[^\n]*", " ", value)
    normalized = re.sub(r"\s*\|\s*", " | ", normalized)
    pieces = re.split(r"(?<=[.!?])\s+|[\r\n]+|(?=\s*[-*]\s+)|(?=\s*\d+\.\s+)", normalized)
    sentences = [_compact_claim(piece) for piece in pieces]
    return [sentence for sentence in sentences if len(_semantic_tokens(sentence)) >= 2]


def _compact_claim(value: str) -> str:
    compact = re.sub(r"\s+", " ", value).strip(" `|-")
    if len(compact) <= MAX_SELECTED_CLAIM_LENGTH:
        return compact
    truncated = compact[:MAX_SELECTED_CLAIM_LENGTH].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{truncated}."


def _is_structural_fragment(value: str) -> bool:
    lowered = value.lower().strip()
    return bool(
        "-->" in lowered
        or lowered.startswith("flowchart ")
        or (lowered.endswith(":") and len(_semantic_tokens(lowered)) <= 6)
        or re.match(r"^[a-z0-9_]+\s*=\s*\S+", lowered)
        or lowered.count("|") >= 4
    )


def _semantic_tokens(value: str) -> list[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "can",
        "for",
        "from",
        "is",
        "of",
        "the",
        "to",
        "what",
        "which",
        "who",
        "현재",
        "주세요",
        "해도",
        "되나요",
        "알려",
        "확인해",
    }
    suffixes = (
        "입니다",
        "합니다",
        "됩니다",
        "습니다",
        "에서",
        "으로",
        "에게",
        "까지",
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
    tokens: list[str] = []
    for token in re.findall(r"[a-z0-9]+|[\uac00-\ud7a3]+", value.lower().replace("_", " ")):
        normalized = token
        if re.fullmatch(r"[\uac00-\ud7a3]+", normalized):
            for suffix in suffixes:
                if normalized.endswith(suffix) and len(normalized) - len(suffix) >= 2:
                    normalized = normalized[: -len(suffix)]
                    break
        normalized = _canonical_token(normalized)
        if len(normalized) > 1 and normalized not in stopwords:
            tokens.append(normalized)
    return tokens


def _canonical_token(value: str) -> str:
    aliases = {
        "approval": ("승인", "approve", "approved", "approval"),
        "evaluation": ("평가", "evaluate", "evaluation"),
        "evidence": ("근거", "evidence"),
        "ranking": ("추천", "순위", "candidate", "discovery", "ranking"),
        "release": ("릴리스", "배포", "deploy", "deployment", "release"),
    }
    for canonical, prefixes in aliases.items():
        if any(value.startswith(prefix) for prefix in prefixes):
            return canonical
    return value


def _confidence(score: float, query_coverage: float) -> str:
    if score >= 0.5 and query_coverage >= 0.4:
        return "high"
    if score >= 0.26 and query_coverage >= 0.15:
        return "medium"
    return "low"
