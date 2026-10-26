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
