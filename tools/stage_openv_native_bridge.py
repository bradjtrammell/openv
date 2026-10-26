#!/usr/bin/env python3
"""Verify and stage the Windows OpenV authority bridge built from pinned source.

This stages only first-party OpenV code. It neither launches GTA V nor proves
ownership, engine integration, resource execution, or multiplayer gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

MAX_DLL_BYTES = 64 * 1024 * 1024
DLL_NAME = 'openv_world_bridge.dll'


class StageError(ValueError):
    pass


def regular(path: Path, *, directory: bool = False) -> None:
    """Reject symlinks and Windows reparse points at every existing path level."""
    for part in (path, *path.parents):
        try:
            meta = part.lstat()
        except FileNotFoundError as exc:
            raise StageError(f'missing staging path: {part}') from exc
        if stat.S_ISLNK(meta.st_mode) or (
            getattr(meta, 'st_file_attributes', 0) &
            getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
        ):
            raise StageError(f'reparse point not allowed: {part}')
    meta = path.stat()
    if directory and not stat.S_ISDIR(meta.st_mode):
        raise StageError(f'expected directory: {path}')
    if not directory and not stat.S_ISREG(meta.st_mode):
        raise StageError(f'expected regular file: {path}')


def verified_bytes(path: Path) -> bytes:
    regular(path)
    if path.stat().st_size < 512 or path.stat().st_size > MAX_DLL_BYTES:
        raise StageError('native bridge DLL has invalid size')
    data = path.read_bytes()
    if len(data) < 512 or len(data) > MAX_DLL_BYTES:
        raise StageError('native bridge DLL changed size during read')
    return data


def load_auditor(path: Path):
    regular(path)
    if path.name != 'windows_binary_audit.py':
        raise StageError('expected pinned server Windows binary auditor')
    spec = importlib.util.spec_from_file_location('openv_server_binary_audit', path)
    if spec is None or spec.loader is None:
        raise StageError('cannot load pinned server binary auditor')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for symbol in ('pe_validate', 'pe_exports', 'validate_dependencies', 'ABI_EXPORTS'):
        if not hasattr(module, symbol):
            raise StageError('pinned server auditor has incomplete contract')
    return module


def stage(source: Path, runtime: Path, auditor, source_commit: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise StageError('source commit must be a complete lowercase Git SHA')
    regular(runtime, directory=True)
    data = verified_bytes(source)
    try:
        auditor.pe_validate(data, is_dll=True)
        exports = set(auditor.pe_exports(data))
        if exports != set(auditor.ABI_EXPORTS):
            raise StageError('native DLL exports differ from pinned authority ABI')
        imports = sorted(auditor.validate_dependencies(data))
    except StageError:
        raise
    except Exception as exc:
        raise StageError(f'native bridge PE/ABI audit failed: {exc}') from exc

    destination = runtime / DLL_NAME
    digest = hashlib.sha256(data).hexdigest()
    if destination.exists() or destination.is_symlink():
        existing = verified_bytes(destination)
        if existing != data:
            raise StageError('existing native bridge differs; refusing overwrite')
        status = 'already_identical'
    else:
        # Stage within the target directory; never leave a partial DLL behind.
        descriptor, temporary = tempfile.mkstemp(prefix='.openv-native-', suffix='.tmp', dir=runtime)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            # Atomic no-replace publication: concurrent writers cannot replace
            # an already staged binary with different bytes.
            try:
                os.link(temporary, destination)
            except FileExistsError as exc:
                raise StageError('native bridge destination appeared during staging') from exc
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        if verified_bytes(destination) != data:
            raise StageError('staged native DLL bytes changed unexpectedly')
        status = 'staged'
    return {
        'status': status,
        'source_commit': source_commit,
        'destination': DLL_NAME,
        'sha256': digest,
        'bytes': len(data),
        'export_count': len(exports),
        'imports': imports,
        'engine_execution_verified': False,
        'gameplay_verified': False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--audit-module', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        auditor = load_auditor(args.audit_module)
        result = stage(args.source, args.runtime, auditor, args.source_commit)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except (OSError, StageError) as exc:
        print(f'OpenV native bridge staging rejected: {exc}', file=sys.stderr)
        return 2
    print(f"OpenV native bridge {result['status']}: {result['sha256']}; "
          f"{result['export_count']} audited exports; gameplay NOT_RUN")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
