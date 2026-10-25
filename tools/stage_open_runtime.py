#!/usr/bin/env python3
"""Transactionally stage owner-supplied, hash-pinned AMD64 Mono/FFmpeg DLLs.

No downloads, Steam/game files, license bypass or redistribution are performed.
A manifest attests input hashes; it does not prove origin or license compliance.
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
from urllib.parse import urlsplit
from audit_openv_runtime import pe_imports, RuntimeAuditError

ABI = {"mono": ("mono-2.0-sgen.dll",),
       "ffmpeg": ("avutil-56.dll", "swresample-3.dll")}
LICENSES = {"mono": "OPENV-MONO-LICENSE.txt",
            "ffmpeg": "OPENV-FFMPEG-LICENSE.txt"}
ALLOWED_LICENSES = {"mono": {"MIT", "LGPL-2.0-only", "LGPL-2.1-only"},
                    "ffmpeg": {"LGPL-2.1-only", "LGPL-2.1-or-later",
                               "GPL-2.0-only", "GPL-2.0-or-later",
                               "GPL-3.0-only", "GPL-3.0-or-later"}}
HASH = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9_.-]{1,100}\Z")


class StageError(ValueError):
    pass


def directory(path):
    if not path.is_dir() or path.is_symlink() or (
        hasattr(path, "is_junction") and path.is_junction()
    ):
        raise StageError("missing or linked directory: " + str(path))


def read(path, limit):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise StageError("linked input: " + str(path))
    try:
        before = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise StageError("missing input: " + str(path)) from exc
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
        raise StageError("invalid input size/type: " + str(path))
    data = path.read_bytes()
    after = path.stat(follow_symlinks=False)
    if len(data) != before.st_size or (
        before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise StageError("input changed during read: " + str(path))
    return data


def checked_hash(data, expected, name):
    if not isinstance(expected, str) or not HASH.fullmatch(expected):
        raise StageError("invalid SHA-256: " + name)
    if hashlib.sha256(data).hexdigest() != expected:
        raise StageError("SHA-256 mismatch: " + name)


def collect(manifest, manifest_dir):
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "packages"} or type(manifest["schema"]) is not int or manifest["schema"] != 1:
        raise StageError("invalid manifest schema")
    packages = manifest["packages"]
    if not isinstance(packages, dict) or set(packages) != set(ABI):
        raise StageError("both Mono and FFmpeg required")
    payload, evidence = {}, []
    for package, names in ABI.items():
        spec = packages[package]
        if not isinstance(spec, dict) or set(spec) != {"directory", "upstream_url", "license_file", "license_spdx", "license_sha256", "files"}:
            raise StageError("invalid provenance: " + package)
        folder = spec["directory"]
        if not isinstance(folder, str) or not folder or "\0" in folder:
            raise StageError("invalid source directory")
        root = Path(folder)
        if not root.is_absolute():
            root = manifest_dir / root
        directory(root)
        url = spec["upstream_url"]
        if not isinstance(url, str) or len(url) > 2048:
            raise StageError("invalid upstream URL")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise StageError("HTTPS upstream provenance required")
        if spec["license_spdx"] not in ALLOWED_LICENSES[package]:
            raise StageError("unsupported declared license: " + package)
        license_file = spec["license_file"]
        if not isinstance(license_file, str) or not NAME.fullmatch(license_file) or license_file in (".", ".."):
            raise StageError("unsafe license filename")
        hashes = spec["files"]
        if not isinstance(hashes, dict) or set(hashes) != set(names):
            raise StageError("DLL list differs from required ABI")
        license_bytes = read(root / license_file, 2 << 20)
        checked_hash(license_bytes, spec["license_sha256"], license_file)
        if b"\0" in license_bytes or len(license_bytes.strip()) < 32:
            raise StageError("invalid license text")
        payload[LICENSES[package]] = license_bytes
        for name in names:
            data = read(root / name, 256 << 20)
            checked_hash(data, hashes[name], name)
            try:
                pe_imports(data, "dll")
            except RuntimeAuditError as exc:
                raise StageError("invalid AMD64 DLL " + name + ": " + str(exc)) from exc
            payload[name] = data
        evidence.append({"package": package, "upstream_url": url,
                         "declared_license": spec["license_spdx"],
                         "manifest_self_attested": True})
    return payload, evidence


def stage(manifest_path: Path, runtime: Path):
    directory(runtime)
    manifest = json.loads(read(manifest_path, 64 << 10))
    payload, evidence = collect(manifest, manifest_path.parent)
    for name in payload:
        if (runtime / name).exists() or (runtime / name).is_symlink():
            raise StageError("refusing to overwrite " + name)
    temporary, installed = [], []
    try:
        for name, data in payload.items():
            fd, filename = tempfile.mkstemp(prefix=".openv-runtime-", dir=runtime)
            temp = Path(filename)
            temporary.append((temp, runtime / name))
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        for temp, target in temporary:
            if target.exists() or target.is_symlink():
                raise StageError("destination appeared: " + target.name)
            os.link(temp, target)
            info = target.stat(follow_symlinks=False)
            installed.append((target, info.st_dev, info.st_ino))
        for name, data in payload.items():
            if read(runtime / name, 256 << 20) != data:
                raise StageError("published bytes changed: " + name)
        return {"status": "staged", "packages": evidence,
                "files": [{"path": name, "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(payload.items())],
                "license_review_required": True, "gameplay_verified": False}
    except BaseException:
        for target, device, inode in reversed(installed):
            try:
                info = target.stat(follow_symlinks=False)
                if (info.st_dev, info.st_ino) == (device, inode):
                    target.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for temp, _ in temporary:
            temp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = stage(args.manifest, args.runtime)
    except (StageError, OSError, ValueError, TypeError) as exc:
        result = {"status": "failed", "error": str(exc), "gameplay_verified": False}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "staged" else 1


if __name__ == "__main__":
    raise SystemExit(main())
