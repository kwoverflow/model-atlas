import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_publication import audit, inspect_payload, staged_payloads  # noqa: E402


class PublicationAuditTests(unittest.TestCase):
    def test_detects_credentials_without_disclosing_value(self):
        token = b"ghp_" + b"A" * 36
        findings = inspect_payload("config.txt", token)
        self.assertEqual(findings, [{"path": "config.txt", "rule": "github_token"}])
        self.assertNotIn(token.decode(), str(findings))

    def test_detects_private_key_under_innocent_filename(self):
        header = b"-----BEGIN " + b"PRIVATE KEY-----"
        self.assertEqual(inspect_payload("notes.txt", header)[0]["rule"], "private_key")

    def test_rejects_prohibited_paths(self):
        for name in (
            ".env",
            "a/.env.production",
            "artifacts/model.onnx",
            "a/private.pem",
            "a/id_ed25519",
            "a/node_modules/index.js",
            "a/run.sqlite3",
        ):
            with self.subTest(name=name):
                self.assertEqual(
                    inspect_payload(name, b"")[0]["rule"], "prohibited_payload"
                )

    def test_allows_documented_development_examples(self):
        self.assertEqual(
            inspect_payload("deploy/idp/.env.keycloak.example", b"SECRET=replace-me"), []
        )
        self.assertEqual(
            inspect_payload("deploy/observability/.env.observability.example", b""), []
        )
        self.assertEqual(
            inspect_payload(".env.example", b"PASSWORD=local-review-only"), []
        )
        self.assertEqual(
            inspect_payload("demo-public.pem", b"public verification key"), []
        )

    def test_empty_audit_is_not_success(self):
        self.assertEqual(audit([], "test")["status"], "failed")

    def test_audits_staged_bytes_not_modified_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            path = root / "example.txt"
            path.write_bytes(b"github_pat_" + b"A" * 36)
            subprocess.run(["git", "add", "example.txt"], cwd=root, check=True)
            path.write_bytes(b"safe unstaged replacement")
            result = audit(staged_payloads(root), "test")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["payload_count"], 1)


if __name__ == "__main__":
    unittest.main()
