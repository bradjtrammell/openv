#include "OpenVAdmissionCode.h"
#include <cassert>
#include <chrono>
#include <string>
int main()
{
    using openv::admission::CardSession;
    using namespace std::chrono_literals;
    using Clock = CardSession::Clock;
    const auto start = Clock::time_point{} + 1000s;
    const std::string nonce(32, 'a'), other(32, 'b'), code(43, 'Z');
    CardSession card;
    std::string taken;
    assert(card.Arm(nonce, "expired-token", start));
    assert(card.Arm(nonce, "expired-token", start + 59999ms));
    assert(card.RemainingMs(nonce, start + 59999ms) == 1);
    assert(!card.Arm(nonce, "expired-token", start + 60s));
    assert(!card.Active(nonce, start + 60s));
    assert(card.Arm(nonce, "fresh-token", start + 61s));
    assert(!card.Arm(nonce, "expired-token", start + 62s));
    assert(card.Take(nonce, code, taken, start + 62s));
    assert(taken == "fresh-token");
    assert(card.WasConsumed(nonce, "fresh-token"));
    assert(card.Arm(other, "second-token", start + 63s));
    assert(card.Take(other, code, taken, start + 64s));
    assert(card.WasConsumed(nonce, "fresh-token"));
    assert(card.WasConsumed(other, "second-token"));
    assert(!card.Arm(nonce, "fresh-token", start + 65s));
    assert(!card.Arm(nonce, "expired-token", start + 65s));
    assert(!card.Arm(other, "second-token", start + 65s));
    assert(card.Arm(nonce, "third-token", start + 65s));
    assert(card.Arm(nonce, "third-token", start + 66s));
    assert(!card.Arm(other, "third-token", start + 66s));
    assert(card.Take(nonce, code, taken, start + 66s));
    assert(card.WasConsumed(nonce, "third-token"));
    card.Clear();
    assert(!card.WasConsumed(nonce, "fresh-token"));
    assert(card.Arm(nonce, "expired-token", start + 67s));
    card.Clear();
    for (std::size_t i = 0; i < CardSession::MaxCardsPerConnection; ++i)
    {
        const std::string token = "token-" + std::to_string(i);
        assert(card.Arm(nonce, token, start + std::chrono::seconds(i)));
        assert(card.Take(nonce, code, taken, start + std::chrono::seconds(i)));
        assert(taken == token);
    }
    assert(!card.Arm(nonce, "overflow", start + 100s));
    assert(card.WasConsumed(nonce, "token-0"));
    assert(card.WasConsumed(nonce, "token-31"));
    card.Clear();
    assert(card.Arm(nonce, "overflow", start + 101s));
}
