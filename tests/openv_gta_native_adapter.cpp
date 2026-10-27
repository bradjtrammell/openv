#include <OpenVAuthorityGame.h>
#include <Hooking.h>
#include <nutsnbolts.h>
#include <ScriptEngine.h>
#include <array>
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <unordered_map>
#ifdef _WIN32
#include <windows.h>
#endif

namespace {
constexpr uint64_t PLAYER_PED_ID = 0xD80958FC74E988A6ULL;
constexpr uint64_t GET_VEHICLE_PED_IS_IN = 0x9A9112A0FE9A4713ULL;
constexpr uint64_t GET_ENTITY_COORDS = 0x3FEF770D40960D5AULL;
constexpr uint64_t GET_ENTITY_HEADING = 0xE83D4F9BA2A38914ULL;
constexpr uint64_t DOES_ENTITY_EXIST = 0x7239B21A38F536BAULL;
constexpr uint64_t GET_ENTITY_MODEL = 0x9F47B058362C84B5ULL;
constexpr uint64_t IS_MODEL_IN_CDIMAGE = 0x35B9E0803292B641ULL;
constexpr uint64_t IS_MODEL_A_PED = 0x75816577FEA6DAD5ULL;
constexpr uint64_t IS_MODEL_A_VEHICLE = 0x19AAC8F07BFEC53EULL;
constexpr uint64_t REQUEST_MODEL = 0x963D27A58DF860ACULL;
constexpr uint64_t HAS_MODEL_LOADED = 0x98A4EB5D89A0C952ULL;
constexpr uint64_t CREATE_PED = 0xD49F9B0955C367DEULL;
constexpr uint64_t CREATE_VEHICLE = 0xAF35D0D2583051B0ULL;
constexpr uint64_t SET_ENTITY_COORDS_NO_OFFSET = 0x239A3351AC1DA385ULL;
constexpr uint64_t SET_ENTITY_HEADING = 0x8E2530AA8ADA980EULL;
constexpr uint64_t SET_ENTITY_AS_MISSION_ENTITY = 0xAD738C3085FE7E11ULL;
constexpr uint64_t FREEZE_ENTITY_POSITION = 0x428CA6DBD1094446ULL;
constexpr uint64_t SET_ENTITY_COLLISION = 0x1A9205C1B9EE827FULL;
constexpr uint64_t SET_ENTITY_INVINCIBLE = 0x3882114BDE571AD4ULL;
constexpr uint64_t SET_BLOCKING_OF_NON_TEMPORARY_EVENTS = 0x9F8AA94D6D97DBF4ULL;
constexpr uint64_t DELETE_ENTITY = 0xAE3CBE5BF394C9C9ULL;
constexpr uint64_t SET_MODEL_AS_NO_LONGER_NEEDED = 0xE532F5D78798DAABULL;

struct Object {
    float x, y, z, heading;
    uint32_t model;
    bool vehicle;
    bool frozen = false;
    bool ai_blocked = false;
    bool collision_enabled = true;
    bool invincible = false;
};
std::unordered_map<int, Object> objects{{10, {1, 2, 3, 45, 0, false}}};
int next_handle = 10;
int forced_create_handle = 0;
int requested = 0;
int created = 0;
int deleted = 0;
int moved = 0;
int ticked = 0;
bool loaded = false;
bool allowed = true;
int current_vehicle = 0;
bool vehicle_lookup_available = true;
int fail_mission_calls = 0;
int fail_freeze_calls = 0;
int fail_collision_calls = 0;
int fail_invincible_calls = 0;
int fail_ai_block_calls = 0;
bool fail_delete = false;
int session = 7;
bool burst_mode = false;
std::array<uint64_t, 12> burst_handles{};

int authorized(void*) { return allowed ? 1 : 0; }
int tick(void* pointer, openv_authority_frame* frame) {
    assert(pointer == &session);
    assert(frame->struct_size == sizeof(*frame));
    ++ticked;
    if (burst_mode) {
        for (size_t i = 0; i < burst_handles.size(); ++i) {
            if (burst_handles[i]) continue;
            openv_authority_entity entity{
                10000u + uint64_t(i), OPENV_AUTHORITY_PLAYER, 0, 1, 0,
                10, 20, 30, 45
            };
            // The authority pump retries deferred spawns on the next frame.
            (void)OpenVGameAuthoritySpawn(nullptr, &entity, &burst_handles[i]);
        }
    }
    return 1;
}
template<class T>
void result(fx::ScriptContextBuffer& ctx, T value) { ctx.SetResult(value); }
void register_natives() {
    using fx::ScriptEngine;
    ScriptEngine::handlers[PLAYER_PED_ID] = [](auto& c) { result(c, 10); };
    ScriptEngine::handlers[GET_VEHICLE_PED_IS_IN] = [](auto& c) {
        assert(c.template Arg<int>(0) == 10);
        assert(c.template Arg<bool>(1) == false); // exclude previous vehicle
        if (!vehicle_lookup_available)
            throw std::runtime_error("vehicle native temporarily unavailable");
        result(c, current_vehicle);
    };
    ScriptEngine::handlers[DOES_ENTITY_EXIST] = [](auto& c) {
        result(c, objects.count(c.template Arg<int>(0)) != 0);
    };
    ScriptEngine::handlers[GET_ENTITY_MODEL] = [](auto& c) {
        result(c, objects.at(c.template Arg<int>(0)).model);
    };
    ScriptEngine::handlers[GET_ENTITY_COORDS] = [](auto& c) {
        const auto& o = objects.at(c.template Arg<int>(0));
        c.SetVector(o.x, o.y, o.z);
    };
    ScriptEngine::handlers[GET_ENTITY_HEADING] = [](auto& c) {
        result(c, objects.at(c.template Arg<int>(0)).heading);
    };
    ScriptEngine::handlers[IS_MODEL_IN_CDIMAGE] = [](auto& c) {
        result(c, c.template Arg<uint32_t>(0) == 0x705E61F2u ||
                  c.template Arg<uint32_t>(0) == 0x12345678u);
    };
    ScriptEngine::handlers[IS_MODEL_A_PED] = [](auto& c) {
        result(c, c.template Arg<uint32_t>(0) == 0x705E61F2u);
    };
    ScriptEngine::handlers[IS_MODEL_A_VEHICLE] = [](auto& c) {
        result(c, c.template Arg<uint32_t>(0) == 0x12345678u);
    };
    ScriptEngine::handlers[REQUEST_MODEL] = [](auto&) { ++requested; };
    ScriptEngine::handlers[HAS_MODEL_LOADED] = [](auto& c) { result(c, loaded); };
    ScriptEngine::handlers[CREATE_PED] = [](auto& c) {
        if (forced_create_handle) {
            result(c, forced_create_handle);
            return;
        }
        const int h = ++next_handle;
        objects[h] = {c.template Arg<float>(2), c.template Arg<float>(3),
            c.template Arg<float>(4), c.template Arg<float>(5),
            c.template Arg<uint32_t>(1), false};
        ++created;
        result(c, h);
    };
    ScriptEngine::handlers[CREATE_VEHICLE] = [](auto& c) {
        if (forced_create_handle) {
            result(c, forced_create_handle);
            return;
        }
        const int h = ++next_handle;
        objects[h] = {c.template Arg<float>(1), c.template Arg<float>(2),
            c.template Arg<float>(3), c.template Arg<float>(4),
            c.template Arg<uint32_t>(0), true};
        ++created;
        result(c, h);
    };
    ScriptEngine::handlers[SET_ENTITY_COORDS_NO_OFFSET] = [](auto& c) {
        auto& o = objects.at(c.template Arg<int>(0));
        o.x = c.template Arg<float>(1);
        o.y = c.template Arg<float>(2);
        o.z = c.template Arg<float>(3);
        ++moved;
    };
    ScriptEngine::handlers[SET_ENTITY_HEADING] = [](auto& c) {
        objects.at(c.template Arg<int>(0)).heading = c.template Arg<float>(1);
    };
    ScriptEngine::handlers[SET_ENTITY_AS_MISSION_ENTITY] = [](auto&) {
        if (fail_mission_calls > 0) {
            --fail_mission_calls;
            throw std::runtime_error("simulated GTA mission ownership failure");
        }
    };
    ScriptEngine::handlers[FREEZE_ENTITY_POSITION] = [](auto& c) {
        if (fail_freeze_calls > 0) {
            --fail_freeze_calls;
            throw std::runtime_error("simulated GTA freeze failure");
        }
        objects.at(c.template Arg<int>(0)).frozen = c.template Arg<bool>(1);
    };
    ScriptEngine::handlers[SET_ENTITY_COLLISION] = [](auto& c) {
        if (fail_collision_calls > 0) {
            --fail_collision_calls;
            throw std::runtime_error("simulated GTA collision configuration failure");
        }
        assert(c.template Arg<bool>(2) == false);
        objects.at(c.template Arg<int>(0)).collision_enabled =
            c.template Arg<bool>(1);
    };
    ScriptEngine::handlers[SET_ENTITY_INVINCIBLE] = [](auto& c) {
        if (fail_invincible_calls > 0) {
            --fail_invincible_calls;
            throw std::runtime_error("simulated GTA invincibility configuration failure");
        }
        objects.at(c.template Arg<int>(0)).invincible =
            c.template Arg<bool>(1);
    };
    ScriptEngine::handlers[SET_BLOCKING_OF_NON_TEMPORARY_EVENTS] = [](auto& c) {
        if (fail_ai_block_calls > 0) {
            --fail_ai_block_calls;
            throw std::runtime_error("simulated GTA AI suppression failure");
        }
        objects.at(c.template Arg<int>(0)).ai_blocked = c.template Arg<bool>(1);
    };
    ScriptEngine::handlers[DELETE_ENTITY] = [](auto& c) {
        if (fail_delete)
            throw std::runtime_error("simulated GTA entity deletion failure");
        auto* p = c.template Arg<int*>(0);
        deleted += int(objects.erase(*p));
        *p = 0;
    };
    ScriptEngine::handlers[SET_MODEL_AS_NO_LONGER_NEEDED] = [](auto&) {};
}
openv_authority_entity player(uint64_t id) {
    return {id, OPENV_AUTHORITY_PLAYER, 0, 1, 0, 10, 20, 30, 45};
}
openv_authority_entity vehicle(uint64_t id) {
    return {id, OPENV_AUTHORITY_VEHICLE, 0x12345678u, 1, 0, 12, 22, 32, 90};
}

struct FakeAuthority {
    openv_game_native_callbacks callbacks{};
    void* context = nullptr;
    int (*reader)(void*, openv_authority_position*) = nullptr;
    void* reader_context = nullptr;
    uint64_t handle = 0;
    int frames = 0;
    int starts = 0;
    int stops = 0;
    int destroys = 0;
    bool fail_join = false;
    bool fail_async_poll = false;
    bool unexpected_async_poll = false;
    int async_polls = 0;
    bool fail_stop_once = false;
    bool fail_destroy_once = false;
    uint32_t forced_frame_status = OPENV_GAME_FRAME_ACTIVE;
    bool fail_tick = false;
    bool throw_tick = false;
} fake;
uint32_t fake_abi() { return OPENV_AUTHORITY_ABI_VERSION; }
void* fake_create(const openv_game_native_config* config,
                  const openv_game_native_callbacks* callbacks, void* context) {
    assert(config->struct_size == sizeof(*config));
    assert(config->abi_version == OPENV_AUTHORITY_ABI_VERSION);
    assert(config->bridge_port == 4848);
    assert(config->poll_wait_ms == 250);
    assert(config->bridge_io_timeout_ms == 10000);
    assert(std::strlen(config->bridge_capability) == 43);
    assert(config->bridge_capability[0] == 'A');
    assert(callbacks->struct_size == sizeof(*callbacks));
    fake.callbacks = *callbacks;
    fake.context = context;
    return &fake;
}
int fake_configure(void* authority_session,
                   int (*reader)(void*, openv_authority_position*),
                   void* context, uint32_t interval, uint32_t heartbeat,
                   double distance, double heading) {
    assert(authority_session == &fake);
    assert(interval == 50 && heartbeat == 1000);
    assert(distance == 0.05 && heading == 1.0);
    fake.reader = reader;
    fake.reader_context = context;
    return 1;
}
int fake_start(void* authority_session, double x, double y, double z, double heading,
               char* error, size_t capacity) {
    assert(authority_session == &fake);
    assert(x == 1 && y == 2 && z == 3 && heading == 45);
    openv_authority_position sample{};
    assert(fake.reader(fake.reader_context, &sample) == 1);
    assert(sample.x == 1 && sample.y == 2);
    assert(error && capacity > 0);
    ++fake.starts;
    return fake.fail_join ? 0 : 1;
}
int fake_start_async(void* authority_session, double x, double y, double z,
                     double heading, char* error, size_t capacity) {
    if (fake_start(authority_session, x, y, z, heading, error, capacity) != 1)
        return 0;
    fake.async_polls = 0;
    return 1;
}
int fake_poll_start(void* authority_session, char* error, size_t capacity) {
    assert(authority_session == &fake);
    assert(error && capacity);
    assert(OpenVGameAuthorityMainThreadReady() == 1);
    ++fake.async_polls;
    if (fake.async_polls == 1) return 0;
    if (fake.unexpected_async_poll) return 2;
    return fake.fail_async_poll ? -1 : 1;
}
int fake_tick(void* authority_session, openv_authority_frame* frame) {
    assert(authority_session == &fake);
    assert(frame->struct_size == sizeof(*frame));
    assert(OpenVGameAuthorityStopNative() == 0); // never block in OnGameFrame
    if (fake.throw_tick) throw std::runtime_error("simulated native frame exception");
    if (fake.fail_tick) return 0;
    if (fake.frames == 0) {
        auto p = player(400);
        assert(fake.callbacks.authorized(fake.context) == 1);
        assert(fake.callbacks.spawn(fake.context, &p, &fake.handle) == 1);
        assert(fake.handle != 0);
    } else if (fake.frames == 1) {
        auto p = player(400);
        p.sequence = 2;
        p.x = 99;
        assert(fake.callbacks.move(fake.context, fake.handle, &p) == 1);
    }
    ++fake.frames;
    frame->status = fake.forced_frame_status;
    frame->live_entities = 1;
    return 1;
}
int fake_stop(void* authority_session) {
    assert(authority_session == &fake);
    ++fake.stops;
    if (fake.fail_stop_once) {
        fake.fail_stop_once = false;
        return 0;
    }
    if (fake.handle) {
        auto p = player(400);
        // The authority pump withdraws the last rendered sequence, not the
        // initial spawn sequence, including after interpolation.
        if (fake.frames >= 2) p.sequence = 2;
        assert(fake.callbacks.despawn(fake.context, fake.handle, &p) == 1);
        fake.handle = 0;
    }
    return 1;
}
int fake_destroy(void* authority_session) {
    assert(authority_session == &fake);
    ++fake.destroys;
    if (fake.fail_destroy_once) {
        fake.fail_destroy_once = false;
        return 0;
    }
    return 1;
}
openv_game_native_api fake_api() {
    return {sizeof(openv_game_native_api), fake_abi, fake_create,
            fake_configure, fake_start, fake_tick, fake_stop, fake_destroy};
}
openv_game_native_async_api fake_async_api() {
    return {sizeof(openv_game_native_async_api),
            fake_start_async, fake_poll_start};
}
} // namespace

int main() {
    static_assert(sizeof(openv_authority_entity) == 64, "numeric authority ABI drift");
    assert(OpenVGameAuthorityAbiVersion() == 1);
    register_natives();
    // A host must not claim a successful native join before the actual GTA
    // main-frame event identifies its thread. The loading watchdog is not
    // sufficient, and no GTA entity may be created during this probe.
    assert(OpenVGameAuthorityMainThreadReady() == 0);
    assert(OpenVGameAuthorityBind(&session, tick, authorized, nullptr) == 0);
    OnGameFrame.Fire();
    assert(OpenVGameAuthorityMainThreadReady() == 0);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityMainThreadReady() == 1);
    int foreign_ready = -1;
    int foreign_bind = -1;
    std::thread foreign_main_frame([&] {
        OnMainGameFrame.Fire(); // must not steal the established owner thread
        foreign_ready = OpenVGameAuthorityMainThreadReady();
        foreign_bind = OpenVGameAuthorityBind(&session, tick, authorized, nullptr);
    });
    foreign_main_frame.join();
    assert(foreign_ready == 0 && foreign_bind == 0);
    assert(OpenVGameAuthorityMainThreadReady() == 1);
    assert(OpenVGameAuthorityBind(&session, tick, authorized, nullptr) == 1);
    assert(OpenVGameAuthorityBind(&session, tick, authorized, nullptr) == 0);
    assert(OpenVGameAuthorityAuthorized(nullptr) == 1);
    assert(OpenVGameAuthorityAllowModel(OPENV_AUTHORITY_VEHICLE, 0x705E61F2u) == 0);
    assert(OpenVGameAuthorityAllowModel(OPENV_AUTHORITY_PED, 0x12345678u) == 0);
    assert(OpenVGameAuthorityAllowModel(OPENV_AUTHORITY_VEHICLE, 0x12345678u) == 1);
    assert(OpenVGameAuthorityAllowModel(OPENV_AUTHORITY_VEHICLE, 0x12345678u) == 0);
    assert(OpenVGameAuthorityActivate(&session) == 1);
    assert(OpenVGameAuthorityAllowModel(OPENV_AUTHORITY_VEHICLE, 0x12345678u) == 0);
    OnMainGameFrame.Fire();
    assert(ticked == 1);
    // The real Cfx OnGameFrame event can run on a loading watchdog thread.
    // The native bridge must never be dispatched by that event.
    OnGameFrame.Fire();
    assert(ticked == 1);

    openv_authority_position local{};
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 1);
    assert(local.x == 1 && local.y == 2 && local.z == 3 && local.heading == 45);

    // Actual seated vehicle transform, not the ped's fixed seat heading,
    // must be submitted to the authenticated movement sampler.
    objects[20] = {100, 200, 300, 175, 0x12345678u, true};
    current_vehicle = 20;
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 1);
    assert(local.x == 100 && local.y == 200 && local.z == 300 &&
           local.heading == 175);
    objects[20].heading = 210;
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 1);
    assert(local.heading == 210);
    // After exiting, GET_VEHICLE_PED_IS_IN(false) must not use the last car.
    current_vehicle = 0;
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 1);
    assert(local.x == 1 && local.heading == 45);
    // The native can temporarily fail on game transitions; on-foot sampling
    // remains available, and a deleted vehicle never supplies stale state.
    vehicle_lookup_available = false;
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 1);
    assert(local.x == 1);
    vehicle_lookup_available = true;
    current_vehicle = 20;
    objects.erase(20);
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 1);
    assert(local.x == 1);
    current_vehicle = 0;

    uint64_t handle = 0;
    auto p = player(100);
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &handle) == 0);
    assert(handle == 0 && requested == 1 && created == 0);
    // Repeated entities of the same unloaded model must not request it on
    // every game frame. The loaded state is still probed on every attempt.
    auto waiting_player = player(888);
    uint64_t waiting_handle = 9;
    assert(OpenVGameAuthoritySpawn(nullptr, &waiting_player, &waiting_handle) == 0);
    assert(waiting_handle == 0 && requested == 1 && created == 0);
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &waiting_handle) == 0);
    assert(requested == 1);
    // A different permitted model is independently requested, not blocked by
    // the player model's cooldown.
    auto waiting_vehicle = vehicle(889);
    assert(OpenVGameAuthoritySpawn(nullptr, &waiting_vehicle, &waiting_handle) == 0);
    assert(requested == 2 && waiting_handle == 0);
    assert(OpenVGameAuthoritySpawn(nullptr, &waiting_vehicle, &waiting_handle) == 0);
    assert(requested == 2 && created == 0);
    loaded = true;
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &handle) == 1);
    assert(handle == 11 && created == 1);
    assert(objects.at(11).frozen && objects.at(11).ai_blocked);
    assert(!objects.at(11).collision_enabled && objects.at(11).invincible);
    uint64_t duplicate = 0;
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &duplicate) == 0);
    assert(created == 1 && duplicate == 0);

    // GTA's CREATE_* must not be allowed to alias an already tracked
    // remote proxy or the local player's actual ped. Such a native result
    // is rejected without deleting, freezing or moving either entity.
    forced_create_handle = int(handle);
    auto alias_vehicle = vehicle(201);
    uint64_t alias_handle = 123;
    const int deleted_before_alias = deleted;
    assert(OpenVGameAuthoritySpawn(nullptr, &alias_vehicle, &alias_handle) == 0);
    assert(alias_handle == 0 && deleted == deleted_before_alias);
    assert(objects.count(int(handle)) == 1);
    assert(objects.at(int(handle)).model == 0x705E61F2u);
    forced_create_handle = 10;
    auto alias_player = player(202);
    assert(OpenVGameAuthoritySpawn(nullptr, &alias_player, &alias_handle) == 0);
    assert(alias_handle == 0 && deleted == deleted_before_alias);
    assert(objects.count(10) == 1);
    forced_create_handle = 0;

    p.sequence = 2;
    p.x = 25;
    assert(OpenVGameAuthorityMove(nullptr, handle + 1, &p) == 0);
    assert(OpenVGameAuthorityMove(nullptr, handle, &p) == 1);
    assert(objects.at(11).x == 25 && moved == 1);
    // The engine must not replay older authenticated transforms, even if
    // called outside the authority pump. Same-sequence interpolation is legal.
    auto stale = p;
    stale.sequence = 1;
    stale.x = 500;
    assert(OpenVGameAuthorityMove(nullptr, handle, &stale) == 0);
    assert(objects.at(11).x == 25 && moved == 1);
    p.x = 26;
    assert(OpenVGameAuthorityMove(nullptr, handle, &p) == 1);
    assert(objects.at(11).x == 26 && moved == 2);
    assert(OpenVGameAuthorityDespawn(nullptr, handle, &stale) == 0);
    assert(objects.count(11) == 1);

    auto v = vehicle(200);
    uint64_t vehicle_handle = 0;
    assert(OpenVGameAuthoritySpawn(nullptr, &v, &vehicle_handle) == 1);
    assert(objects.at(int(vehicle_handle)).vehicle);
    assert(objects.at(int(vehicle_handle)).frozen);
    assert(!objects.at(int(vehicle_handle)).ai_blocked);
    assert(!objects.at(int(vehicle_handle)).collision_enabled);
    assert(objects.at(int(vehicle_handle)).invincible);
    v.sequence = 2;
    v.heading = 120;
    assert(OpenVGameAuthorityMove(nullptr, vehicle_handle, &v) == 1);
    assert(objects.at(int(vehicle_handle)).heading == 120);

    // A session losing admission cannot create/move, but cleanup is allowed.
    allowed = false;
    assert(OpenVGameAuthorityAuthorized(nullptr) == 0);
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 0);
    assert(OpenVGameAuthorityMove(nullptr, handle, &p) == 0);
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &duplicate) == 0);
    assert(OpenVGameAuthorityUnbind(&session) == 0);
    assert(OpenVGameAuthorityDespawn(nullptr, handle, &p) == 1);
    assert(OpenVGameAuthorityDespawn(nullptr, vehicle_handle, &v) == 1);
    assert(deleted == 2);
    assert(OpenVGameAuthorityUnbind(&session) == 0);
    assert(OpenVGameAuthorityDeactivate(&session) == 1);
    assert(OpenVGameAuthorityUnbind(&session) == 1);
    OnMainGameFrame.Fire();
    assert(ticked == 1);

    // Rebinding a new authenticated session cannot resurrect old handles.
    allowed = true;
    assert(OpenVGameAuthorityBind(&session, tick, authorized, nullptr) == 1);
    assert(OpenVGameAuthorityActivate(&session) == 1);
    assert(OpenVGameAuthoritySpawn(nullptr, &v, &vehicle_handle) == 0);
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &handle) == 1);
    assert(handle == 13);
    assert(OpenVGameAuthorityDespawn(nullptr, handle, &p) == 1);
    assert(OpenVGameAuthorityDeactivate(&session) == 1);
    assert(OpenVGameAuthorityUnbind(&session) == 1);
    // A new session must independently authorize its resource model policy.
    assert(OpenVGameAuthorityBind(&session, tick, authorized, nullptr) == 1);
    assert(OpenVGameAuthorityAllowModel(OPENV_AUTHORITY_VEHICLE, 0x12345678u) == 1);
    assert(OpenVGameAuthorityActivate(&session) == 1);

    // A GTA CREATE_* can succeed even when mission ownership or rollback
    // fails. Retain that unacknowledged handle instead of leaking it or
    // creating a second proxy on a server retry.
    const int before_created = created;
    const int before_deleted = deleted;
    auto pending = vehicle(999);
    fail_mission_calls = 1;
    fail_delete = true;
    uint64_t orphan_handle = 0;
    assert(OpenVGameAuthoritySpawn(nullptr, &pending, &orphan_handle) == 0);
    assert(orphan_handle == 0 && created == before_created + 1);
    assert(OpenVGameAuthoritySpawn(nullptr, &pending, &orphan_handle) == 0);
    assert(created == before_created + 1 && deleted == before_deleted);
    fail_delete = false;
    assert(OpenVGameAuthoritySpawn(nullptr, &pending, &orphan_handle) == 1);
    assert(orphan_handle != 0 && created == before_created + 2);
    assert(deleted == before_deleted + 1);
    assert(OpenVGameAuthorityDespawn(nullptr, orphan_handle, &pending) == 1);
    assert(deleted == before_deleted + 2);

    // GTA physics or ped AI configuration failures must not ACK a live
    // replica. Failed rollback retains the handle and blocks duplicates.
    auto unstable = player(998);
    fail_freeze_calls = 1;
    fail_delete = true;
    const int freeze_created = created;
    assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 0);
    assert(orphan_handle == 0 && created == freeze_created + 1);
    assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 0);
    assert(created == freeze_created + 1);
    fail_delete = false;
    assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 1);
    assert(objects.at(int(orphan_handle)).frozen);
    assert(objects.at(int(orphan_handle)).ai_blocked);
    assert(OpenVGameAuthorityDespawn(nullptr, orphan_handle, &unstable) == 1);

    // Collision and invincibility are gameplay invariants, not optional
    // cosmetic calls: failed native handlers must not ACK remote entities.
    for (int failure = 0; failure < 2; ++failure) {
        if (failure == 0) fail_collision_calls = 1;
        else fail_invincible_calls = 1;
        const int before = created;
        const int removed = deleted;
        fail_delete = true;
        assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 0);
        assert(orphan_handle == 0 && created == before + 1);
        // The failed spawn remains tracked until its GTA handle is deleted.
        assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 0);
        assert(created == before + 1 && deleted == removed);
        fail_delete = false;
        assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 1);
        assert(created == before + 2 && deleted == removed + 1);
        assert(!objects.at(int(orphan_handle)).collision_enabled);
        assert(objects.at(int(orphan_handle)).invincible);
        assert(OpenVGameAuthorityDespawn(nullptr, orphan_handle, &unstable) == 1);
    }

    fail_ai_block_calls = 1;
    const int ai_created = created;
    assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 0);
    assert(orphan_handle == 0 && created == ai_created + 1);
    assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 1);
    assert(objects.at(int(orphan_handle)).frozen);
    assert(objects.at(int(orphan_handle)).ai_blocked);
    assert(OpenVGameAuthorityDespawn(nullptr, orphan_handle, &unstable) == 1);

    // GTA can reclaim a remote handle and reuse the same integer for an
    // unrelated model. Neither a movement update nor a later despawn may
    // touch that foreign game entity. Server ID bookkeeping is retired.
    auto recycled = vehicle(777);
    uint64_t recycled_handle = 0;
    assert(OpenVGameAuthoritySpawn(nullptr, &recycled, &recycled_handle) == 1);
    const int reused = int(recycled_handle);
    objects.at(reused).model = 0xDEADBEEFu;
    const int moved_before_reuse = moved;
    const int deleted_before_reuse = deleted;
    recycled.sequence = 2;
    assert(OpenVGameAuthorityMove(nullptr, recycled_handle, &recycled) == 0);
    assert(moved == moved_before_reuse);
    assert(OpenVGameAuthorityDespawn(nullptr, recycled_handle, &recycled) == 1);
    assert(deleted == deleted_before_reuse);
    assert(objects.at(reused).model == 0xDEADBEEFu);
    // A fresh server entity may use the old numeric ID without inheriting
    // the recycled engine handle; the old foreign GTA object stays intact.
    assert(OpenVGameAuthoritySpawn(nullptr, &recycled, &recycled_handle) == 1);
    assert(recycled_handle != uint64_t(reused));
    assert(OpenVGameAuthorityDespawn(nullptr, recycled_handle, &recycled) == 1);
    objects.erase(reused);

    // Unbind must also drain an unacknowledged handle, even if the server
    // never issued a despawn for the failed spawn.
    fail_mission_calls = 1;
    fail_delete = true;
    orphan_handle = 0;
    assert(OpenVGameAuthoritySpawn(nullptr, &pending, &orphan_handle) == 0);
    assert(OpenVGameAuthorityDeactivate(&session) == 1);
    assert(OpenVGameAuthorityUnbind(&session) == 0);
    fail_delete = false;
    assert(OpenVGameAuthorityUnbind(&session) == 1);
    assert(objects.size() == 1);

    // A burst of 12 authorized remote players must not run 12 synchronous
    // GTA CREATE_PED and mission-ownership sequences on a single frame.
    // Deferred spawns succeed on the next main frame without duplicates,
    // without requiring a fresh session and without running on OnGameFrame.
    assert(OpenVGameAuthorityBind(&session, tick, authorized, nullptr) == 1);
    assert(OpenVGameAuthorityActivate(&session) == 1);
    burst_mode = true;
    const int burst_start = created;
    OnMainGameFrame.Fire();
    assert(created == burst_start + 8);
    for (size_t i = 0; i < burst_handles.size(); ++i)
        assert((burst_handles[i] != 0) == (i < 8));
    OnGameFrame.Fire();
    assert(created == burst_start + 8);
    OnMainGameFrame.Fire();
    assert(created == burst_start + 12);
    for (const auto burst_handle : burst_handles) assert(burst_handle != 0);
    OnMainGameFrame.Fire();
    assert(created == burst_start + 12); // retries cannot duplicate spawns
    burst_mode = false;
    for (size_t i = 0; i < burst_handles.size(); ++i) {
        auto entity = player(10000u + uint64_t(i));
        assert(OpenVGameAuthorityDespawn(nullptr, burst_handles[i], &entity) == 1);
        burst_handles[i] = 0;
    }
    assert(objects.size() == 1);
    assert(OpenVGameAuthorityDeactivate(&session) == 1);
    assert(OpenVGameAuthorityUnbind(&session) == 1);

    // Full native C ABI lifecycle: game ped -> authenticated bridge join ->
    // nonblocking GTA frame replication -> teardown after entitlement loss.
    const char private_token[] = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    static_assert(sizeof(private_token) == 44, "43-byte capability");
    const openv_game_native_model models[] = {
        {OPENV_AUTHORITY_VEHICLE, 0x12345678u}
    };
    openv_game_native_launch launch{
        sizeof(openv_game_native_launch), 4848, private_token,
        authorized, nullptr, models, 1
    };
    auto api = fake_api();
    char error[128]{};
    assert(OpenVGameAuthorityNativeActive() == 0);
    api.abi_version = []() -> uint32_t { return 999; };
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 0);
    assert(OpenVGameAuthorityNativeActive() == 0);
    api = fake_api();
    // A launcher may own credentials on a worker, but it must marshal native
    // activation to the real game thread. An off-thread call fails BEFORE
    // constructing the private authority session or attempting network I/O.
    int foreign_start = -1;
    std::thread launcher_worker([&] {
        char worker_error[128]{};
        foreign_start = OpenVGameAuthorityStartNative(
            &api, &launch, worker_error, sizeof(worker_error));
        assert(std::strstr(worker_error, "main game thread") != nullptr);
    });
    launcher_worker.join();
    assert(foreign_start == 0 && fake.starts == 0 && fake.destroys == 0);
    allowed = false;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 0);
    allowed = true;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityNativeActive() == 1);
    assert(fake.starts == 1 && fake.destroys == 0);
    OnGameFrame.Fire();
    assert(fake.frames == 0);
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 0);
    OnMainGameFrame.Fire();
    assert(fake.frames == 1 && fake.handle != 0);
    assert(objects.count(int(fake.handle)) == 1);
    OnMainGameFrame.Fire();
    assert(fake.frames == 2);
    assert(objects.at(int(fake.handle)).x == 99);
    int foreign_stop = -1;
    std::thread other([&] { foreign_stop = OpenVGameAuthorityStopNative(); });
    other.join();
    assert(foreign_stop == 0);
    assert(OpenVGameAuthorityNativeActive() == 1);
    allowed = false;
    assert(OpenVGameAuthorityNativeActive() == 0);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.stops == 1 && fake.destroys == 1);
    assert(fake.handle == 0 && objects.size() == 1);
    OnMainGameFrame.Fire();
    assert(fake.frames == 2);
    assert(OpenVGameAuthorityNativeActive() == 0);

    // Failed join is single-use and cleans up without activating game frames.
    allowed = true;
    fake.fail_join = true;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 0);
    assert(fake.starts == 2 && fake.stops == 2 && fake.destroys == 2);
    assert(OpenVGameAuthorityNativeActive() == 0);
    fake.fail_join = false;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.starts == 3 && fake.stops == 3 && fake.destroys == 3);

    // Failed native stop must retain the session for a retry; a successful
    // stop must not be replayed just because the later destroy stage fails.
    fake.fail_stop_once = true;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityStopNative() == 0);
    assert(OpenVGameAuthorityNativeActive() == 0);
    assert(fake.stops == 4 && fake.destroys == 3);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.stops == 5 && fake.destroys == 4);

    fake.fail_destroy_once = true;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityStopNative() == 0);
    assert(OpenVGameAuthorityNativeActive() == 0);
    assert(fake.stops == 6 && fake.destroys == 5);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.stops == 6 && fake.destroys == 6);
    assert(OpenVGameAuthorityNativeActive() == 0);
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.stops == 7 && fake.destroys == 7);

    // Actual authority frame statuses must control native admission. RETRY
    // is a temporary transport condition; a later REVOKED frame permanently
    // disables replication even when the launcher entitlement stays valid.
    fake.frames = 0;
    fake.forced_frame_status = OPENV_GAME_FRAME_RETRY;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeActive() == 1);
    assert(OpenVGameAuthorityNativeNeedsCleanup() == 0);
    fake.forced_frame_status = OPENV_GAME_FRAME_ACTIVE;
    OnMainGameFrame.Fire();
    assert(fake.frames == 2 && OpenVGameAuthorityNativeActive() == 1);
    fake.forced_frame_status = OPENV_GAME_FRAME_REVOKED;
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -1);
    assert(OpenVGameAuthorityNativeActive() == 0);
    assert(OpenVGameAuthorityNativeNeedsCleanup() == 1);
    const int revoked_frames = fake.frames;
    OnMainGameFrame.Fire();
    assert(fake.frames == revoked_frames);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.handle == 0 && objects.size() == 1);
    assert(OpenVGameAuthorityNativeNeedsCleanup() == 0);

    // Invalid server statuses, failed callbacks and thrown native errors
    // must not be interpreted as a healthy admitted gameplay frame.
    for (int failure = 0; failure < 4; ++failure) {
        fake.frames = 0;
        fake.forced_frame_status = failure == 0 ?
            OPENV_GAME_FRAME_WRONG_THREAD : failure == 1 ? 999u :
            OPENV_GAME_FRAME_ACTIVE;
        fake.fail_tick = failure == 2;
        fake.throw_tick = failure == 3;
        assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
        OnMainGameFrame.Fire();
        assert(OpenVGameAuthorityNativeAdmissionStatus() == -1);
        assert(OpenVGameAuthorityNativeActive() == 0);
        assert(OpenVGameAuthorityNativeNeedsCleanup() == 1);
        const int failed_frames = fake.frames;
        OnMainGameFrame.Fire();
        assert(fake.frames == failed_frames);
        assert(OpenVGameAuthorityStopNative() == 1);
        assert(fake.handle == 0 && objects.size() == 1);
        fake.fail_tick = false;
        fake.throw_tick = false;
    }
    fake.forced_frame_status = OPENV_GAME_FRAME_ACTIVE;

    // A revoked live entitlement must not run even one more engine tick.
    // Restoring the callback alone must never resurrect the old session.
    fake.frames = 0;
    assert(OpenVGameAuthorityStartNative(&api, &launch, error, sizeof(error)) == 1);
    OnMainGameFrame.Fire();
    assert(fake.frames == 1);
    allowed = false;
    OnMainGameFrame.Fire();
    assert(fake.frames == 1);
    assert(OpenVGameAuthorityNativeNeedsCleanup() == 1);
    allowed = true;
    OnMainGameFrame.Fire();
    assert(fake.frames == 1 && OpenVGameAuthorityNativeActive() == 0);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.handle == 0 && objects.size() == 1);

    // Async numeric admission must never call blocking join or spawn remote
    // proxies before the bridge has validated its authenticated ACK. Only
    // OnMainGameFrame can poll, and a failed poll requires out-of-frame stop.
    auto async_api = fake_async_api();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);
    async_api.poll_start = nullptr;
    assert(OpenVGameAuthorityStartNativeAsync(
        &api, &async_api, &launch, error, sizeof(error)) == 0);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);
    async_api = fake_async_api();
    const int starts_before_async = fake.starts;
    int foreign_async_start = -1;
    std::thread foreign_async([&] {
        char worker_error[128]{};
        foreign_async_start = OpenVGameAuthorityStartNativeAsync(
            &api, &async_api, &launch, worker_error, sizeof(worker_error));
    });
    foreign_async.join();
    assert(foreign_async_start == 0 && fake.starts == starts_before_async);
    fake.frames = 0;
    assert(OpenVGameAuthorityStartNativeAsync(
        &api, &async_api, &launch, error, sizeof(error)) == 1);
    assert(fake.starts == starts_before_async + 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    assert(OpenVGameAuthorityNativeActive() == 0);
    OnGameFrame.Fire();
    assert(fake.async_polls == 0 && fake.frames == 0);
    OnMainGameFrame.Fire();
    assert(fake.async_polls == 1 && fake.frames == 0);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    OnMainGameFrame.Fire();
    assert(fake.async_polls == 2 && fake.frames == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 1);
    assert(OpenVGameAuthorityNativeActive() == 1);
    assert(fake.handle && objects.count(int(fake.handle)) == 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.handle == 0 && objects.size() == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);

    fake.frames = 0;
    fake.fail_async_poll = true;
    assert(OpenVGameAuthorityStartNativeAsync(
        &api, &async_api, &launch, error, sizeof(error)) == 1);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -1);
    assert(OpenVGameAuthorityNativeActive() == 0 && fake.frames == 0);
    OnMainGameFrame.Fire();
    assert(fake.async_polls == 2); // rejected joins never poll again
    assert(OpenVGameAuthorityStopNative() == 1);
    fake.fail_async_poll = false;

    // Unknown bridge status codes must fail closed rather than remaining
    // indefinitely pending or accidentally activating replication.
    fake.unexpected_async_poll = true;
    assert(OpenVGameAuthorityStartNativeAsync(
        &api, &async_api, &launch, error, sizeof(error)) == 1);
    OnMainGameFrame.Fire();
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -1);
    assert(OpenVGameAuthorityNativeActive() == 0);
    assert(OpenVGameAuthorityStopNative() == 1);
    fake.unexpected_async_poll = false;

    // Revocation while admission is pending never activates a late join.
    assert(OpenVGameAuthorityStartNativeAsync(
        &api, &async_api, &launch, error, sizeof(error)) == 1);
    allowed = false;
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -1);
    assert(fake.async_polls == 0 && fake.frames == 0);
    assert(OpenVGameAuthorityStopNative() == 1);
    allowed = true;

    // A queued join can also be cancelled before the next main frame.
    assert(OpenVGameAuthorityStartNativeAsync(
        &api, &async_api, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);

    // A trusted launcher worker can now hand off the actual native ABI,
    // without attempting GTA native calls or exposing its private capability.
    // The queue owns the capability and model array, not the caller's stack.
    assert(OpenVGameAuthorityQueuedStatus() == -2);
    assert(OpenVGameAuthorityQueueNativeAsync(&api, &async_api, nullptr) == 0);
    std::array<char, 44> mutable_token{};
    std::memcpy(mutable_token.data(), private_token, sizeof(private_token));
    openv_game_native_model mutable_models[] = {
        {OPENV_AUTHORITY_VEHICLE, 0x12345678u}
    };
    openv_game_native_launch worker_launch{
        sizeof(openv_game_native_launch), 4848, mutable_token.data(),
        authorized, nullptr, mutable_models, 1
    };
    int worker_queue = -1;
    std::thread queue_worker([&] {
        worker_queue = OpenVGameAuthorityQueueNativeAsync(
            &api, &async_api, &worker_launch);
    });
    queue_worker.join();
    assert(worker_queue == 1 && OpenVGameAuthorityQueuedStatus() == 0);
    assert(OpenVGameAuthorityQueueNativeAsync(
        &api, &async_api, &worker_launch) == 0); // no overwrite
    assert(OpenVGameAuthorityCancelQueuedNative() == 1);
    assert(OpenVGameAuthorityCancelQueuedNative() == 0);
    assert(OpenVGameAuthorityQueuedStatus() == -2);
    assert(OpenVGameAuthorityQueueNativeAsync(
        &api, &async_api, &worker_launch) == 1);
    // Destroy the caller's credential/model content after enqueue; the
    // eventual game-thread startup must use its independently owned copy.
    mutable_token.fill('!');
    mutable_models[0].model = 0;
    const int before_handoff = fake.starts;
    OnGameFrame.Fire();
    assert(fake.starts == before_handoff);
    assert(OpenVGameAuthorityQueuedStatus() == 0);
    fake.frames = 0;
    OnMainGameFrame.Fire();
    assert(fake.starts == before_handoff + 1);
    assert(OpenVGameAuthorityQueuedStatus() == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    assert(OpenVGameAuthorityNativeActive() == 0);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 1);
    assert(OpenVGameAuthorityNativeActive() == 1);
    assert(fake.handle != 0);
    assert(OpenVGameAuthorityCancelQueuedNative() == 0);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(fake.handle == 0 && objects.size() == 1);

    // A first GTA main frame can arrive before the player's ped is streamed.
    // Keep the one-shot capability queued, without loading a bridge or
    // constructing a session, until an actual local avatar is readable.
    // A waiting request remains cancellable from the launcher worker.
    const auto local_ped = objects.at(10);
    const int starts_before_avatar = fake.starts;
    objects.erase(10);
    assert(OpenVGameAuthorityQueueNativeAsync(
        &api, &async_api, &launch) == 1);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == 0);
    assert(fake.starts == starts_before_avatar);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);
    assert(OpenVGameAuthorityCancelQueuedNative() == 1);
    assert(OpenVGameAuthorityQueuedStatus() == -2);
    // A revoked entitlement during the avatar wait must reject, not retry.
    assert(OpenVGameAuthorityQueueNativeAsync(
        &api, &async_api, &launch) == 1);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == 0);
    allowed = false;
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == -1);
    assert(fake.starts == starts_before_avatar);
    allowed = true;
    // A later frame with a real ped must dispatch exactly once and complete
    // authenticated async admission, without a second launcher handshake.
    assert(OpenVGameAuthorityQueueNativeAsync(
        &api, &async_api, &launch) == 1);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == 0);
    objects[10] = local_ped;
    fake.frames = 0;
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == 1);
    assert(fake.starts == starts_before_avatar + 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 1);
    assert(OpenVGameAuthorityNativeActive() == 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(objects.size() == 1);

    // Entitlement is checked again on the game thread, not trusted from
    // queue time. A revoked launch never constructs a native session.
    const int before_denied_handoff = fake.starts;
    assert(OpenVGameAuthorityQueueNativeAsync(
        &api, &async_api, &launch) == 1);
    allowed = false;
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == -1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);
    assert(fake.starts == before_denied_handoff);
    allowed = true;

    // A real Windows DLL must be loadable by absolute path, its ABI exports
    // must be resolved, and the same GTA game-thread callbacks must work.
#ifdef _WIN32
    const int created_before_dll = created;
    const int moved_before_dll = moved;
    const int deleted_before_dll = deleted;
    assert(OpenVGameAuthorityStartNativeFromDll(
        L"openv-gta-native-mock.dll", &launch, error, sizeof(error)) == 0);
    wchar_t dll_path[MAX_PATH]{};
    const DWORD path_size = GetFullPathNameW(
        L"openv-gta-native-mock.dll", MAX_PATH, dll_path, nullptr);
    assert(path_size > 0 && path_size < MAX_PATH);
    assert(OpenVGameAuthorityStartNativeFromDll(
        dll_path, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityNativeActive() == 1);
    assert(OpenVGameAuthorityStartNativeFromDll(
        dll_path, &launch, error, sizeof(error)) == 0);
    OnMainGameFrame.Fire();
    assert(created == created_before_dll + 1);
    OnMainGameFrame.Fire();
    assert(moved == moved_before_dll + 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(deleted == deleted_before_dll + 1);
    assert(OpenVGameAuthorityNativeActive() == 0);
    // DLL unload and native session destroy must permit a fresh join.
    assert(OpenVGameAuthorityStartNativeFromDll(
        dll_path, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    // Resolve the NEW real DLL async exports. A queued join must not claim
    // admission or create a GTA proxy until the bridge poll returns ready.
    const int async_created = created;
    assert(OpenVGameAuthorityStartNativeAsyncFromDll(
        dll_path, &launch, error, sizeof(error)) == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    assert(OpenVGameAuthorityNativeActive() == 0);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    assert(created == async_created);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 1);
    assert(OpenVGameAuthorityNativeActive() == 1);
    assert(created == async_created + 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);
    // Real Windows DLL handoff from a launcher worker: DLL loading and
    // GetProcAddress occur only after the GTA main frame consumes the queue.
    assert(OpenVGameAuthorityQueueNativeAsyncFromDll(
        L"openv-gta-native-mock.dll", &launch) == 0);
    int queued_dll = -1;
    std::thread dll_launcher([&] {
        queued_dll = OpenVGameAuthorityQueueNativeAsyncFromDll(
            dll_path, &launch);
    });
    dll_launcher.join();
    assert(queued_dll == 1 && OpenVGameAuthorityQueuedStatus() == 0);
    const int created_before_queued_dll = created;
    OnGameFrame.Fire();
    assert(created == created_before_queued_dll);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 1);
    assert(created == created_before_queued_dll + 1);
    assert(OpenVGameAuthorityStopNative() == 1);
    // The Windows DLL itself must not be loaded while GTA is still waiting
    // for its local player ped. This is a real LoadLibrary/ABI fixture.
    const auto local_ped_for_dll = objects.at(10);
    objects.erase(10);
    assert(OpenVGameAuthorityQueueNativeAsyncFromDll(
        dll_path, &launch) == 1);
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == 0);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == -2);
    assert(GetModuleHandleW(L"openv-gta-native-mock.dll") == nullptr);
    objects[10] = local_ped_for_dll;
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityQueuedStatus() == 1);
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 0);
    OnMainGameFrame.Fire();
    OnMainGameFrame.Fire();
    assert(OpenVGameAuthorityNativeAdmissionStatus() == 1);
    assert(OpenVGameAuthorityStopNative() == 1);
#else
    assert(OpenVGameAuthorityStartNativeFromDll(
        L"/tmp/openv_world_bridge.so", &launch, error, sizeof(error)) == 0);
    assert(OpenVGameAuthorityStartNativeAsyncFromDll(
        L"/tmp/openv_world_bridge.so", &launch, error, sizeof(error)) == 0);
#endif
    std::cout << "OpenV GTA engine native adapter: PASS\\n";
}
