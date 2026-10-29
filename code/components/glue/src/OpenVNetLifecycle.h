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
}
