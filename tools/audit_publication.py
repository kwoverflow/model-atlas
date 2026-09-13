"""Scan exact staged Git blobs or a verified review ZIP before public publication.

This is a conservative high-confidence check, not a complete secret/security audit.
Findings contain paths and rule names only, never matched credential values.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from verify_mvp_package import validate_archive

CONTENT_RULES = {
    "private_key": re.compile(
        rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
    ),
    "github_token": re.compile(
        rb"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})\b"
    ),
    "provider_api_key": re.compile(rb"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{30,}\b"),
    "aws_access_key": re.compile(rb"\bAKIA[A-Z0-9]{16}\b"),
}
EXCLUDED_DIRECTORIES = {
    ".git",
    ".cache",
    ".next",
    "node_modules",
    "__pycache__",
    "tmp",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "dist",
    "build",
}
EXCLUDED_SUFFIXES = {
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
    ".pyc",
    ".pyo",
    ".tsbuildinfo",
}


def inspect_payload(name: str, content: bytes) -> list[dict[str, str]]:
    path = PurePosixPath(name.lower())
    findings = []
    if (
        any(
            part in EXCLUDED_DIRECTORIES or part.startswith(".venv")
            for part in path.parts
        )
        or (path.name.startswith(".env") and not path.name.endswith(".example"))
        or ("private" in path.name and path.suffix == ".pem")
        or path.name in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
        or path.suffix in EXCLUDED_SUFFIXES
    ):
        findings.append({"path": name, "rule": "prohibited_payload"})
    for rule, pattern in CONTENT_RULES.items():
        if pattern.search(content):
            findings.append({"path": name, "rule": rule})
    return findings


def staged_payloads(root: Path):
    result = subprocess.run(
        ["git", "ls-files", "--stage", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    entries = []
    for row in result.stdout.split(b"\0"):
        if not row:
            continue
        metadata, name = row.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        if mode not in {b"100644", b"100755"} or stage != b"0":
            raise ValueError("Refusing linked, submodule, or unmerged staged entry")
        entries.append((name.decode("utf-8"), oid))
    if not entries:
        raise ValueError("No staged payloads to audit")
    result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=root,
        check=True,
        capture_output=True,
        input=b"\n".join(oid for _, oid in entries) + b"\n",
    )
    stream = io.BytesIO(result.stdout)
    for name, expected_oid in entries:
        oid, kind, size = stream.readline().rstrip(b"\n").split()
        if oid != expected_oid or kind != b"blob":
            raise ValueError("Unexpected staged object")
        content = stream.read(int(size))
        if len(content) != int(size) or stream.read(1) != b"\n":
            raise ValueError("Truncated staged object")
        yield name, content
    if stream.read():
        raise ValueError("Unexpected trailing Git output")


def audit(payloads, scope: str) -> dict:
    findings = []
    count = 0
    total_bytes = 0
    for name, content in payloads:
        count += 1
        total_bytes += len(content)
        findings.extend(inspect_payload(name, content))
    return {
        "schema_version": "publication-audit-v1",
        "status": "passed" if count and not findings else "failed",
        "scope": scope,
        "payload_count": count,
        "payload_bytes": total_bytes,
        "findings": findings,
        "limitation": (
            "High-confidence patterns and payload rules only; not a complete security audit."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--git-index", type=Path)
    source.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.archive:
        with zipfile.ZipFile(args.archive) as archive:
            validate_archive(archive)
            result = audit(
                ((name, archive.read(name)) for name in archive.namelist()),
                "verified_zip",
            )
    else:
        result = audit(staged_payloads(args.git_index), "exact_git_index_blobs")
    serialized = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(serialized)
    print(serialized, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
