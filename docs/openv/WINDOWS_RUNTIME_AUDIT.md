# Windows runtime artifact audit — 2026-10-14

## Verified successful build

Workflow run: https://github.com/bradjtrammell/openv/actions/runs/38631316965

The GitHub build report artifact was downloaded and its `package-manifest.json` inspected. This is evidence about compiled outputs, **not evidence of successful launch**.

| Finding | Verified |
|---|---|
| Workflow | successful |
| Source-derived release tree | 608 files, 2,044,213,544 bytes |
| Compiled executable | `FiveM.exe`, 5,164,032 bytes |
| Other executables | `FiveM_Diag.exe`, `CitiTest.exe`, `pe_debug.exe`, `retarget_pe.exe` |
| Authentication-related binary | `legitimacy.dll` present |
| Chrome subprocess binary | `CitizenFX_SubProcess_chrome.bin` present |
| `citizen/ui` under compiled release tree | **Not listed in manifest** |
| Installed game/client launch | Not tested |
| OpenV Identity client integration | Not implemented |
| New client licensing/redistribution authorization | Not established |

Build report included ~1.2 GB MSBuild diagnostic text, causing its compressed report to be ~54 MB. The release tree contains many `.pdb` symbols (one V8 PDB is ~323 MB), which should not be bundled with an ordinary test runtime.

## Follow-up instrumentation

The OpenV workflow now writes `runtime-readiness.json`, listing expected presence checks, and stages a separate `openv-win-runtime-candidate` artifact without debug symbol and intermediary files. A separate diagnostic artifact remains available. The runtime candidate is **not** automatically an installer, should not be characterized as an OpenV-branded playable client, and is subject to upstream redistribution permissions.

The missing `citizen/ui` files are a concrete startup risk. The original project build guide documents a UI-missing symptom (background and console only). Build the UI from permitted source using its documented toolchain. Do not copy restricted binaries or assets from a proprietary client distribution without authorization.

## PC testing gate

1. Obtain the successful build's `openv-win-runtime-candidate` artifact, once its workflow has passed.
2. Extract to a *new* folder, without overwriting existing GTA V/FiveM installations; do not run arbitrary executables as administrator.
3. Validate manifest hashes (if available), and run `tools/inspect-openv-artifact.ps1` (inspection-only).
4. Confirm proper asset provenance, local GTA V entitlement, necessary runtime files and `citizen/ui`.
5. Attempt authorized launch; capture startup/log and crashes before any authentication changes.
6. Separately integrate and validate OpenV Identity and dedicated server. A successful compiled FiveM-derived client does not imply OpenV multiplayer works.

## Hard blockers

- Native launcher startup not exercised on a gaming PC.
- Missing `citizen/ui` in the inspected runtime.
- `OnInterceptConnectionForAuth` subscriber / legitimacy authorization interplay not completely traced.
- OpenV tickets not compatible with the upstream `cfxTicket2` admission flow.
- Unverified rights to distribute compiled client and certain precompiled components.

Do not call this a completed client until the build, authorized install, startup and multiplayer gates are recorded separately.
