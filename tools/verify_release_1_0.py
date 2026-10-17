"""Assemble inspectable 1.0 closeout evidence without inventing a release approval."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EVIDENCE = REPO / "artifacts/personal-assistant-release/2026-10-16"


def sha(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def junit(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise ValueError("Missing test suites")
    result = {
        key: sum(int(s.get(key, "0")) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }
    if result["failures"] or result["errors"] or not result["tests"]:
        raise ValueError(f"Unsuccessful tests: {result}")
    result["passed"] = result["tests"] - result["skipped"]
    return result


def verify(output, accept_development_risk=False, security_closeout=False):
    output = output.resolve()
    assert (
        output.resolve().is_relative_to(EVIDENCE.resolve())
        and output.resolve() != EVIDENCE.resolve()
    )
    output.mkdir(parents=True)
    checks = []

    def receipt(relative):
        path = EVIDENCE / relative
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") != "passed":
            raise ValueError(f"Incomplete receipt: {relative}")
        checks.append(
            {
                "name": relative,
                "status": "passed",
                "path": path.relative_to(REPO).as_posix(),
                "sha256": sha(path),
            }
        )
        return data

    model_path = EVIDENCE / "regression-v1/summary.json"
    model = json.loads(model_path.read_text(encoding="utf-8"))
    assert model["regression_gate"] == "PASS_PENDING_APP_RELEASE" and model["calls"] == 328
    for key in ("protocol", "observations"):
        assert sha(model_path.parent / f"{key}.json") == model[f"{key}_sha256"]
    protocol = json.loads((model_path.parent / "protocol.json").read_text(encoding="utf-8"))
    for relative, expected in protocol["source_sha256"].items():
        assert sha(REPO / relative) == sha(model_path.parent / "sources" / relative) == expected
    checks.append(
        {
            "name": "known_model_regression",
            "status": "passed",
            "sha256": sha(model_path),
            "calls": 328,
            "new_holdout": False,
        }
    )
    replay = receipt(
        "security-v1/replay/verification.json"
        if security_closeout
        else "replay-v1/verification.json"
    )
    assert replay["replayed"] == 328 and replay["model_calls"] == 0
    browser = receipt(
        "security-v1/browser/browser-e2e.json"
        if security_closeout
        else "browser-v2/browser-e2e.json"
    )
    assert browser["version"] == "1.0.0" and browser["strategy"] == "assistant-release-v1"
    assert browser["model_corrections"] == 0 and browser["new_model_requests"] == 11
    layout = receipt(
        "security-v1/layout-final/layout.json" if security_closeout else "layout-v2/layout.json"
    )
    assert len(layout["observations"]) == 3
    rollback, forward = receipt("rollback.json"), receipt("rollforward.json")
    assert (
        rollback["draft_strategy"] == "legacy"
        and forward["draft_strategy"] == "assistant-release-v1"
    )
    assert rollback["state_sha256"] == forward["state_sha256"]
    assert rollback["reviews_sha256"] == forward["reviews_sha256"]
    live = receipt("security-v1/live-after.json" if security_closeout else "live-after.json")
    assert (
        live["draft_strategy"] == "assistant-release-v1" and live["application_version"] == "1.0.0"
    )
    installation = receipt(
        "security-v1/clean-install-api.json" if security_closeout else "clean-install-api.json"
    )
    assert len(installation["checks"]) == 33 and not installation["human_review_performed"]
    receipt(
        "security-v1/deployment-ui/deployment-ui.json"
        if security_closeout
        else "deployment-ui/deployment-ui.json"
    )

    test_counts = {}
    for name in ("backend-tests.xml", "backend-linux-tests.xml", "experiment-tests.xml"):
        path = EVIDENCE / name
        test_counts[name] = junit(path)
        checks.append({"name": name, "status": "passed", "sha256": sha(path), **test_counts[name]})
    assert test_counts["backend-tests.xml"]["passed"] == 1261
    assert test_counts["backend-linux-tests.xml"]["passed"] == 1263
    assert test_counts["experiment-tests.xml"]["passed"] == 241
    if security_closeout:
        for name, passed in (("backend-tests.xml", 1261), ("backend-linux-tests.xml", 1263)):
            path = EVIDENCE / "security-v1" / name
            counts = junit(path)
            assert counts["passed"] == passed
            test_counts[f"security-v1/{name}"] = counts
            checks.append(
                {"name": f"security-v1/{name}", "status": "passed", "sha256": sha(path), **counts}
            )

    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    assert npm
    python = str(REPO / ".venv/Scripts/python.exe") if os.name == "nt" else sys.executable
    ruff = str(REPO / ".venv/Scripts/ruff.exe") if os.name == "nt" else "ruff"

    def command(name, args, cwd=REPO, allowed_codes=(0,)):
        completed = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        log = output / f"{name}.txt"
        log.write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode not in allowed_codes:
            raise ValueError(f"{name} failed with code {completed.returncode}; see {log}")
        checks.append(
            {
                "name": name,
                "status": "passed" if completed.returncode == 0 else "findings_recorded",
                "returncode": completed.returncode,
                "sha256": sha(log),
                "path": log.relative_to(REPO).as_posix(),
            }
        )
        return completed

    command("backend-lint", [ruff, "check", "backend"])
    command(
        "release-lint",
        [
            ruff,
            "check",
            "--config",
            "backend/pyproject.toml",
            "experiments/personal_assistant_release",
            "tools/check_personal_assistant_release_state.py",
            "tools/verify_release_1_0.py",
        ],
    )
    command(
        "tools-lint",
        [
            ruff,
            "check",
            "--config",
            "tools/ruff.toml",
            "tools/verify_mvp_package.py",
            "tools/tests",
        ],
    )
    command("tools-tests", [python, "-m", "unittest", "discover", "-s", "tools/tests", "-v"])
    command("frontend-tests", [npm, "test"], REPO / "frontend")
    command("frontend-types", [npm, "run", "typecheck"], REPO / "frontend")
    command("frontend-lint", [npm, "run", "lint"], REPO / "frontend")
    command("whitespace", ["git", "diff", "--check"])
    prod = command("runtime-audit", [npm, "audit", "--omit=dev", "--json"], REPO / "frontend")
    full = command(
        "full-audit" if security_closeout else "full-audit-recorded-not-clean",
        [npm, "audit", "--json"],
        REPO / "frontend",
        allowed_codes=(0,) if security_closeout else (0, 1),
    )
    runtime_audit, full_audit = json.loads(prod.stdout), json.loads(full.stdout)
    assert "error" not in runtime_audit and "error" not in full_audit
    assert runtime_audit["metadata"]["vulnerabilities"]["total"] == 0
    assert full_audit["metadata"]["vulnerabilities"]["critical"] == 0
    lock = json.loads((REPO / "frontend/package-lock.json").read_text(encoding="utf-8"))
    for vulnerability in full_audit.get("vulnerabilities", {}).values():
        assert all(lock["packages"][node].get("dev") is True for node in vulnerability["nodes"])
    python_audits = {}
    if security_closeout:
        assert full_audit["metadata"]["vulnerabilities"]["total"] == 0
        for scope in ("python", "python-container"):
            requirements = EVIDENCE / "security-v1" / f"{scope}-audit-requirements.txt"
            audited = command(
                f"{scope}-audit",
                [
                    "uv",
                    "tool",
                    "run",
                    "--from",
                    "pip-audit==2.10.1",
                    "pip-audit",
                    "--strict",
                    "--no-deps",
                    "--disable-pip",
                    "--progress-spinner",
                    "off",
                    "-r",
                    str(requirements),
                    "--format",
                    "json",
                ],
            )
            data = json.loads(audited.stdout)
            assert len(data["dependencies"]) == 50
            assert all(
                not item.get("vulns") and not item.get("skip_reason")
                for item in data["dependencies"]
            )
            expected = set(requirements.read_text(encoding="utf-8").splitlines())
            actual = {
                f"{item['name'].lower().replace('_', '-')}=={item['version']}"
                for item in data["dependencies"]
            }
            assert expected == actual
            python_audits[scope] = {
                "packages": len(actual),
                "vulnerabilities": 0,
                "requirements_sha256": sha(requirements),
            }
    package = json.loads((REPO / "frontend/package.json").read_text(encoding="utf-8"))
    backend = tomllib.loads((REPO / "backend/pyproject.toml").read_text(encoding="utf-8"))
    assert (
        backend["project"]["version"]
        == package["version"]
        == lock["version"]
        == lock["packages"][""]["version"]
        == "1.0.0"
    )
    inventory = command(
        "production-image-inventory",
        [
            "docker",
            "compose",
            "-p",
            "model-atlas-1-0-security-20261016"
            if security_closeout
            else "model-atlas-1-0-qa-20261016",
            "-f",
            "deploy/mvp-review.compose.yml",
            "exec",
            "-T",
            "frontend",
            "node",
            "-e",
            "const fs=require('fs');"
            "const names=['eslint','eslint-config-next','tailwindcss','braces','fast-glob'];"
            "const p=names.filter(n=>fs.existsSync('node_modules/'+n));"
            "console.log(JSON.stringify({next:require('next/package.json').version,"
            "development_packages_present:p}));process.exit(p.length?1:0)",
        ],
    )
    assert json.loads(inventory.stdout)["next"] == "16.4.2"
    remaining = full_audit["metadata"]["vulnerabilities"]
    status = (
        "LOCAL_REVIEW_1_0_READY"
        if accept_development_risk or remaining["total"] == 0
        else "CANDIDATE_PENDING_DEVELOPMENT_RISK_DECISION"
    )
    result = {
        "schema_version": "mvp-closeout-verification-v1",
        "application_version": "1.0.0",
        "release_status": status,
        "checks": checks,
        "test_counts": test_counts,
        "runtime_vulnerabilities": runtime_audit["metadata"]["vulnerabilities"],
        "development_vulnerabilities": remaining,
        "development_risk_scope_accepted_by_user": accept_development_risk,
        "full_audit_clean": remaining["total"] == 0,
        "python_audits": python_audits,
        "security_closeout": security_closeout,
        "security_scope_excludes": [
            "OS/base-image vulnerability scan",
            "penetration testing",
            "external human security review",
        ],
        "external_review": "pending",
        "production_readiness": "not_production_ready",
        "autonomous_release": "blocked",
        "human_attestation": False,
        "readiness_excludes_package_integrity": True,
    }
    (output / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--security-closeout", action="store_true")
    parser.add_argument(
        "--accept-development-risk",
        action="store_true",
        help="Use only after direct user authorization of this release scope.",
    )
    args = parser.parse_args()
    value = verify(args.output, args.accept_development_risk, args.security_closeout)
    print(
        json.dumps(
            {
                "release_status": value["release_status"],
                "checks": len(value["checks"]),
                "full_audit_clean": value["full_audit_clean"],
            }
        )
    )
