#include <OpenVAuthorityGame.h>
#include <Hooking.h>
#include <nutsnbolts.h>
#include <ScriptEngine.h>
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
constexpr uint64_t SET_BLOCKING_OF_NON_TEMPORARY_EVENTS = 0x9F8AA94D6D97DBF4ULL;
constexpr uint64_t DELETE_ENTITY = 0xAE3CBE5BF394C9C9ULL;
constexpr uint64_t SET_MODEL_AS_NO_LONGER_NEEDED = 0xE532F5D78798DAABULL;

struct Object {
    float x, y, z, heading;
    uint32_t model;
    bool vehicle;
    bool frozen = false;
    bool ai_blocked = false;
};
std::unordered_map<int, Object> objects{{10, {1, 2, 3, 45, 0, false}}};
int next_handle = 10;
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
int fail_ai_block_calls = 0;
bool fail_delete = false;
int session = 7;

int authorized(void*) { return allowed ? 1 : 0; }
int tick(void* pointer, openv_authority_frame* frame) {
    assert(pointer == &session);
    assert(frame->struct_size == sizeof(*frame));
    ++ticked;
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
        const int h = ++next_handle;
        objects[h] = {c.template Arg<float>(2), c.template Arg<float>(3),
            c.template Arg<float>(4), c.template Arg<float>(5),
            c.template Arg<uint32_t>(1), false};
        ++created;
        result(c, h);
    };
    ScriptEngine::handlers[CREATE_VEHICLE] = [](auto& c) {
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
    bool fail_stop_once = false;
    bool fail_destroy_once = false;
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
int fake_tick(void* authority_session, openv_authority_frame* frame) {
    assert(authority_session == &fake);
    assert(frame->struct_size == sizeof(*frame));
    assert(OpenVGameAuthorityStopNative() == 0); // never block in OnGameFrame
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
    frame->status = 1;
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
} // namespace

int main() {
    static_assert(sizeof(openv_authority_entity) == 64, "numeric authority ABI drift");
    assert(OpenVGameAuthorityAbiVersion() == 1);
    register_natives();
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
    loaded = true;
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &handle) == 1);
    assert(handle == 11 && created == 1);
    assert(objects.at(11).frozen && objects.at(11).ai_blocked);
    uint64_t duplicate = 0;
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &duplicate) == 0);
    assert(created == 1 && duplicate == 0);

    p.sequence = 2;
    p.x = 25;
    assert(OpenVGameAuthorityMove(nullptr, handle + 1, &p) == 0);
    assert(OpenVGameAuthorityMove(nullptr, handle, &p) == 1);
    assert(objects.at(11).x == 25 && moved == 1);

    auto v = vehicle(200);
    uint64_t vehicle_handle = 0;
    assert(OpenVGameAuthoritySpawn(nullptr, &v, &vehicle_handle) == 1);
    assert(objects.at(int(vehicle_handle)).vehicle);
    assert(objects.at(int(vehicle_handle)).frozen);
    assert(!objects.at(int(vehicle_handle)).ai_blocked);
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

    fail_ai_block_calls = 1;
    const int ai_created = created;
    assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 0);
    assert(orphan_handle == 0 && created == ai_created + 1);
    assert(OpenVGameAuthoritySpawn(nullptr, &unstable, &orphan_handle) == 1);
    assert(objects.at(int(orphan_handle)).frozen);
    assert(objects.at(int(orphan_handle)).ai_blocked);
    assert(OpenVGameAuthorityDespawn(nullptr, orphan_handle, &unstable) == 1);

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
#else
    assert(OpenVGameAuthorityStartNativeFromDll(
        L"/tmp/openv_world_bridge.so", &launch, error, sizeof(error)) == 0);
#endif
    std::cout << "OpenV GTA engine native adapter: PASS\\n";
}
