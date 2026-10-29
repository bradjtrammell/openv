/*
 * OpenV native FXServer Adaptive Card capability, bound to a single
 * connection nonce. No CEF or game dependency; portable C++17 contract.
 */
#pragma once
#include "OpenVConnectionRequest.h"
#include <string>
#include <string_view>
#include <utility>
namespace openv::admission
{
inline bool ValidCode(std::string_view code)
{
    if (code.size() != 43) return false;
    for (const char c : code)
    {
        if (!((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
              (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
    }
    return true;
}
class CardSession
{
    std::string nonce_;
    std::string token_;
public:
    bool Arm(std::string_view nonce, std::string_view token)
    {
        Clear();
        if (!connection::ValidNonce(nonce) || token.empty() || token.size() > 1024) return false;
        nonce_.assign(nonce.data(), nonce.size());
        token_.assign(token.data(), token.size());
        return true;
    }
    bool Active(std::string_view nonce) const
    {
        return !token_.empty() && nonce_ == nonce;
    }
    bool Take(std::string_view nonce, std::string_view code, std::string& token)
    {
        if (!Active(nonce) || !ValidCode(code)) return false;
        token = std::move(token_);
        Clear();
        return true;
    }
    void Clear() { nonce_.clear(); token_.clear(); }
};
}
