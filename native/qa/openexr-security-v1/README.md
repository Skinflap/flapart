# OpenEXR 3.4.16 with upstream checker fix

This bundle prepares an isolated source candidate. It is not a qualified desktop release.

Download the source archive from the URL in `receipt.json`. Run:

```sh
python3 prepare.py --archive /path/to/openexr-3.4.16.tar.gz --work /new/private/directory
```

The helper verifies the archive and patch SHA-256 hashes, extracts with the Python data filter, applies the original upstream patch, and verifies the one changed file against its reviewed before/after hashes. It records a complete file/link content manifest and refuses existing destinations. Python with tar extraction filters and Git are required. It does not download dependencies, compile, install, or change any existing SDK.

The fix is upstream commit `6fedb3e3f7b120266550a848bcf302e11f950dc4`, addressing [GHSA-7qg8-w3rj-qxx9](https://github.com/AcademySoftwareFoundation/openexr/security/advisories/GHSA-7qg8-w3rj-qxx9). The resulting checker file is byte-identical to upstream v3.5.2. Original copyright, license and patent notices are retained; bundled dependency notices remain in the exact source archive.

Unpatched 3.4.16 passed all 140 upstream tests on the Linux development host. The exact patched arithmetic helper passed bounded UBSan checks. These checks do not establish platform package compatibility. Patched full-library testing, pinned Windows/macOS/Linux builds, actual EXR import/export, relocation, source delivery and final advisory review remain required before adoption. The original recipe's `NAMESPACE_VERSIONING` option is unused by this OpenEXR version; do not infer ABI compatibility from that flag or the shared SONAME alone.
