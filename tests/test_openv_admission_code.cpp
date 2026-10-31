#include "OpenVAdmissionCode.h"
#include <cassert>
#include <chrono>
#include <string>
int main()
{
    using openv::admission::CardSession;
    using openv::admission::ValidCode;
    const std::string nonce(32, 'a'), other(32, 'b'), code(43, 'A');
    assert(ValidCode(code));
    assert(ValidCode(std::string(42, '0') + "_"));
    assert(ValidCode(std::string(42, '0') + "-"));
    assert(!ValidCode(std::string(42, 'A')));
    assert(!ValidCode(std::string(44, 'A')));
    assert(!ValidCode(std::string(42, 'A') + "="));
    assert(!ValidCode(std::string(42, 'A') + "\n"));
    using namespace std::chrono_literals;
    using Clock = CardSession::Clock;
    const auto start = Clock::time_point{} + 1000s;
    CardSession card;
    std::string result = "unchanged";
    assert(!card.Arm("invalid", "token"));
    assert(!card.Arm(nonce, ""));
    assert(!card.Arm(nonce, std::string(1025, 'x')));
    assert(card.Arm(nonce, "native-private-token", start));
    assert(card.Active(nonce, start + 59999ms));
    assert(card.RemainingMs(nonce, start) == 60000);
    assert(card.RemainingMs(nonce, start + 25000ms) == 35000);
    assert(card.RemainingMs(nonce, start + 59999ms) == 1);
    assert(card.RemainingMs(nonce, start + 60s) == 0);
    assert(card.RemainingMs(other, start + 100ms) == 0);
    assert(card.RemainingMs(nonce, start - 1ms) == 0);
    assert(!card.Active(nonce, start + 60s));
    assert(!card.Active(nonce, start - 1ms));
    assert(!card.Take(nonce, code, result, start + 60s));
    assert(result == "unchanged");
    assert(!card.Active(nonce, start));
    assert(!card.Arm(nonce, "native-private-token")); // expired native token cannot be revived
    assert(card.Arm(nonce, "native-private-token-2"));
    assert(card.Active(nonce));
    assert(!card.Active(other));
    assert(!card.Take(other, code, result));
    assert(result == "unchanged");
    assert(!card.Take(nonce, "invalid", result));
    assert(card.Active(nonce));
    assert(card.Take(nonce, code, result));
    assert(result == "native-private-token-2");
    assert(!card.Active(nonce));
    assert(!card.Take(nonce, code, result));
    assert(card.Arm(other, "new-token"));
    card.Clear();
    assert(!card.Take(other, code, result));
    assert(card.Arm(nonce, "old-token"));
    assert(!card.Arm(other, "new-token"));
    assert(card.Active(nonce));
    card.Clear();
    assert(card.Arm(other, "new-token"));
    assert(!card.Take(nonce, code, result));
    assert(card.Take(other, code, result));
    assert(result == "new-token");
    assert(card.Arm(nonce, "clock-test", start));
    assert(card.Take(nonce, code, result, start + 59999ms));
    assert(result == "clock-test");
    assert(card.Arm(nonce, "clock-reversal", start));
    assert(!card.Take(nonce, code, result, start - 1ms));
    assert(!card.Active(nonce, start));
    return 0;
}
