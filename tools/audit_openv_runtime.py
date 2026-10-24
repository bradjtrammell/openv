#!/usr/bin/env python3
"""Offline Windows AMD64 OpenV runtime inventory and PE dependency audit.

This is a static gate, not evidence that GTA V launched, an entitlement was
validated, or that dynamically loaded game plugins are compatible. It never
executes candidate binaries or downloads missing proprietary dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import sys
import zipfile
import zlib
from typing import Iterable

from build_openv_ui import UIError, verify_runtime

# Cfx loads several components dynamically, so import closure alone is not a
# substitute for checking the known native runtime anchors.
REQUIRED_FILES = (
    'FiveM.exe',
    'legitimacy.dll',
    'CitizenFX_SubProcess_chrome.bin',
    'citizen-game-main.dll',
    'citizen-resources-core.dll',
    'citizen-resources-client.dll',
    'citizen/ui.zip',
    'citizen/ui-big.zip',
)
MAX_FILES = 20000
MAX_RUNTIME_BYTES = 12 * (1 << 30)
MAX_PE_BYTES = 512 * (1 << 20)
MAX_IMPORTS = 1024
MAX_IMPORT_NAME = 128
HASH_BLOCK_BYTES = 1024 * 1024
# Only build/debug intermediates are intentionally removed from the lean
# runtime. Everything else must survive staging byte-for-byte.
EXCLUDED_STAGING_EXTENSIONS = frozenset({'.pdb', '.exp', '.lib', '.ilk', '.ipch', '.iobj', '.ipdb'})

# These names are OS-provided on supported Windows 10/11 builds. API-set
# contracts are resolved by the OS. This is intentionally not an allowlist of
# third-party runtimes (e.g. vcruntime140.dll or libcef.dll).
WINDOWS_DLLS = frozenset('''
advapi32.dll apphelp.dll authz.dll bcrypt.dll bcryptprimitives.dll cabinet.dll
cfgmgr32.dll clbcatq.dll comctl32.dll comdlg32.dll combase.dll crypt32.dll
cryptbase.dll cryptnet.dll cryptui.dll d2d1.dll d3d10.dll d3d11.dll
d3d12.dll d3d9.dll d3dcompiler_47.dll dbghelp.dll dnsapi.dll dsound.dll
dwmapi.dll dxgi.dll dxva2.dll fwpuclnt.dll gdi32.dll gdiplus.dll hid.dll
imm32.dll iphlpapi.dll kernel32.dll kernelbase.dll mpr.dll msacm32.dll
msvcrt.dll ncrypt.dll netapi32.dll normaliz.dll ntdll.dll ole32.dll
oleacc.dll oleaut32.dll opengl32.dll powrprof.dll propsys.dll psapi.dll
rasapi32.dll rpcrt4.dll secur32.dll setupapi.dll shell32.dll shcore.dll
shlwapi.dll user32.dll userenv.dll uxtheme.dll version.dll winhttp.dll
wininet.dll winmm.dll winspool.drv wintrust.dll wlanapi.dll ws2_32.dll
wtsapi32.dll ucrtbase.dll xmllite.dll
'''.split())

class RuntimeAuditError(ValueError):
    pass


def read_u16(data: bytes, off: int) -> int:
    if off < 0 or off + 2 > len(data):
        raise RuntimeAuditError('truncated PE field')
    return struct.unpack_from('<H', data, off)[0]


def read_u32(data: bytes, off: int) -> int:
    if off < 0 or off + 4 > len(data):
        raise RuntimeAuditError('truncated PE field')
    return struct.unpack_from('<I', data, off)[0]


def pe_imports(data: bytes, role: str) -> set[str]:
    """Parse PE32+ headers and both normal and delay-load import directories.

    All RVAs are constrained to file-backed sections; malformed and
    unterminated descriptor tables fail rather than silently underreporting.
    """
    if len(data) < 0x100 or data[:2] != b'MZ':
        raise RuntimeAuditError('missing PE MZ signature')
    pe = read_u32(data, 0x3c)
    if pe < 0x40 or pe + 24 > len(data) or data[pe:pe+4] != b'PE\0\0':
        raise RuntimeAuditError('invalid PE header offset or signature')
    if read_u16(data, pe+4) != 0x8664:
        raise RuntimeAuditError('binary is not Windows AMD64')
    count = read_u16(data, pe+6)
    opt_size = read_u16(data, pe+20)
    flags = read_u16(data, pe+22)
    opt = pe + 24
    if not 1 <= count <= 96 or opt_size < 112 or opt+opt_size+count*40 > len(data):
        raise RuntimeAuditError('invalid PE section or optional header')
    if read_u16(data, opt) != 0x20b or not (flags & 0x0002):
        raise RuntimeAuditError('binary is not an executable PE32+ image')
    if role != 'either' and bool(flags & 0x2000) != (role == 'dll'):
        raise RuntimeAuditError('PE DLL/executable role mismatch')
    directory_count = read_u32(data, opt+108)
    if directory_count > 16 or opt_size < 112+min(directory_count, 16)*8:
        raise RuntimeAuditError('invalid PE data-directory bounds')
    sections = []
    for i in range(count):
        pos = opt+opt_size+i*40
        virtual_size, rva, raw_size, file_pos = struct.unpack_from('<IIII', data, pos+8)
        if raw_size and (file_pos > len(data) or raw_size > len(data)-file_pos):
            raise RuntimeAuditError('PE section extends beyond file')
        sections.append((rva, max(virtual_size, raw_size), raw_size, file_pos))

    def locate(rva: int, size: int) -> int:
        if rva == 0 or size <= 0:
            raise RuntimeAuditError('invalid import RVA')
        for base, span, raw, file_pos in sections:
            delta = rva-base
            if 0 <= delta < span and size <= raw-delta and file_pos+delta+size <= len(data):
                return file_pos+delta
        raise RuntimeAuditError('PE import RVA outside file-backed sections')

    def dll_name(rva: int) -> str:
        pos = locate(rva, 1)
        end = data.find(b'\0', pos, min(len(data), pos+MAX_IMPORT_NAME+1))
        if end < 0 or end == pos:
            raise RuntimeAuditError('unterminated or empty imported DLL name')
        try:
            name = data[pos:end].decode('ascii').lower()
        except UnicodeDecodeError as exc:
            raise RuntimeAuditError('non-ASCII imported DLL name') from exc
        if not re.fullmatch(r'[a-z0-9_.-]+\.(?:dll|drv)', name):
            raise RuntimeAuditError('invalid imported DLL name')
        return name

    result: set[str] = set()
    def parse_table(index: int, entry_size: int, name_field: int) -> None:
        if directory_count <= index:
            return
        table_rva = read_u32(data, opt+112+index*8)
        table_size = read_u32(data, opt+116+index*8)
        if table_rva == 0 and table_size == 0:
            return
        if not table_rva or table_size < entry_size or table_size > MAX_IMPORTS*entry_size:
            raise RuntimeAuditError('invalid PE import directory')
        # A zero descriptor is required within the declared directory.
        for i in range(table_size//entry_size):
            off = locate(table_rva+i*entry_size, entry_size)
            descriptor = data[off:off+entry_size]
            if descriptor == bytes(entry_size):
                return
            if index == 13:  # IMAGE_DELAYLOAD_DESCRIPTOR, 32 bytes
                attrs = read_u32(data, off)
                if attrs != 1:  # modern RVA format only; old VA pointers are unsafe to guess
                    raise RuntimeAuditError('unsupported delay-import address format')
            result.add(dll_name(read_u32(data, off+name_field)))
        raise RuntimeAuditError('unterminated PE import descriptor table')

    parse_table(1, 20, 12)
    parse_table(13, 32, 4)
    return result


def is_system_dll(name: str) -> bool:
    return name in WINDOWS_DLLS or name.startswith(('api-ms-win-', 'ext-ms-win-'))


def sha256_file(path: Path) -> str:
    """Hash with bounded memory and reject concurrent file-size changes."""
    before = path.stat(follow_symlinks=False)
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(HASH_BLOCK_BYTES):
            digest.update(chunk)
    after = path.stat(follow_symlinks=False)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
        raise RuntimeAuditError(f'runtime file changed while hashing: {path}')
    return digest.hexdigest()


def staging_excluded(path: str) -> bool:
    return path.casefold().startswith('dbg/') or Path(path).suffix.casefold() in EXCLUDED_STAGING_EXTENSIONS


def compare_staging(baseline: dict, staged: dict[str, dict]) -> dict:
    """Prove a lean runtime contains exactly the original runtime payloads.

    The baseline must be a completed full-runtime audit, not an unverified
    manifest or a user-supplied list of filenames. A stage may only omit
    debug/build intermediates, and may never add or alter any runtime bytes.
    """
    if not isinstance(baseline, dict) or baseline.get('audit') != 'openv-windows-runtime-static-v1' or baseline.get('status') != 'static_inventory_pass':
        raise RuntimeAuditError('staging baseline must be a successful full-runtime static audit')
    manifest = baseline.get('file_manifest')
    if not isinstance(manifest, dict) or not manifest:
        raise RuntimeAuditError('staging baseline missing hashed file manifest')
    canonical: dict[str, dict] = {}
    for name, entry in manifest.items():
        if not isinstance(name, str) or not name or '\\' in name or name.startswith('/') or any(part in ('', '.', '..') for part in name.split('/')):
            raise RuntimeAuditError('staging baseline has invalid file path')
        key = name.casefold()
        if key in canonical or not isinstance(entry, dict) or not isinstance(entry.get('bytes'), int) or isinstance(entry['bytes'], bool) or entry['bytes'] < 0 or not isinstance(entry.get('sha256'), str) or not re.fullmatch('[a-f0-9]{64}', entry['sha256']):
            raise RuntimeAuditError('staging baseline has invalid or duplicate file metadata')
        canonical[key] = entry
    expected = {key: value for key, value in canonical.items() if not staging_excluded(key)}
    missing = sorted(set(expected) - set(staged))
    unexpected = sorted(set(staged) - set(expected))
    altered = sorted(key for key in set(expected) & set(staged) if expected[key] != staged[key])
    return {'status': 'pass' if not (missing or unexpected or altered) else 'mismatch',
            'expected_files': len(expected), 'staged_files': len(staged),
            'excluded_build_files': len(canonical)-len(expected),
            'missing': missing, 'unexpected': unexpected, 'altered': altered}


def audit(root: Path, baseline: dict | None = None) -> dict:
    if not root.is_dir() or root.is_symlink() or (hasattr(root, 'is_junction') and root.is_junction()):
        raise RuntimeAuditError('runtime root missing or a symbolic link')
    files: dict[str, Path] = {}
    total = 0
    manifest: dict[str, dict] = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise RuntimeAuditError(f'link/reparse-point candidate rejected: {path.relative_to(root)}')
        if path.is_dir():
            continue
        if not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
            raise RuntimeAuditError(f'non-regular runtime entry: {path.relative_to(root)}')
        relative = path.relative_to(root).as_posix()
        key = relative.casefold()
        if key in files:
            raise RuntimeAuditError(f'Windows case-insensitive file collision: {relative}')
        files[key] = path
        size = path.stat(follow_symlinks=False).st_size
        total += size
        if len(files) > MAX_FILES or total > MAX_RUNTIME_BYTES:
            raise RuntimeAuditError('runtime file count or byte budget exceeded')
        manifest[key] = {'bytes': size, 'sha256': sha256_file(path)}
    missing = [name for name in REQUIRED_FILES if name.casefold() not in files]
    report: dict = {'audit': 'openv-windows-runtime-static-v1',
                    'status': 'incomplete', 'files': len(files), 'total_bytes': total,
                    'missing_required': missing, 'binaries': [], 'unresolved_imports': [],
                    'ui': None, 'file_manifest': manifest, 'execution_verified': False, 'gameplay_verified': False}
    if not missing:
        try:
            report['ui'] = verify_runtime(root)
            for archive in report['ui']['archives']:
                archive_path = Path(archive['path'])
                archive_key = archive_path.relative_to(root).as_posix().casefold()
                if archive['sha256'] != manifest[archive_key]['sha256']:
                    raise RuntimeAuditError('UI archive changed between inventory and verification')
        except (UIError, OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, EOFError) as exc:
            report['ui_error'] = str(exc)
    # Parse every PE-looking runtime image, not just a single launcher, so
    # an accidentally bundled x86 or broken plugin cannot silently ship.
    for key, path in sorted(files.items()):
        if not (key.endswith(('.exe', '.dll')) or (key.endswith('.bin') and path.name.lower().startswith('citizenfx_subprocess_'))):
            continue
        if path.stat().st_size > MAX_PE_BYTES:
            report.setdefault('binary_errors', []).append({'path': path.relative_to(root).as_posix(), 'error': 'PE image too large'})
            continue
        role = 'dll' if key.endswith('.dll') else 'either' if key.endswith('.bin') else 'exe'
        try:
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != manifest[key]['sha256']:
                raise RuntimeAuditError('PE image changed between inventory and verification')
            imports = pe_imports(data, role)
        except RuntimeAuditError as exc:
            report.setdefault('binary_errors', []).append({'path': path.relative_to(root).as_posix(), 'error': str(exc)})
            continue
        unresolved = sorted(name for name in imports if not is_system_dll(name) and
                            (path.parent / name).relative_to(root).as_posix().casefold() not in files and
                            name.casefold() not in files)
        report['binaries'].append({'path': path.relative_to(root).as_posix(),
                                   'sha256': hashlib.sha256(data).hexdigest(), 'imports': sorted(imports)})
        if unresolved:
            report['unresolved_imports'].append({'path': path.relative_to(root).as_posix(), 'dlls': unresolved})
    if baseline is not None:
        report['staging_integrity'] = compare_staging(baseline, manifest)
    if (not missing and report['ui'] and not report.get('binary_errors') and
            not report['unresolved_imports'] and
            (baseline is None or report['staging_integrity']['status'] == 'pass')):
        report['status'] = 'static_inventory_pass'
    return report


def audit_manifest(manifest: dict) -> dict:
    """Evaluate a historical inventory without pretending its bytes were audited."""
    files = manifest.get('files')
    if not isinstance(files, list):
        raise RuntimeAuditError('manifest has no files array')
    names = set()
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get('path'), str):
            raise RuntimeAuditError('invalid manifest file entry')
        names.add(entry['path'].replace('\\', '/').casefold())
    missing = [name for name in REQUIRED_FILES if name.casefold() not in names]
    return {'audit': 'openv-windows-runtime-manifest-v1', 'status': 'incomplete' if missing else 'manifest_only',
            'missing_required': missing, 'files': len(names), 'execution_verified': False,
            'gameplay_verified': False, 'note': 'Manifest names only; binary bytes and UI archive contents were not verified.'}


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--runtime', type=Path)
    group.add_argument('--manifest', type=Path)
    parser.add_argument('--report', type=Path, help='Write full machine-readable audit even when incomplete')
    parser.add_argument('--baseline-report', type=Path, help='For staged runtime, require exact SHA-256 agreement with an earlier successful full-runtime audit')
    if '--baseline-report' in (argv if argv is not None else sys.argv[1:]) and '--manifest' in (argv if argv is not None else sys.argv[1:]):
        parser.error('--baseline-report requires --runtime')
    args = parser.parse_args(argv)
    try:
        if args.baseline_report and not args.runtime:
            raise RuntimeAuditError('--baseline-report requires --runtime')
        baseline = json.loads(args.baseline_report.read_text(encoding='utf-8-sig')) if args.baseline_report else None
        result = audit(args.runtime, baseline) if args.runtime else audit_manifest(json.loads(args.manifest.read_text(encoding='utf-8-sig')))
    except (RuntimeAuditError, OSError, ValueError, json.JSONDecodeError) as exc:
        result = {'audit': 'openv-windows-runtime-static-v1', 'status': 'audit_error', 'error': str(exc),
                  'execution_verified': False, 'gameplay_verified': False}
    output = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output, encoding='utf-8')
    print(output, end='')
    return 0 if result['status'] == 'static_inventory_pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
