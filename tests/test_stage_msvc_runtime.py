"""Offline VC143 staging tests: no proprietary runtime bytes required."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import json
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import stage_msvc_runtime as staging
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

    def test_rejects_mutation_between_read_and_signature_verification(self):
        def mutate(path):
            if path.name == REQUIRED_DLLS[0]:
                path.write_bytes(fixture_pe(dll=True) + b'mutated')
        with self.assertRaisesRegex(StagingError, 'changed during signature'):
            stage(self.root, self.runtime, verifier=mutate)
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

    def test_microsoft_organization_accepts_quoted_and_plain_rdn(self):
        self.assertTrue(staging.microsoft_organization(
            'CN=Microsoft Corporation, O=Microsoft Corporation, L=Redmond, C=US'))
        self.assertTrue(staging.microsoft_organization(
            'CN=Microsoft Corporation, O="Microsoft Corporation", C=US'))
        self.assertFalse(staging.microsoft_organization(
            'CN=Microsoft Corporation, O=Impostor LLC, C=US'))
        self.assertFalse(staging.microsoft_organization(
            'OU=Microsoft Corporation, O=Impostor LLC, C=US'))
        self.assertFalse(staging.microsoft_organization(
            'CN=Microsoft Corporation, O=Microsoft Corporation Spoofed, C=US'))

    def test_authenticode_structured_evidence_and_fail_closed_status(self):
        subject = 'CN=Microsoft Corporation, O="Microsoft Corporation", C=US'
        def result(status='Valid', signer=subject, code=0):
            payload = {'status': status, 'subject': signer, 'signature_type': 'Authenticode',
                       'status_message': 'Certificate trust could not be verified'}
            return subprocess.CompletedProcess([], code, stdout=json.dumps(payload), stderr='')
        with mock.patch.object(staging.sys, 'platform', 'win32'):
            with mock.patch.object(staging.subprocess, 'run', return_value=result()) as run:
                evidence = staging.verify_microsoft_signature(self.crt / REQUIRED_DLLS[0])
                self.assertEqual(evidence['publisher'], 'Microsoft Corporation')
                self.assertEqual(evidence['status'], 'Valid')
                self.assertEqual(run.call_args.kwargs['env']['OPENV_MSVC_DLL'],
                                 str(self.crt / REQUIRED_DLLS[0]))
            with mock.patch.object(staging.subprocess, 'run', return_value=result('NotSigned')):
                with self.assertRaisesRegex(StagingError, 'status='):
                    staging.verify_microsoft_signature(self.crt / REQUIRED_DLLS[0])
            with mock.patch.object(staging.subprocess, 'run', return_value=result(signer='O=Fake Corp')):
                with self.assertRaisesRegex(StagingError, 'organization rejected'):
                    staging.verify_microsoft_signature(self.crt / REQUIRED_DLLS[0])
            with mock.patch.object(staging.subprocess, 'run', return_value=result(code=1)):
                with self.assertRaisesRegex(StagingError, 'command failed'):
                    staging.verify_microsoft_signature(self.crt / REQUIRED_DLLS[0])
            with mock.patch.object(staging.subprocess, 'run',
                                   return_value=subprocess.CompletedProcess([], 0, stdout='oops', stderr='')):
                with self.assertRaisesRegex(StagingError, 'invalid evidence'):
                    staging.verify_microsoft_signature(self.crt / REQUIRED_DLLS[0])

    def test_rollback_on_second_publication_failure(self):
        original = staging.os.link
        count = 0
        def link(src, dest):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('simulated publication failure')
            return original(src, dest)
        with mock.patch.object(staging.os, 'link', side_effect=link):
            with self.assertRaisesRegex(OSError, 'publication failure'):
                stage(self.root, self.runtime, verifier=self.verifier)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_post_publish_mutation_rolls_back_owned_files(self):
        original = staging.os.link
        def link(src, dest):
            original(src, dest)
            if Path(dest).name == REQUIRED_DLLS[-1]:
                Path(dest).write_bytes(b'changed')
        with mock.patch.object(staging.os, 'link', side_effect=link):
            with self.assertRaisesRegex(StagingError, 'changed during publication'):
                stage(self.root, self.runtime, verifier=self.verifier)
        self.assertEqual(list(self.runtime.iterdir()), [])

    def test_default_verifier_requires_windows(self):
        if sys.platform == 'win32':
            self.skipTest('Windows verifies actual Authenticode on official redistributables')
        with self.assertRaisesRegex(StagingError, 'requires Windows'):
            stage(self.root, self.runtime)


if __name__ == '__main__':
    unittest.main()
