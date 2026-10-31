/*
 * OpenV native FXServer Adaptive Card capability, bound to a single
 * connection nonce. No CEF or game dependency; portable C++17 contract.
 */
#pragma once
#include "OpenVConnectionRequest.h"
#include <chrono>
#include <cstdint>
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
public:
    using Clock = std::chrono::steady_clock;
    static constexpr auto SubmissionWindow = std::chrono::seconds(60);
private:
    std::string nonce_;
    std::string token_;
    Clock::time_point armed_at_{};
public:
    bool Arm(std::string_view nonce, std::string_view token, Clock::time_point now = Clock::now())
    {
        Clear();
        if (!connection::ValidNonce(nonce) || token.empty() || token.size() > 1024) return false;
        nonce_.assign(nonce.data(), nonce.size());
        token_.assign(token.data(), token.size());
        armed_at_ = now;
        return true;
    }
    bool Active(std::string_view nonce, Clock::time_point now = Clock::now()) const
    {
        return !token_.empty() && nonce_ == nonce && now >= armed_at_ && now - armed_at_ < SubmissionWindow;
    }
    // CEF reloads cannot reset the original 60-second native card deadline.
    uint32_t RemainingMs(std::string_view nonce, Clock::time_point now = Clock::now()) const
    {
        if (!Active(nonce, now)) return 0;
        const auto remaining = SubmissionWindow - (now - armed_at_);
        return static_cast<uint32_t>(
            std::chrono::duration_cast<std::chrono::milliseconds>(remaining).count());
    }
    bool Take(std::string_view nonce, std::string_view code, std::string& token,
              Clock::time_point now = Clock::now())
    {
        if (!Active(nonce, now) || !ValidCode(code))
        {
            if (!token_.empty() && (now < armed_at_ || now - armed_at_ >= SubmissionWindow)) Clear();
            return false;
        }
        token = std::move(token_);
        Clear();
        return true;
    }
    void Clear() { nonce_.clear(); token_.clear(); armed_at_ = Clock::time_point{}; }
};
}
