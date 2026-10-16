# Completing the maintained macOS runtime

Status: portable planning and mutation-failure tests pass. **Native execution,
TLS, signing and distribution remain unvalidated by this helper.** No change to
package-candidate.py or CI is included. This is a post-collector, pre-signing step.
Run on the collector's final `Flapart Studio.app` before codesign and inventory.

```
python3 complete-maintained-runtime.py \
  --bundle '/output/Flapart Studio.app' --sdk /private/tls-work/sdk \
  --private-prefix /private/tls-work/python-stage \
  --private-prefix /private/tls-work/openssl \
  --openssl-license /private/tls-work/openssl-build/arm64/openssl-3.5.9/LICENSE.txt \
  --python-license /private/tls-work/python-build/Python-3.13.16/LICENSE \
  --certificate-sha256 HASH_FROM_PYTHON_BUILD_RECEIPT \
  --output /output/maintained-runtime.json --apply
```

Without `--apply`, the helper stages a disposable full bundle copy, plans all
mutations and returns a non-completion receipt. With `--apply`, Darwin is required;
checked native operations occur on that private sibling, static validation must
pass, and only then is the original bundle replaced. Existing signature hashes
become invalid: signing and final inventory must follow. Do not run twice.
The SDK and existing system trust are never changed. Inputs must come from the
passed maintained-runtime promotion, not an arbitrary similarly named SDK.
License arguments are complete source-license files, not generated summaries;
source/archive provenance and all other dependency licenses remain the enclosing
release closure's responsibility. Neither argument nor PEM content is printed.

## Collected paths

| SDK source | Final bundle-relative destination |
|---|---|
| `lib/Python.framework/Versions/3.13/Resources/Python.app` | `Contents/Frameworks/Python.framework/Versions/3.13/Resources/Python.app` |
| `bin/openssl` | `Contents/MacOS/openssl` |
| `lib/libssl.3.dylib`, `lib/libcrypto.3.dylib` | `Contents/Frameworks/` |
| `lib/ossl-modules/` | `Contents/Frameworks/ossl-modules/` |
| `ssl/cert.pem` | `Contents/Resources/openssl/cert.pem` |
| explicit OpenSSL / CPython source licenses | `Contents/Resources/licenses/maintained-runtime/OpenSSL-LICENSE.txt`, `CPython-LICENSE.txt` |

The real interpreter is
`Contents/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python`.
The framework's `bin/python3.13` is CPython's pythonw launcher, which needs that
nested app. Upstream deployment deletes it. Restoration retains its Info.plist
and executable; both real interpreter and launcher need native qualification.

## Relocation contract

The existing source-qualification Mach-O parser reads every architecture slice.
Every packaged native binary must be universal arm64+x86_64. The helper resolves
non-system dependencies only to actual bundled Mach-O files, rejects missing or
ambiguous suffix matches (including confined symlink aliases), old SSL1.1 imports, escaping symlinks and unknown absolute
imports. Absolute imports can map only from explicitly approved private roots
(`--sdk` is automatically approved), and only their lib/bin/plugins subtrees.
Explicit loader-relative references must resolve inside the bundle. An
`@executable_path` import in MH_EXECUTE uses that executable's own directory,
including nested Python.app. For a library, possible bundled executable contexts
are enumerated and a missing/ambiguous target fails. Absolute system imports with
`..` traversal are rejected rather than treated as a trusted system path.

Resolved imports become explicit per-binary `@loader_path/...` dependencies.
All rpaths are removed. This also removes the private OpenSSL path deliberately
compiled into maintained CPython. Slice-dependent rpaths fail closed rather than
issuing ambiguous universal edits. MH_DYLIB identities are normalized; MH_BUNDLE provider modules do not receive a
dylib ID operation.
Commands use argument arrays and check return status; spaces in app/path names
remain single arguments. The final parser pass permits only system imports or
existing loader-relative bundled files. It does not substitute for dyld runtime
mapping, per-architecture application execution or signed-package checks.

## Narrow build-asset exclusion

The pinned SDK contains 15 Windows redistribution DLLs under
`Python.framework/Versions/3.13/lib/python3.13/site-packages/pyqtbuild/bundle/dlls/`:
four OpenSSL1.1 DLLs in `openssl-32`/`openssl-64`, and eleven MSVC runtime DLLs in
`msvc-32`/`msvc-64`. The helper removes only those explicitly enumerated names,
requires their PE signature, and records every removed path/hash. An unreviewed
file in that directory fails before any deletion. PyQt5 bindings are preserved.
Foreign native files anywhere else remain errors; this is not a general PE skip.
This list was verified read-only against the pinned local audit SDK.

## Default trust and providers

A generated stdlib `sitecustomize.py` runs during normal Python startup, including
`-I` (which excludes user site, not the interpreter's site initialization).
It computes paths from its own packaged location and supplies defaults for:

- `SSL_CERT_FILE`: bundled, hash-pinned OS-root snapshot from maintained build.
- `SSL_CERT_DIR`: bundled empty certs directory, avoiding obsolete build defaults.
- `OPENSSL_MODULES`: bundled provider directory.
- `OPENSSL_CONF`: bundled minimal configuration, retaining OpenSSL's automatic
  default provider and **not activating the legacy provider**.

Existing upstream sitecustomize source is retained as a separate imported module,
so future imports remain syntactically legal and site-path setup is preserved.
Missing bootstrap assets abort interpreter startup. User-supplied environment
values remain explicit overrides; the qualification driver must clear SSL_CERT_*,
OPENSSL_*, PYTHON*, DYLD_* and build paths before launch. No test CA enters these
defaults; certificate and hostname verification are unchanged. The root snapshot
has a documented freshness obligation; a future release must refresh it through
the maintained build rather than treating this frozen snapshot as perpetual trust.

The TLS helper's OpenSSL subprocess inherits these production Python defaults.
A directly launched OpenSSL CLI does not execute sitecustomize: native load paths
are fixed, but its compiled config/provider defaults still reference the build
prefix. The builtin default provider needs no external module. If standalone CLI
use or native C++ operations require dynamic providers, production startup must
set an application-local module/config location (or use the OpenSSL provider API)
before loading providers. Do not add this as a QA-only environment workaround.
Qt's normal system-root trust remains untouched and needs real native HTTPS tests;
this helper does not change C++ startup or claim Qt trust qualification.

## Qualification still required

Create the final signed ZIP first; unpack elsewhere under a path containing spaces,
hide/remove the original build prefixes, then run the archive-bound
`package-runtime-probe.py` with this exact real interpreter, `-I -B`, and the bundled
OpenSSL CLI. Test actual arm64 and x86_64/Rosetta processes, baseline extensions,
Python+Qt official HTTPS and controlled rejection cases, mapped native hashes,
application launch/paint/save/reopen, and signature validity. No runtime receipt
may claim success merely because this portable planner passes.

Portable tests:
`python3 -m unittest discover -s native/qa/macos-build -p test_complete_maintained_runtime.py -v`
They use real thin/fat Mach-O command encoding and the existing parser, plus
isolated host-Python bootstrap execution; they do not emulate successful dyld or
install_name_tool mutation.
