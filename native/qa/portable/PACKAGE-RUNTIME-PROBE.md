# Candidate runtime provenance probe

`package-runtime-probe.py` must run with the candidate's embedded Python after
fresh archive extraction or an actual installed-launcher test. It refuses host
Python (both executable and base prefix must resolve under the candidate root).
It also requires `sys.flags.isolated == 1` and every nonempty `sys.path` entry to
resolve inside the candidate root before importing baseline/PyQt modules. Use `-I`;
a genuinely isolated Windows `._pth` runtime is also accepted. Bundled sitecustomize
remains allowed; external PYTHONPATH/SDK pure-Python paths are refused. The TLS
child is explicitly invoked with `-I`.
It does not perform installation, draw artwork, launch Krita, or qualify a release.

Example, using paths determined by actual packaging:

```sh
"$CANDIDATE_PYTHON" -I package-runtime-probe.py \
  --archive candidate.zip --runtime-root extracted \
  --baseline-extension-manifest baseline.json \
  --baseline-extension-sha256 "$REVIEWED_BASELINE_SHA256" \
  --openssl "$CANDIDATE_OPENSSL" --output new-receipts \
  --runtime-scope relocated-package --target-platform macos-universal2
```

The runtime root is the archive extraction root, **not** the `.app` directory when
archive entries include `Flapart Studio.app/`. Windows archives include
`Flapart-Studio/`. Installed trees must retain that same relative layout. The
output directory must be new. No runtime files are extracted or rewritten.
The baseline is explicitly hash-pinned JSON with `extensions: [module names]`;
`extension_modules.baseline` is also accepted. All entries are actually imported
and must be native extension modules or built-in modules. Candidate coverage here
means the imported baseline, not an exhaustive inventory of additional modules.

The probe checks every archived regular file and symlink against the runtime,
then rechecks loaded candidate binary hashes. It refuses path escapes, substituted
files, host/SDK dependencies, missing baseline extensions, and mismatched archive
bytes. It hashes the archive before and after execution. Generated Python caches
outside the archive are not claimed as release files.

The unchanged shared `../tls-evaluation/https-validation-probe.py` runs in a child
of the same embedded interpreter. Its actual TLS process's module mappings are
captured after its checks. Parent extension-import mappings are audited separately
and cannot fill missing child TLS libraries. Core interpreter identification
excludes Windows `python3.dll` stable ABI shims, Python executables, and PyQt's
QtNetwork extension wrappers. System imports are restricted to documented OS
locations: Windows System32/SysWOW64, macOS `/usr/lib` and `/System/Library`, and
Linux `/usr/lib`, `/lib`, `/lib64`. System paths and available file hashes are
recorded; macOS shared-cache-only images explicitly have no on-disk hash. SSL,
crypto, Python core, and QtNetwork runtime libraries must come from the candidate.

`--https-proxy http://host:port` enables explicit HTTP CONNECT transport for urllib
and Qt without changing certificate trust. It accepts no embedded credentials.
Loopback certificate fixtures bypass the proxy. The optional `--official-url`
must be HTTPS (enforced by the shared helper). `--tls-helper` supports a relocated
copy of that unchanged helper; its exact hash is recorded for review. No system
trust store, security approval, or global proxy setting is modified.

Outputs:

- `tls-raw.json`: unchanged shared helper result.
- `tls-maps.json`: actual TLS child paths and process/hardware/translation metadata.
- `tls.json`: helper result with exact archive/platform binding and loaded-library
  paths/hashes, matching the final freeze TLS fields where measured.
- `python.json`: actual version, SOABI, ABI, baseline imports, and core library
  mapping. Deliberately omits `native_plugin_imports_passed`; a separate actual
  Krita app probe must provide that evidence before final release review.
- `provenance.json`: separate child/parent mapped files and system paths, with
  `release_qualified: false` and `app_probe_required: true`.

Failure exits nonzero; some failures happen before output creation. Native Windows archive-bound execution passed in the retained Windows 11 VM
(`windows-vm/maintained-runtime-v4-evidence`) for candidate SHA256
`8a3ff3117f6674c6864b1c38ab59e3537cf5b904ec841600afb838bfb8216225`.
This does not qualify a future changed archive or establish Mac execution. The current TLS helper
requires OpenSSL >=3.5.9, so this tool does not qualify Linux's separately reviewed
Ubuntu backport runtime. Existing SDK receipts cannot substitute for final archive
runs. Relocation, installed upgrades, app artwork/plugin tests, source closure,
and both process architectures for universal Mac remain separate release gates.

Focused local verification:

```sh
python test_package_runtime_probe.py
```

These 28 synthetic provenance tests include actual host-Python refusal but do not
claim candidate native execution, successful TLS, or completed release evidence.

Windows permits exactly the measured Python/Qt OpenSSL pair layout: the
`python/lib{ssl,crypto}-3.dll` pair and `bin/lib{ssl,crypto}-3-x64.dll` pair
inside the same archive root. Every loaded member retains its archive hash.
Other duplicate runtime roles fail closed. The only additional non-System32
OS-module exception is the actual `ProgramFiles/Windows Defender/MpOAV.dll`
KnownFolder location. Each run requires a valid default-trust Microsoft Windows
signature and matching before/after hash; the signature and system verifier
identity are retained in provenance. Defender is never disabled.
