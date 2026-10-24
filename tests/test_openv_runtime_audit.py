"""Static OpenV Windows runtime gate regression and malformed PE tests."""
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / 'tools'))
import audit_openv_runtime as audit
import build_openv_ui as ui


def fixture_pe(*, dll=False, imports=(), delay_imports=(), machine=0x8664, terminate=True):
    """Small synthetic PE32+ with file-backed import descriptors, no executable code."""
    data = bytearray(0x1000)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', data, 0x84, machine, 1, 0, 0, 0, 240, 0x2022 if dll else 0x22)
    opt = 0x98
    struct.pack_into('<H', data, opt, 0x20b)
    struct.pack_into('<I', data, opt+108, 16)
    section = opt+240
    data[section:section+8] = b'.rdata\0\0'
    struct.pack_into('<IIII', data, section+8, 0xE00, 0x1000, 0xE00, 0x200)
    cursor = 0x600
    def make_table(names, rva, entry, name_offset, directory):
        nonlocal cursor
        if not names:
            return
        struct.pack_into('<II', data, opt+112+directory*8, rva, (len(names)+int(terminate))*entry)
        for index, name in enumerate(names):
            off = 0x200 + rva-0x1000 + index*entry
            if directory == 13:
                struct.pack_into('<I', data, off, 1)
            struct.pack_into('<I', data, off+name_offset, 0x1000+cursor-0x200)
            encoded = name.encode('ascii') + b'\0'
            data[cursor:cursor+len(encoded)] = encoded
            cursor += len(encoded)
    make_table(imports, 0x1000, 20, 12, 1)
    make_table(delay_imports, 0x1200, 32, 4, 13)
    return bytes(data)


class PEImportTests(unittest.TestCase):
    def test_normal_and_delay_imports(self):
        pe = fixture_pe(imports=('KERNEL32.dll', 'vcruntime140.dll'), delay_imports=('LIBCEF.DLL',))
        self.assertEqual(audit.pe_imports(pe, 'exe'), {'kernel32.dll', 'vcruntime140.dll', 'libcef.dll'})

    def test_import_free_pe(self):
        self.assertEqual(audit.pe_imports(fixture_pe(), 'exe'), set())

    def test_reject_wrong_arch(self):
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'AMD64'):
            audit.pe_imports(fixture_pe(machine=0x14c), 'exe')

    def test_reject_dll_role_mismatch(self):
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'role mismatch'):
            audit.pe_imports(fixture_pe(dll=True), 'exe')
        self.assertEqual(audit.pe_imports(fixture_pe(dll=True), 'either'), set())

    def test_reject_unterminated_imports(self):
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'unterminated'):
            audit.pe_imports(fixture_pe(imports=('kernel32.dll',), terminate=False), 'exe')

    def test_reject_bad_import_rva(self):
        pe = bytearray(fixture_pe(imports=('kernel32.dll',)))
        struct.pack_into('<I', pe, 0x98+120, 0xF00000)
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'outside'):
            audit.pe_imports(bytes(pe), 'exe')

    def test_reject_import_path_traversal(self):
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'invalid imported'):
            audit.pe_imports(fixture_pe(imports=('../evil.dll',)), 'exe')

    def test_reject_truncated_headers(self):
        for data in (b'', b'MZ', b'MZ'+b'\0'*128, fixture_pe()[:160]):
            with self.subTest(length=len(data)):
                with self.assertRaises(audit.RuntimeAuditError):
                    audit.pe_imports(data, 'exe')

    def test_os_and_third_party_imports(self):
        self.assertTrue(audit.is_system_dll('kernel32.dll'))
        self.assertTrue(audit.is_system_dll('api-ms-win-core-file-l1-1-0.dll'))
        self.assertFalse(audit.is_system_dll('vcruntime140.dll'))
        self.assertFalse(audit.is_system_dll('libcef.dll'))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'runtime'
        self.root.mkdir()
        for name in audit.REQUIRED_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix == '.zip':
                with zipfile.ZipFile(path, 'w') as z:
                    entries = ui.REQUIRED_MAIN + ui.REQUIRED_LOADSCREEN if path.name == 'ui.zip' else ()
                    for entry in entries:
                        z.writestr(entry, b'asset')
            else:
                path.write_bytes(fixture_pe(dll=path.suffix == '.dll'))

    def test_complete_static_fixture(self):
        result = audit.audit(self.root)
        self.assertEqual(result['status'], 'static_inventory_pass', result)
        self.assertEqual(result['missing_required'], [])
        self.assertFalse(result['execution_verified'])
        self.assertFalse(result['gameplay_verified'])
        self.assertEqual(len(result['binaries']), 6)

    def test_missing_file_fails(self):
        (self.root / 'legitimacy.dll').unlink()
        result = audit.audit(self.root)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['missing_required'], ['legitimacy.dll'])

    def test_unbundled_import_fails(self):
        (self.root / 'FiveM.exe').write_bytes(fixture_pe(imports=('libcef.dll',)))
        result = audit.audit(self.root)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['unresolved_imports'][0]['dlls'], ['libcef.dll'])
        (self.root / 'libcef.dll').write_bytes(fixture_pe(dll=True))
        self.assertEqual(audit.audit(self.root)['status'], 'static_inventory_pass')

    def test_delay_import_fails_when_missing(self):
        (self.root / 'FiveM.exe').write_bytes(fixture_pe(delay_imports=('vcruntime140.dll',)))
        self.assertEqual(audit.audit(self.root)['unresolved_imports'][0]['dlls'], ['vcruntime140.dll'])

    def test_bad_pe_fails(self):
        (self.root / 'legitimacy.dll').write_bytes(b'fake DLL')
        self.assertEqual(audit.audit(self.root)['status'], 'incomplete')
        self.assertIn('missing PE MZ', audit.audit(self.root)['binary_errors'][0]['error'])

    def test_wrong_arch_fails(self):
        (self.root / 'FiveM.exe').write_bytes(fixture_pe(machine=0x14c))
        self.assertEqual(audit.audit(self.root)['status'], 'incomplete')

    def test_tampered_ui_archive_fails(self):
        with zipfile.ZipFile(self.root / 'citizen/ui.zip', 'w') as z:
            z.writestr('root.html', b'only root')
        result = audit.audit(self.root)
        self.assertEqual(result['status'], 'incomplete')
        self.assertIn('Missing required', result['ui_error'])

    def test_corrupt_ui_crc_reports_incomplete_without_crashing(self):
        archive = self.root / 'citizen/ui.zip'
        data = bytearray(archive.read_bytes())
        with zipfile.ZipFile(archive) as z:
            info = z.getinfo('app/app.js')
            data[info.header_offset + 30 + len(info.filename)] ^= 0xFF
        archive.write_bytes(data)
        result = audit.audit(self.root)
        self.assertEqual(result['status'], 'incomplete')
        self.assertIn('ui_error', result)

    def test_case_collision_fails(self):
        (self.root / 'fivem.EXE').write_bytes(fixture_pe())
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'collision'):
            audit.audit(self.root)

    def test_symlink_fails(self):
        try:
            (self.root / 'bad-link').symlink_to(self.root / 'FiveM.exe')
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'link'):
            audit.audit(self.root)

    def test_unrelated_nested_dll_is_not_dependency_closure(self):
        (self.root / 'FiveM.exe').write_bytes(fixture_pe(imports=('libcef.dll',)))
        hidden = self.root / 'unrelated' / 'libcef.dll'
        hidden.parent.mkdir()
        hidden.write_bytes(fixture_pe(dll=True))
        result = audit.audit(self.root)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['unresolved_imports'][0]['dlls'], ['libcef.dll'])

    def test_dependency_beside_importing_binary(self):
        extra = self.root / 'citizen' / 'plugins'
        extra.mkdir()
        (extra / 'plugin.dll').write_bytes(fixture_pe(dll=True, imports=('helper.dll',)))
        (extra / 'helper.dll').write_bytes(fixture_pe(dll=True))
        self.assertEqual(audit.audit(self.root)['status'], 'static_inventory_pass')

    def test_cfx_subprocess_bin_may_have_dll_characteristic(self):
        (self.root / 'CitizenFX_SubProcess_chrome.bin').write_bytes(fixture_pe(dll=True))
        self.assertEqual(audit.audit(self.root)['status'], 'static_inventory_pass')

    def test_file_manifest_contains_exact_payload_hashes(self):
        import hashlib
        report = audit.audit(self.root)
        self.assertEqual(report['status'], 'static_inventory_pass')
        self.assertEqual(report['file_manifest']['fivem.exe'], {
            'bytes': (self.root / 'FiveM.exe').stat().st_size,
            'sha256': hashlib.sha256((self.root / 'FiveM.exe').read_bytes()).hexdigest(),
        })
        self.assertEqual(report['file_manifest']['citizen/ui.zip']['sha256'],
                         hashlib.sha256((self.root / 'citizen/ui.zip').read_bytes()).hexdigest())

    def test_staging_integrity_accepts_identical_payloads_and_excludes_debug(self):
        (self.root / 'build.pdb').write_bytes(b'debug')
        (self.root / 'dbg').mkdir()
        (self.root / 'dbg' / 'symbols.dat').write_bytes(b'debug')
        baseline = audit.audit(self.root)
        (self.root / 'build.pdb').unlink()
        (self.root / 'dbg' / 'symbols.dat').unlink()
        (self.root / 'dbg').rmdir()
        staged = audit.audit(self.root, baseline)
        self.assertEqual(staged['status'], 'static_inventory_pass')
        self.assertEqual(staged['staging_integrity']['status'], 'pass')
        self.assertEqual(staged['staging_integrity']['excluded_build_files'], 2)

    def test_staging_integrity_rejects_changed_non_pe_bytes(self):
        (self.root / 'citizen' / 'assets.dat').write_bytes(b'good')
        baseline = audit.audit(self.root)
        (self.root / 'citizen' / 'assets.dat').write_bytes(b'evil')
        staged = audit.audit(self.root, baseline)
        self.assertEqual(staged['status'], 'incomplete')
        self.assertEqual(staged['staging_integrity']['altered'], ['citizen/assets.dat'])

    def test_staging_integrity_rejects_missing_or_injected_payloads(self):
        (self.root / 'citizen' / 'assets.dat').write_bytes(b'good')
        baseline = audit.audit(self.root)
        (self.root / 'citizen' / 'assets.dat').unlink()
        (self.root / 'injected.dat').write_bytes(b'extra')
        staged = audit.audit(self.root, baseline)
        self.assertEqual(staged['status'], 'incomplete')
        self.assertEqual(staged['staging_integrity']['missing'], ['citizen/assets.dat'])
        self.assertEqual(staged['staging_integrity']['unexpected'], ['injected.dat'])

    def test_staging_integrity_rejects_injected_debug_file(self):
        baseline = audit.audit(self.root)
        (self.root / 'new.pdb').write_bytes(b'not in original')
        staged = audit.audit(self.root, baseline)
        self.assertEqual(staged['status'], 'incomplete')
        self.assertEqual(staged['staging_integrity']['unexpected'], ['new.pdb'])

    def test_staging_integrity_rejects_invalid_or_unverified_baselines(self):
        baseline = audit.audit(self.root)
        for invalid in (
            {'audit': 'openv-windows-runtime-static-v1', 'status': 'incomplete',
             'file_manifest': baseline['file_manifest']},
            {'audit': 'openv-windows-runtime-manifest-v1', 'status': 'static_inventory_pass',
             'file_manifest': baseline['file_manifest']},
            {**baseline, 'file_manifest': {}},
            {**baseline, 'file_manifest': {'../evil': {'bytes': 1, 'sha256': '0'*64}}},
            {**baseline, 'file_manifest': {'file': {'bytes': 1, 'sha256': 'bad'}}},
            {**baseline, 'file_manifest': {'FILE': {'bytes': 1, 'sha256': '0'*64},
                                          'file': {'bytes': 1, 'sha256': '0'*64}}},
        ):
            with self.subTest(invalid=invalid.get('status', 'invalid')):
                with self.assertRaises(audit.RuntimeAuditError):
                    audit.audit(self.root, invalid)

    def test_staging_integrity_cli_failure_writes_diagnostics(self):
        baseline = audit.audit(self.root)
        (self.root / 'citizen' / 'assets.dat').write_bytes(b'changed after baseline')
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'baseline.json'
            output = Path(temp) / 'staged.json'
            source.write_text(json.dumps(baseline), encoding='utf-8')
            self.assertEqual(audit.main(['--runtime', str(self.root),
                                         '--baseline-report', str(source),
                                         '--report', str(output)]), 1)
            result = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(result['staging_integrity']['status'], 'mismatch')

    def test_manifest_malformed_entry_fails(self):
        with self.assertRaisesRegex(audit.RuntimeAuditError, 'invalid manifest'):
            audit.audit_manifest({'files': [{'path': 42}]})

    def test_manifest_missing_ui(self):
        report = audit.audit_manifest({'files': [{'path': 'FiveM.exe'}, {'path': 'legitimacy.dll'}]})
        self.assertEqual(report['status'], 'incomplete')
        self.assertIn('citizen/ui.zip', report['missing_required'])
        self.assertFalse(report['execution_verified'])

    def test_manifest_never_claims_runtime_pass(self):
        report = audit.audit_manifest({'files': [{'path': name} for name in audit.REQUIRED_FILES]})
        self.assertEqual(report['status'], 'manifest_only')
        self.assertFalse(report['gameplay_verified'])


if __name__ == '__main__':
    unittest.main()
