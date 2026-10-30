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
    assert(CheckNativeStart(false, true, 0) == NativeStartReadiness::ready);
    assert(CheckNativeStart(false, false, 0) == NativeStartReadiness::unavailable);
    assert(CheckNativeStart(true, true, 0) == NativeStartReadiness::busy);
    assert(CheckNativeStart(true, false, 0) == NativeStartReadiness::busy);
    for (int state = 1; state <= 8; ++state)
        assert(CheckNativeStart(false, true, state) == NativeStartReadiness::busy);
    for (int state : {-1, 9, 1000})
        assert(CheckNativeStart(false, true, state) == NativeStartReadiness::unavailable);
    int first = 1, second = 2;
    using openv::connection::IsCurrentLibrary;
    assert(IsCurrentLibrary(&first, &first));
    assert(!IsCurrentLibrary(&first, &second));
    assert(!IsCurrentLibrary(nullptr, &first));
    assert(!IsCurrentLibrary(&first, nullptr));
    assert(!IsCurrentLibrary(nullptr, nullptr));
    using openv::connection::NativeClosureConfirmed;
    assert(NativeClosureConfirmed(false, -1));
    assert(NativeClosureConfirmed(false, 8));
    assert(NativeClosureConfirmed(true, 0));
    for (int state : {-1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 1000})
        assert(!NativeClosureConfirmed(true, state));
    using openv::connection::NativeProbeState;
    assert(std::string_view(NativeProbeState(false, false, -1, false)) == "absent");
    assert(std::string_view(NativeProbeState(false, true, 0, true)) == "absent");
    assert(std::string_view(NativeProbeState(true, true, 0, true)) == "absent");
    assert(std::string_view(NativeProbeState(false, true, 8, true)) == "pending");
    assert(std::string_view(NativeProbeState(false, true, 6, false)) == "pending");
    assert(std::string_view(NativeProbeState(true, true, -1, true)) == "pending");
    assert(std::string_view(NativeProbeState(true, true, 9, true)) == "pending");
    assert(std::string_view(NativeProbeState(true, true, 8, false)) == "other");
    assert(std::string_view(NativeProbeState(true, true, 8, true)) == "active");
    assert(std::string_view(NativeProbeState(true, true, 7, true)) == "pending");
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
