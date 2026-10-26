/*
 * Windows CI-only native bridge DLL fixture.
 * Exercises the real LoadLibraryExW/GetProcAddress ABI path without tickets,
 * network access, GTA assets or an entitlement bypass.
 */
#include <OpenVAuthorityGame.h>
#include <cstdint>
#include <new>

#if !defined(_WIN32)
#error This fixture is intentionally Windows-only
#endif

struct MockSession {
    openv_game_native_callbacks callbacks{};
    void* context = nullptr;
    int (*reader)(void*, openv_authority_position*) = nullptr;
    void* reader_context = nullptr;
    uint64_t handle = 0;
    uint64_t sequence = 1;
    int frames = 0;
    bool started = false;
    bool motion_configured = false;
    bool interest_configured = false;
};

extern "C" {
__declspec(dllexport) uint32_t openv_authority_abi_version() {
    return OPENV_AUTHORITY_ABI_VERSION;
}
__declspec(dllexport) void* openv_authority_create(
    const openv_game_native_config* config,
    const openv_game_native_callbacks* callbacks, void* context) {
    if (!config || !callbacks ||
        config->struct_size != sizeof(*config) ||
        config->abi_version != OPENV_AUTHORITY_ABI_VERSION ||
        callbacks->struct_size != sizeof(*callbacks) ||
        !callbacks->authorized || !callbacks->spawn ||
        !callbacks->move || !callbacks->despawn)
        return nullptr;
    auto* session = new (std::nothrow) MockSession;
    if (!session) return nullptr;
    session->callbacks = *callbacks;
    session->context = context;
    return session;
}
__declspec(dllexport) int openv_authority_configure_position_source(
    void* pointer, int (*reader)(void*, openv_authority_position*),
    void* context, uint32_t interval, uint32_t heartbeat,
    double distance, double heading) {
    auto* session = static_cast<MockSession*>(pointer);
    if (!session || !reader || interval != 50 || heartbeat != 1000 ||
        distance != 0.05 || heading != 1.0) return 0;
    session->reader = reader;
    session->reader_context = context;
    return 1;
}
__declspec(dllexport) int openv_authority_configure_motion(
    void* pointer, uint32_t interpolation_ms, double snap_distance) {
    auto* session = static_cast<MockSession*>(pointer);
    if (!session || session->started || interpolation_ms != 120 ||
        snap_distance != 80.0 || session->motion_configured) return 0;
    session->motion_configured = true;
    return 1;
}
__declspec(dllexport) int openv_authority_configure_interest(
    void* pointer, double radius, double hysteresis) {
    auto* session = static_cast<MockSession*>(pointer);
    if (!session || session->started || radius != 350.0 ||
        hysteresis != 50.0 || session->interest_configured) return 0;
    session->interest_configured = true;
    return 1;
}
__declspec(dllexport) int openv_authority_start(
    void* pointer, double x, double y, double z, double heading,
    char* error, size_t capacity) {
    auto* session = static_cast<MockSession*>(pointer);
    if (!session || !session->reader || !session->motion_configured ||
        !session->interest_configured || !error || !capacity ||
        x != 1 || y != 2 || z != 3 || heading != 45 ||
        session->callbacks.authorized(session->context) != 1)
        return 0;
    openv_authority_position sampled{};
    if (session->reader(session->reader_context, &sampled) != 1 ||
        sampled.x != x || sampled.y != y) return 0;
    session->started = true;
    return 1;
}
__declspec(dllexport) int openv_authority_tick(
    void* pointer, openv_authority_frame* frame) {
    auto* session = static_cast<MockSession*>(pointer);
    if (!session || !session->started || !frame ||
        frame->struct_size != sizeof(*frame)) return 0;
    openv_authority_entity entity{
        901, OPENV_AUTHORITY_PLAYER, 0, session->sequence,
        0, 10, 20, 30, 45
    };
    if (session->frames == 0) {
        if (session->callbacks.spawn(session->context, &entity,
                                     &session->handle) != 1) return 0;
    } else if (session->frames == 1) {
        entity.sequence = ++session->sequence;
        entity.x = 33;
        if (session->callbacks.move(session->context,
                                    session->handle, &entity) != 1) return 0;
    }
    ++session->frames;
    frame->status = 1;
    frame->live_entities = 1;
    return 1;
}
__declspec(dllexport) int openv_authority_stop(void* pointer) {
    auto* session = static_cast<MockSession*>(pointer);
    if (!session) return 0;
    if (session->handle) {
        openv_authority_entity entity{
            901, OPENV_AUTHORITY_PLAYER, 0, session->sequence,
            0, 33, 20, 30, 45
        };
        if (session->callbacks.despawn(session->context,
                                       session->handle, &entity) != 1)
            return 0;
        session->handle = 0;
    }
    session->started = false;
    return 1;
}
__declspec(dllexport) int openv_authority_destroy(void* pointer) {
    auto* session = static_cast<MockSession*>(pointer);
    if (!session || session->handle) return 0;
    delete session;
    return 1;
}
}
