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
 * All functions must be invoked on the Cfx GTA V OnGameFrame thread.
 * Bind before openv_authority_start; activate only after it succeeds.
 * The session and authorization callback must remain alive until unbind.
 * A failed bind never enables entity creation. Unbind does NOT stop a session;
 * the owner must call openv_authority_stop and destroy on its game thread.
 */
OPENV_GAME_API uint32_t OpenVGameAuthorityAbiVersion(void);
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
/* Retryable teardown. Retains the session and callbacks on failed cleanup. */
OPENV_GAME_API int OpenVGameAuthorityStopNative(void);
OPENV_GAME_API int OpenVGameAuthorityNativeActive(void);

#ifdef __cplusplus
}
#endif
