# Reviewable native source-closure producer

This isolated producer reads a candidate ZIP and its pinned evidence. It never
executes binaries, downloads sources, changes existing SDK/mirror data, or publishes
anything. Missing source mappings, notices, imports, or build provenance produce
`complete: false`, an explicit `unresolved` list, and exit code 2. Invalid archive
bytes/input hashes fail before a result. A complete source result is **not** native
runtime or release qualification (`release_qualified` is always false).

```sh
python qualify_sources.py --archive candidate.zip --sha256 ACTUAL_REVIEWED_SHA256 \
  --platform macos-universal2 --inputs inputs.json \
  --evidence-root reviewed-bundle --output new-results
```

Supported canonical platforms are `windows-x86_64`, `macos-x86_64`, `macos-arm64`,
and `macos-universal2`. The output directory must not exist. The archive is hashed
before and after processing; its entire regular-file/symlink inventory must match.
`inventory.json` is enriched with native metadata parsed from actual archive bytes,
including per-slice dependencies. `source_closure.json` supplies final freeze
schema2 fields `payload_sha256`, `target_platform`, `complete`, `artifacts`, and
`native_sources`, plus correspondence and unresolved detail. Retain final reviewed
receipts and referenced artifacts under the same evidence root used by the freeze
manifest; artifact paths remain relative to that root, not the output directory.

## Input bundle

`inputs.json` has exactly seven keys, each a `{path, sha256}` reference:

- `inventory`: actual package inventory with canonical `platform`, `files`, and
  optional `entrypoint` for Mach-O executable-relative dependency resolution.
- `correspondence`: existing platform-closure/windows-binary-correspondence.json
  or macos-binary-correspondence.json format.
- `sdk_lock`: actual platform dependencies.lock.json.
- `source_plan`, `url_receipt`, `recipes`: existing platform-closure formats.
- `selections`: explicit reviewed platform branch, notice, dependency, and rebuild
  decisions described below. The all-platform source plan is never auto-selected.

Reference files must exist within the evidence root and match their hashes. Stage
copies of inputs as needed; do not rewrite the original source mirror. Preserve
URL-receipt source paths relative to the staged evidence root.

`selections` has `platform: "windows"` or `"macos"` and optional sections:

- `packages`: entries with `package`, `recipe_commit`, `platform`, `recipe` ref,
  `branch_evidence` ref, `sources`, and nonempty `license_notices` refs. A recipe
  must match that exact commit/archive in recipes.json. Branch evidence JSON has
  the same platform/package/commit, `recipe_sha256`, substantive `selection_basis`,
  and `selected_sources` exactly equal to the chosen `sources` list. This is a
  reviewed record of recipe conditions, not automatic interpretation of CMake.
- Each URL source has `url`, `algorithm`, `digest`, and `artifact` ref. It must
  occur in the matching platform/package/commit plan and verified URL receipt;
  both its modern SHA256 and original recipe hash are rechecked. Git sources have
  `kind: "git"`, `url`, `revision`, `artifact`, and `checkout_provenance` ref.
  That JSON records `url`, `requested_revision`, full `resolved_commit`, and exact
  `snapshot_sha256`. Git/source provenance still requires substantive review.
- `transformations`: maps packaged native paths to proof refs. For UUID-only
  origin matches, proof has canonical `target_platform`, exact `input_sha256`
  matching the SDK origin, exact `output_sha256`, actual `commands`, and a `log`
  ref. All architecture UUIDs must match. UUID identity by itself is insufficient:
  it establishes origin correspondence, not unchanged executable code.
- `rebuilt`: maps packaged paths to actual build-provenance refs. Proof has
  `target_platform`, `component`, `outputs: [{archive_path, sha256}]`, actual
  `commands`, `build_environment`, `build_log` and `toolchain` refs, and nonempty
  `sources`, `license_notices`, and `recipes` ref lists. It must bind the exact
  final packaged output, including controlled signing/relocation transformations.
  An SDK recipe/package name alone cannot satisfy this requirement.
- `dependencies`: maps packaged native paths to their exact parsed import strings,
  then either `{archive_path}` or `{system_evidence: ref}`. Windows bundled imports
  must match the target DLL name. Mac loader/executable-relative imports must
  match exact archive paths; RPATH imports must match a target or checked symlink
  alias. Missing targets stay unresolved. System evidence has `platform`, exact
  `dependency`, and substantive `basis`; Windows also requires
  `windows_system_component: true`. Only narrow OS DLL/API-set names or macOS
  `/System/Library` and `/usr/lib` paths can be exempted. Runtime DLLs such as
  OpenSSL and compiler redistributables cannot be waved through as arbitrary
  Windows system libraries.
- `asset_notices`: maps every non-native regular-file path to actual license/notice
  refs. Fonts, artwork, Python source, scripts, and other non-native assets are
  therefore not silently covered by a native-only correspondence result.

The producer verifies artifact bytes and consistency. Review must establish that
source, patches, recipes, notices, and recorded commands really correspond to each
binary; JSON hashes cannot prove a fabricated build assertion true or replace
license review. Source/license/recipe artifacts are mapped to each native binary
for the final freeze gate, with additional provenance artifacts retained.

## Maintained components and preserved bindings

Application/Krita, actual QtNetwork runtime and bearer plugins, OpenSSL, CPython
core/stdlib extensions, and bundled compiler runtime components retain explicit
rebuild holds until output-specific provenance exists. Unknown binaries remain
unresolved even when a similarly named package exists. Exact SDK PyQt5 QtNetwork
`.pyd`/ABI extension wrappers are preserved bindings, not fictional QtNetwork
rebuilds: they may use byte-exact SDK source/notice correspondence. Their actual
compatibility with refreshed Python/Qt remains a separate final runtime gate.

PE imports and delay imports are parsed directly. Mach-O load, weak, reexport,
lazy, and upward dylib commands are parsed for every architecture; dylib identity
commands are excluded from imports. Per-slice dependency differences and UUIDs are
retained. Malformed or unsupported native data prevents completeness.

## Checks performed

`python test_qualification.py` passes 18 tests, with additional parameterized
missing-provenance and maintained-component cases. Fixtures are synthetic and are
not final qualification evidence. They cover pin/inventory failures, wrong locks,
wrong recipe branches, absent notices, URL source mismatch, unknown imports,
rebuilt output mismatch, preserved bindings, non-native notice coverage, UUID
transformation holds, delay/weak imports, all-slice metadata, and Java magic.

`python crosscheck_retained.py` performs a bounded read-only LLVM comparison on
four corrected retained SDK samples (`audit-sdk-casefold`), not native execution.
The saved `retained-crosscheck/receipt.json` records exact sample/tool-output hashes:

- Windows Qt5Network: 18 imports; x86_64 agrees with llvm-readobj.
- Windows Python core: 19 imports; x86_64 agrees with llvm-readobj.
- Mac QtNetwork: 14 unique imports; both slices' imports, UUIDs, and architectures
  agree with llvm-objdump.
- Mac Python framework: 2 unique imports; both slices agree on those same fields.

These retained SDK libraries are baseline artifacts, including old TLS, and are
not a qualified maintained runtime. There is no complete real candidate source
closure yet. Actual rebuilt output provenance, reviewed selected source branches,
notices, and final dependency resolutions still need to be supplied.
