"""Optional, local CPU ranker. No application imports, labels, network or generation."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

MODEL_ID = "cross-encoder/ms-marco-MiniLM-L6-v2"
MODEL_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
MODEL_SHA256 = "5d3e70fd0c9ff14b9b5169a51e957b7a9c74897afd0a35ce4bd318150c1d4d4a"
TOKENIZER_SHA256 = "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"
LAMBDA = 0.7


def validate_scores(chunks, scores):
    if len(chunks) != len(scores) or len(chunks) > 50:
        raise ValueError("score count must match at most 50 sources")
    if len({c["chunk_id"] for c in chunks}) != len(chunks):
        raise ValueError("duplicate source identity")
    if any(type(s) not in (int, float) or not math.isfinite(s) for s in scores):
        raise ValueError("scores must be finite numbers")


def select_top(chunks, scores, k=5):
    validate_scores(chunks, scores)
    if type(k) is not int or not 1 <= k <= 5:
        raise ValueError("top-k must be 1-5")
    return sorted(range(len(chunks)), key=lambda i: (-scores[i], chunks[i]["chunk_id"]))[:k]


def select_mmr(chunks, scores, similarities, k=5, weight=LAMBDA):
    validate_scores(chunks, scores)
    if type(k) is not int or not 1 <= k <= 5 or not 0 <= weight <= 1:
        raise ValueError("invalid MMR parameters")
    n = len(chunks)
    if len(similarities) != n or any(len(row) != n for row in similarities):
        raise ValueError("similarity shape mismatch")
    if any(
        not math.isfinite(float(v)) or not -1e-6 <= v <= 1.000001
        for row in similarities
        for v in row
    ):
        raise ValueError("invalid cosine similarities")
    relevance = [1 / (1 + math.exp(-max(-700.0, min(700.0, s)))) for s in scores]
    selected, remaining = [], set(range(n))
    while remaining and len(selected) < k:

        def objective(i):
            redundancy = max((similarities[i][j] for j in selected), default=0.0)
            return weight * relevance[i] - (1 - weight) * redundancy

        winner = min(remaining, key=lambda i: (-objective(i), chunks[i]["chunk_id"]))
        selected.append(winner)
        remaining.remove(winner)
    return selected


class RedundancyIndex:
    def __init__(self, chunks):
        from sklearn.feature_extraction.text import TfidfVectorizer

        ordered = sorted(chunks, key=lambda c: c["chunk_id"])
        if not ordered or len({c["chunk_id"] for c in ordered}) != len(ordered):
            raise ValueError("public corpus must be nonempty and unique")
        self.positions = {c["chunk_id"]: i for i, c in enumerate(ordered)}
        self.matrix = TfidfVectorizer(ngram_range=(1, 2), norm="l2").fit_transform(
            [c["title"] + "\n" + c["text"] for c in ordered]
        )

    def similarities(self, chunks):
        matrix = self.matrix[[self.positions[c["chunk_id"]] for c in chunks]]
        return (matrix @ matrix.T).toarray().tolist()


class OnnxRanker:
    def __init__(self, model_dir: Path):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        path = model_dir / "onnx/model.onnx"
        with path.open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != MODEL_SHA256:
                raise ValueError("model weight hash mismatch")
        with (model_dir / "tokenizer.json").open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != TOKENIZER_SHA256:
                raise ValueError("tokenizer hash mismatch")
        self.tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        if self.tokenizer.token_to_id("[PAD]") != 0:
            raise ValueError("unexpected padding token")
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        if {i.name for i in self.session.get_inputs()} != {
            "input_ids",
            "attention_mask",
            "token_type_ids",
        }:
            raise ValueError("unexpected ONNX model inputs")

    def windows(self, query, passage):
        tokenizer = self.tokenizer
        tokenizer.no_truncation()
        if not query.strip() or not passage.strip() or not query.isascii():
            raise ValueError("requires English query and nonempty full passage")
        if len(tokenizer.encode(query, add_special_tokens=False).ids) > 128:
            raise ValueError("query exceeds 128-token budget")
        original = tokenizer.encode(passage, add_special_tokens=False)
        expected = set(original.offsets)
        tokenizer.enable_truncation(max_length=512, stride=64, strategy="only_second")
        try:
            encoded = tokenizer.encode(query, passage)
        finally:
            tokenizer.no_truncation()
        windows = [encoded, *encoded.overflowing]
        if len(windows) > 8:
            raise ValueError("complete passage exceeds eight-window budget")
        covered = {
            offset
            for window in windows
            for offset, sequence in zip(window.offsets, window.sequence_ids, strict=True)
            if sequence == 1
        }
        if covered != expected or any(len(w.ids) > 512 for w in windows):
            raise ValueError("passage token coverage mismatch")
        return windows

    def score(self, query, chunks):
        import numpy as np

        validate_scores(chunks, [0.0] * len(chunks))
        pending, counts, scores = [], [], [[] for _ in chunks]
        for i, chunk in enumerate(chunks):
            windows = self.windows(query, chunk["title"] + "\n" + chunk["text"])
            counts.append(len(windows))
            pending.extend((i, window) for window in windows)
        for start in range(0, len(pending), 8):
            batch = pending[start : start + 8]
            length = max(len(window.ids) for _, window in batch)
            inputs = {}
            for name, attr in (
                ("input_ids", "ids"),
                ("attention_mask", "attention_mask"),
                ("token_type_ids", "type_ids"),
            ):
                inputs[name] = np.asarray(
                    [
                        getattr(window, attr) + [0] * (length - len(window.ids))
                        for _, window in batch
                    ],
                    dtype=np.int64,
                )
            values = self.session.run(None, inputs)[0]
            if values.shape != (len(batch), 1) or not np.isfinite(values).all():
                raise ValueError("invalid ONNX relevance scores")
            for (i, _), value in zip(batch, values[:, 0], strict=True):
                scores[i].append(float(value))
        maxima = [max(values) for values in scores]
        validate_scores(chunks, maxima)
        return {"scores": maxima, "window_scores": scores, "window_counts": counts}
