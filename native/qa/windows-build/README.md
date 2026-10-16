# Native Windows build qualification

These helpers build the pinned Flapart source with the same LLVM-MinGW compiler family as the official Qt 5 Windows dependency SDK. This is a source-build candidate, not a signed or qualified desktop release.

The parent repository workflow should explicitly provision full Python 3.13 (including development headers). The embedded Python archive alone is insufficient. `tools.lock.json` pins the upstream compiler, CMake, Ninja, and reference Python downloads; `prepare-tools.py` extracts only the portable build tools and never changes system PATH. The SDK lock contains 88 individually hashed official KDE archives. No Microsoft compiler installer is required.

Run `prepare-fork.py` on the exact clean upstream commit, `fetch-dependencies.py` into an isolated prefix, and `prepare-tools.py` into a separate tools directory. Then `build.py --source SOURCE --prefix SDK --build BUILD --tools TOOLS` compiles and installs there. `test-compiled.py --prefix SDK --probe native/qa/portable --output OUTPUT` requires a disposable native Windows CI account. It obtains real Windows Known Folders, seeds original Krita sentinels, and tests the independently named Flapart profile, native drawing pixels, PNG, KRA reopening, focus controls, fonts and palette.

`native-source-windows.yml` is a proposed manually dispatched workflow. The parent owns publishing it under `.github/workflows/` and provisioning Python. Retain test receipts/screenshots/build logs only. Do not upload the SDK or resulting binary application until corresponding-source and dependency-license closure, packaging, signing expectations and native runtime qualification are addressed. Physical tablet and broader hardware tests are not covered by this probe.
