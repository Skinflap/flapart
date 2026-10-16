# Full retained-chain envelope (local implementation only)

`full_chain.py` is a separate path; it does not alter the strict harmless fixture,
three-file protocol, current network adapter or either hosted workflow. No candidate
upload, dispatch, network mutation or native execution occurred in this work.

## Format and independent authority

The original restored preparation root is packed with existing retention-v2 into
`retained/`. Its original candidate ZIP, inventories, chain manifest, stage receipts,
logs/snapshots/native blobs and qualification files remain exact original bytes.
The envelope also contains `installer-original.json` (exact original installer
manifest), `exchange.json` (complete original request plus independent chain pin,
all native/source/release flags false) and a retention-compatible outer inventory.
No asserted chain-result file substitutes for `verify_chain`.

An external descriptor binds request SHA, independent chain-manifest SHA, ephemeral
recipient, outer inventory canonical SHA, payload byte total/file count, ciphertext
SHA and ciphertext size. Its own SHA MUST come from an independent authenticated
operator/dispatch exchange. Do not read descriptor authority from the ciphertext,
accept an unpinned adjacent JSON file, or treat encryption alone as sender identity.
The current generic GitHub response protocol does not yet carry this new descriptor;
a future separately reviewed candidate coordinator/receiver must bind it to the
existing operator/run/attempt/job/architecture/nonce/deadline. No existing fixture
response is silently reinterpreted. Current tests pass explicit independently known
pins. The exact original installer/inventory/ZIP pins remain in the request.

The descriptor's envelope_inventory_sha256 is SHA256 of `protocol.encode(parsed
outer inventory)`, not its original textual formatting: existing retain.encrypt and
retain.decrypt deliberately serialize their own outer inventory. All nested original
inventory/manifests remain retained files and preserve exact bytes. Duplicate JSON
keys are rejected by the readers before canonicalization.

## Local API sequence

1. `pack(original_root, original_installer_manifest, request, chain_pin,
   fresh_envelope_root, now)` verifies all original retained files and executes
   actual `verify_chain` before packing. It checks exact candidate/original manifest
   pins, fixed package mapping and unqualified Mac manifest. It packs retention-v2,
   verifies object sets/bytes/schema/totals, then rechecks original evidence. No
   source input is modified. The resulting extra files remain private.
2. `encrypt(envelope_root, request, chain_pin, ephemeral_public_key,
   fresh_ciphertext, now)` validates envelope/key SHA, uses existing retention
   encryption (which validates the actual public key/full fingerprint), checks
   resulting ciphertext is strictly below2GiB, rechecks envelope and expiry, and
   exclusively exposes the ciphertext. It returns the descriptor. Caller retains
   its independently authenticated canonical SHA. Failure does not publish output.
3. `decrypt_restore_admit(ciphertext, ephemeral_private_home, request, chain_pin,
   descriptor, independently_pinned_descriptor_sha, fresh_output, now)` validates
   all descriptor pins/types/limits and ciphertext bytes first. It invokes an
   isolated retention module with its payload limit reduced to the descriptor's
   authenticated payload total (never increased above8GiB). GPG must authenticate
   the exact ephemeral recipient. It validates the complete envelope, restores
   retention-v2 to `recovered/`, then calls `candidate_runner.admit` to reread actual
   stage blobs, verify all four linked stages and bind final ZIP members.

Successful output contains `envelope/`, `recovered/`, and evidence-only admission.json.
Original installer manifest is `envelope/installer-original.json`; original runtime
ZIP is `recovered/candidate.zip`. The adapter can subsequently hand these paths to
the separately reviewed actual installer entry point. This module never launches it.
Ephemeral-key ownership/cleanup and token-free child environment belong to the
runner orchestration layer; this library does not delete a supplied GPG home or
retrieve credentials. Do not invoke it under an unsanitized runner token environment.

## Bounds and disk measurements

No bound is relaxed: ciphertext <2GiB, retention payload ≤8GiB, outer files≤4096,
retention-v2 logical paths/bytes/object bounds unchanged, strict JSON and safe paths,
no evidence symlinks or unlisted objects. Outer envelope metadata consumes additional
file slots; an existing retention-v2 pack at its absolute object cap may therefore
be refused. This is deliberate. The actual complete chain may not fit; no chunks or
unqualified public asset workaround are introduced.

Immediately before packing, free space must cover the original tree's measured
physical bytes plus128MiB margin. Before encryption, additional free space must
cover three payload copies plus the largest member and128MiB margin (tar, snapshot,
ciphertext/staging). Before decrypt/restore it must cover three authenticated payload
copies plus128MiB margin (bounded plaintext tar, decrypted unique objects, restored
unique bytes). Existing files already consume space and are reflected in free-space
measurement. Original tree hardlinks are measured by inode; restored duplicates use
existing retention-v2 hardlinks. The lower-bound GPG tar padding allowance from
retain.py remains bounded; descriptor total is enforced again after decryption.

All outputs are fresh/canonical, built in private temporary siblings and exposed
only after validation. Failures remove owned staged trees; preexisting outputs are
never replaced. Expiry is rechecked using elapsed monotonic time after long work.
Actual free space/complete-candidate sizes and hosted restore timing remain unproven.

## Evidence

```sh
python -m unittest discover -s native/qa/installer-followup/rendezvous \
  -p 'test_full_chain.py' -v
```

Fourteen focused tests pass. They use actual locally recorded four-stage fixture
transformations, exact native-byte parser fixtures, final ZIP and preparation helper;
then real ephemeral GPG encryption/decryption, retention-v2 restoration and actual
chain re-verification. Original ZIP/installer/chain manifest bytes match after the
round trip. Tests reject incomplete chains, wrong independent pins, tampered objects,
self-consistent malicious transport paths before encryption, ciphertext corruption
even with recomputed outer SHA, altered descriptor metadata, expiry, low disk,
symlinks, oversized ciphertext and preexisting output replacement.

These are actual local cryptographic/byte-chain checks, not a Mac application run.
No native/source/release flag becomes true. Remaining real-host gates are: actual
complete candidate retention, authenticated descriptor transport wiring, measured
whole-envelope admission, fresh ARM/Intel GUI/security/installer execution and
separate installed-runtime TLS/Python evidence. The harmless hosted exchange does
not satisfy those candidate-specific gates.
