# Maintained image-library source inputs

Use Python 3.12 or newer and git:

```
python3 prepare.py libraw --archive /downloads/LibRaw-0.22.2.tar.gz --work /new/libraw
python3 prepare.py libde265 --archive /downloads/libde265-1.1.3.tar.gz --work /new/libde265
python3 prepare.py libheif --archive /downloads/libheif-1.23.6.tar.gz --work /new/libheif
```

`pins.json` contains upstream download URLs, exact archive hashes, original LibRaw recipe patch hashes, and full source manifest hashes. The helper refuses an existing destination, changed archive or changed patch. It checks every prepared source file/link against the exact inputs used by the Linux candidate builds. It never modifies the downloaded archive or an existing source tree. Original patches retain upstream whitespace and license notices.

Build libde265 before libheif. Set both CMake's prefix search and pkg-config search to the new decoder prefix before configuring libheif. Changing only the runtime library does not enable libheif's compile-time integration with the decoder security-limit API. In the Linux candidate, the resulting libheif imports `de265_get_security_limits`; both HEIC and AVIF round trips are tested with the exact new libraries mapped. Keep the unversioned `libde265.so` alias for existing consumers, alongside the new versioned aliases.

Native qualification covers pinned Linux builds and application import/export. Windows/macOS builds, source-delivery integration and relocated package testing remain separate requirements. Source preparation is not a security certification: historical OSS-Fuzz reports, including LibRaw OSV-2026-958 and libheif OSV-2020-2308/OSV-2023-1129, remain explicitly unresolved. Public desktop release is not authorized by these receipts.

License copies accompany this helper; consult the source headers and complete upstream archives for component-specific notices. Native notices must match the exact binaries and final source delivery.
