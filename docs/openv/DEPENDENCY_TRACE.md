# OpenV — upstream runtime dependency trace

Status: **source-reviewed; builds and behavior not yet verified**. Last review: 2026-10-14.

This is engineering research for compatibility and preservation, **not** a claim that the fork is independently operable or that restricted components may be redistributed. Keep upstream LICENSE, LICENSES, THIRD_PARTY_NOTICES, and authorship intact. The parent license applies to the majority of the source; specifically enumerated paths are LGPL v2.

## Confirmed server call sites

| Location | Existing behavior | Required investigation |
|---|---|---|
| `code/components/citizen-server-impl/src/InitConnectMethod.cpp:100-170` | Retrieves and caches verification public key at `CNL_ENDPOINT "api/ticket/pubkey"` | Determine endpoint configuration and authorized OpenV ticket verification integration |
| `InitConnectMethod.cpp:214-290` | Decodes binary `cfxTicket2`, validates expiry, GUID, replay and RSA/SHA-1 signature | Design versioned community-issued ticket; preserve replay defense, expiry and audience checks |
| `InitConnectMethod.cpp:637-699` | Demands `cfxTicket2` for non-LAN connections | Verify authorized new client+server flow end-to-end |
| `InitConnectMethod.cpp:1215-1265` | Invokes registered `ServerIdentityProviderBase::RunAuthentication` handlers | Review OpenV provider interface, trust/variance and deferrals |
| `code/components/citizen-server-impl/src/EndPointIdentityProvider.cpp:101` | POST `https://cfx.re/api/validateSource/?v=1` | Preserve reverse-proxy/source-IP security semantics |
| `code/components/citizen-server-impl/src/ServerNucleusMock.cpp:71-151` | Uses `sv_licenseKeyToken` and `ServerLicensingComponent::GetNucleusToken()`; POST `https://cfx.re/api/register/?v=2`; emits `_cfx_internal:nucleusConnected` and initializes `web_baseUrl` | Trace internal event consumers and authorized registration replacement |
| `code/components/citizen-server-impl/src/LicenseIdentityProvider.cpp` | Processes entitlement data and license identifiers | Map player identity migration; do not impersonate original entitlements |
| `code/components/citizen-server-impl/src/SteamIdentityProvider.cpp` | Optional Steam authentication | Preserve optional behavior |

## Confirmed client call sites

| Location | Existing behavior | Required investigation |
|---|---|---|
| `code/components/net/src/NetLibrary.cpp:927-960` | Prepares `initConnect` POST map (protocol/game build/guid) | Keep compatible fields |
| `NetLibrary.cpp:1639-1641` | POST to server `/client` | Preserve handshake transport |
| `NetLibrary.cpp:1658-1694` | Optionally requests Steam ticket | Preserve optional provider |
| `NetLibrary.cpp:1850-1884` | Reads `sv_licenseKeyToken` and calls `OnInterceptConnectionForAuth` to supply POST fields | **Unresolved:** locate hook subscriber/provider implementation and source availability |
| `code/client/launcher/Bootstrap.cpp:84-140` | Uses `CFX_UPDATER_URL` for bootstrap manifest | Design independent distribution with signed artifacts |
| `code/client/launcher/Updater.cpp:257-535` | Fetches manifest and content objects | Reproducible builds, integrity and rollback |
| `code/client/launcher/GameCache.cpp` | Refers to Cfx-hosted game/runtime mirrors | Inventory each asset and its redistribution rights; use legitimate installed game assets when supported |

## Precompiled-component risk

`code/components/legitimacy/{debug,release}/` contains `legitimacy.dll` and `legitimacy.lib` while its metadata lists runtime dependencies. Linux reference artifact includes `libsvadhesive.so`. Presence of binaries is **not** evidence that their implementation can be rebuilt or lawfully modified. Confirm build inputs, upstream rights, and linkage.

## Preserve unchanged unless proven necessary

Game networking/OneSync; native bindings; Lua/JS/C# scripting; resource manifests and exports; NUI; asset streaming; Mumble; existing multiplayer wire protocol; GTA ownership and legitimate entitlement checks.

## Still unverified

1. Subscriber implementation for `OnInterceptConnectionForAuth` and full client-side ticket issuance.
2. Source-to-binary reproducibility and exact artifact revision.
3. `ServerLicensingComponent`/svadhesive lifecycle and required licensing semantics.
4. Consumers of `_cfx_internal:nucleusConnected` / `web_baseUrl`.
5. Complete native/build-time/network request inventory including dynamic URLs.
6. Independent authorized Windows client and Linux server builds and runtime traces.
7. Existing resource compatibility, escrow licensing, database identifier migrations and load tests.

## Acceptance evidence

Record exact commit SHAs, build logs, hashes, startup/network captures from a permitted test environment, automated compatibility tests, and no unexpected dependencies. **No authorization bypasses or endpoint changes should be merged without licensing review.**
