# OpenV GTA V native authority adapter

This is a **real Cfx/GTA V engine-native callback implementation**, compiled as part
of `gta:net:five`. It is not a complete multiplayer client. The source is
`code/components/gta-net-five/src/OpenVAuthorityGame.cpp`; the C ABI is
`code/components/gta-net-five/include/OpenVAuthorityGame.h`.

## Native host contract

An already legitimately entitled game host must initialize its independently
authenticated OpenV private bridge and use
`openv-server/native/openv_world_c_api.h` authority ABI version **1**. The
callback signatures and 64-byte entity record match that interface exactly.
Only one bound game session is supported per process. The bridge capability and
signed ticket must remain in the private launcher/bridge IPC; neither enters
this game component, a command line, URL, or log.

On the GTA game thread, **outside the frame callback**:

1. Create an `openv_authority_session` with the bridge's loopback port and
   private capability. Supply `OpenVGameAuthorityAuthorized`,
   `OpenVGameAuthoritySpawn`, `OpenVGameAuthorityMove` and
   `OpenVGameAuthorityDespawn` as its callbacks. The host's independent
   authorization callback must reflect both GTA ownership and the live
   authenticated OpenV session.
2. Call `OpenVGameAuthorityBind(session, openv_authority_tick,
   authorization_callback, context)` before joining. A callback that does
   not return 1 denies admission. Bind must run on the same thread as the
   subsequent `OnGameFrame` callback.
3. Configure the local position reader using
   `openv_authority_configure_position_source(session,
   OpenVGameAuthorityReadLocal, nullptr, 50, 1000, 0.05, 1.0)`.
4. Load the **independently verified** server resource/model policy into
   `OpenVGameAuthorityAllowModel(kind, hash)` for each permitted ped or
   vehicle model. Missing, unknown or wrong-kind models are rejected. The
   built-in player proxy uses the fixed freemode male ped model.
5. Start the numeric session with the actual local GTA ped coordinates using
   `openv_authority_start`. It performs bounded network I/O; do **not** call
   it from `OnGameFrame`. If start fails, unbind and destroy the session.
6. After a successful authenticated join, call
   `OpenVGameAuthorityActivate(session)`. The existing Cfx `OnGameFrame`
   callback now calls `openv_authority_tick` automatically, with no network
   I/O on the game thread. It samples the local ped, requests GTA models,
   creates local-only remote player/ped and vehicle proxies, moves them, and
   deletes them on authoritative departure or revocation.
7. For orderly teardown, call `OpenVGameAuthorityDeactivate(session)`,
   `openv_authority_stop(session)`, `OpenVGameAuthorityUnbind(session)`,
   and `openv_authority_destroy(session)` on the original game thread,
   outside a render frame. If stop or unbind fails, retain the session and
   retry cleanup. Never unload the component while it owns GTA handles.

The adapter rejects duplicate server IDs, wrong game handles, unlisted
models, missing native handlers, invalid transforms, and foreign threads.
Model streaming is asynchronous: a not-yet-loaded model is requested and its
spawn returns 0 without creating an entity. The authority pump retries the
unacknowledged snapshot without removing already active entities. Cleanup
continues after admission is revoked.

## Authenticated native authority session owner

The game component now owns the native numeric authority lifecycle rather than
requiring a separate caller to manually sequence bind/start/activate/stop.
The entry points are `OpenVGameAuthorityStartNative`,
`OpenVGameAuthorityStopNative` and `OpenVGameAuthorityNativeActive`.

A legitimate game launcher must load the **matching, locally verified**
`openv-server` native shared library, resolve
`openv_authority_abi_version`, `openv_authority_create`,
`openv_authority_configure_position_source`, `openv_authority_start`,
`openv_authority_tick`, `openv_authority_stop` and
`openv_authority_destroy`, and populate `openv_game_native_api`.
Those functions are C ABI version 1; the host must verify the library
provenance, bitness, ABI version and exported symbols before using them.
**No arbitrary DLL search, executable injection, entitlement bypass or
launcher command-line secret transfer is implemented here.**

### Windows DLL binding without a hand-built function table

The game component now also exports
`OpenVGameAuthorityStartNativeFromDll(absolute_library_path, launch, error, capacity)`.
This is the concrete Windows bridge-loader path. The trusted launcher supplies
an **absolute local drive path** to its verified, packaged
`openv_world_bridge.dll`; relative paths, UNC shares and DLL search-path
fallbacks are refused. The game component uses `LoadLibraryExW` with
`LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS`,
resolves the seven existing `openv_authority_*` C ABI exports, checks ABI
version 1, and calls the same authenticated `StartNative` lifecycle.
The game component retains the module until native stop, engine-handle cleanup,
callback unbind and destroy have all succeeded. A failed cleanup retains
the module for retry instead of unloading live callbacks.

This **does not** independently authenticate GTA ownership or acquire
session tickets. The legitimate launcher must still validate ownership,
establish the signed-Identity private bridge session, verify the DLL's
provenance and supply the 43-character capability and live authorization
callback privately, on the game thread outside `OnGameFrame`. It must call
`OpenVGameAuthorityStopNative` on logout or entitlement loss.
The DLL-loading function is not an automatic game-start hook or OneSync
wire implementation.

Windows CI compiles a separate fixture DLL exporting the exact seven C ABI
symbols and verifies real DLL loading, GTA mock ped spawning/movement,
cleanup and reload. Linux builds verify that the Windows-only entry point
fails closed. Neither test proves GTA V launch or two-player gameplay.

The trusted launcher supplies an `openv_game_native_launch` directly in
private process memory: a loopback bridge port, exactly 43 canonical
base64url capability characters, a live nonblocking entitlement/session
authorization callback and an independently verified model allowlist
(maximum 256 entries). Never pass or log the capability through arguments,
environment variables, URLs or telemetry. The launch struct and function
table must remain readable for the duration of the synchronous start call;
the native library copies the capability into its private session.

Call `OpenVGameAuthorityStartNative` on the **actual GTA game thread outside
`OnGameFrame`**, after lawful ownership and game initialization are verified.
It validates the ABI, creates the real native bridge session, binds the
engine callbacks, configures a 50ms local avatar sampler with a 1000ms
heartbeat, validates model policy using GTA natives, samples the actual
local ped, performs the authenticated numeric join and activates game-frame
replication. A failed join cannot be reused; cleanup is attempted and the
caller must retry `OpenVGameAuthorityStopNative` if pending. The game frame
only invokes `openv_authority_tick`, which consumes an authenticated
worker mailbox without network I/O.

On logout, engine shutdown, or entitlement loss, call
`OpenVGameAuthorityStopNative` from that same game thread **outside the
frame callback**. It deactivates new replication, asks the native session
to withdraw and despawn tracked entities, unbinds game callbacks, and
destroys the native session. A failed stop retains all callback targets
and the session for retry; do not unload the game component or native DLL
until stop succeeds. Frame reentrancy and foreign-thread teardown are
rejected.

This is **not** automatic launcher integration: the legitimate launcher
must still deliver its private bridge handle and resolve the native DLL
into the game process, and the full Windows game executable must compile
and launch with its lawful runtime dependencies. These are tracked as
remaining integration work, not claimed as completed.

## Verification and remaining work

`tests/openv_gta_native_adapter.cpp` compiles the **same production source**
against deterministic Cfx ScriptEngine native mocks on Linux GCC and Windows
MSVC. The tests cover local-ped sampling, deferred model loading, duplicate
spawn prevention, handle identity, movement, vehicle spawning, admission
withdrawal, cleanup, explicit teardown and allowlist reset.

These mocks **do not prove the GTA V executable can launch or that real
OneSync peers can interact**. The local-only proxies use
`CREATE_PED`/`CREATE_VEHICLE` with `isNetwork=false`, not real OneSync
network entities. The authorized private launcher must still bind and start
this adapter in the actual game lifecycle; the experimental full Windows
client needs lawful Mono, FFmpeg and Steamworks dependencies, and the game
must pass licensed two-PC gameplay and resource execution tests before
OpenV can be called playable. No proprietary assets or entitlement bypasses
are included.


## Pinned native bridge staging contract (2026-10-26)

The public GTA client repository includes
`tools/stage_openv_native_bridge.py` and ten staging regression tests.
The tool verifies an actual Windows AMD64 DLL's PE role, exact C ABI exports
and system-only imports with the first-party server's
`windows_binary_audit.py`, then stages identical bytes atomically and
records SHA-256 and exact source commit. It refuses mismatched existing DLLs,
unexpected imports/exports, reparse points, symlinks and invalid source refs.

**Repository visibility constraint:** `bradjtrammell/openv-server` is private.
The public `bradjtrammell/openv` GitHub Actions token cannot read it; a
cross-repository `actions/checkout` attempt failed with GitHub's 404
`Repository not found`. The public Windows client workflow therefore does
**not** fetch or bundle the private DLL and must not claim a playable package.
The native bridge is built and checked alongside the public GTA adapter
contract in the **private server CI**, which can read the public repository.
An explicitly authorized private-to-public artifact handoff or permitted
credential will be needed before the public client runtime can include it.
Do not copy private server source or binaries into this public repository.

The trusted, lawfully entitled launcher still must supply a private bridge
capability and live entitlement callback to
`OpenVGameAuthorityStartNativeFromDll` on the real GTA game thread.
The adapter currently creates local-only ped/vehicle proxies rather than
interoperable OneSync network objects. Mono, FFmpeg and Steamworks
dependencies, genuine GTA V launch, in-game resource execution and licensed
two-PC gameplay remain separate acceptance gates. No proprietary assets,
ownership bypasses, public releases or production deployments are included.


## Engine-handle ownership on failed native spawns (2026-10-26)

After GTA's `CREATE_PED` or `CREATE_VEHICLE` returns a live handle, the
adapter requires `SET_ENTITY_AS_MISSION_ENTITY` to succeed before returning
success to the authority pump. If mission ownership fails, it attempts to
delete the unacknowledged handle. A failed deletion is **not forgotten**:
that handle remains tracked as pending cleanup, blocks duplicate spawns for
the same authoritative entity ID, and is retried before a subsequent spawn.
On game-thread unbind, pending unacknowledged handles are also drained; an
unsuccessful deletion refuses unbind so the native owner can retry safely.
The same guarantee applies after admission revocation because cleanup is not
gated on a still-valid session. A successful engine spawn is therefore never
acknowledged until the game has accepted mission ownership. This is still a
local-only GTA proxy and is **not** a OneSync network entity.

Deterministic Linux GCC and Windows MSVC adapter tests inject both mission
ownership and entity deletion failures. These are engine-native mocks, not
actual GTA V gameplay tests.

## GTA main-thread frame dispatch (2026-10-26)

The native adapter now includes the actual `rage-nutsnbolts-five/include/nutsnbolts.h` event declaration rather than depending on a test-only declaration. It subscribes to `OnMainGameFrame`, **not** `OnGameFrame`: the latter can be fired by the Cfx loading-screen watchdog on a non-main thread. Only the main-thread event may sample GTA ped state, spawn/move/despawn entities, and drain the authenticated native authority mailbox. Deterministic regression tests independently fire both events and require the watchdog event to leave authority state unchanged. This corrects the `C2065: 'OnGameFrame': undeclared identifier` failure observed in the full Windows MSBuild job 40290304089; actual GTA launch remains NOT_RUN.

## Retry-safe native owner teardown (2026-10-26)

Native teardown is a three-stage transaction on the GTA main thread: stop
worker/session activity, unbind GTA callbacks after tracked handles are gone,
and destroy the native session. Each completed stage is remembered until the
entire transaction succeeds. If `openv_authority_stop` fails, the next
`OpenVGameAuthorityStopNative` retries stop. If callback unbind or native
destroy fails *after* stop succeeded, retrying never calls stop a second
time against an already-stopped session. The DLL remains loaded until every
stage succeeds. Start remains unavailable during partial teardown.

Deterministic GTA adapter tests inject a failed native stop and a failed
native destroy, assert that the correct stage alone is retried, and verify
that a fresh session can start after successful cleanup. These tests do not
exercise an actual GTA V process or prove OneSync interoperability.

## Current occupied vehicle movement sampling (2026-10-26)

The GTA main-thread local-position callback now uses `GET_VEHICLE_PED_IS_IN(ped, false)` to select the **currently occupied** vehicle rather than the last exited vehicle. For a live occupied vehicle it samples the vehicle's actual coordinates and heading, not the ped's seat-relative heading. The numeric server's movement and proximity decisions therefore follow the driven vehicle through turns. An unavailable vehicle lookup or already deleted vehicle falls back to the local ped; a live vehicle with an unreadable transform fails the sample rather than mixing vehicle and ped positions. Deterministic GTA-native adapter tests cover driving, turning, exiting, missing native and despawn. This does not implement remote seating or OneSync entities and is not an actual GTA V gameplay test.

## Local remote-replica physics and AI ownership (2026-10-26)

Authenticated numeric remote player/ped and vehicle replicas are currently **local-only GTA entities**, not OneSync network entities. After a successful GTA CREATE_PED/CREATE_VEHICLE and mission-entity acquisition, the game-thread adapter now freezes the entity so GTA physics cannot drift it between authoritative snapshots. Player/ped proxies also block non-temporary GTA AI events so ambient behavior cannot override server movement. `SET_ENTITY_COORDS_NO_OFFSET` and `SET_ENTITY_HEADING` continue applying authenticated transforms to frozen replicas. Failure to configure either native is a **failed spawn**, never an ACK: the handle is deleted or retained for retryable cleanup if deletion fails. This does not add remote driver seats, animation synchronization, collisions, or OneSync interoperability. Deterministic GCC/MSVC tests exercise successful ped/vehicle setup and both failure paths; actual GTA V gameplay remains NOT_RUN.


## Local proxy collision and damage isolation (2026-10-26)

The current numeric GTA entities are **local visual replicas**, not network-owned
OneSync entities. A remote ped or vehicle is frozen, made non-colliding with the
local world and invincible before the server receives a successful spawn ACK.
The order is intentional: freezing first prevents the local proxy from falling
through world geometry after collision is disabled. Remote peds also have
ambient AI events blocked. Only authenticated server transforms move them.
This prevents a local-only proxy from blocking the real player, colliding with
traffic or being silently destroyed by unsynchronized local damage. It does
**not** implement damage, driving, vehicle seats or OneSync network ownership.
If any GTA native handler fails, the spawn is unacknowledged; its handle is
removed or retained for retryable cleanup without duplicating the entity.
Deterministic GTA-native tests inject both new native failures and deletion
failures, then verify no ACK, stable handle tracking and recovery.
