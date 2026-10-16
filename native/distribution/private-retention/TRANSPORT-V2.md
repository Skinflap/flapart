# Private content-addressed transport v2

Explicit opt-in only. Legacy preparation and the GPG envelope remain unchanged. This removes repeated logical bytes from encrypted transport, not qualification requirements. `verify_chain.py` and native receipts are unchanged. The manual macOS source workflow explicitly opts in after running transport tests and a measured capacity preflight.

`prepare_candidate.py --transport-v2` validates the same real four-stage chain, rechecks original inputs and creates the same receipt/log/candidate/preparation files. It then emits a private fresh transport root:

- `inventory.json`: existing schema-1 GPG envelope inventory, accepted by unchanged retain.py.
- `transport-v2.json`: schema 2, kind `flapart-private-content-addressed`, original candidate path, original path/size/SHA256 rows, logical bytes, unique object bytes and count.
- `objects/<64 lowercase SHA256>`: one regular file per distinct digest. Each object size must be consistent across all references.

Original `inventory.json` bytes are themselves an object and reconstructed exactly. Receipt JSON is never parsed and reserialized by transport. No original stage paths are changed in receipts. Repeated paths' bytes become separate references to the same object.

## Fixed bounds

| Bound | Value |
|---|---:|
| Reconstructed paths, including original inventory | 16,384 |
| Reconstructed logical byte sum | 32 GiB |
| Distinct objects | 4,095 |
| Unique object bytes plus transport manifest | 8 GiB |
| Individual object | 8 GiB |
| Transport and original inventory bytes, each | 8 MiB |
| Outer envelope inventory | 2 MiB |
| Encoded relative path | 1,024 bytes |

Outer inventory has at most 4,096 rows (objects plus manifest), preserving retain.py's existing count/8-GiB bound. The original logical inventory retains schema 1 file semantics but may exceed legacy reader bounds; it is accepted only by the explicit v2 path and must never be sent directly to the legacy encrypt function.

All paths are relative; traversal, backslashes, control characters, colon/ADS paths, duplicates, case-insensitive collisions and file-parent collisions are rejected. JSON duplicate keys, unlisted/missing/unreferenced objects, mismatched totals, sizes/digests and symlinks are rejected. Tar handling, encryption key fingerprint checks and authenticated GPG decryption stay in unchanged retain.py; v2 adds no new archive extraction primitive.

Restore verifies the whole outer inventory, all objects, original inventory and reconstruction manifest before building a private temporary tree. It copies each unique object into that tree, verifies the copy, and hardlinks repeats only to those private copies. It never links caller originals or decrypted input objects into the result. Publication is into an exclusive fresh directory; any exposure failure removes that new partial result. Original receipts and inventory remain byte-for-byte identical.

## Commands

Prepare with the existing explicit candidate/stage/qualification arguments, adding `--transport-v2`. Then use unchanged `retain.py encrypt` with its output root and `inventory.json`. After unchanged authenticated `retain.py decrypt`:

```
python3 transport_v2.py restore --root DECRYPTED_TRANSPORT --output FRESH_RECONSTRUCTED
```

Run unchanged `verify_chain.py` on `FRESH_RECONSTRUCTED/chain-manifest.json` as before. Standalone `transport_v2.py pack --root PREPARED_INPUT --output FRESH_TRANSPORT` is available for a previously prepared tree. Pack alone does not establish a valid native stage chain; the preparer/chain verifier must still run.

## Capacity and evidence limits

Pack rejects symlink roots and ancestors before resolving either input tree.

Pack/preparer return measured original path count, logical bytes, unique object count/bytes, manifest bytes, stored bytes and largest object bytes. Pack also returns its staging byte sum including both manifests. Explicit preparation returns measured unique-inode bytes of its private original tree and the simultaneous prepared-plus-packed copy byte sum. These two private copies coexist before preparation exits; dedup does not remove that peak. Byte sums exclude filesystem allocation overhead. Restore returns reconstructed logical bytes and unique-copy bytes. These are inputs to separate capacity admission, not a claim of sufficient free disk. Physical preparation copies, unique transport copies, plaintext tar, ciphertext, temporary snapshots and reserve still need admission. No compression savings are assumed.

The retained original SDK has 600 unique native blobs (~1.046 GiB). Actual maintained SDK plus package states are not yet measured; more than 4,095 unique objects or 8 GiB stored content still fails. Dedup does not justify silently increasing either cap.

Tests include real GPG encryption/decryption through the unchanged helper and unchanged chain verification of a reconstructed recorded fixture, exact original receipt/inventory bytes, private hardlink scope, tamper, duplicate JSON/path keys, traversal/casefold/parent collisions, bounds, missing/extra/unreferenced objects and partial-output cleanup. They are transport/fixture tests, not native runtime or source-closure evidence.
