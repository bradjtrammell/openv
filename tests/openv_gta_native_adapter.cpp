#include <OpenVAuthorityGame.h>
#include <Hooking.h>
#include <ScriptEngine.h>
#include <cassert>
#include <cmath>
#include <cstring>
#include <iostream>
#include <thread>
#include <unordered_map>

namespace {
constexpr uint64_t PLAYER_PED_ID = 0xD80958FC74E988A6ULL;
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
constexpr uint64_t DELETE_ENTITY = 0xAE3CBE5BF394C9C9ULL;
constexpr uint64_t SET_MODEL_AS_NO_LONGER_NEEDED = 0xE532F5D78798DAABULL;

struct Object {
    float x, y, z, heading;
    uint32_t model;
    bool vehicle;
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
    ScriptEngine::handlers[SET_ENTITY_AS_MISSION_ENTITY] = [](auto&) {};
    ScriptEngine::handlers[DELETE_ENTITY] = [](auto& c) {
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
    OnGameFrame.Fire();
    assert(ticked == 1);

    openv_authority_position local{};
    assert(OpenVGameAuthorityReadLocal(nullptr, &local) == 1);
    assert(local.x == 1 && local.y == 2 && local.z == 3 && local.heading == 45);

    uint64_t handle = 0;
    auto p = player(100);
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &handle) == 0);
    assert(handle == 0 && requested == 1 && created == 0);
    loaded = true;
    assert(OpenVGameAuthoritySpawn(nullptr, &p, &handle) == 1);
    assert(handle == 11 && created == 1);
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
    OnGameFrame.Fire();
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
    std::cout << "OpenV GTA engine native adapter: PASS\n";
}
