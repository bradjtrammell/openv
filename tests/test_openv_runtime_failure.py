"""Regression tests for actionable, non-bypassing Windows build diagnoses."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from openv_runtime_failure import explain, read_report, main


class FailureExplanationTests(unittest.TestCase):
    def test_actual_missing_native_imports_and_ownership(self):
        audit = {"status": "incomplete", "unresolved_imports": [
            {"path": "citizen-scripting-mono.dll", "dlls": ["mono-2.0-sgen.dll"]},
            {"path": "extra-natives-five.dll", "dlls": ["avutil-56.dll", "swresample-3.dll"]},
            {"path": "legitimacy.dll", "dlls": ["steam_api64.dll"]},
        ], "gameplay_verified": False}
        stage = {"status": "not_configured"}
        result = explain(audit, stage)
        self.assertEqual(set(result["unresolved"]), {"mono-2.0-sgen.dll", "avutil-56.dll", "swresample-3.dll", "steam_api64.dll"})
        self.assertFalse(result["gameplay_verified"])
        self.assertIn("OPENV_RUNTIME_DEPENDENCIES_MANIFEST", " ".join(result["problems"]))
        self.assertIn("legitimately installed GTA V/Steam", " ".join(result["recommended_actions"]))
        self.assertNotIn("whitelist steam_api64", " ".join(result["recommended_actions"]))

    def test_missing_audit_fails_to_claim_verified_build(self):
        out = explain({"status": "unavailable"}, {"status": "unavailable"})
        self.assertEqual(out["status"], "blocked")
        self.assertFalse(out["gameplay_verified"])
        self.assertIn("not produced", out["problems"][0])

    def test_stage_error_and_other_import(self):
        out = explain({"status": "incomplete", "unresolved_imports": [{"path": "some.dll", "dlls": ["unexpected.dll"]}], "binary_errors": [{"path": "other.dll"}]}, {"status": "failed"})
        self.assertIn("unexpected.dll", out["unresolved"])
        self.assertTrue(any("PE binaries" in x for x in out["problems"]))
        self.assertTrue(any("remaining imports" in x for x in out["recommended_actions"]))

    def test_report_reader_handles_missing_malformed_non_object(self):
        with tempfile.TemporaryDirectory() as p:
            path = Path(p) / "bad.json"
            self.assertEqual(read_report(path)["status"], "unavailable")
            for blob in ('{oops', '[]'):
                path.write_text(blob, encoding="utf-8")
                self.assertEqual(read_report(path)["status"], "unavailable")

    def test_cli_writes_actionable_json_and_does_not_fail_before_upload(self):
        with tempfile.TemporaryDirectory() as p:
            root = Path(p)
            audit = root / "audit.json"
            stage = root / "stage.json"
            report = root / "out.json"
            md = root / "summary.md"
            audit.write_text(json.dumps({"status": "incomplete", "unresolved_imports": [{"path": "legitimacy.dll", "dlls": ["steam_api64.dll"]}]}), encoding="utf-8")
            stage.write_text(json.dumps({"status": "not_configured"}), encoding="utf-8")
            self.assertEqual(main(["--audit", str(audit), "--open-runtime", str(stage),
                                   "--report", str(report), "--github-summary", str(md)]), 0)
            self.assertIn("steam_api64.dll", json.loads(report.read_text())["unresolved"])
            self.assertIn("exact build diagnosis", md.read_text())
            self.assertFalse(json.loads(report.read_text())["gameplay_verified"])


if __name__ == "__main__":
    unittest.main()
