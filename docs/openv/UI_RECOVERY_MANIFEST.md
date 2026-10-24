# Verified first-party UI recovery — 2026-10-24

- Recovered local UI Git head: `543c6e559e782ba20c381ea4cd89ff0a1d3eb67d`.
- Remote baseline: `24c104f061771726a24d7eed18d2e51649037aed`.
- Remote implementation commit: `b898380d4de1bd002e69f2833bc76ac1c63796af`.
- Existing upstream `.gitignore` preserved, not replaced with the smaller recovered overlay.
- All 20 recovered paths and SHA-256 digests verified against the checked-out Git history before transfer.

| Status | File | Recovered SHA-256 |
| --- | --- | --- |
| IMPORTED | `.github/workflows/openv-ui.yml` | `477ef24dc3e92e435f3d1b132f7e6b2814053d761b63fc3097461f373c345994` |
| IMPORTED | `.github/workflows/openv-windows-client.yml` | `592af04f8c90e36658548a050641e9f603aedff91d67fce06e124bdfceb99474` |
| PRESERVED REMOTE | `.gitignore` | `27649bd2b192c0c1792c7ce07e7e54be32deeb88a6fb329c1161a0420573e470` |
| IMPORTED | `DEVELOPMENT_LOG.md` | `51700854b3205d9bbf1a4541a27f63956457ab98e8f34e6acc0a1deb719a6442` |
| IMPORTED | `ext/ui-build/README.md` | `49f084c8b5955d48400e3c6b12de84256d009a4a3d36cb16165f8875281b2b75` |
| IMPORTED | `ext/ui-build/build.cmd` | `5ef1d624debfa0b8bf29d786f6d07fab8463341857f4be6d50cea0e6d6a073b8` |
| IMPORTED | `ext/ui-build/data/app/app.js` | `8a614738e912abf34644cc5d9df5c5a6227bf5952fc30d129b60379db218f1db` |
| IMPORTED | `ext/ui-build/data/app/index.html` | `fcb6c890eeba5d9cf595e8f86fa2af138cd0f81b7b846f8d7df87461ede55e0f` |
| IMPORTED | `ext/ui-build/data/app/styles.css` | `b59fa5c1ed95401a4517f45f79b6d9d812926f7488610099e8ccb8ea75636cdc` |
| IMPORTED | `ext/ui-build/data/root.css` | `6591f359386aca44eea689b132636ea53b4490ee34363b7e8f0dd0c5489087be` |
| IMPORTED | `ext/ui-build/data/root.html` | `1aa958ecf4f1de2779bb004c3645e8804aead3972291795881a3ff0a80cf4d57` |
| IMPORTED | `ext/ui-build/data/root.js` | `11d09acf2120eb00d1fb9fba413b9fe8ad5a229ebd32b0841e277f2350adddd8` |
| IMPORTED | `ext/ui-build/loadscreen-fallback/code.js` | `d56af579bcff3b853612055707175fc4c45038c423a20cb61a343912f233baad` |
| IMPORTED | `ext/ui-build/loadscreen-fallback/index.html` | `302f4c6f76655ef7969455184d6bd7b9eec2d356a2091f5cc26add28fc6f0944` |
| IMPORTED | `ext/ui-build/loadscreen-fallback/styles.css` | `7cc81d5f832605c1584238ec01aaf6ea8dc7d83a3a6e911123756f0b55c2721a` |
| IMPORTED | `tests/test_openv_runtime_audit.py` | `a4db4d1df0fe4889b5105ce135e766f78446fde129fa1aeaf5a14e5df184dfa4` |
| IMPORTED | `tests/test_openv_ui.py` | `0d0abf207d58b8a5dddb06f4f0210d3eb4cb12651e8da8ab56b9c69c3fe1d911` |
| IMPORTED | `tests/test_openv_ui_browser.py` | `f6cf2771be7159c07d8d956431d29393f0144eecb32779f897e1522a2cd81438` |
| IMPORTED | `tools/audit_openv_runtime.py` | `cde27bf31609cf274ddaaf306fd60877abe67acfbf6191c18838b67b59f9d7b1` |
| IMPORTED | `tools/build_openv_ui.py` | `ee4ba0b986c721dcdc7888b5df651865aab1937bff496c579a9141a2c7e93142` |
