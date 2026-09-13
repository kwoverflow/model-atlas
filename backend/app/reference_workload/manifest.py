from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.reference_workload.contracts import ReferenceWorkloadManifestContract


class ManifestValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedCorpusFile:
    path: str
    resolved_path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class ValidatedReferenceManifest:
    contract: ReferenceWorkloadManifestContract
    repository_root: Path
    manifest_path: Path
    files: tuple[ValidatedCorpusFile, ...]
    manifest_hash: str


def default_repository_root() -> Path:
    configured = os.getenv("MODEL_ATLAS_REPOSITORY_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


def default_manifest_path(repository_root: Path | None = None) -> Path:
    root = (repository_root or default_repository_root()).resolve()
    return root / "reference_workload" / "manifest.json"


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_reference_manifest(
    manifest_path: Path | None = None,
    *,
    repository_root: Path | None = None,
) -> ReferenceWorkloadManifestContract:
    root = (repository_root or default_repository_root()).resolve()
    source_path = (manifest_path or default_manifest_path(root)).resolve()
    if not source_path.is_relative_to(root):
        raise ManifestValidationError("reference manifest must resolve under the repository root")
    try:
        raw = source_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ManifestValidationError(f"reference manifest is missing: {source_path}") from exc
    except UnicodeDecodeError as exc:
        raise ManifestValidationError("reference manifest must be UTF-8") from exc
    try:
        payload = json.loads(raw)
        return ReferenceWorkloadManifestContract.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ManifestValidationError(f"reference manifest is invalid: {exc}") from exc


def _resolve_corpus_file(repository_root: Path, relative_path: str) -> Path:
    candidate = repository_root / relative_path
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ManifestValidationError(
            f"allowlisted corpus file is missing: {relative_path}"
        ) from exc
    if not resolved.is_relative_to(repository_root):
        raise ManifestValidationError(
            f"allowlisted corpus path escapes the repository root: {relative_path}"
        )
    if not resolved.is_file():
        raise ManifestValidationError(
            f"allowlisted corpus path is not a file: {relative_path}"
        )
    return resolved


def validate_reference_manifest(
    contract: ReferenceWorkloadManifestContract,
    *,
    manifest_path: Path | None = None,
    repository_root: Path | None = None,
    require_locked_hashes: bool = True,
) -> ValidatedReferenceManifest:
    root = (repository_root or default_repository_root()).resolve()
    source_path = (manifest_path or default_manifest_path(root)).resolve()
    if not source_path.is_relative_to(root):
        raise ManifestValidationError("reference manifest must resolve under the repository root")

    files: list[ValidatedCorpusFile] = []
    for declaration in contract.corpus.files:
        if not declaration.included:
            continue
        resolved = _resolve_corpus_file(root, declaration.path)
        actual_hash = file_sha256(resolved)
        if declaration.sha256 is None and require_locked_hashes:
            raise ManifestValidationError(
                f"corpus hash is not locked for {declaration.path}; run the manifest lock command"
            )
        if declaration.sha256 is not None and declaration.sha256 != actual_hash:
            raise ManifestValidationError(
                "corpus hash mismatch for "
                f"{declaration.path}: expected {declaration.sha256}, observed {actual_hash}"
            )
        files.append(
            ValidatedCorpusFile(
                path=declaration.path,
                resolved_path=resolved,
                sha256=actual_hash,
                size_bytes=resolved.stat().st_size,
            )
        )

    manifest_hash = stable_hash(
        {
            "schema_version": contract.schema_version,
            "workload_slug": contract.workload_slug,
            "workload_version": contract.workload_version,
            "language": contract.language,
            "corpus_id": contract.corpus.corpus_id,
            "corpus_version": contract.corpus.corpus_version,
            "chunking_version": contract.corpus.chunking_version,
            "case_contract_version": contract.case_contract_version,
            "files": [
                {"path": item.path, "sha256": item.sha256, "size_bytes": item.size_bytes}
                for item in files
            ],
        }
    )
    return ValidatedReferenceManifest(
        contract=contract,
        repository_root=root,
        manifest_path=source_path,
        files=tuple(files),
        manifest_hash=manifest_hash,
    )


def load_and_validate_reference_manifest(
    manifest_path: Path | None = None,
    *,
    repository_root: Path | None = None,
    require_locked_hashes: bool = True,
) -> ValidatedReferenceManifest:
    contract = load_reference_manifest(
        manifest_path,
        repository_root=repository_root,
    )
    return validate_reference_manifest(
        contract,
        manifest_path=manifest_path,
        repository_root=repository_root,
        require_locked_hashes=require_locked_hashes,
    )


def lock_reference_manifest(
    manifest_path: Path | None = None,
    *,
    repository_root: Path | None = None,
) -> ValidatedReferenceManifest:
    root = (repository_root or default_repository_root()).resolve()
    source_path = (manifest_path or default_manifest_path(root)).resolve()
    contract = load_reference_manifest(source_path, repository_root=root)
    validated = validate_reference_manifest(
        contract,
        manifest_path=source_path,
        repository_root=root,
        require_locked_hashes=False,
    )
    observed = {item.path: item.sha256 for item in validated.files}
    locked_files = [
        declaration.model_copy(
            update={"sha256": observed.get(declaration.path, declaration.sha256)}
        )
        for declaration in contract.corpus.files
    ]
    locked_contract = contract.model_copy(
        update={
            "corpus": contract.corpus.model_copy(update={"files": locked_files})
        }
    )
    serialized = json.dumps(
        locked_contract.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    temporary_path = source_path.with_suffix(source_path.suffix + ".tmp")
    temporary_path.write_text(serialized, encoding="utf-8", newline="\n")
    temporary_path.replace(source_path)
    return validate_reference_manifest(
        locked_contract,
        manifest_path=source_path,
        repository_root=root,
        require_locked_hashes=True,
    )
