# Maintained TLS native CI helpers

These helpers do not publish, modify the original SDK, install host packages, or run a VM. Use fresh paths in runner workspace. Native compilation remains unexecuted here. Copy the SDK first and retain the original until runtime validation passes.

## Pins and local checks already executed

- OpenSSL 3.5.9 source SHA256: 603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a. Parent's verified archive is native/distribution/sources/platform-closure/maintained-tls/openssl-3.5.9.tar.gz.
- CPython 3.13.16 full source: python-downloads/Python-3.13.16.tar.xz, SHA256 f4b1bfb3c79b5bb11b8d228a12504163b4c0dab4d679828d8f5f26b6cb6ab35d.
- Official Windows embedded runtime: python-downloads/python-3.13.16-embed-amd64.zip, SHA256 97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297.
- Both Python downloads matched their official published Sigstore digest. The signature itself was not verified; bundles retained for CI verification. URLs, sizes and hashes are in python.lock.json.
- Actual staging helper executed on Linux into windows-python-staged. PE inspection confirms _ssl/_hashlib import python313.dll and OpenSSL3 DLLs; bundled libcrypto reports OpenSSL3.5.9. This is artifact inspection, not Windows execution.
- All helpers passed py_compile. Static review caught Python framework installer defaults that can write /Applications; helper overrides FRAMEWORKINSTALLLAST and FRAMEWORKALTINSTALLLAST to frameworkinstallmaclib, avoiding app-menu/system unix tool installation.

## Windows runner

Provision exact LLVM-MinGW20251118 compiler bin, Perl and GNU make inside runner tools. Explicit paths avoid assumptions about shell/tool discovery. Use existing source/SDK qmake/private headers at Qt5.15.7.

```powershell
python build-openssl.py --archive $SSL_ARCHIVE --work $WORK/ssl-build --prefix $WORK/ssl-stage --toolchain $LLVM_BIN --perl $PERL --make $MAKE --jobs 3
python build-network-module.py --qmake $SDK/bin/qmake.exe --qtbase $QTBASE_COPY --openssl-prefix $WORK/ssl-stage --ssl-library $WORK/ssl-stage/lib/libssl.dll.a --crypto-library $WORK/ssl-stage/lib/libcrypto.dll.a --build $WORK/network-build --make $MAKE --jobs 3 --execute
python stage-windows-python.py --downloads $TLS_HELPERS/python-downloads --old-python $ORIGINAL_SDK/python --destination $WORK/python-new --site-packages $SDK/lib/site-packages
```

The staging helper verifies the corresponding full source too, preserves existing custom site scripts/path entries, adds the explicit PyQt site-packages path, and executes a Python/PyQt/SSL probe on Windows. It never copies old binary modules into the new Python tree. Integrator must place this whole runtime at the candidate SDK's intended Python root and ensure the application does not accidentally load an older python313.dll copied elsewhere. Development headers/import libs must remain cp313-compatible; final application probe is mandatory. Preserve custom application PYTHONPATH setup in the app launcher/source.

QtNetwork build helper is a targeted native experiment. If qmake reports absent generated build internals, configure the exact copied qtbase against the new OpenSSL and build its network target; do not copy unmatched QtCore/private headers. Record compiler/link command and inspect resulting imports before replacing candidate QtNetwork. No old OpenSSL DLL deletion until dependency scan shows no remaining consumer.

## Apple macOS runner

```sh
python3 build-openssl.py --archive "$SSL_ARCHIVE" --work "$WORK/ssl-build" --prefix "$WORK/ssl-stage" --jobs 3 --deployment-target 11.0
python3 build-network-module.py --qmake "$SDK/bin/qmake" --qtbase "$QTBASE_COPY" --openssl-prefix "$WORK/ssl-stage" --ssl-library "$WORK/ssl-stage/lib/libssl.3.dylib" --crypto-library "$WORK/ssl-stage/lib/libcrypto.3.dylib" --build "$WORK/network-build" --make make --jobs 3 --execute
python3 build-macos-python.py --archive "$TLS_HELPERS/python-downloads/Python-3.13.16.tar.xz" --openssl-prefix "$WORK/ssl-stage" --old-framework "$ORIGINAL_SDK/lib/Python.framework" --site-packages "$SDK/lib/site-packages" --work "$WORK/python-build" --prefix "$WORK/python-stage" --jobs 3 --deployment-target 11.0
```

OpenSSL is built for arm64 and x86_64 separately, merged with lipo, checked for both slices, given relocatable dylib IDs and ad-hoc signatures. Per-architecture generated headers are retained behind architecture dispatch where needed. Python is a full universal2 3.13.16 framework, deliberately chosen over patching 3.13.5 extensions alone: current CPython includes SSLContext/hostname-validation and standard-library security fixes. Existing cp313 PyQt and custom site configuration are retained/tested via explicit SDK site-packages. Both _ssl and _hashlib imports are checked to reject old1.1 dylibs.

Python needs real CA roots. The helper snapshots the native runner's system root certificates into the isolated OpenSSL ssl/cert.pem, without changing OS trust. Package integration must preserve a maintained CA strategy and relocate both default CA path and framework/dylib load commands; do not treat a CI absolute path as a distributable layout. Final ad-hoc/signing stage happens after all relocation. A fresh unpacked bundle must pass default-trust HTTPS without build-prefix environment variables.

## Required runtime gate

Run using candidate embedded Python with candidate PyQt/QtNetwork and its actual dynamic-library search paths:

```sh
CANDIDATE_PYTHON https-validation-probe.py --openssl CANDIDATE_OPENSSL --output tls-receipt.json
```

Checks actual loaded Python and Qt SSL versions >=3.5.9, trusted local CA/localhost success, untrusted CA rejection, hostname mismatch rejection, then separate Python and Qt requests to https://www.python.org/ with untouched default trust. No ignored SSL errors or global trust modification. Exceptions/timeouts fail. Local fixture keys are temporary and removed. To test the Ubuntu backported library use --minimum 3.0.2 plus independent exact package hash/BuildID gate. Before release add expired-certificate coverage and verify all package imports/load commands, both macOS slices, app plugin UI and archive relocation. Current helpers are not evidence of a completed native TLS build.
