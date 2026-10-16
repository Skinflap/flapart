# Prepare explicit private Mac candidate retention inputs

`prepare_candidate.py` is independent of CI and does not build, encrypt, upload,
release, or fabricate absent stage evidence. It stages actual inputs, runs the
four-stage native chain verifier, then emits the inventory expected by existing
`retain.py encrypt`. No source/release qualification becomes true.

Example, for a future reviewed run whose candidate and evidence already exist:

```sh
python3 native/distribution/private-retention/prepare_candidate.py \
  --candidate /private/packaged/candidate.zip \
  --inventory /private/packaged/candidate-inventory.json \
  --stage-evidence /private/actual-package-stages \
  --qualification sdk-promotion.json=/private/qa/sdk-promotion.json \
  --qualification packaged-runtime.json=/private/qa/packaged-runtime/qualification.json \
  --qualification arm64-python.json=/private/qa/packaged-runtime/arm64/python.json \
  --qualification arm64-tls.json=/private/qa/packaged-runtime/arm64/tls.json \
  --qualification arm64-provenance.json=/private/qa/packaged-runtime/arm64/provenance.json \
  --qualification x86_64-python.json=/private/qa/packaged-runtime/x86_64/python.json \
  --qualification x86_64-tls.json=/private/qa/packaged-runtime/x86_64/tls.json \
  --qualification x86_64-provenance.json=/private/qa/packaged-runtime/x86_64/provenance.json \
  --output /private/prepared-retention

python3 native/distribution/private-retention/retain.py encrypt \
  --root /private/prepared-retention \
  --inventory /private/prepared-retention/inventory.json \
  --public-key /reviewed/recipient-public.asc --recipient REVIEWED_FULL_FINGERPRINT \
  --output /private/candidate.gpg
```

The qualification paths above are illustrative: use actual emitted paths, and
list any additional required logs/JSON explicitly. The helper requires those files
to exist; it does not invent them, glob a workspace, infer similarly named outputs,
or assert that retained qualification JSON means passed runtime qualification.
Its chain verifier validates the packaging chain; separate release review must
assess runtime and source evidence. No credentials or full environment dump is
collected by this helper. Only intentionally listed JSON/log files are accepted
as additional evidence; review those files before choosing them.

## Exact layout and mapping

`--stage-evidence` must contain **exactly** the four directories `collector`,
`completion`, `codesign`, `verify`, each with `receipt.json`, `before.json`,
`stdout.log`, `stderr.log`, and `native-bytes/`. Native-blob names must be lowercase
64-character SHA256 strings; there may be no other nested directories or extras.
The recorder must have used actual byte retention. Missing stages, failed chains,
unexpected entries and all input symlinks are rejected. The fixed verified mapping
is `tree: package` and `archive_prefix: Flapart Studio.app`, matching the concrete
Mac package-stage integration. No arbitrary prefix rewriting is performed.

Output is a new private directory, mode0700, with regular files mode0600:

- `candidate.zip`: byte-identical input ZIP.
- `candidate-inventory.json`: byte-identical final candidate inventory.
- `stages/STAGE/...`: byte-identical actual recorder evidence and native blobs.
- `qualification/NAME`: only explicitly selected additional JSON/log files.
- `chain-manifest.json`: actual hashes pin staged receipts, inventory and ZIP.
- `chain-result.json`: output of the real chain verifier against these staged bytes.
- `preparation.json`: observed original source paths/hashes, preparer/helper hashes,
  candidate and chain-manifest pins, and explicit unqualified status.
- `inventory.json`: existing retain.py schema; inventories every staged regular
  file **except itself**, because retain.py adds its own inventory envelope.

The manifest has no inferred independent tool-byte artifacts. Pinned stage
receipts retain recorded tool identities, while chain output explicitly identifies
which tool hashes remain recorded-only. Original runner tool paths need not exist
when the private payload is recovered.

## Bounds, immutability and failure behavior

Preflight rejects source/output overlap, symlink inputs or path components,
case-colliding destination names, non-regular files, unexpected stage entries and
existing output. Every selected input is hashed with stable file identity before
staging and again after verification; changed input sets, inodes, sizes, mtimes or
hashes fail. Work belongs in completed, quiescent build directories; this is not a
sandbox against a hostile concurrent filesystem process.

Identical staged bytes share hardlinks **only between private copies**, never back
to original inputs. This bounds local physical duplication but does not bypass
logical retention bounds: all repeated stage paths count toward the existing
4096-file / 8-GiB envelope. Generated evidence also counts, and the inventory must
fit the existing 2-MiB decrypt limit. A real SDK's 602 native files/~1.12GiB are not
an exemption. If complete evidence exceeds a bound, preparation fails; it never
silently drops inputs, raises limits, or substitutes hashes for required bytes.
Plan sufficient disk for private staging plus retain.py's separate plaintext tar
and encrypted output. Hardlink deduplication does not make the encrypted tar's
logical repeated payload smaller by definition.

Staging occurs in a private temporary sibling. Failed verification removes that
temporary workspace and produces no successful output directory. Success reserves
a fresh destination exclusively, preserving preexisting files. Existing inputs
are never modified. Private plaintext cleanup afterward remains the caller's
responsibility; no automatic secure-erasure or public-artifact behavior is implied.

The helper does not modify `retain.py`, pipelines, workflow files or encryption
configuration. Tests run actual recorded short-process mutations and ZIP fixtures,
not a real Mac application build:

```
python3 -m unittest discover -s native/distribution/private-retention \
  -p test_prepare_candidate.py -v
```

Eleven focused tests pass locally, including a real prepare → GnuPG encrypt →
authenticated decrypt → chain reverify round-trip using an ephemeral fixture key.
The test compares every recovered file hash, keeps all release/source flags false,
terminates the disposable GPG agent, and removes temporary key material. Fixture
paths are canonicalized for macOS `/var` aliases; production symlink rejection
is unchanged. GPG bridge testing is skipped explicitly when GnuPG is unavailable.
This is envelope integration evidence, not native Mac execution qualification.
