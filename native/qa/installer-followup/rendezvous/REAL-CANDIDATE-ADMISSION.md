# Exact real-candidate admission: staged implementation

`candidate_runner.py` is separate from `fixture.py` / `runner_fixture.py`; their
harmless-only restrictions remain unchanged. No workflow, dispatch, candidate upload,
key enrollment or hosted native launch was performed for this implementation.
The prior harmless ARM/Intel handshake establishes only that exchange, not admission
or execution of a real candidate.

## Why this is not the three-file fixture envelope

Existing `protocol.pack` accepts only ZIP, candidate inventory, original manifest
and exchange metadata. Full `verify_chain` needs collector/completion/codesign/verify
receipts, before snapshots, stdout/stderr and retained native blobs. An operator's
"verified" JSON cannot replace these bytes. A later real-candidate coordinator must
transfer a separate complete retained evidence envelope (possibly retention-v2),
plus the original installer manifest, without altering the ZIP or any original
recorded evidence. Do not overload candidate-inventory.json with an assertion or
relax `protocol.validate_pack` for this purpose.

The current adapter accepts an **explicit already decrypted/restored root**. This is
an intentional staging boundary: ephemeral-key creation, authenticated GitHub GET
admission and GPG decryption remain the reviewed rendezvous/retention layers. No new
network orchestration or real-candidate envelope producer is claimed ready here.
The independent chain-manifest SHA is an additional immutable dispatch/operator pin;
it must not be learned from the received envelope. Existing request pins still bind
the exact original ZIP, original candidate inventory and original installer manifest.
A future workflow must bind that extra chain pin to its authenticated exchange before
transfer. It must re-use the short private key home, current operator/run/attempt/job/
architecture/nonce checks and cleanup boundaries; never provision a long-lived key.

## Admission API

```python
result = candidate_runner.admit(
    recovered_root, original_request, original_installer_manifest_path,
    independently_pinned_chain_manifest_sha256,
    received_ciphertext_path, authenticated_ciphertext_sha256, now_epoch_seconds)
```

`recovered_root` must be the restored original preparation root with fixed
candidate.zip, candidate-inventory.json, chain-manifest.json and inventory.json.
`tree_inventory` validates all actual retained files against the complete inventory,
rejects extra/missing files or any symlink, and checks existing retention-v2 logical/
unique-byte/file bounds. It never treats chain-result.json as proof. `admit` then
checks exact original pins and the separately pinned chain-manifest, requires its
fixed package/archive mapping, and executes existing `verify_chain.verify` against
all real stage bytes and the final ZIP. It repeats critical pins and deadline after
verification. The original installer manifest must remain `ci-candidate`, for the
universal namespaced Mac fork. Its test-only unlock happens later inside ci_e2e.

Ciphertext remains strictly below 2 GiB. The actual transfer's GPG authentication is
an upstream requirement: comparing ciphertext SHA here is not a claim of encryption
or sender authentication. The whole evidence tree can be too large for this limit;
refuse such a transfer. Retention-v2 may reduce duplicate bytes but does not establish
that a particular real candidate fits. No chunking or relaxed bound was introduced.

Successful admission reports `chain_verified:true`, `native_executed:false`,
`source_closure_complete:false`, `release_qualified:false`. Portable fixtures can
produce this evidence-only result; they cannot produce real native qualification.

## Actual installer adapter, not yet executed

`installer_plan` generates the exact existing ci_e2e argv without executing it.
It checks independently supplied hashes for the complete installer/helper/probe
input set, fresh canonical output and nonoverlap with recovered evidence. It passes
the original ZIP, original manifest, requested architecture and exact archive SHA;
it never re-zips, re-signs, rewrites application/plugin bytes, changes quarantine or
uses a different binary under an unchanged version label.

`run_installer` is an explicit callable entry point, with no CLI/workflow wiring yet.
It requires actual Darwin + real GitHub Actions/CI environment, GUI console ownership,
GUI launchctl domain and absent Flapart settings/profile. It performs full admission,
requires the runner temporary installation space on the measured output volume,
and checks free space **after** recovery: three expanded archive copies, two ZIP
copies and 1 GiB evidence margin. This is a conservative additional installer budget;
prior ciphertext/decryption/v2 restoration capacity must be separately admitted
before transfer. Existing retained evidence consumption is already reflected in the
measured free space. Measurements and refusal do not prove a future candidate fits.

It launches the real installer driver with sanitized child environment (no GitHub
token or inherited Python/Qt/DYLD injection variables), retains driver logs, and
requires measured first/upgrade native outcomes from the real driver receipt. The
receipt must bind the exact archive/process architecture/installed-runtime scope;
helper and original archive hashes are rechecked afterward. Both initial and upgraded
native child exit observations are required. A success leaves release/source flags
false. Error output records an exception type rather than arbitrary potentially
sensitive exception text. Preflight refusal occurs before native output is created;
a started driver failure receives failure evidence.

Use separate fresh hosted jobs/profiles for ARM and Intel, as in the harmless
handshake. Hosted GUI launch/security behavior with this actual app remains unknown.
No Open Anyway automation, Gatekeeper disabling, quarantine removal, certificate
trust changes or re-signing is authorized. A security prompt may cause a truthful
failed journey. Browser sign-in/publication and downloaded-user security approval
remain separate gates. Installed-path TLS/Python probes still need an extension
inside the driver's temporary-install lifetime; earlier relocated-package probes
are not automatically installed-runtime evidence.

## Portable tests and actual next gates

```sh
python -m unittest discover -s native/qa/installer-followup/rendezvous \
  -p 'test_candidate_runner.py' -v
```

Twelve tests create real locally recorded four-stage transformations, retained native
byte fixtures and an exact final ZIP via the existing preparation helper. They test
actual chain admission, blob/ZIP tampering even with rewritten retention rows,
missing stages, changed independently pinned chain manifest, extra files/symlinks,
wrong original manifest status, elapsed expiry, ciphertext bound, helper pinning and
non-Mac launch refusal. The tiny Mach-O fixtures are parser/test data, not applications.

Remaining before actual hosted use: a real complete retained candidate; authenticated
operator pins for original manifests/chain/helper inputs; actual ciphertext size and
recovery-space admission; a separate complete-chain envelope and coordinator/receiver
wiring; parent-reviewed workflow; then real first/upgrade launcher journeys on both
fresh Macs. No successful native, source-closure or release result is inferred.
