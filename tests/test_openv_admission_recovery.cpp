#include "OpenVAdmissionCode.h"
#include <cassert>
#include <chrono>
#include <string>
int main() {
    using openv::admission::CardSession;
    using namespace std::chrono_literals;
    using Clock = CardSession::Clock;
    const auto t = Clock::time_point{} + 1000s;
    const std::string nonce(32,'a'), other(32,'b'), code(43,'A');
    CardSession card;
    assert(card.Arm(nonce,"token-a",t));
    assert(card.Arm(nonce,"token-a",t+45s)); // duplicate delivery must not extend expiry
    assert(card.RemainingMs(nonce,t+50s)==10000);
    assert(!card.Arm(nonce,"token-b",t+51s)); // no silent replacement while live
    assert(!card.Arm(other,"token-a",t+51s));
    assert(card.RemainingMs(nonce,t+59s)==1000);
    assert(!card.Arm(nonce,"token-a",t-1ms)); // backward time is not an extension
    assert(!card.Active(nonce,t+60s));
    assert(card.Arm(nonce,"token-b",t+60s)); // expired cards may be replaced
    assert(card.RemainingMs(nonce,t+61s)==59000);
    std::string taken;
    assert(card.Take(nonce,code,taken,t+61s));
    assert(taken=="token-b");
    assert(!card.Arm(nonce,"token-b",t+62s)); // consumed native token cannot be replayed
    assert(card.Arm(nonce,"token-c",t+62s));
    card.Clear();
    assert(card.Arm(nonce,"token-b",t+63s)); // new connection resets replay fence
}
