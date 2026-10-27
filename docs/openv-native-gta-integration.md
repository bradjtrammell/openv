## Queued admission waits for the real local GTA avatar (2026-10-26)

The trusted launcher can queue an authenticated native handoff before GTA
finishes streaming its local player ped. The real `OnMainGameFrame` now
preflights the same local ped/vehicle position sampler used by native
movement. A missing or temporarily unreadable avatar leaves the owned
capability and model policy in the cancellable queue for at most 15 seconds,
without loading the bridge DLL or creating a native authority session.
Entitlement is checked on every attempt; revocation fails closed immediately.
Once the avatar is readable, the request dispatches exactly once and the
existing authenticated asynchronous bridge admission continues. An avatar
that never becomes readable is rejected after the deadline. The queued status
0 means **waiting for the avatar or dispatch**, never authenticated; status
1 means dispatched but not necessarily admitted. Only
`OpenVGameAuthorityNativeAdmissionStatus() == 1` indicates admission.
GCC/MSVC adapter regressions cover waiting, cancellation, revocation,
and successful retry. Genuine GTA V gameplay is still NOT RUN.

## Trusted in-process launcher handoff to GTA main frame (2026-10-26)

The native GTA adapter now provides `OpenVGameAuthorityQueueNativeAsync`
(for an already verified in-process ABI table) and
`OpenVGameAuthorityQueueNativeAsyncFromDll` (for an independently verified,
absolute local Windows DLL path). A legitimately entitled launcher component
can call either from its own worker thread **without calling GTA natives**.
The request owns copies of the 43-character private bridge capability,
model allowlist (maximum 256 entries), port and DLL path. It never passes
secrets via command lines, environment variables, URLs or UI logs.

The next real `OnMainGameFrame` consumes the one-shot request on the pinned
GTA thread, loads the Windows bridge DLL if required, and invokes
`OpenVGameAuthorityStartNativeAsync` or its DLL variant. The bridge's
authenticated join runs on its existing worker; the main frame only polls
completed admission. `OpenVGameAuthorityQueuedStatus` is thread-safe and
reports **-2** idle/cancelled, **0** queued, **1** dispatched (not yet
authenticated), **-1** rejected. A separate game-thread call to
`OpenVGameAuthorityNativeAdmissionStatus` must return **1** before gameplay
replication is considered admitted. `OpenVGameAuthorityCancelQueuedNative`
only cancels an unconsumed request. Duplicate pending requests are rejected,
and a queued request cannot replace an active session.

The entitlement callback and context remain live caller-owned references
through the complete session; the launcher must keep them valid until
`OpenVGameAuthorityStopNative` finishes. It must arrange game-thread
teardown on logout/revocation and retry failed cleanup; cancellation is
not a substitute for stopping an admitted native session. The in-process
handoff is a production adapter API, **not** an external-process credential
channel or an automatic launch hook. The actual entitled launcher still
needs to call it from a verified in-game component. OneSync-owned entities,
resource execution, full Windows runtime and two-PC GTA gameplay remain
unverified. The GTA frame performs one-time DLL loading on handoff; a
slow disk or antivirus may cause a one-time hitch, which must be measured
in a real licensed game session.

## Nonblocking authenticated native admission (2026-10-26)

The GTA adapter now consumes the private server's existing additive ABI v1
`openv_authority_start_async` and `openv_authority_poll_start` exports.
A trusted, lawfully entitled launcher calls
`OpenVGameAuthorityStartNativeAsyncFromDll(absolute_local_dll_path, launch,
error, capacity)` on the **observed GTA main game thread, outside a frame**.
The matching in-memory function-table path is
`OpenVGameAuthorityStartNativeAsync(api, async_api, launch, error, capacity)`.
The legacy synchronous entry points remain unchanged for compatibility.

**Return 1 means admission has been queued, NOT that the server admitted the
client.** `OpenVGameAuthorityNativeAdmissionStatus()` returns -2 when no
native session is owned, 0 while the private bridge is joining, 1 only after
the authenticated bridge ACK is validated and the GTA callbacks are activated,
and -1 on rejection or entitlement withdrawal. The status getter must be
called on the observed game thread; a foreign-thread call returns -2.
`OpenVGameAuthorityNativeActive()` remains false until admission completes.

The production `OnMainGameFrame` callback polls `poll_start` only while
joining, and never dispatches entity creation or movement while pending.
The bridge's network join runs on its own worker. The frame poll performs
no network I/O or wait for unfinished admission; it transitions to active
only after a verified server acknowledgment. The loading watchdog
`OnGameFrame` cannot poll or activate. A rejection remains inactive and
cannot be retried until `OpenVGameAuthorityStopNative()` succeeds on the
same game thread **outside the frame**. Teardown cancels pending joins,
withdraws game handles, and retains DLL callbacks across retryable failures.
Raw bridge diagnostics and the 43-character capability never enter UI logs.

The Windows DLL path requires both async exports and all existing ABI v1
exports; it refuses incompatible DLLs before creating a session. Linux GCC
and Windows MSVC compile the production adapter with deterministic frame,
rejection, cancellation and entitlement-loss tests; Windows additionally
loads an actual mock DLL to exercise `GetProcAddress` and queued activation.

This is an integrated nonblocking admission mechanism, **not** automatic
launcher-to-game credential delivery. An authorized launcher still must
privately hand off the capability on the game thread. Actual GTA V launch,
licensed two-player gameplay, OneSync ownership and resource execution are
NOT RUN. The proxies are still local-only, not OneSync network entities.

## Main-game-thread readiness and trusted launcher handoff (2026-10-26)

The engine component now exports `OpenVGameAuthorityMainThreadReady()`.
It returns 1 **only after the first actual `OnMainGameFrame` event and only
when called from the thread that delivered that event**. The loading-screen
watchdog's `OnGameFrame` does not establish readiness. The first observed
main-frame thread is pinned for the process lifetime; a later foreign-thread
event cannot steal ownership. Readiness probes synchronize thread identity
and do not touch bridge credentials, game entities or network sockets.

`OpenVGameAuthorityBind`, `OpenVGameAuthorityStartNative` and Windows
`OpenVGameAuthorityStartNativeFromDll` now reject premature or off-thread
activation **before** creating a native session or loading a DLL. A trusted
launcher must retain the private capability and retry from the established
main game thread **outside the frame callback**. This makes an incorrectly
scheduled launcher fail explicitly instead of reporting a successful
authenticated join whose native frame callbacks never execute.

This change is a game-thread lifecycle prerequisite, not a launcher
implementation. It does not acquire signed tickets, perform entitlement
checks, install a GTA hook, create OneSync network entities or demonstrate
licensed two-player gameplay. The deterministic native adapter tests fire
the main and watchdog events independently and attempt foreign-thread
binding and startup. Actual GTA V launch remains NOT_RUN.

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

## GTA engine handle recycling and stale movement rejection (2026-10-26)

The native GTA adapter now checks the actual `GET_ENTITY_MODEL` before moving or deleting a tracked proxy. If GTA has recycled an engine handle for a different model, the adapter never moves or deletes that unrelated entity and retires its stale server-ID bookkeeping on despawn. A missing model native fails closed and retains cleanup for retry. It also tracks each proxy's latest accepted server sequence: older movement is rejected while equal-sequence interpolation remains permitted. Deterministic adapter tests exercise stale updates, recycled handles, foreign-entity preservation, and fresh spawns after cleanup. This is local-only proxy safety, not OneSync network ownership or licensed gameplay verification.

## GTA native handle alias protection (2026-10-26)

The real GTA CREATE_PED/CREATE_VEHICLE native can return an existing handle rather
than a new entity during an engine transition or invalid native result. Before
mission ownership, freezing, collision configuration or rollback deletion, the
adapter now refuses a handle already tracked for another authenticated remote
entity, the real local player ped, or the player's currently occupied vehicle.
If local ped or occupied-vehicle lookup cannot be verified, the new spawn fails
closed. An aliased handle is never treated as a newly allocated proxy and is
never deleted during failed-spawn cleanup. Deterministic production-adapter
regressions inject aliased local and remote handles. This does not implement
OneSync network ownership or prove GTA V gameplay.


## Coalesced GTA model streaming (2026-10-26)

The real GTA main-thread adapter checks `HAS_MODEL_LOADED` on every deferred
spawn, but throttles `REQUEST_MODEL` to at most one successful request per
250 ms for each `(kind, model)` pair. Multiple remote player or vehicle
replicas using the same unloaded model no longer flood the game engine with
identical streaming requests every render frame. Distinct permitted models
can be requested independently. The request cache is cleared on unbind and
when the model becomes loaded. Missing or failing GTA native handlers remain
retryable; no entity is ACKed before its model is loaded. Deterministic
production-source mock tests cover shared-model coalescing and independent
vehicle requests. Actual GTA V gameplay remains NOT_RUN.

## Native GTA rendering options during authenticated DLL startup (2026-10-26)

The Windows DLL startup path now resolves the **existing** server ABI v1
`openv_authority_configure_motion` and
`openv_authority_configure_interest` exports in addition to the seven
required lifecycle functions. Missing exports fail closed before any session
is created. After native session creation and game-thread binding, but before
the authenticated numeric join, the GTA host configures **120 ms** movement
interpolation with an **80-world-unit** teleport snap threshold, and a
**350-world-unit** interest radius with **50-unit** hysteresis. The server
still validates the full authenticated world inventory; only nearby
entities are projected into GTA. These values apply to the DLL-backed
Windows host; the existing direct v1 function-table entry point retains
its prior configuration behavior.

The Windows mock bridge refuses to start unless both configurations were
applied with the exact values and in the correct lifecycle order. No
capability or ticket is exposed to the UI or a command line. This improves
remote-player motion and engine entity load **after** a legitimate host
activates the bridge; it does not provide the missing launcher handoff,
OneSync network ownership, game assets or real two-PC verification.


## Bounded GTA main-frame entity creation (2026-10-26)

The Cfx GTA native adapter now limits synchronous remote `CREATE_PED` and
`CREATE_VEHICLE` attempts to **eight per `OnMainGameFrame`**. A large
authenticated snapshot therefore cannot attempt hundreds of GTA allocations,
mission-ownership changes, physics freezes and collision changes on one
render frame. The budget is charged before the engine CREATE native, even
when creation fails. It resets on each actual main-game frame; the loading
watchdog `OnGameFrame` does not replenish it.

Excess entities return the existing **not yet spawned** result. The native
authority pump retries those snapshots on later frames, preserving already
spawned proxies and session authentication. Model-not-loaded requests remain
coalesced; revocation and despawn cleanup are **not** budget-limited. The
game-thread adapter regression executes a 12-player burst, verifies 8+4
creation across frames, rejects duplicate retries and confirms full cleanup.

This is frame-time protection for existing local-only GTA replicas. It does
not add true OneSync network ownership, automatic lawful game launch, or
licensed two-PC gameplay verification.

## Authoritative native frame revocation and retry safety (2026-10-26)

After a signed session has been admitted, the GTA adapter now interprets the
actual numeric bridge frame status instead of discarding it. Only
`OPENV_AUTHORITY_ACTIVE` and the transient `OPENV_AUTHORITY_RETRY` keep
an admitted native session live. A revoked, wrong-thread, invalid, unknown,
failed or throwing frame irreversibly disables replica dispatch for that
session. A live entitlement callback changing to false also disables the
next frame before any entity native runs; restoring the callback cannot
resurrect the old session.

The additive `OpenVGameAuthorityNativeNeedsCleanup` query reports the
failed native session to its game-thread host. The host **must** schedule
`OpenVGameAuthorityStopNative` outside the render callback and retry if
engine-handle cleanup or native destruction fails. The game frame itself
never invokes blocking stop/network teardown. The bridge DLL and engine
handles remain owned until cleanup succeeds, preventing stale-handle
recycling and accidental duplicate admissions.

Deterministic GCC/MSVC production-adapter tests now exercise transient
RETRY, server REVOKED, wrong-thread and unknown status, callback failure,
exception, entitlement loss, irreversibility and cleanup. These tests
do not establish a running GTA V process, real OneSync interoperability,
or playable two-client multiplayer.

### Bounded asynchronous admission and launcher overlap

The real GTA `OnMainGameFrame` callback polls the native authority's
nonblocking admission result. An async join that has not received a validated
acknowledgment within **20 seconds** after successful `start_async` is
irreversibly rejected, even if its worker eventually completes. No remote
player or vehicle can be spawned from a late acknowledgment. The game host
must observe `OpenVGameAuthorityNativeNeedsCleanup() == 1` and invoke
`OpenVGameAuthorityStopNative()` on the original game thread **outside**
the frame callback. The native session, engine handles, and DLL remain owned
until retryable stop, unbind and destroy complete.

Launcher workers also cannot enqueue a second private session while the
adapter owns a native session (joining, admitted, revoked or retrying cleanup).
This is an atomic cross-thread ownership check; it does not read or mutate
GTA engine handles from the launcher thread. A new session can be queued only
after complete teardown. This protects the one-shot private bearer from being
silently consumed by an overlapping session. The separate 15-second avatar
readiness timeout still begins at the first real GTA main frame.

The 20-second watchdog is a local lifecycle safeguard, **not** proof of
actual game launch, signed-session acceptance, OneSync interoperability or
successful two-player gameplay.
