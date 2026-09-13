"""Validate all package hashes and paths before extracting to a new directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath


def validate_archive(archive: zipfile.ZipFile) -> dict:
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if not names or len({name.casefold() for name in names}) != len(names):
        raise ValueError("Empty archive or duplicate paths")
    roots = set()
    for entry in entries:
        name = entry.filename
        parts = name.split("/")
        if (
            "\\" in name
            or ":" in name
            or any(
                part in {"", ".", ".."} or part.endswith((" ", ".")) for part in parts
            )
            or any(
                re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part)
                for part in parts
            )
            or stat.S_ISLNK(entry.external_attr >> 16)
        ):
            raise ValueError(f"Unsafe archive path: {name}")
        roots.add(parts[0])
        leaf = parts[-1].lower()
        if (
            any(
                part.lower().startswith(".venv")
                or part.lower()
                in {
                    ".git",
                    ".cache",
                    ".next",
                    "node_modules",
                    "__pycache__",
                    "tmp",
                }
                for part in parts
            )
            or (leaf.startswith(".env") and not leaf.endswith(".example"))
            or ("private" in leaf and leaf.endswith(".pem"))
            or leaf in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
            or PurePosixPath(leaf).suffix
            in {
                ".key",
                ".p12",
                ".pfx",
                ".onnx",
                ".gguf",
                ".safetensors",
                ".pt",
                ".pth",
                ".bin",
                ".ckpt",
                ".h5",
                ".hdf5",
                ".db",
                ".sqlite",
                ".sqlite3",
                ".log",
                ".zip",
            }
        ):
            raise ValueError(f"Prohibited payload: {name}")
    if len(roots) != 1:
        raise ValueError("Expected exactly one package root")
    root = roots.pop()
    manifest_path = f"{root}/MANIFEST.sha256"
    manifest = archive.read(manifest_path).decode("utf-8")
    expected = {}
    for line in manifest.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError("Malformed manifest row")
        digest, relative = match.groups()
        name = f"{root}/{relative}"
        if name in expected:
            raise ValueError("Duplicate manifest row")
        expected[name] = digest
    if set(expected) != set(names) - {manifest_path}:
        raise ValueError("Manifest must cover every payload exactly once")
    for name, digest in expected.items():
        with archive.open(name) as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != digest:
                raise ValueError(f"Hash mismatch: {name}")
    return {"root": root, "entries": len(entries), "verified_hashes": len(expected)}


def verify_and_extract(source: Path, destination: Path) -> dict:
    if destination.exists():
        raise ValueError("Extraction destination must not already exist")
    with zipfile.ZipFile(source) as archive:
        result = validate_archive(archive)
        archive.extractall(destination)
    root = destination / result["root"]
    for row in (root / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
        expected, name = row.split("  ", 1)
        with (root / name).open("rb") as extracted:
            if hashlib.file_digest(extracted, "sha256").hexdigest() != expected:
                raise ValueError(f"Extracted file mismatch: {name}")
    with source.open("rb") as bundle:
        result["zip_sha256"] = hashlib.file_digest(bundle, "sha256").hexdigest()
    result.update(status="verified_and_extracted", extracted_root=str(root.resolve()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--extract-to", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify_and_extract(args.archive, args.extract_to), indent=2))


if __name__ == "__main__":
    main()
