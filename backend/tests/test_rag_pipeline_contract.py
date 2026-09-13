"""Characterization of the pre-extraction RAG behavior and its public imports."""

import ast
import hashlib
import importlib
import json
from dataclasses import asdict
from graphlib import TopologicalSorter
from pathlib import Path

import pytest

from app.services import rag_evaluation as rag

SCENARIOS = [
    ("approved deployment gate baseline promotion", ["ops-release-001"], 3, 0.05),
    ("", ["ops-release-001"], 3, 0.05),
    ("unmatchedxyz", ["ops-release-001"], 3, 0.05),
    ("critical evaluation cases explicit review production readiness", ["ops-review-001"], 1, 0.05),
    ("release", ["ops-release-001"], 10, 0.0),
]


def behavior_fingerprint(scenario: tuple) -> str:
    query, relevant, top_k, min_score = scenario
    retrieval = rag.retrieve(
        corpus=rag.DEFAULT_RAG_CORPUS,
        query=query,
        relevant_chunk_ids=relevant,
        top_k=top_k,
        min_score=min_score,
    )
    claim = retrieval.retrieved_chunks[0].text if retrieval.retrieved_chunks else "Unknown."
    outputs = [
        "not json",
        "[]",
        json.dumps({"answer": claim, "citations": relevant, "claims": [claim]}),
        json.dumps({"answer": "Unsupported answer", "citations": ["missing"], "claims": ["fake"]}),
    ]

    def normalized(value):
        if isinstance(value, dict):
            return {
                key: normalized(item)
                for key, item in value.items()
                if key != "retrieval_latency_ms"
            }
        if isinstance(value, list):
            return [normalized(item) for item in value]
        return value

    payload = {
        "registry": rag.DEFAULT_RAG_CORPUS_REGISTRY.descriptor(),
        "retrieval": asdict(retrieval),
        "evaluations": [asdict(rag.evaluate_rag_output(output, retrieval)) for output in outputs],
    }
    serialized = json.dumps(normalized(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


# Captured before extraction. Only nondeterministic retrieval latency is excluded.
EXPECTED_FINGERPRINTS = [
    "f37cc319abceb0cea034cc051e21d2a4b7f8f5a99417acf05286b631a0df875c",
    "d20b687510eda768f6ee34cc63f1b6e5db9d7d8537e3dee73d6fa0628f47eecc",
    "318f7f56bb8d793cb2005e1ba1703ca6fad392d6065cb4b5ff5a84f9144ad15c",
    "6f35665d2c8673695e6b8e35fdac77043c817fdbb8e56a753488983f09115958",
    "162c9dd3c540e816edba063fb0b2120c5dfffc9ee12214e004db71b9d5f445dc",
]


@pytest.mark.parametrize(
    "scenario, expected", list(zip(SCENARIOS, EXPECTED_FINGERPRINTS, strict=True))
)
def test_rag_behavior_matches_pre_refactor_snapshot(scenario: tuple, expected: str) -> None:
    assert behavior_fingerprint(scenario) == expected


@pytest.mark.parametrize(
    "module, symbol",
    [
        ("contracts", "RagCorpus"),
        ("contracts", "RagEvaluationTrace"),
        ("corpus", "DEFAULT_RAG_CORPUS_REGISTRY"),
        ("retrieval", "retrieve"),
        ("execution", "prepare_rag_execution"),
        ("execution", "attach_rag_evaluation"),
        ("scoring", "evaluate_rag_output"),
        ("summaries", "summarize_rag_traces"),
        ("text", "_tokens"),
    ],
)
def test_compatibility_facade_preserves_symbol_identity(module: str, symbol: str) -> None:
    implementation = importlib.import_module(f"app.services.rag_pipeline.{module}")
    assert getattr(rag, symbol) is getattr(implementation, symbol)


def test_pipeline_dependencies_are_acyclic_and_do_not_import_facade() -> None:
    directory = Path(rag.__file__).parent / "rag_pipeline"
    graph = {}
    for path in directory.glob("*.py"):
        dependencies = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom):
                assert "rag_evaluation" not in (node.module or "")
                assert all(alias.name != "rag_evaluation" for alias in node.names)
                if node.level == 1:
                    dependencies.add(node.module)
            elif isinstance(node, ast.Import):
                assert all("rag_evaluation" not in alias.name for alias in node.names)
        graph[path.stem] = dependencies
    assert set(TopologicalSorter(graph).static_order()) == set(graph)
