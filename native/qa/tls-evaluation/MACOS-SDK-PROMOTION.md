# Maintained Mac build SDK

`promote-macos-sdk.py` operates on the private `WORK/sdk` produced by a
successful `run-native-ci.py` invocation. It does not modify the original SDK.
The full application must subsequently compile against that same private SDK.

The helper checks matching workspace/build receipts, both universal QtNetwork
variants, and every promoted native binary's architectures and imports. It
replaces OpenSSL headers, libraries, provider modules, CLI, certificate snapshot,
and development metadata together. It refuses remaining native consumers of
OpenSSL 1.1 before removing the old providers. Source and destination symlinks
must remain confined. Obsolete headers are removed; valid link chains are
created before output hashes are recorded.

This is build preparation, not final archive qualification. Build receipts do
not independently prove unchanged output binaries. The SDK still contains build
tools and foreign-platform assets from upstream development packages; this is
not a distributable application archive. The final bundle needs its own complete
inventory, source/notice mapping, actual application and Python/TLS tests,
relocation and installer tests, and final release approval checks.

`python test_promote_macos_sdk.py` exercises synthetic files with actual Mach-O
parsing. These tests do not execute native code. A separate read-only baseline
check confirmed that both retained upstream QtNetwork variants import old SSL.
No successful native SDK promotion is claimed yet.

The source workflow is being integrated to run maintained TLS preparation,
promotion, full source compilation, native artwork tests, packaging, and
relocation in one job. It is manually dispatched only; no automatic retry is
part of this workflow. Final packaged trust-store and runtime-probe integration
remain under review before dispatch.
