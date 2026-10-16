# Private candidate retention (not wired to CI)

GnuPG is installed on the current Linux host. `retain.py` provides local encryption and recovery of a candidate archive plus explicitly selected stage evidence. It does not upload, publish, launch the candidate, or qualify a release. A dedicated local retention key has been generated; only `recipient-public.asc` and its full fingerprint in `recipient.json` may travel to the runner. The private key remains in the protected local GnuPG home. A local round-trip recovered the exact source-preview ZIP; this was not native package validation. Unit-test keys are disposable, isolated, and removed after tests.

Proposed integration:

1. Use the dedicated local retention key; never generate or export its private key on a runner. Export only its public key to the runner. Pin the full primary fingerprint independently in the reviewed workflow. Confirm local recovery before dispatch and preserve local key custody.
2. Finish candidate/evidence writes, then create an explicit JSON inventory under a stable input root. Never inventory an entire workspace automatically. Exclude credentials, environment dumps, unrelated logs, and private signing material. Each entry must specify the exact relative path, byte count and SHA256. Include the candidate archive and at least one stage evidence file.
3. Run encryption with the exported public key. The helper imports into an isolated temporary GPG home, refuses secret-key input or extra primary keys, requires the pinned fingerprint, snapshots and verifies every input before archiving, and encrypts with GnuPG. Only the `.gpg` output should become a CI artifact. Retain its SHA256/size and build identity through a trusted channel.
4. Recover locally using the dedicated key's GPG home and the trusted encrypted SHA256. The helper requires successful integrity-protected decryption and the exact primary recipient, verifies all inventory members before publishing the private output directory, and never overwrites an existing destination.
5. The recovered candidate ZIP remains an opaque file. Its eventual native extraction must use the existing platform package validator. This helper safely extracts only its own retention envelope; it does not bless arbitrary inner archives or their symlinks.

Inventory schema:

```json
{"schema":1,"candidate":"candidate.zip","files":[
  {"path":"candidate.zip","bytes":123,"sha256":"<64 lowercase hex>"},
  {"path":"evidence/stage.json","bytes":456,"sha256":"<64 lowercase hex>"}
]}
```

Usage (replace placeholders with reviewed paths and pins):

```sh
python retain.py encrypt --root /private/input --inventory /private/input-list.json \
  --public-key /reviewed/retention-public.asc --recipient FULL_PRIMARY_FINGERPRINT \
  --output /private/candidate.gpg
python retain.py decrypt --encrypted /private/candidate.gpg --sha256 TRUSTED_CIPHERTEXT_SHA256 \
  --gnupg-home /private/retention-key-home --recipient FULL_PRIMARY_FINGERPRINT \
  --output /private/recovered-build
python test_retention.py -v
```

Inputs and decrypted contents are bounded to 8 GiB and 4096 files, with 16 MiB envelope allowance. Temporary workspaces are mode 0700; ciphertext and extracted files are mode 0600. Only regular, inventoried files are accepted. Paths, duplicates, links, sparse files, file/parent collisions, unexpected entries, and size/hash mismatches fail closed. Existing outputs are preserved. GPG personal configuration, automatic key retrieval, and default recipients are disabled. `--trust-model always` bypasses web-of-trust prompts only after independently checking the exact key fingerprint; it does not bypass payload validation.

Encryption alone does not authenticate the sender: anyone possessing the public key can encrypt to it. The ciphertext digest/build identity must come from the trusted job evidence; this tool makes no signing or source-closure assertion. Temporary plaintext is deleted on normal completion/failure, but secure erasure on SSDs, process crashes, and runner teardown are not guaranteed. Use ephemeral private runner storage and never upload plaintext outputs. Local key unlocking uses the existing GPG agent/pinentry; no passphrase is accepted as a CLI argument.

The reviewed Mac workflow uses seven-day encrypted-artifact retention and records the ciphertext digest with commit/run identity in its authenticated job evidence. The private key remains local. Actual run38905208990 found GnuPG2.5.22 on ARM macOS15.7.9, but encryption fixture imports failed before the application build. That run did not capture GPG stderr, so the precise cause is unproved. Its deeply nested temporary GPG homes are consistent with UNIX socket path limits. Encryption now uses a separate short mode0700 temporary GPG home, stops only its temporary daemons, and surfaces bounded IPC errors without imported identities. A deep-payload-path round-trip passes locally; native Mac validation remains required. The payload workspace stays private beside the requested output. Disk headroom, full native retention and local recovery still require validation on the actual candidate.

Eight local tests pass: real GPG round-trip, deep output path with short isolated key home, exact fingerprint refusal, missing/changed/symlink inputs, corrupt ciphertext/wrong recipient, inventory traversal/duplicates, overwrite refusal, and authenticated-but-malicious envelope rejection. These tests use throwaway keys and synthetic bytes, not a native Mac candidate.
