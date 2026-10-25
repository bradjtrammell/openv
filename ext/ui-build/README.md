# OpenV first-party client UI

`data/app/` contains the OpenV multiplayer menu. `data/root.html`,
`data/root.js` and `data/root.css` are a source-authored NUI root frame manager
for the same native `registerPushFunction` / `registerFrameFunction` /
`registerPollFunction` callback contract. The root creates, focuses, polls,
replaces and destroys resource iframes, forwarding native `frameCall` messages
only to an existing frame. It rejects malformed native payloads and unsafe
frame URL schemes. The menu entry point remains `app/index.html`; direct
connect, favorites, server queries and quit still use the existing native
`invokeNative` interface. The game bridge must be present.

On Windows run `build.cmd five` with Python 3. If the full upstream
`ext/ui-build/loadscreen/package.json` is present, the build uses its locked
Yarn/webpack pipeline as before (Node.js and Yarn are then required). In an
independently recoverable source-only overlay without those upstream files,
`build.cmd` instead uses the checked-in `loadscreen-fallback/` HTML, CSS and JS.
This fallback provides genuine loading status/progress but is not a replacement
for every upstream loadscreen animation. The packager produces `data.zip` and
`data_big.zip`, with required root, menu and loadscreen assets, reproducible
hashes, path checks and CRC validation. No prebuilt upstream UI is downloaded.
The game runtime consumes these as `citizen/ui.zip` and `citizen/ui-big.zip`.

Linux/source-only verification (no proprietary game assets):

```bash
python tools/build_openv_ui.py --source ext/ui-build/data \
  --loadscreen-dist ext/ui-build/loadscreen-fallback --output build/openv-ui
python -m unittest discover -s tests -p test_openv_ui.py -v
python -m unittest discover -s tests -p test_openv_ui_browser.py -v
```

The Chromium tests execute the actual first-party root manager with native
callback fakes and a real iframe. They do **not** exercise CEF native callback
injection, Windows MSVC compilation or GTA V. The remote Cfx repository has
an older inherited root manager: replacing it must be reviewed against the
actual native client before any Windows release, not blindly force-published.

To validate an installed candidate:

```powershell
python tools/build_openv_ui.py --verify-runtime code/bin/five/release
```

To run the local build/packaging tests:

```powershell
python -m unittest discover -s tests -p test_openv_ui.py -v
```

**Limits:** Native `connectTo`/`queryServer` event behavior, CEF rendering and
GTA V multiplayer still require execution on a licensed Windows game PC. The
static browser preview is not a multiplayer client. The Cfx-derived native client
still requires separate lawful game transport integration to join OpenV.

Native `frameCall` events originate in the **root iframe parent**, not the
menu's own window. The menu accepts those messages only from its parent at the
the explicitly permitted `nui://game` native root origin (or the same-origin
browser test fixture), rejecting sibling/self-frame, opaque and foreign-origin
messages. The real native root and child use different origins; see
`NUIInitialize.cpp` and `NUIApp.cpp`. The
connection nonce is mandatory: if CEF cannot provide cryptographic randomness,
OpenV refuses to submit the connection instead of silently sending an empty
nonce. `tests/test_openv_ui_browser.py` verifies this actual parent-to-child
transport and is included in the dedicated Chromium CI job.

## Native frame startup delivery and bounded recovery

The independently authored root queues native `frameCall` and `poll` events
until the intended iframe finishes loading. Creating a frame no longer first
attaches an empty `about:blank` document: its target URL is set before the
iframe is appended, preventing premature load callbacks from consuming the
startup queue. Focus is re-established after navigation, and loading-screen
handover is sent after the child is ready. Replacing or destroying an iframe
discards that iframe's queued messages; old events are never replayed into a
new resource frame with the same name.

Each pending frame is limited to **64 events and 512 KiB** of payload. If the
limit is exceeded, the root retains the most recent bounded events and sends
one `openvStartupOverflow` signal after loading. The first-party menu responds
by re-querying native favorites and server discovery and warning the user,
rather than silently treating incomplete startup discovery as complete. This
is a best-effort startup recovery for UI state, **not** a durable transport for
non-idempotent game commands. Live events after the iframe loads are delivered
normally. The native root uses the exact `nui://<resource>` origin for custom
CEF resource frames instead of the wildcard `*`, because the upstream CEF
registers `nui:` as a standard secure scheme.

The Chromium regression tests reproduce early native messages being lost in
the previous implementation, verify ordered delivery after navigation,
replacement isolation, queue bounds, recovery requests and exact NUI origins.
They cannot replace genuine Windows CEF/native or GTA V execution.

## Discovery-only OpenV gateway compatibility

The separately implemented `openv-session-server` now offers optional
Cfx-compatible UDP `getinfo` and HTTP `/info.json`/`/dynamic.json` metadata.
This is a server-list integration step, **not** a playable GTA V server. Its
`info.json` advertises `vars.openv_discovery_only = "true"`; the menu shows
that status, disables the corresponding Connect button, and rejects manual
connection attempts to an address already identified as discovery-only.
Unmarked, ordinarily playable Cfx server entries retain their existing
connection behavior. The inherited native Cfx client still requires an
authorized, independently verified game-transport integration before it can
join the authenticated Go gateway.

## Windows runtime static completeness gate

`tools/audit_openv_runtime.py` performs an **offline, fail-closed** audit of
actual staged Windows AMD64 files. It checks all required Cfx runtime anchors,
the complete first-party UI archives, case-insensitive collisions, symbolic
links/reparse-point candidates, PE32+ architecture/role, normal and delay-load
DLL imports, and the local dependency closure. It produces SHA-256 evidence
for parsed binaries. Windows system/API-set DLLs are distinguished from
third-party libraries; missing `libcef.dll`, VC++ runtimes, or other imported
third-party DLLs are reported rather than silently assumed to exist.

```powershell
python tools/audit_openv_runtime.py --runtime code/bin/five/release --report build-report/runtime-static-audit.json
python -m unittest discover -s tests -p test_openv_runtime_audit.py -v
```

The Windows CI workflow preserves the full build report even on audit failure
and **does not upload a runtime candidate** until the native build, first-party
UI build and static dependency audit all pass. Historical inventories can be
examined with `--manifest path/to/package-manifest.json`; that mode never
returns a passing runtime status because it cannot inspect the actual bytes.

The pinned Windows CEF 103 runtime uses `resources.pak`,
`chrome_100_percent.pak`, and `chrome_200_percent.pak`, **not** the
pre-CEF-90 `cef.pak` naming convention. Staging also requires the CEF
`chrome_elf.dll`, V8 context snapshot, ICU data, English locale, and
license, and preserves optional Vulkan/ANGLE components when present.
A missing modern pack is a real runtime blocker, not grounds to fabricate
or silently substitute an older incompatible dependency.

A static audit is **not** proof of execution, correct dynamic `LoadLibrary`
paths, game entitlement, authorized redistribution, or GTA V gameplay. A
licensed Windows PC and actual CEF/game-host testing remain required.
