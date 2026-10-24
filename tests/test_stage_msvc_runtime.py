"""Offline VC143 staging tests: no proprietary runtime bytes required."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from stage_msvc_runtime import REQUIRED_DLLS, StagingError, redist_directories, stage
from test_openv_runtime_audit import fixture_pe


class StageMSVCTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.root = self.base / 'VC' / 'Redist' / 'MSVC'
        self.runtime = self.base / 'runtime'
        self.runtime.mkdir()
        self.crt = self.root / '14.44.35211' / 'x64' / 'Microsoft.VC143.CRT'
        self.crt.mkdir(parents=True)
        for name in REQUIRED_DLLS:
            (self.crt / name).write_bytes(fixture_pe(dll=True))
        self.verified = []

    def verifier(self, path):
        self.verified.append(path.name)

    def test_stages_complete_signed_set_with_hashes(self):
        report = stage(self.root, self.runtime, verifier=self.verifier)
        self.assertEqual(report['status'], 'staged')
        self.assertEqual(report['source_version'], '14.44.35211')
        self.assertEqual(set(self.verified), set(REQUIRED_DLLS))
        for item in report['files']:
            self.assertEqual(len(item['sha256']), 64)
            self.assertEqual((self.runtime / item['name']).read_bytes(), (self.crt / item['name']).read_bytes())
        self.assertFalse(report['gameplay_verified'])

    def test_does_not_mix_partial_versions(self):
        newer = self.root / '14.45.99999' / 'x64' / 'Microsoft.VC143.CRT'
        newer.mkdir(parents=True)
        (newer / REQUIRED_DLLS[0]).write_bytes(fixture_pe(dll=True))
        self.assertEqual(redist_directories(self.root)[0], newer)
        self.assertEqual(stage(self.root, self.runtime, verifier=self.verifier)['source_version'], '14.44.35211')

    def test_rejects_invalid_architecture_and_no_partial_publish(self):
        (self.crt / REQUIRED_DLLS[1]).write_bytes(fixture_pe(dll=True, machine=0x14c))
        with self.assertRaisesRegex(StagingError, 'invalid AMD64'):
            stage(self.root, self.runtime, verifier=self.verifier)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_refuses_unsigned_source_and_no_partial_publish(self):
        def fail(path):
            if path.name == REQUIRED_DLLS[-1]:
                raise StagingError('unsigned')
        with self.assertRaisesRegex(StagingError, 'unsigned'):
            stage(self.root, self.runtime, verifier=fail)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_never_overwrites_existing_dll(self):
        (self.runtime / REQUIRED_DLLS[0]).write_bytes(b'original')
        with self.assertRaisesRegex(StagingError, 'overwrite'):
            stage(self.root, self.runtime, verifier=self.verifier)
        self.assertEqual((self.runtime / REQUIRED_DLLS[0]).read_bytes(), b'original')
        self.assertEqual(len(list(self.runtime.iterdir())), 1)

    def test_missing_source_or_missing_complete_set(self):
        (self.crt / REQUIRED_DLLS[-1]).unlink()
        with self.assertRaisesRegex(StagingError, 'complete'):
            stage(self.root, self.runtime, verifier=self.verifier)
        with self.assertRaisesRegex(StagingError, 'unavailable'):
            stage(self.base / 'missing', self.runtime, verifier=self.verifier)

    def test_symlink_source_is_rejected(self):
        (self.crt / REQUIRED_DLLS[0]).unlink()
        try:
            (self.crt / REQUIRED_DLLS[0]).symlink_to(self.crt / REQUIRED_DLLS[1])
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(StagingError, 'complete'):
            stage(self.root, self.runtime, verifier=self.verifier)

    def test_default_verifier_requires_windows(self):
        if sys.platform == 'win32':
            self.skipTest('Windows verifies actual Authenticode on official redistributables')
        with self.assertRaisesRegex(StagingError, 'requires Windows'):
            stage(self.root, self.runtime)


if __name__ == '__main__':
    unittest.main()
