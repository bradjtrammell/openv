# OpenV Windows Client — failed runtime diagnosis

The CI job compiles the GTA V/CitizenFX-based client and builds the UI, but a
successful compilation is **not** a runnable or redistributable product.

The October 26, 2026 failed build (`40410020384`) completed compilation,
first-party UI and CEF/VC++ staging. Its PE audit found these unresolved imports:

| Import | Direct consumers | Correct owner |
| --- | --- | --- |
| `mono-2.0-sgen.dll` | CitizenFX Mono/C# scripting | Approved, source-verified Mono runtime |
| `avutil-56.dll` | Extra natives, voice | ABI-compatible FFmpeg runtime |
| `swresample-3.dll` | Extra natives, voice | Matching ABI-compatible FFmpeg runtime |
| `steam_api64.dll` | Legitimacy module | Authorized game/platform installation |

`tools/stage_open_runtime.py` already supports **secure, hash-pinned**
provisioning of the approved Mono and FFmpeg binary dependencies. However, the
build had no `OPENV_RUNTIME_DEPENDENCIES_MANIFEST` GitHub repository variable,
so the staging step correctly did nothing. The build cannot be truthfully
advertised as ready or secure by merely adding those filenames to an allowlist.

Required engineering actions:

1. Choose **compatible x64** Mono and FFmpeg binaries from legal,
   redistributable builds. Verify their actual provenance and full license
   obligations; generate the existing manifest schema with exact SHA-256
   values and a copy of each required license. The `upstream_url` field
   is descriptive, not an authenticated download and not a substitute for
   a license audit.
2. Arrange controlled provisioning of those source files into the Windows
   builder and configure the manifest path; the current manifest variable
   alone does **not** upload or distribute files.
3. Resolve the Steam platform import against the verified installed licensed
   game at launch or with an independently authorized distribution. Do not
   bundle game-platform files from untrusted download sites, replace
   ownership logic with a stub, or silently exempt missing imports.
4. Retain the strict audit, verify all staged binary hashes, perform a
   real-game launch test and test resource APIs/OneSync/MDT/real FivePD.
   **No source audit alone proves GTA V gameplay.**

For every failed run, CI now writes:
`build-report/runtime-failure-summary.json` and an explicit GitHub job
summary, with concrete missing DLL names and actions. The detailed
`runtime-static-audit.json` is preserved. This is diagnostic code, **not**
an attempt to make the incomplete runtime pass.

The Server's internal Identity authentication passed real Windows API tests;
it is a separate product and does not require redistributing these Client
dependencies.
