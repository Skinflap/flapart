# Complete-chain coordinator command

`coordinator_cli.py` is a separate explicit entry point for `coordinator_full`.
Importing it performs no network work. It accepts an already recovered original
retention root and original installer manifest, never a private retention key.
It does not reinterpret the harmless fixture protocol, dispatch a workflow,
launch an application, or qualify a public release.

The binding JSON must be independently pinned using authenticated run/attempt/job
observations and independently retained candidate pins, not copied on trust from
a peer request. Its exact fields are the existing `protocol.binding` fields:
repository, workflow, run_id, attempt, commit, job_id, architecture, operator_id,
candidate_sha256, candidate_bytes, inventory_sha256, manifest_sha256. The separate
chain SHA and request artifact ID are also independent inputs. ARM and Intel jobs
need their own binding, artifact ID and fresh output directory.

After review and separate authorization for a real exchange:

```sh
python coordinator_cli.py coordinate \
  --binding /canonical/private/arm-binding.json \
  --artifact-id "$REQUEST_ARTIFACT_ID" \
  --chain-sha256 "$INDEPENDENT_CHAIN_SHA256" \
  --recovered-root /canonical/private/original-retained-root \
  --original-manifest /canonical/private/original-installer-manifest.json \
  --output /canonical/private/new-arm-exchange
```

All paths must have existing canonical, nonsymlink ancestors. Output must be new
and separate from the recovered root and manifest. Initial local hashes and
candidate size are checked before constructing the authenticated adapter. The
existing producer subsequently performs complete original inventory and chain
verification, measured disk checks, retention-v2 packing and encryption, expiry
checks, authenticated request rereads, and exact uploaded-byte readback. These
checks remain authoritative; initial hash checks do not replace the chain verifier.
Existing less-than-2-GiB ciphertext and retention bounds are unchanged.

The command uses the current `gh` authenticated session through the existing
`GhAdapter`. It checks the numeric operator ID initially and again immediately
before every draft creation, asset upload and draft deletion. The underlying
producer retains its request/run/job and draft/asset checks. No credentials,
private keys, signed URLs or exception text are printed by this wrapper. Summary
JSON contains only bounded status, release ID and explicitly false native/source/
release qualification flags. There is no automatic delete on failure: inspect
`new-arm-exchange/coordinator-receipt.json`, retained by the underlying producer.

Explicit cleanup uses the same independently pinned binding, artifact and chain:

```sh
python coordinator_cli.py cleanup \
  --binding /canonical/private/arm-binding.json \
  --artifact-id "$REQUEST_ARTIFACT_ID" \
  --chain-sha256 "$INDEPENDENT_CHAIN_SHA256" \
  --receipt /canonical/private/new-arm-exchange/coordinator-receipt.json
```

Cleanup is exactly the existing receipt-bound operation: authenticated draft
identity and exact asset set are rechecked before DELETE. Unknown assets,
published releases, mismatched pins and changed operators are refused. It is not
a general release-delete command. No real cleanup was run during implementation.

Validation: `python -m unittest discover -s native/qa/installer-followup/rendezvous
-p 'test_coordinator_cli.py' -q` exercises CLI wiring, changed real local fixture
bytes, hash/size/binding errors before adapter creation, output confinement,
operator changes before each mutation, exact cleanup arguments, and redacted
errors. Coordinator calls are mocked only for wiring tests; no mocked return is
claimed as encryption, network or native proof. Existing full-exchange tests
separately cover real local encryption and chain restoration with offline HTTP
fixtures. Actual candidate availability, reviewed hosted workflow, authenticated
real transfer, and native installer qualification remain future gates.
