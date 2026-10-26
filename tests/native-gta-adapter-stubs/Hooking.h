#pragma once
#include <functional>
#include <vector>
struct OpenVTestFrameEvent {
    std::vector<std::function<void()>> handlers;
    void Connect(std::function<void()> fn) { handlers.push_back(std::move(fn)); }
    void Fire() { for (const auto& fn : handlers) fn(); }
};
inline OpenVTestFrameEvent OnGameFrame;
struct InitFunction {
    explicit InitFunction(std::function<void()> fn) { fn(); }
};
