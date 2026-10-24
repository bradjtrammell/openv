"""Pinned CEF runtime staging and atomic rollback regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import stage_cef_runtime as cef


class StageCEFTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'cef'
        self.runtime = self.base / 'runtime'
        self.runtime.mkdir()
        for name in ('Release', 'Resources', 'Resources/locales'):
            (self.source / name).mkdir(parents=True, exist_ok=True)
        (self.source / 'cef_build_name.txt').write_text(
            'cef_binary_103.0.0-cfx-m103.2605+g1316dae+chromium-103.0.5060.141_windows64_minimal\n')
        for name in cef.REQUIRED + tuple('Resources/' + n for n in cef.REQUIRED_PAK):
            (self.source / name).write_bytes(b'MZmock' if name.endswith('.dll') else b'CEF resource')
        (self.source / 'Resources/locales/en-US.pak').write_bytes(b'locale')
        self.pe = mock.patch.object(cef, 'pe_imports', side_effect=lambda data, role: set())
        self.pe.start()
        self.addCleanup(self.pe.stop)

    def test_publishes_pinned_runtime_with_hashes_and_license(self):
        (self.source / 'Release/chrome_elf.dll').write_bytes(b'MZchrome')
        (self.source / 'Resources/cef_extensions.pak').write_bytes(b'extension')
        (self.source / 'Resources/locales/fr.pak').write_bytes(b'fr')
        report = cef.stage(self.source, self.runtime)
        self.assertEqual(report['status'], 'staged')
        self.assertFalse(report['gameplay_verified'])
        self.assertEqual((self.runtime / 'libcef.dll').read_bytes(), b'MZmock')
        self.assertEqual((self.runtime / 'CEF-LICENSE.txt').read_bytes(), b'CEF resource')
        self.assertEqual((self.runtime / 'locales/en-US.pak').read_bytes(), b'locale')
        self.assertEqual((self.runtime / 'cef_extensions.pak').read_bytes(), b'extension')
        self.assertEqual(len(report['files']), 10)
        for entry in report['files']:
            import hashlib
            self.assertEqual(entry['sha256'], hashlib.sha256(
                (self.runtime / entry['path']).read_bytes()).hexdigest())

    def test_no_clobber_of_existing_libcef(self):
        (self.runtime / 'libcef.dll').write_bytes(b'existing')
        with self.assertRaisesRegex(cef.CEFStageError, 'overwrite'):
            cef.stage(self.source, self.runtime)
        self.assertEqual((self.runtime / 'libcef.dll').read_bytes(), b'existing')
        self.assertFalse((self.runtime / 'icudtl.dat').exists())

    def test_rejects_missing_license_or_resource(self):
        for name in ('LICENSE.txt', 'Resources/cef.pak', 'Resources/icudtl.dat'):
            path = self.source / name
            original = path.read_bytes()
            path.unlink()
            with self.subTest(name=name), self.assertRaises(cef.CEFStageError):
                cef.stage(self.source, self.runtime)
            path.write_bytes(original)

    def test_rejects_unpinned_build(self):
        (self.source / 'cef_build_name.txt').write_text('cef_binary_103_linux64_minimal')
        with self.assertRaisesRegex(cef.CEFStageError, 'unpinned'):
            cef.stage(self.source, self.runtime)

    def test_rejects_source_links(self):
        path = self.source / 'Release/libcef.dll'
        path.unlink()
        try:
            path.symlink_to(self.source / 'LICENSE.txt')
        except OSError:
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(cef.CEFStageError, 'linked'):
            cef.stage(self.source, self.runtime)

    def test_rejects_unsafe_locale(self):
        (self.source / 'Resources/locales/bad!.pak').write_bytes(b'bad')
        with self.assertRaisesRegex(cef.CEFStageError, 'unsafe'):
            cef.stage(self.source, self.runtime)

    def test_rejects_oversized_payload(self):
        with (self.source / 'Release/libcef.dll').open('wb') as handle:
            handle.truncate(cef.MAX_FILE_BYTES + 1)
        with self.assertRaisesRegex(cef.CEFStageError, 'invalid CEF source'):
            cef.stage(self.source, self.runtime)

    def test_pe_rejection_is_fatal(self):
        self.pe.stop()
        with mock.patch.object(cef, 'pe_imports', side_effect=cef.RuntimeAuditError('wrong architecture')):
            with self.assertRaisesRegex(cef.CEFStageError, 'x64 PE'):
                cef.stage(self.source, self.runtime)
        self.pe.start()

    def test_partial_publication_rollback(self):
        original_link = cef.os.link
        counter = 0
        def fail_third(source, target):
            nonlocal counter
            counter += 1
            if counter == 3:
                raise OSError('simulated publish failure')
            return original_link(source, target)
        with mock.patch.object(cef.os, 'link', side_effect=fail_third):
            with self.assertRaisesRegex(OSError, 'simulated'):
                cef.stage(self.source, self.runtime)
        self.assertEqual(list(self.runtime.rglob('*')), [])

    def test_race_does_not_delete_intruder(self):
        original_link = cef.os.link
        counter = 0
        def race(source, target):
            nonlocal counter
            counter += 1
            if counter == 2:
                Path(target).write_bytes(b'intruder')
                raise FileExistsError('simulated competing publisher')
            return original_link(source, target)
        with mock.patch.object(cef.os, 'link', side_effect=race):
            with self.assertRaises(FileExistsError):
                cef.stage(self.source, self.runtime)
        self.assertEqual((self.runtime / 'cef_100_percent.pak').exists(), False)
        self.assertEqual((self.runtime / 'cef.pak').exists(), False)
        self.assertEqual(len([p for p in self.runtime.rglob('*') if p.is_file()]), 1)
        self.assertEqual(next(p for p in self.runtime.rglob('*') if p.is_file()).read_bytes(), b'intruder')

    def test_cli_reports_failure_without_success_claim(self):
        (self.source / 'LICENSE.txt').unlink()
        report = self.base / 'report.json'
        self.assertEqual(cef.main(['--source', str(self.source), '--runtime', str(self.runtime),
                                   '--report', str(report)]), 1)
        data = json.loads(report.read_text())
        self.assertEqual(data['status'], 'failed')
        self.assertFalse(data['gameplay_verified'])


if __name__ == '__main__':
    unittest.main()
