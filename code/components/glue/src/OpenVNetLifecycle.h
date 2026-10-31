/*
 * OpenV native NetLibrary connection-state contract.
 * Values mirror NetLibrary::ConnectionState and are guarded by static_assert
 * in ConnectToNative.cpp. ACTIVE does not prove game ownership, FXServer
 * admission, resource execution, or multiplayer gameplay.
 */
#pragma once

namespace openv::connection
{
inline const char* NativeStageName(int state)
{
    switch (state)
    {
    case 0: return "idle";
    case 1: return "initializing";
    case 2: return "handshake";
    case 3: return "downloading";
    case 4: return "download_complete";
    case 5: return "fetching";
    case 6: return "connecting";
    case 7: return "connected";
    case 8: return "active";
    default: return nullptr;
    }
}
inline bool NativeTransportActive(int state)
{
    return state == 8;
}
// NUI may initialize before the native NetLibrary is constructed. Likewise,
// the UI latch may have been cleared by an error while Cfx is still tearing
// down its previous transport. A new request is safe only at native IDLE.
enum class NativeStartReadiness { ready, busy, unavailable };
inline NativeStartReadiness CheckNativeStart(bool connected, bool has_library, int native_state) noexcept
{
    if (connected) return NativeStartReadiness::busy;
    if (!has_library || !NativeStageName(native_state)) return NativeStartReadiness::unavailable;
    return native_state == 0 ? NativeStartReadiness::ready : NativeStartReadiness::busy;
}

// A callback registered on an obsolete NetLibrary must never close or mutate
// the nonce, admission card or progress of a replacement native transport.
inline bool IsCurrentLibrary(const void* event_library, const void* current_library) noexcept
{
    return event_library != nullptr && event_library == current_library;
}

// An error callback does not prove the asynchronous Cfx teardown finished.
inline bool NativeClosureConfirmed(bool has_library, int native_state) noexcept
{
    return !has_library || native_state == 0;
}

// A CEF reload may recover the existing native nonce but cannot create one.
// Pre-dispatch IDLE or unknown native states remain pending until probed.
inline const char* NativeSnapshotStage(bool connected, bool valid_nonce,
                                       bool has_library, int native_state) noexcept
{
    if (!connected || !valid_nonce) return nullptr;
    if (!has_library || native_state == 0) return "pending";
    const char* stage = NativeStageName(native_state);
    return stage ? stage : "pending";
}

// Probe native transport state, not only the UI connection latch. Error paths
// may clear the latch before Cfx has completed asynchronous teardown.
// Unknown native states fail closed until an authoritative IDLE is observed.
inline const char* NativeProbeState(bool connected, bool has_library, int native_state, bool owns_nonce) noexcept
{
    if (NativeClosureConfirmed(has_library, native_state)) return "absent";
    if (!NativeStageName(native_state) || !connected) return "pending";
    if (!owns_nonce) return "other";
    return NativeTransportActive(native_state) ? "active" : "pending";
}

// A synchronous transport exception must not strand the connection latch.
// Callers revoke their nonce and publish a terminal event on failure.
template <typename Start>
bool DispatchNativeStart(Start&& start) noexcept
{
    try { start(); return true; }
    catch (...) { return false; }
}

}
