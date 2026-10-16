# Relocated maintained runtime test

`test-packaged-runtime.py` runs only in disposable Mac CI. It takes a completed
and signed `.app`, a pinned Python baseline receipt, a fresh evidence directory,
an archive output under `RUNNER_TEMP`, and explicit private build prefixes to
hide temporarily. The archive stays outside uploaded evidence.

The driver copies the bundle to a directory whose name contains spaces and
archives its exact files, executable permissions, and confined relative links.
It removes Python, Qt, compiler, dynamic-loader, certificate, and OpenSSL build
environment overrides. Production bundled startup code must supply any required
certificate/provider defaults; the test does not supply a special trust store.

While private build prefixes are unavailable, the real bundled interpreter runs
with `-I -B`, first as ARM64 and then as x86_64. The portable runtime probe checks
the archive hashes, extension baseline, actual loaded libraries, and HTTPS
verification. Its TLS child explicitly retains the requested Mac architecture.
Actual execution mode is recorded; Intel execution under Rosetta is not described
as physical Intel hardware testing. An unavailable architecture is a failed test,
not a skipped pass.

Prefixes are restored on ordinary probe failure. If another process recreates an
original prefix name, the driver preserves both copies and reports a conflict;
it never overwrites the new directory. These operations are restricted to private
runner temporary paths. Force-killing an entire runner cannot run Python cleanup,
which is why this driver is limited to disposable CI.

`test_packaged_runtime_driver.py` covers archive symlinks/permissions, escaping
links, environment cleanup, nested-prefix refusal, and failure/conflict recovery.
These portable tests do not qualify native execution. The driver also does not
replace application interaction, installer/upgrade testing, source/license
closure, signing/notarization decisions, or the final release gate.
