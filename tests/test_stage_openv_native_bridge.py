"""Offline staging contract tests; CI additionally audits the real MSVC DLL."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

SCRIPT = Path(__file__).resolve().parents[1] / 'tools' / 'stage_openv_native_bridge.py'
spec = importlib.util.spec_from_file_location('stage_openv_native_bridge', SCRIPT)
stage_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_module)
SHA = '776bdddf71446c99f5e256aa53e7c98c013f7be2'


class StagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source.dll'
        self.source.write_bytes(b'MZ' + bytes(2046))
        self.runtime = self.root / 'runtime'
        self.runtime.mkdir()
        self.auditor = Mock()
        self.auditor.ABI_EXPORTS = frozenset({'openv_authority_start', 'openv_authority_stop'})
        self.auditor.pe_exports.return_value = set(self.auditor.ABI_EXPORTS)
        self.auditor.validate_dependencies.return_value = {'kernel32.dll', 'ws2_32.dll'}

    def run_stage(self):
        return stage_module.stage(self.source, self.runtime, self.auditor, SHA)

    def test_exact_staging_and_idempotence(self):
        first = self.run_stage()
        self.assertEqual(first['status'], 'staged')
        self.assertEqual(first['source_commit'], SHA)
        self.assertEqual(first['export_count'], 2)
        self.assertFalse(first['gameplay_verified'])
        self.assertEqual((self.runtime / stage_module.DLL_NAME).read_bytes(), self.source.read_bytes())
        second = self.run_stage()
        self.assertEqual(second['status'], 'already_identical')
        self.assertEqual(second['sha256'], first['sha256'])

    def test_refuse_existing_different_binary(self):
        target = self.runtime / stage_module.DLL_NAME
        target.write_bytes(b'MZ' + bytes(2045) + b'X')
        with self.assertRaisesRegex(stage_module.StageError, 'refusing overwrite'):
            self.run_stage()
        self.assertEqual(target.read_bytes()[-1:], b'X')

    def test_bad_abi_refused_before_write(self):
        self.auditor.pe_exports.return_value = {'openv_authority_start'}
        with self.assertRaisesRegex(stage_module.StageError, 'exports differ'):
            self.run_stage()
        self.assertFalse((self.runtime / stage_module.DLL_NAME).exists())

    def test_bad_pe_refused_before_write(self):
        self.auditor.pe_validate.side_effect = ValueError('not an AMD64 DLL')
        with self.assertRaisesRegex(stage_module.StageError, 'PE/ABI audit failed'):
            self.run_stage()
        self.assertFalse((self.runtime / stage_module.DLL_NAME).exists())

    def test_unknown_import_refused_before_write(self):
        self.auditor.validate_dependencies.side_effect = ValueError('unknown dependency')
        with self.assertRaisesRegex(stage_module.StageError, 'PE/ABI audit failed'):
            self.run_stage()
        self.assertFalse((self.runtime / stage_module.DLL_NAME).exists())

    def test_short_source_refused(self):
        self.source.write_bytes(b'MZ')
        with self.assertRaisesRegex(stage_module.StageError, 'invalid size'):
            self.run_stage()

    def test_noncanonical_commit_refused(self):
        with self.assertRaisesRegex(stage_module.StageError, 'complete lowercase Git SHA'):
            stage_module.stage(self.source, self.runtime, self.auditor, 'main')

    def test_source_symlink_refused(self):
        original = self.root / 'original.dll'
        self.source.rename(original)
        try:
            self.source.symlink_to(original)
        except (NotImplementedError, OSError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(stage_module.StageError, 'reparse point'):
            self.run_stage()

    def test_runtime_symlink_refused(self):
        actual = self.root / 'actual'
        self.runtime.rename(actual)
        try:
            self.runtime.symlink_to(actual, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(stage_module.StageError, 'reparse point'):
            self.run_stage()

    def test_destination_symlink_refused(self):
        external = self.root / 'external.dll'
        external.write_bytes(b'Z' * 2048)
        try:
            (self.runtime / stage_module.DLL_NAME).symlink_to(external)
        except (NotImplementedError, OSError):
            self.skipTest('symlinks unavailable')
        with self.assertRaisesRegex(stage_module.StageError, 'reparse point'):
            self.run_stage()
        self.assertEqual(external.read_bytes(), b'Z' * 2048)


if __name__ == '__main__':
    unittest.main()
