import hashlib
import importlib.util
import io
import unittest
import zipfile
from pathlib import Path


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / f"{name}.py"
    )
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


smoke = module("verify_mvp_review")
package = module("verify_mvp_package")


def archive_with(path="README.md", body=b"review", expected=None, extra_manifest=""):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(f"review/{path}", body)
        digest = expected or hashlib.sha256(body).hexdigest()
        archive.writestr(
            "review/MANIFEST.sha256", f"{digest}  {path}\n" + extra_manifest
        )
    stream.seek(0)
    return zipfile.ZipFile(stream)


class TargetTests(unittest.TestCase):
    def test_explicit_local_review_allowed(self):
        self.assertEqual(
            smoke.validate_target("http://127.0.0.1:18010/api/v1/", True),
            "http://127.0.0.1:18010/api/v1",
        )

    def test_confirmation_required(self):
        with self.assertRaises(ValueError):
            smoke.validate_target("http://localhost:18010/api/v1", False)

    def test_unsafe_targets_refused(self):
        for url in (
            "http://localhost:18000/api/v1",
            "http://localhost:8000/api/v1",
            "http://example.com:18010/api/v1",
            "https://localhost:18010/api/v1",
            "http://localhost/api/v1",
            "http://user:pass@localhost:18010/api/v1",
            "http://localhost:18010/api/v1?token=test",
            "http://localhost:18010/api/v1#x",
            "http://localhost:18010/",
            "http://localhost:invalid/api/v1",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                smoke.validate_target(url, True)


class PackageTests(unittest.TestCase):
    def test_complete_manifest(self):
        with archive_with() as archive:
            self.assertEqual(package.validate_archive(archive)["verified_hashes"], 1)

    def test_tampering_detected(self):
        with archive_with(expected="0" * 64) as archive, self.assertRaises(ValueError):
            package.validate_archive(archive)

    def test_prohibited_and_unsafe_paths(self):
        for path in (
            "../escape",
            "/absolute",
            "C:/escape",
            "dir\\escape",
            "NUL.txt",
            "dir./x",
            ".env",
            ".env.local",
            ".venv-rag/file.py",
            ".cache/model.json",
            "models/model.onnx",
            "models/model.gguf",
            "weights.safetensors",
            "key.key",
            "demo-private.pem",
            "id_rsa",
            "db.sqlite",
            "node_modules/a.js",
        ):
            with (
                self.subTest(path=path),
                archive_with(path) as archive,
                self.assertRaises(ValueError),
            ):
                package.validate_archive(archive)

    def test_missing_manifest_entry(self):
        with (
            archive_with(extra_manifest=f"{'0' * 64}  missing.md\n") as archive,
            self.assertRaises(ValueError),
        ):
            package.validate_archive(archive)

    def test_duplicate_manifest_entry(self):
        digest = hashlib.sha256(b"review").hexdigest()
        with (
            archive_with(extra_manifest=f"{digest}  README.md\n") as archive,
            self.assertRaises(ValueError),
        ):
            package.validate_archive(archive)

    def test_public_environment_example_allowed(self):
        with archive_with(".env.example") as archive:
            self.assertEqual(package.validate_archive(archive)["entries"], 2)


if __name__ == "__main__":
    unittest.main()
