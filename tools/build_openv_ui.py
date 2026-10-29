#!/usr/bin/env python3
"""Build reproducible, first-party OpenV NUI archives without upstream binary downloads.

The main UI is authored in ext/ui-build/data/app. An optional, locally compiled
loadscreen is included when --loadscreen-dist is supplied. No network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tempfile
import zipfile

FIXED_DATE = (1980, 1, 1, 0, 0, 0)
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAIN_FILES = (
    'root.html', 'root.js', 'root.css', 'jquery.js', 'jquery.mustache.js', 'mustache.js',
    'app/index.html', 'app/connection.js', 'app/app.js', 'app/styles.css',
)
REQUIRED_MAIN = ('root.html', 'root.js', 'root.css', 'app/index.html', 'app/connection.js', 'app/app.js', 'app/styles.css')
REQUIRED_LOADSCREEN = ('loadscreen/index.html', 'loadscreen/code.js')
LOADSCREEN_EXTENSIONS = {'.html', '.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.svg', '.webp', '.woff', '.woff2'}


class UIError(ValueError):
    pass


def safe_path(path: str) -> str:
    if not path or '\\' in path or '\x00' in path or path.startswith('/') or ':' in path:
        raise UIError(f'Unsafe archive path: {path!r}')
    segments = PurePosixPath(path).parts
    if any(segment in ('.', '..') or segment.startswith('.') for segment in segments):
        raise UIError(f'Unsafe archive path: {path!r}')
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    if any(segment.split('.')[0].upper() in reserved or segment.endswith((' ', '.')) for segment in segments):
        raise UIError(f'Windows-reserved archive path: {path!r}')
    if PurePosixPath(path).as_posix() != path:
        raise UIError(f'Noncanonical archive path: {path!r}')
    return path


def checked_file(path: Path, root: Path) -> bytes:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise UIError(f'File outside source directory: {path}') from exc
    if path.is_symlink() or root.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent == root or root in parent.parents):
        raise UIError(f'Symbolic link rejected: {relative}')
    if not path.is_file() or not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise UIError(f'Not a regular file: {relative}')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise UIError(f'File too large: {relative}')
    content = path.read_bytes()
    if len(content) > MAX_FILE_BYTES:
        raise UIError(f'File too large after read: {relative}')
    return content


def collect(source: Path, loadscreen: Path | None) -> tuple[dict[str, bytes], dict[str, bytes]]:
    if not source.is_dir():
        raise UIError(f'Missing UI source: {source}')
    main: dict[str, bytes] = {}
    big: dict[str, bytes] = {}
    for name in MAIN_FILES:
        path = source / name
        if path.is_file() or path.is_symlink():
            main[safe_path(name)] = checked_file(path, source)
        elif name in REQUIRED_MAIN:
            raise UIError(f'Missing required UI file: {name}')
    if loadscreen is not None:
        if not loadscreen.is_dir() or loadscreen.is_symlink():
            raise UIError(f'Missing compiled loadscreen directory: {loadscreen}')
        for path in sorted(loadscreen.rglob('*')):
            if path.is_dir() and not path.is_symlink():
                continue
            relative = safe_path('loadscreen/' + path.relative_to(loadscreen).as_posix())
            if path.suffix.lower() not in LOADSCREEN_EXTENSIONS:
                raise UIError(f'Unsupported loadscreen asset: {relative}')
            content = checked_file(path, loadscreen)
            target = big if path.suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'} else main
            target[relative] = content
        for name in REQUIRED_LOADSCREEN:
            if name not in main:
                raise UIError(f'Missing compiled loadscreen file: {name}')
    validate_entries(main, big)
    return main, big


def validate_entries(main: dict[str, bytes], big: dict[str, bytes]) -> None:
    seen: set[str] = set()
    total = 0
    for path, content in list(main.items()) + list(big.items()):
        safe_path(path)
        key = path.casefold()
        if key in seen:
            raise UIError(f'Case-insensitive duplicate archive path: {path}')
        seen.add(key)
        total += len(content)
        if len(content) > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES:
            raise UIError('UI payload exceeds size limit')
    for name in REQUIRED_MAIN:
        if name not in main:
            raise UIError(f'Missing required UI entry: {name}')


def make_archive(entries: dict[str, bytes], path: Path) -> None:
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9, allowZip64=False) as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 << 16)
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def verify_archive(path: Path, required: tuple[str, ...]) -> dict[str, object]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise UIError(f'Missing or oversized archive: {path}')
    with zipfile.ZipFile(path, 'r') as archive:
        seen: set[str] = set()
        names: list[str] = []
        total = 0
        for info in archive.infolist():
            name = safe_path(info.filename)
            key = name.casefold()
            if key in seen or info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise UIError(f'Unsafe or duplicate archive member: {name}')
            if info.file_size > MAX_FILE_BYTES:
                raise UIError(f'Oversized archive member: {name}')
            total += info.file_size
            if total > MAX_ARCHIVE_BYTES:
                raise UIError('Archive decompressed size limit exceeded')
            seen.add(key)
            names.append(name)
            with archive.open(info) as stream:
                while stream.read(64 * 1024):
                    pass  # force CRC validation without loading large assets into memory
        for name in required:
            if name not in names:
                raise UIError(f'Missing required archive member: {name}')
    return {'path': str(path), 'files': len(names), 'uncompressed_bytes': total,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def publish_bundle(pending: list[tuple[Path, Path]]) -> None:
    """Replace the two UI archives and provenance as a rollback-safe set.

    A power failure between renames cannot make three filesystem entries
    atomic. For ordinary I/O failures, however, retain and restore all old
    entries so a failed second ZIP or manifest publish never mixes versions.
    """
    backups: list[tuple[Path, Path]] = []
    installed: list[Path] = []
    committed = False
    try:
        for _, final in pending:
            if final.is_symlink() or (hasattr(final, 'is_junction') and final.is_junction()):
                raise UIError(f'Refusing to overwrite linked output: {final}')
            if final.exists():
                fd, name = tempfile.mkstemp(prefix='.openv-backup-', dir=final.parent)
                os.close(fd)
                backup = Path(name)
                os.replace(final, backup)
                backups.append((backup, final))
        for temporary, final in pending:
            os.replace(temporary, final)
            installed.append(final)
        committed = True
    except BaseException:
        restore_errors: list[OSError] = []
        for final in installed:
            try:
                final.unlink(missing_ok=True)
            except OSError as exc:
                restore_errors.append(exc)
        for backup, final in reversed(backups):
            try:
                os.replace(backup, final)
            except OSError as exc:
                restore_errors.append(exc)
        if restore_errors:
            # Never delete unrecovered backups. An operator can restore them.
            raise UIError('UI publication rollback failed; retained .openv-backup-* files for recovery') from restore_errors[0]
        raise
    finally:
        if committed:
            for backup, _ in backups:
                backup.unlink(missing_ok=True)


def build(source: Path, output: Path, loadscreen: Path | None) -> dict[str, object]:
    main, big = collect(source, loadscreen)
    if output.is_symlink() or (hasattr(output, 'is_junction') and output.is_junction()):
        raise UIError(f'Refusing linked output directory: {output}')
    output.mkdir(parents=True, exist_ok=True)
    pending: list[tuple[Path, Path]] = []
    try:
        archives = []
        for name, entries, required in (
            ('data.zip', main, REQUIRED_MAIN + (REQUIRED_LOADSCREEN if loadscreen else ())),
            ('data_big.zip', big, ()),
        ):
            fd, temporary = tempfile.mkstemp(prefix='.openv-ui-', suffix='.zip', dir=output)
            os.close(fd)
            temp = Path(temporary)
            final = output / name
            pending.append((temp, final))
            make_archive(entries, temp)
            details = verify_archive(temp, required)
            details['path'] = str(final)
            archives.append(details)
        report = {
            'builder': 'openv-first-party-ui-v1',
            'loadscreen_included': loadscreen is not None,
            'archives': archives,
            'source_files': [{'path': path, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}
                             for path, content in sorted({**main, **big}.items())],
        }
        fd, name = tempfile.mkstemp(prefix='.openv-ui-', suffix='.json', dir=output)
        os.close(fd)
        temp = Path(name)
        pending.append((temp, output / 'openv-ui-manifest.json'))
        temp.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        publish_bundle(pending)
        return report
    finally:
        for temp, _ in pending:
            temp.unlink(missing_ok=True)


def verify_runtime(root: Path) -> dict[str, object]:
    citizen = root / 'citizen'
    return {'archives': [verify_archive(citizen / 'ui.zip', REQUIRED_MAIN + REQUIRED_LOADSCREEN),
                         verify_archive(citizen / 'ui-big.zip', ())]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--loadscreen-dist', type=Path)
    parser.add_argument('--verify-runtime', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.verify_runtime:
            result = verify_runtime(args.verify_runtime)
        else:
            if args.source is None or args.output is None:
                parser.error('--source and --output are required when building')
            result = build(args.source, args.output, args.loadscreen_dist)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (UIError, OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        print(f'OpenV UI build verification failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
