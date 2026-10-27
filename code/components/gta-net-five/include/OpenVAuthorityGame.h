#pragma once
/*
 * OpenV native GTA V entity callbacks.
 * C ABI layouts match openv-server/native/openv_world_c_api.h, authority ABI 1.
 * The game component never receives or stores bridge capabilities or tickets.
 * Copyright (c) OpenV contributors; see the repository LICENSE.
 */
#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
# define OPENV_GAME_API __declspec(dllexport)
#elif defined(__GNUC__)
# define OPENV_GAME_API __attribute__((visibility("default")))
#else
# define OPENV_GAME_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define OPENV_AUTHORITY_ABI_VERSION 1u
#define OPENV_AUTHORITY_PLAYER 1u
#define OPENV_AUTHORITY_PED 2u
#define OPENV_AUTHORITY_VEHICLE 3u

/* Native frame statuses from openv-server/native/openv_world_c_api.h.
 * ACTIVE and RETRY alone permit an admitted session to remain live.
 * REVOKED, WRONG_THREAD, INVALID_FRAME and unknown statuses fail closed.
 */
#define OPENV_GAME_FRAME_WAITING 0u
#define OPENV_GAME_FRAME_ACTIVE 1u
#define OPENV_GAME_FRAME_RETRY 2u
#define OPENV_GAME_FRAME_REVOKED 3u
#define OPENV_GAME_FRAME_WRONG_THREAD 4u
#define OPENV_GAME_FRAME_INVALID_FRAME 5u

typedef struct openv_authority_entity {
    uint64_t id;
    uint32_t kind;
    uint32_t model;
    uint64_t sequence;
    uint32_t bucket;
    double x, y, z, heading;
} openv_authority_entity;

typedef struct openv_authority_position {
    double x, y, z, heading;
} openv_authority_position;

typedef struct openv_authority_frame {
    uint32_t struct_size;
    uint32_t status;
    uint64_t local_entity_id;
    uint64_t revision;
    uint32_t bucket;
    size_t live_entities, spawned, moved, despawned;
} openv_authority_frame;

typedef int (*openv_game_authority_check)(void* context);
typedef int (*openv_game_authority_tick)(void* session, openv_authority_frame* frame);

/*
 * All functions must be invoked on the Cfx GTA V OnMainGameFrame thread.
 * Bind before openv_authority_start; activate only after it succeeds.
 * The session and authorization callback must remain alive until unbind.
 * A failed bind never enables entity creation. Unbind does NOT stop a session;
 * the owner must call openv_authority_stop and destroy on its game thread.
 */
OPENV_GAME_API uint32_t OpenVGameAuthorityAbiVersion(void);
/*
 * Returns 1 only on the observed GTA OnMainGameFrame thread after its first
 * frame. A launcher worker and the loading-screen watchdog return 0.
 * A trusted launcher must schedule bind/start/stop on that same thread,
 * outside the render callback. Probe without exposing bridge credentials.
 */
OPENV_GAME_API int OpenVGameAuthorityMainThreadReady(void);
OPENV_GAME_API int OpenVGameAuthorityBind(
    void* session, openv_game_authority_tick tick,
    openv_game_authority_check authorized, void* context);
/* Independent host-side model allowlist. Configure only before activation. */
OPENV_GAME_API int OpenVGameAuthorityAllowModel(uint32_t kind, uint32_t model);
OPENV_GAME_API int OpenVGameAuthorityActivate(void* session);
/* Deactivate frame dispatch after the owner starts orderly native stop. */
OPENV_GAME_API int OpenVGameAuthorityDeactivate(void* session);
OPENV_GAME_API int OpenVGameAuthorityUnbind(void* session);

/* Pass these callbacks to openv_authority_create; entity layouts are ABI-identical. */
OPENV_GAME_API int OpenVGameAuthorityAuthorized(void* context);
OPENV_GAME_API int OpenVGameAuthoritySpawn(
    void* context, const openv_authority_entity* entity, uint64_t* handle);
OPENV_GAME_API int OpenVGameAuthorityMove(
    void* context, uint64_t handle, const openv_authority_entity* entity);
OPENV_GAME_API int OpenVGameAuthorityDespawn(
    void* context, uint64_t handle, const openv_authority_entity* entity);
OPENV_GAME_API int OpenVGameAuthorityReadLocal(
    void* context, openv_authority_position* position);


/*
 * Native session ownership: a legitimately entitled launcher resolves the
 * matching openv-server native C ABI and supplies these function pointers
 * through a private in-process call. No bridge capability is read from
 * arguments, environment variables, URLs or logs by this game component.
 *
 * These layouts mirror the authority ABI v1 C structs. The owner checks
 * struct_size and ABI before passing them to the native bridge. Start/stop
 * must execute on the GTA game thread, outside OnGameFrame; start can block
 * for authenticated loopback admission, but each subsequent tick cannot.
 */
typedef struct openv_game_native_config {
    uint32_t struct_size;
    uint32_t abi_version;
    uint16_t bridge_port;
    const char* bridge_capability;
    uint32_t poll_wait_ms;
    uint32_t bridge_io_timeout_ms;
} openv_game_native_config;

typedef struct openv_game_native_callbacks {
    uint32_t struct_size;
    int (*authorized)(void*);
    int (*spawn)(void*, const openv_authority_entity*, uint64_t*);
    int (*move)(void*, uint64_t, const openv_authority_entity*);
    int (*despawn)(void*, uint64_t, const openv_authority_entity*);
} openv_game_native_callbacks;

typedef struct openv_game_native_api {
    uint32_t struct_size;
    uint32_t (*abi_version)(void);
    void* (*create)(const openv_game_native_config*,
                    const openv_game_native_callbacks*, void*);
    int (*configure_position_source)(void*,
        int (*reader)(void*, openv_authority_position*), void*,
        uint32_t, uint32_t, double, double);
    int (*start)(void*, double, double, double, double, char*, size_t);
    int (*tick)(void*, openv_authority_frame*);
    int (*stop)(void*);
    int (*destroy)(void*);
} openv_game_native_api;

/*
 * Additive ABI v1 async admission contract. No change to the existing
 * openv_game_native_api layout: both exports come from the same pinned DLL.
 * start_async queues an authenticated join; poll_start returns 0 pending,
 * 1 admitted, -1 denied. The native bridge owns its join worker.
 */
typedef struct openv_game_native_async_api {
    uint32_t struct_size;
    int (*start_async)(void*, double, double, double, double, char*, size_t);
    int (*poll_start)(void*, char*, size_t);
} openv_game_native_async_api;

typedef struct openv_game_native_model {
    uint32_t kind;
    uint32_t model;
} openv_game_native_model;

typedef struct openv_game_native_launch {
    uint32_t struct_size;
    uint16_t bridge_port;
    const char* bridge_capability; /* ephemeral 43-character private token */
    openv_game_authority_check entitlement; /* live, nonblocking snapshot */
    void* entitlement_context;
    const openv_game_native_model* models; /* independently verified policy */
    size_t model_count; /* 0..256 */
} openv_game_native_launch;

/* 1 on admitted startup; 0 on denial/failure. Error never includes secrets. */
OPENV_GAME_API int OpenVGameAuthorityStartNative(
    const openv_game_native_api* api, const openv_game_native_launch* launch,
    char* error, size_t error_capacity);
/*
 * Windows native DLL integration: the entitled launcher supplies an absolute
 * local path to its independently packaged openv_world_bridge.dll and the
 * same private launch contract used by StartNative. This function resolves
 * the actual openv_authority_* exports, checks ABI v1, and retains the DLL
 * until native stop/destroy completes. It never discovers tickets, credentials
 * or game ownership itself. Linux test builds return 0 (Windows-only host).
 */
OPENV_GAME_API int OpenVGameAuthorityStartNativeFromDll(
    const wchar_t* absolute_library_path,
    const openv_game_native_launch* launch,
    char* error, size_t error_capacity);
/*
 * Nonblocking authenticated admission. Call StartNativeAsync or the Windows
 * DLL variant on the observed main game thread OUTSIDE OnMainGameFrame.
 * Return 1 means admission QUEUED, never that a session is authenticated.
 * The game frame automatically polls the private bridge and activates only
 * after a validated join. No network I/O or blocking join on the frame.
 * Status: -2 no owned session, -1 rejected/cleanup required, 0 pending,
 * 1 admitted and active. Status may be queried only on the game thread.
 * A failed/revoked join must be stopped OUTSIDE the frame before retrying.
 */
OPENV_GAME_API int OpenVGameAuthorityStartNativeAsync(
    const openv_game_native_api* api,
    const openv_game_native_async_api* async_api,
    const openv_game_native_launch* launch,
    char* error, size_t error_capacity);
OPENV_GAME_API int OpenVGameAuthorityStartNativeAsyncFromDll(
    const wchar_t* absolute_library_path,
    const openv_game_native_launch* launch,
    char* error, size_t error_capacity);
OPENV_GAME_API int OpenVGameAuthorityNativeAdmissionStatus(void);
/* Game-thread-only: 1 means the native session is no longer trustworthy and
 * the host MUST schedule StopNative outside the render callback. The adapter
 * retains the DLL, session and engine handles until retryable teardown works.
 * A revoked/failed authority frame can never reactivate this session.
 */
OPENV_GAME_API int OpenVGameAuthorityNativeNeedsCleanup(void);
/*
 * Trusted in-process launcher -> GTA main-thread handoff. The launcher worker
 * queues one asynchronous admission without loading DLLs or calling GTA
 * natives. The adapter owns a copy of the private capability, DLL path and
 * model policy until dispatch on the next real OnMainGameFrame.
 *
 * Entitlement callback/context and direct ABI function pointers must remain
 * valid through dispatch and until the native session is stopped. Never
 * transfer the private capability by command line, environment, URL or log.
 *
 * A queued request waits up to 15 seconds for GTA's local player ped and
 * position to become readable. Until then it remains cancellable and never
 * creates a bridge session or consumes its private capability.
 * QueuedStatus: -2 idle/cancelled, 0 queued/waiting for avatar, 1 dispatched
 * to the native async API (NOT admitted), -1 rejected or timed out. Query NativeAdmissionStatus for verified
 * server admission. Queue, cancel and queued-status are thread-safe.
 * Cancellation affects only requests not yet consumed by the game thread.
 */
OPENV_GAME_API int OpenVGameAuthorityQueueNativeAsync(
    const openv_game_native_api* api,
    const openv_game_native_async_api* async_api,
    const openv_game_native_launch* launch);
OPENV_GAME_API int OpenVGameAuthorityQueueNativeAsyncFromDll(
    const wchar_t* absolute_library_path,
    const openv_game_native_launch* launch);
OPENV_GAME_API int OpenVGameAuthorityCancelQueuedNative(void);
OPENV_GAME_API int OpenVGameAuthorityQueuedStatus(void);
/* Credential-free progress for a trusted launcher worker. No GTA natives,
 * entitlement callbacks, pointers, tickets or capabilities are accessed.
 * This is observational only, never an authentication or readiness proof.
 * Counters other than main_frames reset when a native session is replaced.
 */
typedef struct openv_game_native_telemetry {
    uint32_t struct_size;
    int32_t queued_status;       /* -2 idle, -1 denied, 0 queued, 1 dispatched */
    int32_t admission_status;    /* -2 idle, -1 revoked, 0 joining, 1 admitted */
    uint32_t native_owned;       /* 1 until complete retryable teardown */
    uint64_t main_frames;        /* actual GTA OnMainGameFrame callbacks */
    uint64_t replica_frames;     /* accepted authority callbacks */
    uint64_t last_revision;
    uint64_t local_entity_id;
    uint64_t live_entities;
} openv_game_native_telemetry;
OPENV_GAME_API int OpenVGameAuthorityNativeTelemetry(
    openv_game_native_telemetry* out);
/* Retryable teardown. Retains the session and callbacks on failed cleanup. */
OPENV_GAME_API int OpenVGameAuthorityStopNative(void);
OPENV_GAME_API int OpenVGameAuthorityNativeActive(void);

#ifdef __cplusplus
}
#endif
