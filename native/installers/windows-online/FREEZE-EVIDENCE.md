# Final native release evidence

This contract applies to both `windows-online/freeze-release.py` and the identical
`macos-online/freeze-release.py`. It does not apply to CI-only candidate assembly.
Running synthetic contract tests is not native runtime qualification. No currently
available SDK-stage receipt satisfies the final release contract.

Run `python native/installers/windows-online/test_freeze_release.py` to test both
copies. The suite uses explicitly synthetic archives and evidence. It accepts
complete Windows/universal Mac fixtures and rejects missing, mismatched, obsolete,
or failed evidence, invalid binary headers, and unsafe/cyclic/dangling symlinks.

## Inputs and binding

The top-level evidence JSON has `schema: 2`, `payload_sha256`, `platform`,
`profile_namespace: "flapart-native"`, and `receipts`. Mac also records actual
`signature` (`unsigned`, `adhoc`, or `developer-id`); this does not imply notarization.
Every receipt reference is `{ "path": "relative.json", "sha256": "..." }`, resolved
inside the evidence directory. Referenced bytes must match their digest. Every
receipt must pin `payload_sha256` and canonical `target_platform` to the exact
archive being frozen. Evidence hashes preserve reviewed captures; they are not
cryptographic proof that arbitrary submitted test claims are true.

`receipts` has exactly these keys:

- `inventory`: one reference. Requires `platform`, `runtime_collected: true`, and
  `files` covering the complete archive. Regular files have `path`, `bytes`, and
  `sha256`. Native files also have `architectures` and `native_dependencies`.
  Architecture claims are checked against PE/Mach-O CPU headers and universal
  slices. Legacy OpenSSL imports are refused. Mac symlinks use the existing
  inventory shape `{path, symlink}` and must match ZIP link bytes, remain inside
  the app bundle, and resolve without cycles or dangling targets.
- `source_closure`: one reference. Requires `complete: true`, `artifacts` entries
  `{kind, path, sha256}`, and `native_sources`, mapping **every packaged native
  archive path** to artifact references. Each binary requires corresponding
  reviewed `source`, `license`, and `recipe` artifacts whose bytes are hashed.
  System imports are outside this packaged-binary mapping. A generic source ZIP
  is insufficient unless review establishes corresponding source for each mapped
  binary and its dependencies.
- `relocation`, `installer`, `tls`, `python`: each an array with one reference for
  every executed process architecture. Each has `process_architecture` reported
  by the actual child runtime, `hardware_architecture`, `execution_mode` (`native`
  or `translated`), `native_execution: true`, and `runtime_scope` (`relocated-package`
  or `installed-runtime`). Rosetta x86_64 execution on arm64 hardware is allowed
  and retained as translated execution in the resulting manifest.

`macos-universal2` inventory maps explicitly to installer `macos-universal`.
Every native file must contain arm64 and x86_64 slices, and all four runtime
receipt categories need both process architectures. Physical Intel hardware is
not required; translating a real x86_64 process qualifies when accurately labeled.

## Required runtime results

Relocation requires `relocated_package_test`, `compiled_fork`,
`original_krita_sentinels_preserved`, and `build_environment_absent`, all true.

Installer scope must be `installed-runtime`; the actual installed launcher must
produce true results for `installer_passed`, `native_runtime_tested`,
`profile_isolation_verified`, `ordinary_krita_unchanged`,
`native_canvas_png_kra_passed`, `studio_menu_reopens`,
`failed_upgrade_preserved_receipt`, `failed_upgrade_preserved_artwork_and_settings`,
`successful_upgrade_preserved_artwork_and_settings`, and `previous_runtime_retained`.
`security_approval_automated` must be false. These checks do not claim the downloaded
Gatekeeper/SmartScreen user approval flow was tested.

TLS requires `passed`, `python_openssl` and `qt_openssl_runtime` at least 3.5.9,
plus actual Python and Qt controlled-certificate results in `cases`: `valid`,
`unknown_ca`, `hostname_mismatch`, and `expired`. Failures must be certificate
rejections, including Python verify code 10 and Qt error code 6 for expiry.
`official_python` and `official_qt` prove real HTTPS with default trust.
`loaded_libraries` entries `{role, archive_path, sha256}` bind actual mapped
`ssl`, `crypto`, `python_ssl`, and `qt_network` libraries to packaged native files.
The precise case fields follow the shared HTTPS probe and checks in the script.

Python requires `passed`, `version` at least 3.13.16 within the 3.13 series,
`abi: "cp313"`, actual `soabi` (`cp313-win_amd64` or `cpython-313-darwin`), and
`native_plugin_imports_passed`. `extension_modules` has nonempty `baseline`,
`candidate` containing all baseline modules, and empty `missing`.
`interpreter_library: {archive_path, sha256}` binds the loaded interpreter to the
package. Refreshed SDK-only tests do not satisfy this gate.

## Remaining producer work

Final packaging adapters must bind inventories after archive creation, collect
native dependency imports, assemble reviewed per-binary source closure, and capture
actual relocated/installed runs with process/hardware metadata and loaded-library
hashes. Existing CI E2E output needs the explicit failed-upgrade artwork/settings
result and the common binding fields. Existing TLS/Python SDK receipts must be
rerun against the exact final archive. There is no complete source-closure producer
or qualified Windows/Mac manifest yet; the final freeze correctly refuses them.
