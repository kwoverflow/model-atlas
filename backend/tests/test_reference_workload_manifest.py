from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.reference_workload.manifest import (
    ManifestValidationError,
    load_and_validate_reference_manifest,
    lock_reference_manifest,
)


def _manifest_payload(path: str, sha256: str | None = None) -> dict[str, object]:
    return {
        "schema_version": "model-atlas-reference-workload-manifest-v1",
        "workload_slug": "model-atlas-operator-assistant-ko",
        "workload_version": "1.0.0",
        "language": "ko",
        "corpus": {
            "corpus_id": "model-atlas-operator-handbook-ko",
            "corpus_version": "1.0.0",
            "chunking_version": "markdown-section-chunker-v1",
            "files": [{"path": path, "sha256": sha256, "included": True}],
        },
        "case_contract_version": "reference-case-v1",
        "minimum_active_cases": 60,
        "minimum_critical_cases": 20,
    }


def _write_manifest(root: Path, payload: dict[str, object]) -> Path:
    path = root / "reference_workload" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_manifest_rejects_path_traversal(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest_payload("../outside.md"))

    with pytest.raises(ManifestValidationError, match="parent segments"):
        load_and_validate_reference_manifest(path, repository_root=tmp_path)


def test_manifest_rejects_absolute_path(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest_payload("C:/outside.md"))

    with pytest.raises(ManifestValidationError, match="absolute corpus paths"):
        load_and_validate_reference_manifest(path, repository_root=tmp_path)


def test_manifest_rejects_missing_allowlisted_file(tmp_path: Path) -> None:
    path = _write_manifest(tmp_path, _manifest_payload("docs/missing.md"))

    with pytest.raises(ManifestValidationError, match="allowlisted corpus file is missing"):
        load_and_validate_reference_manifest(
            path,
            repository_root=tmp_path,
            require_locked_hashes=False,
        )


def test_manifest_lock_writes_and_validates_observed_hash(tmp_path: Path) -> None:
    document = tmp_path / "docs" / "guide.md"
    document.parent.mkdir()
    document.write_text("# 안내\n\n배포 근거를 확인합니다.\n", encoding="utf-8")
    path = _write_manifest(tmp_path, _manifest_payload("docs/guide.md"))

    locked = lock_reference_manifest(path, repository_root=tmp_path)

    expected = hashlib.sha256(document.read_bytes()).hexdigest()
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["corpus"]["files"][0]["sha256"] == expected
    assert locked.files[0].sha256 == expected
    assert len(locked.manifest_hash) == 64


def test_manifest_rejects_changed_locked_file(tmp_path: Path) -> None:
    document = tmp_path / "docs" / "guide.md"
    document.parent.mkdir()
    document.write_text("# 안내\n\n원본\n", encoding="utf-8")
    path = _write_manifest(tmp_path, _manifest_payload("docs/guide.md"))
    lock_reference_manifest(path, repository_root=tmp_path)
    document.write_text("# 안내\n\n변경됨\n", encoding="utf-8")

    with pytest.raises(ManifestValidationError, match="corpus hash mismatch"):
        load_and_validate_reference_manifest(path, repository_root=tmp_path)


def test_manifest_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.md"
    outside.write_text("# 외부\n\n허용되지 않습니다.\n", encoding="utf-8")
    link = tmp_path / "docs" / "linked.md"
    link.parent.mkdir()
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable in this Windows environment")
    path = _write_manifest(tmp_path, _manifest_payload("docs/linked.md"))

    with pytest.raises(ManifestValidationError, match="escapes the repository root"):
        load_and_validate_reference_manifest(
            path,
            repository_root=tmp_path,
            require_locked_hashes=False,
        )
