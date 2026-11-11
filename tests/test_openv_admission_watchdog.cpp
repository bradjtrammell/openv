#include "OpenVAdmissionCode.h"
#include <cassert>
#include <chrono>
#include <string>

int main()
{
    using openv::admission::CardSession;
    using namespace std::chrono_literals;
    const auto start = CardSession::Clock::time_point{} + 1000s;
    const std::string nonce(32, 'a');
    const std::string code(43, 'A');
    CardSession session;
    std::string token;

    assert(!session.Expired(start));
    assert(session.Arm(nonce, "card-1", start));
    assert(!session.Expired(start));
    assert(!session.Expired(start + 59999ms));
    assert(session.RemainingMs(nonce, start + 59999ms) == 1);
    assert(session.Expired(start + 60s));
    assert(session.Expired(start + 61s));
    assert(session.Expired(start - 1ms));
    assert(!session.Take(nonce, code, token, start + 60s));
    assert(!session.Expired(start + 60s));
    assert(!session.Arm(nonce, "card-1", start + 61s));

    assert(session.Arm(nonce, "card-2", start + 62s));
    assert(!session.Expired(start + 63s));
    assert(session.Take(nonce, code, token, start + 63s));
    assert(token == "card-2");
    assert(!session.Expired(start + 1000s));
    assert(session.WasConsumed(nonce, "card-2"));
    assert(!session.Arm(nonce, "card-2", start + 1001s));

    assert(session.Arm(nonce, "card-3", start + 1002s));
    assert(session.Expired(start + 1062s));
    session.DropPending();
    assert(!session.Expired(start + 1063s));
    assert(!session.Arm(nonce, "card-3", start + 1063s));
    assert(session.WasConsumed(nonce, "card-2"));
    assert(session.Arm(nonce, "card-4", start + 1063s));
    session.Clear();
    assert(!session.Expired(start + 1064s));
    assert(session.Arm(nonce, "card-3", start + 1064s));
}
