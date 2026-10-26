#pragma once
#include <cstdint>
#include <cstring>
#include <functional>
#include <type_traits>
#include <unordered_map>
namespace fx {
class ScriptContextBuffer {
    uint64_t data_[32]{};
    int count_ = 0;
public:
    template<class T> void Push(T value) {
        static_assert(sizeof(T) <= 8, "native argument exceeds 8 bytes");
        std::memcpy(&data_[count_++], &value, sizeof(value));
    }
    template<class T> T Arg(int index) const {
        T value{};
        std::memcpy(&value, &data_[index], sizeof(value));
        return value;
    }
    template<class T> void SetResult(T value) {
        std::memcpy(&data_[0], &value, sizeof(value));
    }
    template<class T> T GetResult() const { return Arg<T>(0); }
    void* GetResultBuffer() { return data_; }
    void SetVector(float x, float y, float z) {
        std::memcpy(&data_[0], &x, sizeof(x));
        std::memcpy(&data_[1], &y, sizeof(y));
        std::memcpy(&data_[2], &z, sizeof(z));
    }
};
using TNativeHandler = std::function<void(ScriptContextBuffer&)>;
struct ScriptEngine {
    static inline std::unordered_map<uint64_t, TNativeHandler> handlers;
    static TNativeHandler GetNativeHandler(uint64_t hash) {
        const auto it = handlers.find(hash);
        return it == handlers.end() ? TNativeHandler{} : it->second;
    }
};
}
struct FxNativeInvoke {
    template<class R, class... Args>
    static R Invoke(const fx::TNativeHandler& handler, Args... args) {
        fx::ScriptContextBuffer context;
        (context.Push(args), ...);
        handler(context);
        if constexpr (!std::is_void_v<R>) return context.GetResult<R>();
    }
};
