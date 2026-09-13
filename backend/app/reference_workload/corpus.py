from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.reference_workload.manifest import (
    ManifestValidationError,
    ValidatedCorpusFile,
    ValidatedReferenceManifest,
    default_manifest_path,
    default_repository_root,
    load_and_validate_reference_manifest,
    stable_hash,
)
from app.services.rag_evaluation import RagChunk, RagCorpus, RagCorpusRegistry

REFERENCE_CORPUS_REGISTRY_VERSION = "reference-file-rag-registry-v1"
REFERENCE_CHUNK_SCHEMA_VERSION = "markdown-section-chunk-v1"


@dataclass(frozen=True)
class MarkdownSection:
    heading_path: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class ReferenceCorpusBundle:
    manifest: ValidatedReferenceManifest
    corpus: RagCorpus
    registry: RagCorpusRegistry


def _markdown_sections(source: str, *, fallback_title: str) -> tuple[MarkdownSection, ...]:
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    heading_stack: list[str] = []
    body: list[str] = []
    sections: list[MarkdownSection] = []

    def flush() -> None:
        text = "\n".join(body).strip()
        if not text:
            body.clear()
            return
        headings = tuple(heading_stack) if heading_stack else (fallback_title,)
        sections.append(MarkdownSection(heading_path=headings, text=text))
        body.clear()

    for line in source.splitlines():
        match = heading_pattern.match(line)
        if match is None:
            body.append(line)
            continue
        flush()
        level = len(match.group(1))
        title = match.group(2).strip()
        heading_stack[:] = heading_stack[: level - 1]
        heading_stack.append(title)
    flush()
    return tuple(sections)


def _chunk_id(*, path: str, heading_path: tuple[str, ...], chunk_hash: str) -> str:
    digest = stable_hash(
        {
            "path": path,
            "heading_path": list(heading_path),
            "content_sha256": chunk_hash,
        }
    )
    return f"ko-{digest[:24]}"


def _build_file_chunks(record: ValidatedCorpusFile, *, language: str) -> Iterable[RagChunk]:
    try:
        source = record.resolved_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestValidationError(f"corpus file must be UTF-8: {record.path}") from exc
    sections = _markdown_sections(source, fallback_title=Path(record.path).stem)
    for section in sections:
        title = section.heading_path[-1]
        text = f"{' > '.join(section.heading_path)}\n\n{section.text}".strip()
        chunk_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        yield RagChunk(
            chunk_id=_chunk_id(
                path=record.path,
                heading_path=section.heading_path,
                chunk_hash=chunk_hash,
            ),
            document_id=record.path,
            title=title,
            text=text,
            metadata={
                "schema_version": REFERENCE_CHUNK_SCHEMA_VERSION,
                "file_path": record.path,
                "heading_path": list(section.heading_path),
                "language": language,
                "source_sha256": record.sha256,
                "chunk_sha256": chunk_hash,
            },
        )


def build_reference_corpus(
    manifest_path: Path | None = None,
    *,
    repository_root: Path | None = None,
    require_locked_hashes: bool = True,
) -> ReferenceCorpusBundle:
    root = (repository_root or default_repository_root()).resolve()
    resolved_manifest_path = manifest_path or default_manifest_path(root)
    manifest = load_and_validate_reference_manifest(
        resolved_manifest_path,
        repository_root=root,
        require_locked_hashes=require_locked_hashes,
    )
    chunks = tuple(
        chunk
        for record in manifest.files
        for chunk in _build_file_chunks(record, language=manifest.contract.language)
    )
    if not chunks:
        raise ManifestValidationError("reference corpus did not produce any Markdown chunks")
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ManifestValidationError(
            "reference corpus produced duplicate stable chunk IDs; disambiguate source headings"
        )

    corpus_hash = stable_hash(
        {
            "schema_version": "model-atlas-reference-corpus-v1",
            "manifest_hash": manifest.manifest_hash,
            "corpus_id": manifest.contract.corpus.corpus_id,
            "corpus_version": manifest.contract.corpus.corpus_version,
            "chunking_version": manifest.contract.corpus.chunking_version,
            "files": [
                {"path": item.path, "sha256": item.sha256} for item in manifest.files
            ],
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "heading_path": chunk.metadata["heading_path"],
                    "chunk_sha256": chunk.metadata["chunk_sha256"],
                }
                for chunk in chunks
            ],
        }
    )
    corpus = RagCorpus(
        corpus_id=manifest.contract.corpus.corpus_id,
        corpus_version=manifest.contract.corpus.corpus_version,
        display_name="Model Atlas Korean Operator Handbook",
        description=(
            "Deterministic file-backed corpus built from allowlisted Model Atlas documentation."
        ),
        language=manifest.contract.language,
        chunks=chunks,
        corpus_hash=corpus_hash,
    )
    registry = RagCorpusRegistry(
        corpora={corpus.corpus_id: corpus},
        registry_id="model_atlas_reference_workload_corpus",
        registry_version=REFERENCE_CORPUS_REGISTRY_VERSION,
    )
    return ReferenceCorpusBundle(manifest=manifest, corpus=corpus, registry=registry)


@dataclass(frozen=True)
class ReferenceCorpusProvider:
    repository_root: Path = default_repository_root()
    manifest_path: Path | None = None

    def load(self) -> ReferenceCorpusBundle:
        root = self.repository_root.resolve()
        return build_reference_corpus(
            self.manifest_path or default_manifest_path(root),
            repository_root=root,
        )
