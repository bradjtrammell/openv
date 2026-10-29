#include "OpenVAdmissionCode.h"
#include <cassert>
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
    CardSession card;
    std::string result = "unchanged";
    assert(!card.Arm("invalid", "token"));
    assert(!card.Arm(nonce, ""));
    assert(!card.Arm(nonce, std::string(1025, 'x')));
    assert(card.Arm(nonce, "native-private-token"));
    assert(card.Active(nonce));
    assert(!card.Active(other));
    assert(!card.Take(other, code, result));
    assert(result == "unchanged");
    assert(!card.Take(nonce, "invalid", result));
    assert(card.Active(nonce));
    assert(card.Take(nonce, code, result));
    assert(result == "native-private-token");
    assert(!card.Active(nonce));
    assert(!card.Take(nonce, code, result));
    assert(card.Arm(other, "new-token"));
    card.Clear();
    assert(!card.Take(other, code, result));
    assert(card.Arm(nonce, "old-token"));
    assert(card.Arm(other, "new-token"));
    assert(!card.Take(nonce, code, result));
    assert(card.Take(other, code, result));
    assert(result == "new-token");
    return 0;
}
