#!/usr/bin/env python3
"""Stage the locally installed, Microsoft-signed VC++ x64 redistributable.

This tool does not download anything, accept arbitrary DLL names, copy Windows
System32 files, or assert a license to redistribute. The caller must have a
valid Visual Studio redistributable license before distributing its output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

from audit_openv_runtime import RuntimeAuditError, pe_imports

REQUIRED_DLLS = ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll', 'concrt140.dll')
MAX_DLL_SIZE = 64 * 1024 * 1024


class StagingError(ValueError):
    pass


def checked_regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or not stat.S_ISREG(path.stat(follow_symlinks=False).st_mode):
        raise StagingError(f'not a regular file: {path}')
    if path.stat(follow_symlinks=False).st_size > MAX_DLL_SIZE:
        raise StagingError(f'oversized redistributable: {path}')
    data = path.read_bytes()
    if len(data) > MAX_DLL_SIZE:
        raise StagingError(f'oversized redistributable: {path}')
    return data


def redist_directories(root: Path) -> list[Path]:
    """Find official VS2022 VC143 x64 CRT directories; never scan System32."""
    if root.is_symlink() or not root.is_dir():
        raise StagingError('Visual Studio VC/Redist/MSVC directory is unavailable')
    candidates = []
    for version in root.iterdir():
        if version.is_symlink() or not version.is_dir() or not re.fullmatch(r'\d+\.\d+\.\d+', version.name):
            continue
        directory = version / 'x64' / 'Microsoft.VC143.CRT'
        if directory.is_dir() and not directory.is_symlink() and not (directory.parent.is_symlink()):
            candidates.append((tuple(map(int, version.name.split('.'))), directory))
    return [directory for _, directory in sorted(candidates, reverse=True)]


def microsoft_organization(subject: str) -> bool:
    """Match the actual X.500 organization RDN, including quoted Windows forms.

    A CN, OU, or unrelated organization containing the words Microsoft
    Corporation must never satisfy the publisher identity requirement.
    """
    return bool(re.search(
        r'(?i)(?:^|,\s*)O\s*=\s*(?:"Microsoft Corporation"|Microsoft Corporation)(?=\s*,|$)',
        subject,
    ))


def verify_microsoft_signature(path: Path) -> dict:
    """Verify Windows Authenticode trust and the Microsoft publisher identity.

    PowerShell returns structured evidence so that an unavailable catalog,
    untrusted certificate, or unexpected publisher is distinguishable in CI.
    No status other than Valid is accepted.
    """
    if sys.platform != 'win32':
        raise StagingError('Authenticode verification requires Windows')
    script = (
        "$ErrorActionPreference='Stop'; "
        "$s=Get-AuthenticodeSignature -LiteralPath $env:OPENV_MSVC_DLL; "
        "[pscustomobject]@{"
        "status=[string]$s.Status; "
        "subject=$(if ($s.SignerCertificate) { [string]$s.SignerCertificate.Subject } else { '' }); "
        "signature_type=[string]$s.SignatureType; "
        "status_message=[string]$s.StatusMessage"
        "} | ConvertTo-Json -Compress -Depth 2"
    )
    env = dict(os.environ, OPENV_MSVC_DLL=str(path))
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
            env=env, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StagingError(f'Authenticode verification unavailable for {path.name}') from exc
    if result.returncode:
        raise StagingError(
            f'Authenticode verification command failed for {path.name}: exit {result.returncode}; ' 
            f'stderr={result.stderr[:500]!r}'
        )
    try:
        signature = json.loads(result.stdout)
        if not isinstance(signature, dict):
            raise ValueError('not an object')
        status = signature['status']
        subject = signature['subject']
        signature_type = signature['signature_type']
        if not all(isinstance(value, str) for value in (status, subject, signature_type)):
            raise ValueError('invalid field type')
    except (ValueError, KeyError, TypeError) as exc:
        raise StagingError(f'Authenticode returned invalid evidence for {path.name}') from exc
    if status != 'Valid':
        raise StagingError(
            f'Authenticode signature rejected: {path.name}; status={status!r}; '
            f'type={signature_type!r}; reason={str(signature.get("status_message", ""))[:200]!r}'
        )
    if not microsoft_organization(subject):
        raise StagingError(
            f'Authenticode signer organization rejected: {path.name}; '
            f'subject={subject[:250]!r}'
        )
    return {'status': status, 'signature_type': signature_type,
            'publisher': 'Microsoft Corporation'}


def stage(root: Path, runtime: Path, *, verifier=verify_microsoft_signature) -> dict:
    if runtime.is_symlink() or not runtime.is_dir():
        raise StagingError('runtime destination missing or linked')
    directories = redist_directories(root)
    if not directories:
        raise StagingError('no installed VC143 x64 redistributable directory found')
    selected = None
    source_bytes = {}
    for directory in directories:
        try:
            values = {name: checked_regular(directory / name) for name in REQUIRED_DLLS}
        except StagingError:
            continue  # select a complete single-version CRT, never mix versions
        selected, source_bytes = directory, values
        break
    if selected is None:
        raise StagingError('no complete VC143 x64 redistributable set found')
    signatures = {}
    for name, data in source_bytes.items():
        try:
            pe_imports(data, 'dll')
        except RuntimeAuditError as exc:
            raise StagingError(f'invalid AMD64 redistributable {name}: {exc}') from exc
        evidence = verifier(selected / name)
        if isinstance(evidence, dict):
            signatures[name] = evidence
        if checked_regular(selected / name) != data:
            raise StagingError(f'redistributable changed during signature verification: {name}')
    # Existing runtime files are never replaced, even if their bytes match:
    # the build might have placed a different signed CRT beside the launcher.
    for name in REQUIRED_DLLS:
        if (runtime / name).exists() or (runtime / name).is_symlink():
            raise StagingError(f'refusing to overwrite existing runtime file: {name}')
    pending = []
    installed = []
    try:
        for name in REQUIRED_DLLS:
            fd, temp = tempfile.mkstemp(prefix='.openv-crt-', dir=runtime)
            pending.append((Path(temp), runtime / name))
            with os.fdopen(fd, 'wb') as stream:
                stream.write(source_bytes[name])
                stream.flush()
                os.fsync(stream.fileno())
        for temp, target in pending:
            if target.exists() or target.is_symlink():
                raise StagingError(f'runtime file appeared during staging: {target.name}')
            # Atomic no-overwrite publish: os.replace() would clobber a DLL
            # created between the preflight check and this publication.
            os.link(temp, target)
            identity = target.stat(follow_symlinks=False)
            installed.append((target, identity.st_dev, identity.st_ino))
        for target, _, _ in installed:
            if checked_regular(target) != source_bytes[target.name]:
                raise StagingError(f'staged runtime changed during publication: {target.name}')
        return {'status': 'staged', 'origin': 'installed-visual-studio-vc143-x64-redist',
                'source_version': selected.parent.parent.name,
                'files': [{'name': name, 'bytes': len(source_bytes[name]),
                           'sha256': hashlib.sha256(source_bytes[name]).hexdigest()}
                          for name in REQUIRED_DLLS],
                'authenticode': 'verified', 'signature_evidence': signatures,
                'gameplay_verified': False,
                'license_note': 'Redistribution subject to installed Visual Studio license terms.'}
    except BaseException:
        # Never delete a file substituted by another process after our
        # publication. Roll back only inodes that this operation created.
        for target, device, inode in installed:
            try:
                current = target.stat(follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (device, inode):
                    target.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for temp, _ in pending:
            temp.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--redist-root', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = stage(args.redist_root, args.runtime)
    except (StagingError, OSError) as exc:
        result = {'status': 'failed', 'error': str(exc), 'gameplay_verified': False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'staged' else 1


if __name__ == '__main__':
    raise SystemExit(main())
