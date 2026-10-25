"""Owner-supplied Mono/FFmpeg staging and rollback regressions."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import stage_open_runtime as stage


class RuntimeDependencyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.runtime = self.base / "runtime"
        self.runtime.mkdir()
        self.manifest = self.base / "manifest.json"
        self.spec = {"schema": 1, "packages": {}}
        for package, names in stage.ABI.items():
            folder = self.base / package
            folder.mkdir()
            for name in names:
                (folder / name).write_bytes(b"MZfixture" + name.encode())
            license_data = b"An example license text for test fixture only, not a real license.\n"
            (folder / "LICENSE.txt").write_bytes(license_data)
            self.spec["packages"][package] = {
                "directory": package,
                "upstream_url": "https://example.org/" + package,
                "license_file": "LICENSE.txt",
                "license_spdx": "MIT" if package == "mono" else "LGPL-2.1-or-later",
                "license_sha256": hashlib.sha256(license_data).hexdigest(),
                "files": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                          for name in names},
            }
        self.save()
        patch = mock.patch.object(stage, "pe_imports", return_value=set())
        patch.start()
        self.addCleanup(patch.stop)

    def save(self):
        self.manifest.write_text(json.dumps(self.spec), encoding="utf-8")

    def test_all_dlls_and_licenses_with_verified_hashes(self):
        result = stage.stage(self.manifest, self.runtime)
        self.assertEqual(result["status"], "staged")
        self.assertEqual(len(result["files"]), 5)
        self.assertFalse(result["gameplay_verified"])
        for item in result["files"]:
            self.assertEqual(item["sha256"], hashlib.sha256(
                (self.runtime / item["path"]).read_bytes()).hexdigest())

    def test_digest_mismatch_and_wrong_abi_fail_closed(self):
        self.spec["packages"]["mono"]["files"]["mono-2.0-sgen.dll"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(stage.StageError, "SHA-256 mismatch"):
            stage.stage(self.manifest, self.runtime)
        self.spec["packages"]["mono"]["files"] = {"mono-renamed.dll": "0" * 64}
        self.save()
        with self.assertRaisesRegex(stage.StageError, "DLL list"):
            stage.stage(self.manifest, self.runtime)

    def test_license_path_and_url_are_checked(self):
        self.spec["packages"]["mono"]["license_file"] = "../bad"
        self.save()
        with self.assertRaisesRegex(stage.StageError, "unsafe"):
            stage.stage(self.manifest, self.runtime)
        self.spec["packages"]["mono"]["license_file"] = "LICENSE.txt"
        self.spec["packages"]["mono"]["upstream_url"] = "http://example.org"
        self.save()
        with self.assertRaisesRegex(stage.StageError, "HTTPS"):
            stage.stage(self.manifest, self.runtime)

    def test_rejects_bad_pe_and_existing_file(self):
        with mock.patch.object(stage, "pe_imports", side_effect=stage.RuntimeAuditError("x86")):
            with self.assertRaisesRegex(stage.StageError, "AMD64"):
                stage.stage(self.manifest, self.runtime)
        (self.runtime / "avutil-56.dll").write_bytes(b"original")
        with self.assertRaisesRegex(stage.StageError, "overwrite"):
            stage.stage(self.manifest, self.runtime)
        self.assertEqual((self.runtime / "avutil-56.dll").read_bytes(), b"original")

    def test_transaction_rollback_preserves_intruder(self):
        original = stage.os.link
        count = 0
        def collision(source, target):
            nonlocal count
            count += 1
            if count == 3:
                Path(target).write_bytes(b"intruder")
                raise FileExistsError("concurrent writer")
            return original(source, target)
        with mock.patch.object(stage.os, "link", side_effect=collision):
            with self.assertRaises(FileExistsError):
                stage.stage(self.manifest, self.runtime)
        self.assertEqual(len(list(self.runtime.iterdir())), 1)
        self.assertEqual(next(self.runtime.iterdir()).read_bytes(), b"intruder")

    def test_cli_failure_writes_provenance_report(self):
        self.spec["packages"]["mono"]["files"]["mono-2.0-sgen.dll"] = "0" * 64
        self.save()
        report = self.base / "report.json"
        self.assertEqual(stage.main(["--manifest", str(self.manifest),
                                     "--runtime", str(self.runtime),
                                     "--report", str(report)]), 1)
        self.assertEqual(json.loads(report.read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
