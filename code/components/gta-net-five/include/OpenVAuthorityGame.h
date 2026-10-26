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

#ifdef __cplusplus
}
#endif
