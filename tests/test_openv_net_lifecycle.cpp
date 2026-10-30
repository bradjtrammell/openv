#include "OpenVNetLifecycle.h"
#include <cassert>
#include <string_view>
#include <stdexcept>
int main()
{
    using openv::connection::NativeStageName;
    constexpr const char* names[] = {
        "idle", "initializing", "handshake", "downloading",
        "download_complete", "fetching", "connecting", "connected", "active"
    };
    for (int i = 0; i < 9; ++i)
    {
        assert(NativeStageName(i) != nullptr);
        assert(std::string_view(NativeStageName(i)) == names[i]);
        assert(openv::connection::NativeTransportActive(i) == (i == 8));
    }
    assert(NativeStageName(-1) == nullptr);
    assert(NativeStageName(9) == nullptr);
    assert(NativeStageName(1000) == nullptr);
    assert(!openv::connection::NativeTransportActive(-1));
    using openv::connection::NativeStartReadiness;
    using openv::connection::CheckNativeStart;
    assert(CheckNativeStart(false, true) == NativeStartReadiness::ready);
    assert(CheckNativeStart(false, false) == NativeStartReadiness::unavailable);
    assert(CheckNativeStart(true, true) == NativeStartReadiness::busy);
    assert(CheckNativeStart(true, false) == NativeStartReadiness::busy);
    int starts = 0;
    assert(openv::connection::DispatchNativeStart([&] { ++starts; }));
    assert(starts == 1);
    assert(!openv::connection::DispatchNativeStart([&] {
        ++starts;
        throw std::runtime_error("native initialization failed");
    }));
    assert(starts == 2);
    assert(openv::connection::DispatchNativeStart([&] { ++starts; }));
    assert(starts == 3);
    return 0;
}
