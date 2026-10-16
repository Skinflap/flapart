# Verify the actual Mac packaging byte chain

`verify_chain.py` checks retained, pinned stage evidence against the final ZIP.
It never builds, signs, uploads, edits the pipeline, or produces historical stage
receipts. `chain_verified: true` means the observed native byte states connect;
`source_closure_complete` and `release_qualified` always remain false. Source,
license, toolchain, command-semantics review and actual native runtime/signature
qualification are separate requirements.

## Concrete mapping

The required sequence is exactly `collector`, `completion`, `codesign`, `verify`.
Each actual recorder receipt must use that stage name, contain the same declared
package-tree label, and capture the same absolute package root before/after and
between stages. Extra captured input trees are also checked, not discarded.

The existing `package-candidate.py` invokes upstream collection, then renames the
app to `Flapart Studio.app` and adjusts Info.plist, then runs maintained completion,
codesign and strict signature verification. **The future collector-stage wrapper
must include the rename/plist adjustment before its after-snapshot.** Capture the
final app root, not a parent directory with a changing basename. No hidden rename,
subtree filtering, arbitrary stage-specific prefix, or unrecorded mutation is
accepted by this verifier. This document does not perform that integration.

Use `--retain-native-bytes` on every recorded stage. Without before/after native
blobs, this verifier refuses the chain. For a component build, use a separate
component proof; this verifier covers the four packaging stages only. The collector
input source/build linkage still requires its own reviewed evidence.

## Pinned manifest

The evidence root contains all stage receipts, logs, before snapshots, native blobs,
final inventory and the exact ZIP. References are relative and hash-pinned:

```json
{
  "schema": 1,
  "platform": "macos-universal2",
  "tree": "package",
  "archive_prefix": "Flapart Studio.app",
  "stages": [
    {"stage": "collector", "receipt": {"path": "collector/receipt.json", "sha256": "ACTUAL_HASH"}},
    {"stage": "completion", "receipt": {"path": "completion/receipt.json", "sha256": "ACTUAL_HASH"}},
    {"stage": "codesign", "receipt": {"path": "codesign/receipt.json", "sha256": "ACTUAL_HASH"}},
    {"stage": "verify", "receipt": {"path": "verify/receipt.json", "sha256": "ACTUAL_HASH"}}
  ],
  "inventory": {"path": "candidate-inventory.json", "sha256": "ACTUAL_HASH"},
  "archive": {"path": "candidate.zip", "sha256": "ACTUAL_HASH"},
  "tool_artifacts": []
}
```

Placeholders are illustrative, never acceptable evidence. Invoke:

```
python3 native/distribution/provenance/verify_chain.py \
  --manifest /private/evidence/chain.json --manifest-sha256 ACTUAL_MANIFEST_HASH \
  --evidence-root /private/evidence --output /private/new-chain-result.json
```

Inputs are read-only. Output must not exist. An invalid chain raises an error and
produces no success receipt. Recompute and review the manifest pin only after
collecting real evidence; the verifier cannot authenticate an intentionally
fabricated or maliciously repinned entire evidence set.

## What is verified

- Exact required stage order, pinned receipt bytes, successful actual return code,
  complete comparisons, no timeout/errors or historical-reconstruction marker.
- Persisted `before.json` hash and equality with the receipt, stdout/stderr hashes
  and lengths, every retained native input/output blob's SHA/length and reparsed
  architecture/slice/import metadata. Altering an embedded after-state without
  corresponding actual bytes fails. The changed-file ledger is recomputed.
- Tool/helper recorded before/after SHA agreement and the first tool's agreement
  with executed argv. Original runner paths are **not opened**: they may disappear
  after teardown. Optional `tool_artifacts` contain independently retained exact
  tool/helper byte references; any supplied blob is rehashed and checked against
  corresponding recorded size. Output explicitly separates independently retained
  tool hashes from recorded-only identities. Recorded-only hashes remain recorded
  observations, not a claim that tool bytes were independently recovered.
- Every adjacent package native/alias state must match exactly; native mode changes
  matter as well as SHA/size. Verification must leave the package unchanged.
- Every final ZIP member must match pinned final inventory: exact file set,
  regular-file SHA/length, symlink target and type. Duplicate/case-colliding names,
  absolute/traversing/backslash paths, members outside the one app prefix,
  unsupported/encrypted types, file/symlink traversal and cyclic/dangling/escaping
  aliases fail. Archive limits are 100,000 entries and 8 GiB uncompressed.
- Final ZIP native files must be universal Mac Mach-O and exactly match the final
  verified stage's native set, actual bytes, mode and all-slice metadata. Final
  aliases must match the recorded target, kind and canonical file destination.
  The archive SHA is checked again after reading it.

The native recorder does not capture ordinary resource bytes between stages.
Their **final** bytes are bound by the pinned inventory and ZIP; this verifier does
not claim a transformation history for fonts, Python source, plist or other assets.
Full source closure must supply their provenance/notices separately.

The stage role labels do not prove that the tool was genuinely Apple codesign or
that a collector performed every expected action. Review the pinned exact argv,
helper/toolchain evidence and actual signing result. This verifier proves byte
continuity, not platform code-signature validity. It does not claim nested commands
were observed merely because an outer helper was hashed.

## Tests and status

`python3 -m unittest discover -s native/distribution/provenance -p test_verify_chain.py -v`

Tests execute real short subprocesses that mutate synthetic universal Mach-O
fixtures, record their actual bytes, create actual ZIPs, and verify failure on
broken links/tampering. They are not native application or signing qualification.
No successful real candidate chain has been claimed or manufactured by this work.
The recorder's later PE32 extension captures the known collector-stage Windows
builder DLLs before completion removes them; these can be actual removed rows
in the chain. They cannot survive into the final Mac ZIP, whose native check
requires Mach-O universal2. The old recorder without PE32 support cannot capture
that raw collector tree and must not be represented as integrated successfully.
