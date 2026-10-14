# OpenV gaming-PC test gate — October 16, 2026

**Purpose:** create a reproducible, honest test path for the first Windows GTA V client build, then verify the OpenV-authenticated connection when integration becomes available.

## 1. Build status

The **OpenV Windows client build (experimental)** workflow lives at `.github/workflows/openv-windows-client.yml`. It builds the existing fork with the upstream toolchain, uploads a build report, and attempts to upload release binaries.

Workflow: https://github.com/bradjtrammell/openv/actions/workflows/openv-windows-client.yml

**Do not treat the experimental artifact as an installer.** It may be missing runtime assets, UI, dependencies, signing, and packaging. The build is subject to upstream redistribution and entitlement restrictions.

## 2. Check target PC

Download this repo or the preflight script, open PowerShell 7, and run:

```powershell
pwsh -NoProfile -File .\tools\openv-gaming-pc-preflight.ps1
```

The script is read-only apart from writing `openv-preflight.json` into the current directory. It cannot verify GTA ownership, compatibility, or an OpenV build.

## 3. Client build gate (required)

- Workflow succeeds; record exact source commit SHA.
- All expected binaries and the client UI are available, including permitted game runtime dependencies.
- Client launches on Windows using a legitimate local GTA V installation.
- No unexpected Cfx authorization dependencies are silently bypassed.
- Startup logs, crash reports, and network calls are collected for a permitted test.

## 4. Identity integration gate (required)

- Community URL configured in client.
- Community account login against running `openv-identity`.
- Community server list appears.
- OpenV-issued ticket is generated and independently verified by the authorized server integration.
- One-time replay, bad audience, expiry, revoked account, offline identity service, and game ownership checks are tested.
- Gameplay networking, client/server protocol and resource loading remain intact.

## 5. Gameplay gate (required)

- Join permitted test server; verify OneSync entities, pma-voice/Mumble, Lua/JS/C# scripts, NUI, streamed vehicles/maps, and reconnect/disconnect.
- Verify resource permissions and player identity aliases against a backed-up test dataset.
- Measure basic stability over a substantial session, record issues with source commit and logs.

## 6. Known blockers as of initial publication

1. No verified independently built OpenV Windows client or packaged installer.
2. The existing client authentication hook provider / precompiled legitimacy behavior is not completely traced.
3. Existing server licensing components and legitimate entitlement rules still require investigation and authorization.
4. The Go identity service tickets are not compatible with native `cfxTicket2` yet.
5. No actual Windows gaming-PC launch, player connection, or real resource test has been completed.

**Green build ≠ installable client ≠ authenticated OpenV multiplayer.** Report these stages separately.
