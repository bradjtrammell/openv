/*
 * OpenV first-party NUI connection request validation.
 * Keep the wire nonce separate from game ownership and admission credentials.
 * This header deliberately depends only on the C++17 standard library.
 */
#pragma once

#include <cstddef>
#include <string_view>

namespace openv::connection
{
inline bool ValidNonce(std::string_view nonce)
{
    if (nonce.size() != 32) return false;
    for (const char c : nonce)
    {
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    }
    return true;
}

inline bool ValidPort(std::string_view port)
{
    if (port.empty() || port.size() > 5) return false;
    unsigned int value = 0;
    for (const char c : port)
    {
        if (c < '0' || c > '9') return false;
        value = value * 10 + static_cast<unsigned int>(c - '0');
    }
    return value >= 1 && value <= 65535;
}

inline bool ValidEndpoint(std::string_view endpoint)
{
    if (endpoint.empty() || endpoint.size() > 255) return false;
    std::string_view host = endpoint;
    if (endpoint.front() == '[')
    {
        const auto closing = endpoint.find(']');
        if (closing == std::string_view::npos || closing < 3) return false;
        host = endpoint.substr(1, closing - 1);
        unsigned int colons = 0;
        for (const char c : host)
        {
            if (c == ':') { ++colons; continue; }
            if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
                  (c >= 'A' && c <= 'F') || c == '.')) return false;
        }
        if (colons < 2 || host.find(":::") != std::string_view::npos) return false;
        const auto suffix = endpoint.substr(closing + 1);
        return suffix.empty() || (suffix.front() == ':' && ValidPort(suffix.substr(1)));
    }
    const auto colon = endpoint.find(':');
    if (colon != std::string_view::npos)
    {
        if (endpoint.find(':', colon + 1) != std::string_view::npos) return false;
        host = endpoint.substr(0, colon);
        if (!ValidPort(endpoint.substr(colon + 1))) return false;
    }
    if (host.empty() || host.size() > 253 || host.front() == '.' || host.back() == '.') return false;
    std::size_t labelStart = 0;
    bool numeric = true;
    for (std::size_t i = 0; i <= host.size(); ++i)
    {
        if (i == host.size() || host[i] == '.')
        {
            const auto label = host.substr(labelStart, i - labelStart);
            if (label.empty() || label.size() > 63 || label.front() == '-' || label.back() == '-') return false;
            labelStart = i + 1;
        }
        else
        {
            const char c = host[i];
            if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '-' || c == '_')) return false;
            if (c != '.' && (c < '0' || c > '9')) numeric = false;
        }
    }
    if (numeric)
    {
        unsigned int octets = 0;
        std::size_t begin = 0;
        for (std::size_t i = 0; i <= host.size(); ++i)
        {
            if (i == host.size() || host[i] == '.')
            {
                const auto label = host.substr(begin, i - begin);
                unsigned int value = 0;
                for (char c : label)
                {
                    value = value * 10 + static_cast<unsigned int>(c - '0');
                    if (value > 255) return false;
                }
                ++octets;
                begin = i + 1;
            }
        }
        if (octets != 4) return false;
    }
    return true;
}
/*
 * Bracketed IPv6 literals and JSON connection envelopes both begin with '['.
 * Only a JSON string array contains quotes; a raw IPv6 endpoint never does.
 * Preserve legacy direct IPv6 connections while requiring the first-party
 * NUI envelope to pass strict JSON, nonce and endpoint validation.
 */
inline bool IsStructuredConnectEnvelope(std::string_view input)
{
    return !input.empty() && input.front() == '[' &&
        input.find('"') != std::string_view::npos;
}

}
