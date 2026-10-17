import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_backend_audit_requirements import export_packages  # noqa: E402


def inventory():
    return [
        {"name": name, "version": version}
        for name, version in {
            "model-atlas-backend": "1.0.0",
            "pip": "26.2.1",
            "fastapi": "0.139.0",
            "PyJWT": "2.15.1",
            "cryptography": "50.0.2",
            "pypdf": "6.21.0",
            "anyio": "4.15.1",
            "setuptools": "82.0.1",
        }.items()
    ]


class BackendAuditInventoryTests(unittest.TestCase):
    def test_excludes_only_first_party_and_keeps_installer(self):
        text = export_packages(inventory())
        self.assertNotIn("model-atlas", text)
        self.assertIn("pip==26.2.1\n", text)
        self.assertIn("setuptools==82.0.1\n", text)
        self.assertEqual(len(text.splitlines()), 7)

    def test_requires_complete_inventory(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            export_packages(inventory()[:-2])

    def test_conflicting_versions_fail(self):
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            export_packages(inventory() + [{"name": "anyio", "version": "4.0"}])

    def test_rejects_requirement_injection(self):
        for package in (
            {"name": "--index-url", "version": "1"},
            {"name": "ok", "version": "1\n--extra-index-url evil"},
        ):
            with self.subTest(package=package), self.assertRaisesRegex(ValueError, "Unsafe"):
                export_packages(inventory() + [package])

    def test_missing_first_party_fails(self):
        with self.assertRaisesRegex(ValueError, "first-party"):
            export_packages(inventory()[1:])
