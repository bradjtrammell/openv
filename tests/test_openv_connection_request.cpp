#include "OpenVConnectionRequest.h"
#include <cassert>
#include <string>
#include <iostream>

int main()
{
    using openv::connection::ValidEndpoint;
    using openv::connection::ValidNonce;
    using openv::connection::ValidPort;
    assert(ValidNonce("0123456789abcdef0123456789abcdef"));
    for (const auto& nonce : {"", "0123456789abcdef0123456789abcde", "0123456789abcdef0123456789abcdef0", "0123456789ABCDEF0123456789ABCDEF", "0123456789abcdef0123456789abcde!"})
        assert(!ValidNonce(nonce));
    for (const auto& endpoint : {"play.example.org:30120", "localhost:30120", "127.0.0.1:30120", "[::1]:30120", "[2001:db8::1]:30120", "play-server_1.example:65535"})
        assert(ValidEndpoint(endpoint));
    for (const auto& endpoint : {"", "http://play.example.org", "play.example.org:0", "play.example.org:65536", "play.example.org:-1", "play.example.org:123456", "play.example.org:foo", "play.example.org:30120/path", "evil@play.example.org:30120", "127.0.0.999:30120", "127.0.0.1:30120:44", "[::1", "[::1]:99999", "[ab]", "bad..example:30120", "-bad.example:30120", "bad-.example:30120", "\nlocalhost:30120", "1.2.3:30120", "9999999999999999999999:30120", "[:::]:30120"})
        assert(!ValidEndpoint(endpoint));
    assert(ValidPort("1") && ValidPort("65535"));
    assert(!ValidPort("0") && !ValidPort("65536") && !ValidPort("12a"));
    assert(!ValidEndpoint(std::string(256, 'a')));
    using openv::connection::IsStructuredConnectEnvelope;
    assert(IsStructuredConnectEnvelope(R"(["[::1]:30120","0123456789abcdef0123456789abcdef"])"));
    assert(IsStructuredConnectEnvelope(R"([ "[2001:db8::1]:30120", "0123456789abcdef0123456789abcdef" ])"));
    assert(!IsStructuredConnectEnvelope("[::1]:30120"));
    assert(!IsStructuredConnectEnvelope("[2001:db8::1]:30120"));
    assert(!IsStructuredConnectEnvelope("[::1]"));
    assert(!IsStructuredConnectEnvelope("play.example.org:30120"));
    std::cout << "PASS: OpenV native connection request endpoint, port, nonce and IPv6 envelope routing\n";
}
