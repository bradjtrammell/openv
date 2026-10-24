"""Regression coverage for the OpenV source-only UI packaging contract."""
import importlib.util
import json
from unittest import mock
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
import zlib

MODULE_PATH = Path(__file__).resolve().parents[1] / 'tools' / 'build_openv_ui.py'
spec = importlib.util.spec_from_file_location('build_openv_ui', MODULE_PATH)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


class UIArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.loadscreen = self.root / 'dist'
        self.output = self.root / 'output'
        for name in ui.MAIN_FILES:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('OpenV test fixture ' + name, encoding='utf-8')
        for name in ('index.html', 'code.js', 'color-scheme.min.js', 'backdrop.jpg'):
            path = self.loadscreen / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('OpenV loadscreen ' + name).encode())

    def test_actual_first_party_sources_build_complete_archives(self):
        root = MODULE_PATH.parents[1]
        source = root / 'ext' / 'ui-build' / 'data'
        fallback = root / 'ext' / 'ui-build' / 'loadscreen-fallback'
        result = ui.build(source, self.output, fallback)
        self.assertTrue(result['loadscreen_included'])
        with zipfile.ZipFile(self.output / 'data.zip') as archive:
            self.assertTrue(set(ui.REQUIRED_MAIN + ui.REQUIRED_LOADSCREEN).issubset(archive.namelist()))
            self.assertIn(b'registerFrameFunction', archive.read('root.js'))
            self.assertIn(b'loadProgress', archive.read('loadscreen/code.js'))
        expected_main = {name for name in ui.MAIN_FILES if (source / name).is_file()}
        expected_loadscreen = {
            'loadscreen/' + path.relative_to(fallback).as_posix()
            for path in fallback.rglob('*') if path.is_file()
            and path.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}
        }
        with zipfile.ZipFile(self.output / 'data.zip') as archive:
            self.assertEqual(set(archive.namelist()), expected_main | expected_loadscreen)
        self.assertEqual(ui.verify_archive(self.output / 'data.zip',
                         ui.REQUIRED_MAIN + ui.REQUIRED_LOADSCREEN)['files'],
                         len(expected_main | expected_loadscreen))

    def test_build_has_required_ui_and_loadscreen(self):
        result = ui.build(self.source, self.output, self.loadscreen)
        self.assertEqual(len(result['archives']), 2)
        with zipfile.ZipFile(self.output / 'data.zip') as archive:
            self.assertTrue(set(ui.REQUIRED_MAIN + ui.REQUIRED_LOADSCREEN).issubset(archive.namelist()))
            self.assertNotIn('loadscreen/backdrop.jpg', archive.namelist())
        with zipfile.ZipFile(self.output / 'data_big.zip') as archive:
            self.assertEqual(archive.namelist(), ['loadscreen/backdrop.jpg'])
        runtime = self.root / 'runtime' / 'citizen'
        runtime.mkdir(parents=True)
        shutil.copyfile(self.output / 'data.zip', runtime / 'ui.zip')
        shutil.copyfile(self.output / 'data_big.zip', runtime / 'ui-big.zip')
        self.assertEqual(len(ui.verify_runtime(runtime.parent)['archives']), 2)

    def test_reproducible_zip_and_manifest(self):
        first = ui.build(self.source, self.output, self.loadscreen)
        second = ui.build(self.source, self.output, self.loadscreen)
        self.assertEqual(first, second)
        self.assertEqual(json.loads((self.output / 'openv-ui-manifest.json').read_text()), first)

    def test_publish_second_archive_failure_rolls_back_archives_and_manifest(self):
        ui.build(self.source, self.output, self.loadscreen)
        before = {name: (self.output / name).read_bytes()
                  for name in ('data.zip', 'data_big.zip', 'openv-ui-manifest.json')}
        (self.source / 'app' / 'app.js').write_text('updated OpenV client')
        actual_replace = ui.os.replace
        failed = False
        def fail_once(source, destination):
            nonlocal failed
            if Path(destination).name == 'data_big.zip' and not failed:
                failed = True
                raise OSError('simulated interrupted archive publication')
            return actual_replace(source, destination)
        with mock.patch.object(ui.os, 'replace', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'simulated interrupted'):
                ui.build(self.source, self.output, self.loadscreen)
        self.assertTrue(failed)
        for name, content in before.items():
            self.assertEqual((self.output / name).read_bytes(), content, name)
        self.assertFalse(list(self.output.glob('.openv-*')))

    def test_first_publish_failure_leaves_no_partial_runtime(self):
        actual_replace = ui.os.replace
        def fail_manifest(source, destination):
            if Path(destination).name == 'openv-ui-manifest.json':
                raise OSError('simulated manifest publication failure')
            return actual_replace(source, destination)
        with mock.patch.object(ui.os, 'replace', side_effect=fail_manifest):
            with self.assertRaisesRegex(OSError, 'simulated manifest'):
                ui.build(self.source, self.output, self.loadscreen)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_refuse_linked_output_directory(self):
        outside = self.root / 'outside'
        outside.mkdir()
        try:
            self.output.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(ui.UIError, 'linked output directory'):
            ui.build(self.source, self.output, self.loadscreen)
        self.assertEqual(list(outside.iterdir()), [])

    def test_refuse_to_overwrite_symlinked_output(self):
        self.output.mkdir()
        target = self.root / 'elsewhere.zip'
        target.write_bytes(b'do not overwrite')
        try:
            (self.output / 'data.zip').symlink_to(target)
        except OSError as exc:
            self.skipTest(str(exc))
        with self.assertRaisesRegex(ui.UIError, 'linked output'):
            ui.build(self.source, self.output, self.loadscreen)
        self.assertEqual(target.read_bytes(), b'do not overwrite')
        self.assertTrue((self.output / 'data.zip').is_symlink())

    def test_missing_required_main_fails_without_overwriting_existing(self):
        ui.build(self.source, self.output, self.loadscreen)
        previous = (self.output / 'data.zip').read_bytes()
        (self.source / 'app' / 'index.html').unlink()
        with self.assertRaises(ui.UIError):
            ui.build(self.source, self.output, self.loadscreen)
        self.assertEqual((self.output / 'data.zip').read_bytes(), previous)

    def test_missing_loadscreen_entry_fails(self):
        (self.loadscreen / 'code.js').unlink()
        with self.assertRaisesRegex(ui.UIError, 'Missing compiled loadscreen'):
            ui.build(self.source, self.output, self.loadscreen)

    def test_rejects_symlinked_main_file(self):
        target = self.source / 'app' / 'app.js'
        target.unlink()
        try:
            target.symlink_to(self.root / 'outside.js')
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable on this runner: {exc}')
        with self.assertRaisesRegex(ui.UIError, 'Symbolic link'):
            ui.build(self.source, self.output, self.loadscreen)

    def test_rejects_symlinked_loadscreen_file(self):
        target = self.loadscreen / 'code.js'
        target.unlink()
        try:
            target.symlink_to(self.root / 'outside.js')
        except OSError as exc:
            self.skipTest(f'Symlinks unavailable on this runner: {exc}')
        with self.assertRaisesRegex(ui.UIError, 'Symbolic link'):
            ui.build(self.source, self.output, self.loadscreen)

    def test_rejects_unexpected_executable(self):
        (self.loadscreen / 'payload.exe').write_bytes(b'MZ')
        with self.assertRaisesRegex(ui.UIError, 'Unsupported loadscreen'):
            ui.build(self.source, self.output, self.loadscreen)

    def test_rejects_case_insensitive_collisions(self):
        # A Windows filesystem aliases Index.html and index.html, so creating
        # both paths is not a portable collision test. Exercise the exact
        # archive validation boundary with two distinct logical entry names.
        with self.assertRaisesRegex(ui.UIError, 'Case-insensitive duplicate'):
            ui.validate_entries({'app/index.html': b'a', 'app/Index.html': b'b'}, {})

    def test_rejects_oversize_asset(self):
        with (self.loadscreen / 'huge.png').open('wb') as stream:
            stream.truncate(ui.MAX_FILE_BYTES + 1)
        with self.assertRaisesRegex(ui.UIError, 'too large'):
            ui.build(self.source, self.output, self.loadscreen)

    def test_rejects_zip_traversal(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as handle:
            handle.writestr('../escape.html', 'bad')
        with self.assertRaisesRegex(ui.UIError, 'Unsafe archive path'):
            ui.verify_archive(archive, ())

    def test_rejects_zip_case_collision(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as handle:
            handle.writestr('app/Index.html', 'a')
            handle.writestr('app/index.html', 'b')
        with self.assertRaisesRegex(ui.UIError, 'duplicate'):
            ui.verify_archive(archive, ())

    def test_rejects_zip_corruption(self):
        ui.build(self.source, self.output, self.loadscreen)
        archive = self.output / 'data.zip'
        data = bytearray(archive.read_bytes())
        data[len(data)//2] ^= 0xFF
        archive.write_bytes(data)
        with self.assertRaises((zipfile.BadZipFile, OSError, EOFError, zlib.error)):
            ui.verify_archive(archive, ui.REQUIRED_MAIN)

    def test_missing_runtime_bundle_fails(self):
        runtime = self.root / 'runtime'
        (runtime / 'citizen').mkdir(parents=True)
        with self.assertRaisesRegex(ui.UIError, 'Missing or oversized archive'):
            ui.verify_runtime(runtime)

    def test_extra_source_files_are_not_published(self):
        (self.source / 'secret.txt').write_text('not for packaging')
        ui.build(self.source, self.output, self.loadscreen)
        with zipfile.ZipFile(self.output / 'data.zip') as archive:
            self.assertNotIn('secret.txt', archive.namelist())


    def test_windows_batch_output_path_does_not_end_with_separator(self):
        # %~dp0 always ends in a backslash. In the Windows C runtime argument
        # parser, a trailing backslash inside double quotes escapes the quote,
        # handing Python a literal quotation mark in its output path.
        batch = (MODULE_PATH.parents[1] / 'ext' / 'ui-build' / 'build.cmd').read_text(encoding='utf-8')
        self.assertIn('--output "%ROOT%."', batch)
        self.assertNotIn('--output "%ROOT%"', batch)
        self.assertIn('if errorlevel 1 exit /b 1', batch)



if __name__ == '__main__':
    unittest.main()
