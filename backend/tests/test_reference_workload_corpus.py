from __future__ import annotations

import json
from pathlib import Path

from app.reference_workload.corpus import build_reference_corpus
from app.services.rag_evaluation import DEFAULT_RAG_CORPUS_REGISTRY


def _write_source_pack(root: Path, content: str) -> Path:
    document = root / "docs" / "guide.md"
    document.parent.mkdir(parents=True)
    document.write_text(content, encoding="utf-8")
    manifest = root / "reference_workload" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "model-atlas-reference-workload-manifest-v1",
                "workload_slug": "model-atlas-operator-assistant-ko",
                "workload_version": "1.0.0",
                "language": "ko",
                "corpus": {
                    "corpus_id": "model-atlas-operator-handbook-ko",
                    "corpus_version": "1.0.0",
                    "chunking_version": "markdown-section-chunker-v1",
                    "files": [
                        {"path": "docs/guide.md", "sha256": None, "included": True}
                    ],
                },
                "case_contract_version": "reference-case-v1",
                "minimum_active_cases": 60,
                "minimum_critical_cases": 20,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_file_backed_corpus_is_deterministic_and_preserves_metadata(tmp_path: Path) -> None:
    manifest = _write_source_pack(
        tmp_path,
        "# 운영 안내\n\nGate와 production readiness는 구분합니다.\n\n"
        "## 장애 복구\n\nDead letter 작업은 감사 가능한 requeue로 복구합니다.\n",
    )

    first = build_reference_corpus(
        manifest,
        repository_root=tmp_path,
        require_locked_hashes=False,
    )
    second = build_reference_corpus(
        manifest,
        repository_root=tmp_path,
        require_locked_hashes=False,
    )

    assert first.corpus.corpus_hash == second.corpus.corpus_hash
    assert [chunk.chunk_id for chunk in first.corpus.chunks] == [
        chunk.chunk_id for chunk in second.corpus.chunks
    ]
    assert len(first.corpus.chunks) == 2
    recovery = first.corpus.chunks[1]
    assert recovery.metadata["file_path"] == "docs/guide.md"
    assert recovery.metadata["heading_path"] == ["운영 안내", "장애 복구"]
    assert recovery.metadata["language"] == "ko"
    assert len(recovery.metadata["source_sha256"]) == 64
    assert len(recovery.metadata["chunk_sha256"]) == 64


def test_changed_document_changes_chunk_and_corpus_hash(tmp_path: Path) -> None:
    manifest = _write_source_pack(tmp_path, "# 안내\n\n첫 번째 내용입니다.\n")
    first = build_reference_corpus(
        manifest,
        repository_root=tmp_path,
        require_locked_hashes=False,
    )
    (tmp_path / "docs" / "guide.md").write_text(
        "# 안내\n\n두 번째 내용입니다.\n",
        encoding="utf-8",
    )
    second = build_reference_corpus(
        manifest,
        repository_root=tmp_path,
        require_locked_hashes=False,
    )

    assert first.corpus.corpus_hash != second.corpus.corpus_hash
    assert first.corpus.chunks[0].chunk_id != second.corpus.chunks[0].chunk_id


def test_reference_registry_does_not_mutate_default_fixture_registry(tmp_path: Path) -> None:
    manifest = _write_source_pack(tmp_path, "# 안내\n\n로컬 근거입니다.\n")
    before = DEFAULT_RAG_CORPUS_REGISTRY.descriptor()

    bundle = build_reference_corpus(
        manifest,
        repository_root=tmp_path,
        require_locked_hashes=False,
    )

    assert bundle.registry.get("model-atlas-operator-handbook-ko") is bundle.corpus
    assert DEFAULT_RAG_CORPUS_REGISTRY.descriptor() == before
    assert DEFAULT_RAG_CORPUS_REGISTRY.get("model-atlas-operator-handbook-ko") is None
