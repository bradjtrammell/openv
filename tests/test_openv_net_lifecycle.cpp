#include "OpenVNetLifecycle.h"
#include <cassert>
#include <string_view>
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
    return 0;
}
