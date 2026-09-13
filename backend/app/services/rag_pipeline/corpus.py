"""Deterministic demo corpus and registry; production corpus loading lives separately."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .contracts import RagChunk, RagCorpus, RagCorpusRegistry, RetrieverDescriptor


def _stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _build_default_corpus() -> RagCorpus:
    chunks = (
        RagChunk(
            chunk_id="ops-release-001",
            document_id="release-handbook",
            title="Release gate requirement",
            text=(
                "A release requires an approved deployment gate and verified evidence before "
                "baseline promotion."
            ),
        ),
        RagChunk(
            chunk_id="ops-rollback-001",
            document_id="rollback-runbook",
            title="Rollback ownership",
            text="Rollback owner is the platform team and target recovery time is 30 minutes.",
        ),
        RagChunk(
            chunk_id="ops-incident-001",
            document_id="incident-handbook",
            title="Severity one response",
            text=(
                "Severity one incidents require immediate paging and assignment of an incident "
                "commander."
            ),
        ),
        RagChunk(
            chunk_id="ops-retention-001",
            document_id="data-retention-policy",
            title="Evaluation record retention",
            text="Evaluation result records are retained for 180 days.",
        ),
        RagChunk(
            chunk_id="ops-customer-001",
            document_id="customer-change-policy",
            title="Enterprise customer changes",
            text="Enterprise customer changes require approval from the account owner.",
        ),
        RagChunk(
            chunk_id="ops-privacy-001",
            document_id="local-data-policy",
            title="Restricted data boundary",
            text=(
                "Restricted data must remain on local infrastructure and cannot be sent to "
                "external services."
            ),
        ),
        RagChunk(
            chunk_id="ops-latency-001",
            document_id="runtime-slo",
            title="Interactive latency target",
            text="Interactive workloads require p95 latency below 5000 milliseconds.",
        ),
        RagChunk(
            chunk_id="ops-backup-001",
            document_id="database-runbook",
            title="Database backup schedule",
            text="Database backups run daily at 02:00 UTC and retain seven copies.",
        ),
        RagChunk(
            chunk_id="ops-access-001",
            document_id="release-access-policy",
            title="Release approval roles",
            text="Production release approval roles are Release Manager and ML Ops Lead.",
        ),
        RagChunk(
            chunk_id="ops-review-001",
            document_id="evaluation-review-policy",
            title="Critical case review",
            text=("Critical evaluation cases require explicit review before production readiness."),
        ),
        RagChunk(
            chunk_id="ops-monitoring-001",
            document_id="monitoring-runbook",
            title="Post-release monitoring",
            text=("Post-release monitoring checks error rate and latency every five minutes."),
        ),
        RagChunk(
            chunk_id="ops-prompt-001",
            document_id="prompt-governance",
            title="Prompt baseline comparison",
            text="Prompt changes must be compared against the active baseline.",
        ),
    )
    corpus_payload = [chunk.to_dict() for chunk in chunks]
    return RagCorpus(
        corpus_id="model-atlas-ops-handbook",
        corpus_version="ops-handbook-v1",
        display_name="Model Atlas Operations Handbook",
        description="Deterministic local corpus for retrieval and citation evaluation.",
        language="en",
        chunks=chunks,
        corpus_hash=_stable_hash(corpus_payload),
    )


DEFAULT_RAG_CORPUS = _build_default_corpus()


DEFAULT_RAG_CORPUS_REGISTRY = RagCorpusRegistry(
    corpora={DEFAULT_RAG_CORPUS.corpus_id: DEFAULT_RAG_CORPUS}
)


DEFAULT_RETRIEVER_DESCRIPTOR = RetrieverDescriptor()
