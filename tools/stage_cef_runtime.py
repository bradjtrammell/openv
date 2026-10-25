#!/usr/bin/env python3
"""Stage the exact, already-acquired CEF Windows x64 runtime from vendor/cef.

Does not fetch CEF, alter game entitlements, or assert permission to redistribute.
Source must contain its own license and the pinned build identifier must match
vendor/cef/cef_build_name.txt. Never silently substitute a different CEF ABI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from audit_openv_runtime import RuntimeAuditError, pe_imports

MAX_FILES = 512
MAX_TOTAL_BYTES = 2 * (1 << 30)
MAX_FILE_BYTES = 512 * (1 << 20)
# CEF 103+ changed its resource archive names; cef.pak/cef_100_percent.pak
# belong to older Chromium releases and must never substitute for these.
# Cfx's pinned CEF build may use the standard context snapshot or the
# non-context V8 snapshot. At least one real snapshot must be present.
# Never fabricate a missing snapshot or rename one format to the other.
REQUIRED = ('Release/libcef.dll', 'Release/chrome_elf.dll',
            'Resources/icudtl.dat', 'LICENSE.txt')
SNAPSHOT_VARIANTS = ('v8_context_snapshot.bin', 'snapshot_blob.bin')
REQUIRED_PAK = ('resources.pak', 'chrome_100_percent.pak',
                'chrome_200_percent.pak')
OPTIONAL_DLL = ('d3dcompiler_47.dll', 'libEGL.dll', 'libGLESv2.dll',
                'vk_swiftshader.dll', 'vulkan-1.dll', 'dxcompiler.dll',
                'dxil.dll')
OPTIONAL_RELEASE = ('vk_swiftshader_icd.json',)
OPTIONAL_RESOURCES = ('LICENSES.chromium.html',)
BUILD_NAME_RE = re.compile(r'cef_binary_[a-zA-Z0-9.+_-]+_windows64_minimal\Z')


class CEFStageError(ValueError):
    pass


def regular(path: Path, *, limit: int = MAX_FILE_BYTES) -> bytes:
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise CEFStageError(f'linked CEF source rejected: {path}')
    try:
        info = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise CEFStageError(f'CEF source missing: {path}') from exc
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise CEFStageError(f'invalid CEF source file: {path}')
    data = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    if len(data) != info.st_size or (info.st_dev, info.st_ino, info.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_mtime_ns):
        raise CEFStageError(f'CEF source changed during read: {path}')
    return data


def check_directory(path: Path) -> None:
    if not path.is_dir() or path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise CEFStageError(f'CEF directory missing or linked: {path}')


def discover(source: Path) -> tuple[str, dict[str, bytes]]:
    check_directory(source)
    build = regular(source / 'cef_build_name.txt', limit=256).decode('ascii').strip()
    if not BUILD_NAME_RE.fullmatch(build):
        raise CEFStageError('invalid or unpinned CEF build identifier')
    check_directory(source / 'Release')
    check_directory(source / 'Resources')
    result: dict[str, bytes] = {}
    for name in REQUIRED:
        result[name] = regular(source / name)
    # CEF builds can ship the context snapshot or the default V8 snapshot.
    # Preserve the actual filename and bytes; never substitute one for the
    # other. Some distributions place snapshots in Release, not Resources.
    snapshots = []
    for name in SNAPSHOT_VARIANTS:
        candidates = [source / directory / name for directory in ('Resources', 'Release')]
        present = [path for path in candidates if path.exists() or path.is_symlink()]
        if not present:
            continue
        data = regular(present[0])
        if any(regular(path) != data for path in present[1:]):
            raise CEFStageError(f'conflicting CEF V8 snapshot copies: {name}')
        result['Resources/' + name] = data
        snapshots.append(name)
    if not snapshots:
        raise CEFStageError('CEF V8 snapshot missing: expected v8_context_snapshot.bin or snapshot_blob.bin')
    # Require the modern CEF 103 pack set; old cef.pak cannot satisfy it.
    for name in REQUIRED_PAK:
        result['Resources/' + name] = regular(source / 'Resources' / name)
    for name in OPTIONAL_DLL:
        path = source / 'Release' / name
        if path.exists() or path.is_symlink():
            result['Release/' + name] = regular(path)
    # Some CEF builds include a Vulkan ICD manifest beside their binaries.
    # Preserve it as data, never execute it or silently fabricate one.
    for name in OPTIONAL_RELEASE:
        path = source / 'Release' / name
        if path.exists() or path.is_symlink():
            result['Release/' + name] = regular(path, limit=1 << 20)
    # Preserve every legitimate CEF .pak in this pinned distribution.
    for path in (source / 'Resources').glob('*.pak'):
        if not re.fullmatch(r'[a-zA-Z0-9_-]+\.pak', path.name):
            raise CEFStageError(f'unsafe CEF resource name: {path.name}')
        result['Resources/' + path.name] = regular(path)
    for name in OPTIONAL_RESOURCES:
        path = source / 'Resources' / name
        if path.exists() or path.is_symlink():
            result['Resources/' + name] = regular(path)
    third_party = source / 'LICENSES.chromium.html'
    if third_party.exists() or third_party.is_symlink():
        result['LICENSES.chromium.html'] = regular(third_party, limit=16 << 20)
    locales = source / 'Resources' / 'locales'
    check_directory(locales)
    entries = list(locales.iterdir())
    if not entries or len(entries) > 256:
        raise CEFStageError('CEF locales missing or excessive')
    for path in entries:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+\.pak', path.name):
            raise CEFStageError(f'unsafe CEF locale name: {path.name}')
        result['Resources/locales/' + path.name] = regular(path, limit=16 << 20)
    if 'Resources/locales/en-US.pak' not in result:
        raise CEFStageError('CEF en-US locale missing')
    if len(result) > MAX_FILES or sum(map(len, result.values())) > MAX_TOTAL_BYTES:
        raise CEFStageError('CEF file count or total byte limit exceeded')
    for name, data in result.items():
        if name.startswith('Release/') and name.lower().endswith('.dll'):
            try:
                pe_imports(data, 'dll')
            except RuntimeAuditError as exc:
                raise CEFStageError(f'CEF x64 PE validation failed for {name}: {exc}') from exc
    return build, result


def stage(source: Path, runtime: Path) -> dict:
    check_directory(runtime)
    build, sources = discover(source)
    # Match CEF's normal default layout, with resources and locales beside libcef.dll.
    destinations: dict[str, bytes] = {}
    for path, data in sources.items():
        if path.startswith('Release/'):
            name = path.removeprefix('Release/')
        elif path.startswith('Resources/'):
            name = path.removeprefix('Resources/')
        elif path == 'LICENSES.chromium.html':
            name = 'CEF-THIRD-PARTY-NOTICES.html'
        else:
            name = 'CEF-LICENSE.txt'
        if name.casefold() in {p.casefold() for p in destinations}:
            raise CEFStageError(f'CEF destination name collision: {name}')
        destinations[name] = data
    if not destinations.get('libcef.dll') or not destinations.get('icudtl.dat'):
        raise CEFStageError('CEF runtime incomplete')
    for relative in destinations:
        target = runtime / relative
        if target.exists() or target.is_symlink():
            raise CEFStageError(f'refusing to overwrite runtime file: {relative}')
    pending: list[tuple[Path, Path]] = []
    published: list[tuple[Path, int, int]] = []
    created_directories: list[Path] = []
    try:
        for relative in destinations:
            parent = (runtime / relative).parent
            if parent == runtime:
                continue
            if not parent.exists():
                parent.mkdir()
                created_directories.append(parent)
            check_directory(parent)
        for relative, data in destinations.items():
            target = runtime / relative
            fd, temporary = tempfile.mkstemp(prefix='.openv-cef-', dir=target.parent)
            temp = Path(temporary)
            pending.append((temp, target))
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        for temp, target in pending:
            if target.exists() or target.is_symlink():
                raise CEFStageError(f'CEF runtime target appeared: {target.name}')
            os.link(temp, target)  # atomic no-overwrite publication
            info = target.stat(follow_symlinks=False)
            published.append((target, info.st_dev, info.st_ino))
        for relative, data in destinations.items():
            if regular(runtime / relative) != data:
                raise CEFStageError(f'CEF staged bytes changed: {relative}')
        return {'status': 'staged', 'cef_build': build,
                'v8_snapshots': [name for name in SNAPSHOT_VARIANTS
                                 if 'Resources/' + name in sources],
                'origin': 'pinned-existing-vendor-cef', 'files': [
                    {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                    for name, data in sorted(destinations.items())],
                'license_file': 'CEF-LICENSE.txt', 'gameplay_verified': False,
                'redistribution_note': 'Review CEF/Chromium and third-party notices before distributing.'}
    except BaseException:
        for target, device, inode in reversed(published):
            try:
                info = target.stat(follow_symlinks=False)
                if (info.st_dev, info.st_ino) == (device, inode):
                    target.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for temp, _ in pending:
            temp.unlink(missing_ok=True)
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = stage(args.source, args.runtime)
    except (CEFStageError, OSError, UnicodeError, RuntimeAuditError) as exc:
        result = {'status': 'failed', 'error': str(exc), 'gameplay_verified': False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'staged' else 1


if __name__ == '__main__':
    raise SystemExit(main())
