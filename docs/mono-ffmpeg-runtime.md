# Owner-supplied Mono and FFmpeg Windows runtime

OpenV's Windows client currently imports Mono SGen `mono-2.0-sgen.dll`
and FFmpeg ABI `avutil-56.dll` and `swresample-3.dll`.
The repository has import libraries, **not** redistributable runtime DLLs.
Never rename a newer ABI, copy DLLs from another game, or bypass the audit.

`tools/stage_open_runtime.py` stages **existing, legitimately obtained**
Windows AMD64 binaries from a JSON provenance manifest. It downloads nothing.
The manifest must contain both packages, exactly the ABI filenames above,
each package's local `directory`, `upstream_url` (HTTPS), `license_file`
(single basename), `license_spdx`, `license_sha256`, and `files` mapping
each required DLL to its actual lowercase 64-character SHA-256. Top-level
`schema` must be `1`. Accepted license declarations are MIT or LGPL-2.x
for Mono and LGPL-2.1/GPL-2/GPL-3 variants for FFmpeg. The actual license
must be supplied and reviewed; the manifest's assertions are not a trusted
signature or proof of distribution rights.

Invoke after building, before the static runtime audit:

```powershell
python tools/stage_open_runtime.py --manifest C:\local\openv-dependencies.json --runtime code/bin/five/release --report build-report/open-runtime-provenance.json
python tools/audit_openv_runtime.py --runtime code/bin/five/release --report build-report/runtime-static-audit.json
```

The experimental Windows workflow optionally reads a runner-local manifest
path from the repository variable `OPENV_RUNTIME_DEPENDENCIES_MANIFEST`.
Without the source files it reports `not_configured` and the ordinary
runtime audit continues to fail closed. It does not fetch, commit, or
redistribute any third-party binary. Review FFmpeg LGPL/GPL build flags,
corresponding source and license obligations before distribution. Steamworks,
game entitlements, CEF and actual GTA V launch are separate requirements.
