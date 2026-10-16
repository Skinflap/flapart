# Flapart native macOS build helpers

These source-only helpers are for a disposable actual macOS CI runner. They do not
publish applications, enroll accounts, sign, notarize or claim qualification before
the runner produces a passing receipt. Upstream source is pinned in the root native
UPSTREAM.json and must first receive scripts/prepare-fork.py.

1. `fetch-dependencies.py --prefix <workspace>/sdk --cache <workspace>/cache`
   downloads81 official KDE Qt5 dependency archives (~2.4GB), verifies the frozen
   size/SHA256 lock, and safely extracts them. The lock is the latest stable master
   snapshot before the exact upstream release pipeline timestamp; it preserves
   recipe commits for source attribution. Runtime redistribution still needs full
   corresponding-source/license closure. The lock is not itself corresponding source.
2. `build.py --source <prepared-source> --prefix <workspace>/sdk --build <workspace>/build --jobs 2`
   builds for the native runner architecture using the SDK's embedded Python and
   upstream-compatible configuration. On Intel the deployment target is10.15;
   arm64 uses11.0. This does not create a signed/notarized release bundle.
3. With `CI=true`, run `test-compiled.py --prefix <workspace>/sdk --probe <native>/qa/portable --output <fresh-output>`.
   It locates the installed app, prepares only the disposable runner's Flapart
   preferences/resources, seeds (or hashes existing) original Krita sentinels,
   runs the actual app with SDK libraries, validates the portable functional probe
   and verifies original Krita files were preserved. Never run this harness on a
   person's normal macOS profile. Save logs, result.json, qualification.json and
   studio.png as test evidence; do not upload the built.app as a release yet.

Upstream reference: build-tools/ci-scripts/macos.yml,
packaging/macos/macos-deploy.py, and
https://invent.kde.org/packaging/krita-deps-management/-/blob/master/tools/macos-toolchain-krita.cmake.
The upstream full pipeline includes private signing/notary/upload steps; those are
intentionally absent here. Use the local reviewed source mirror rather than blindly
executing the upstream publishing pipeline.

The SDK lock follows the pinned upstream dependency seed and recursively includes build/runtime dependencies. Registry leftovers are excluded. Extraction checks every archive path before writing, rejects differing file collisions, and allows only the reviewed macOS Python framework directory alias. The dated SDK snapshot is our reproducible build input; it is not asserted to be the exact historical release SDK.
