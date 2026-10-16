# Authenticated complete-chain exchange wiring

New files: response_full.py, coordinator_full.py, runner_full.py and
 test_full_exchange.py. Existing fixture/protocol/github_read/candidate_runner/
full_chain files remain unchanged. No workflow dispatch, real candidate upload,
GitHub mutation, secret enrollment or application launch was performed.

## Descriptor authentication

The separate draft tag is `full-chain-` plus the original request's unique tag.
The API draft body contains a strictly parsed complete-chain metadata object:
request canonical SHA, independent chain SHA, descriptor canonical SHA and descriptor.
The descriptor itself binds full request (therefore repository/workflow/run/attempt/
commit/job/operator/architecture/nonce/candidate pins), chain manifest, ephemeral
recipient, ciphertext SHA/size and canonical outer inventory/size/file count.
The independent chain pin always comes from the caller's immutable operator/dispatch
input; it is never learned from the received body or ciphertext.

Draft metadata alone is insufficient. `response_full.fetch` authenticates the exact
original public-key request artifact/run/attempt/job through hardened github_read,
requires unpublished draft identity, expected author and exact commit, and reads
exactly two assets. Both assets' authenticated uploader IDs must equal the expected
operator. response.json contains the identical descriptor metadata plus exact draft
and ciphertext asset IDs. Its API digest, bytes and parsed value must match, thereby
binding descriptor bytes to an operator-uploaded asset, not merely an editable draft
body. candidate.gpg API digest/size must match that descriptor. Changed authors,
operators, attempts, request artifacts, nonce, chain/candidate pins, recipients,
metadata or asset IDs fail closed.

Only after those checks and measured disk admission does ciphertext stream through
existing Client.download_to into an exclusively created private file. After its hash
and length pass, the adapter rechecks draft body/status/assets and request artifact,
then rechecks elapsed expiry. Any failure removes only that attempt's new ciphertext.
No API authorization follows storage redirects; existing read adapter redaction and
bounds remain in force. The canonical descriptor SHA returned here is authenticated
through the matching API-fetched operator-uploaded response asset and exact request;
it is not a value taken on trust from GPG plaintext.

## Coordinator and receiver entry points

`coordinator_full.coordinate(expected_binding, artifact_id, original_recovered_root,
original_installer_manifest, independent_chain_sha, fresh_private_output, adapter,
clock=...)` first verifies the currently authenticated local operator and original
request artifact. It calls full_chain.pack/encrypt, so complete original stage bytes
and fixed source inputs are checked before a draft exists. It reauthenticates the
request immediately before mutation. It creates a draft explicitly marked private
exchange, uploads ciphertext first and response.json last, and independently reads
both assets back through response_full before recording ready:true.

This is a callable producer, not a command automatically run by tests or workflows.
An explicitly supplied existing coordinator_fixture.GhAdapter can implement the
already-reviewed gh-session calls when separately authorized. Reusing that adapter
and its bounded save/asset utilities does not call the harmless fixture producer or
relax its fixed payload restrictions. Tests inject an entirely offline adapter.
No original retention private key is accessed; input is already locally recovered
and chain-verified evidence and only a runner-generated public recipient is used.

Failures retain a local private coordinator receipt with whatever exact draft/asset
IDs are established; no automatic deletion guesses are made. `cleanup` requires the
same independent binding/artifact/chain pins, authenticated operator, exact recorded
draft/body/commit/status and exact recorded asset metadata. Published drafts,
foreign/unrecorded assets or changed context are refused. Explicit authenticated
DELETE success is recorded without claiming an independent GET404 absence proof.

`runner_full.prepare` creates a separate owned mode0700 short canonical ephemeral GPG
home with rsa3072 encryption key, one-day key expiry and45-minute request admission.
It takes full independent candidate binding plus chain SHA; it exports only request.json
and recipient-public.asc. State is private mode0600 outside the public artifact root.
No long-lived key is used or exported. It reuses unchanged ownership-marker/inode/
owner checks for scoped cleanup; its request is not eligible for harmless fixture
receive because that producer still enforces fixed fixture pins.

`runner_full.receive(state, independent_chain_sha, artifact_id, fresh_output, client,
clock=..., sleep=...)` polls only the exact full-chain draft, tolerates incomplete
expected asset uploads, then executes authenticated response admission. It runs
full_chain.decrypt_restore_admit in a separate sanitized child with no GitHub token
or inherited injection/search environment. The child is bounded to900seconds; its
returned admission JSON is size-bounded. It verifies exact retained chain/ZIP bytes
and reports evidence only. The private key home is scoped-cleaned on success/failure;
an explicit outer always cleanup remains required after hard cancellation.

There is intentionally no public CLI/workflow for full candidate exchange yet.
Caller constructs the authenticated client from an explicitly consumed token using
the reviewed consume_token helper and retains it only in the receiver process.
The caller must keep the independent chain SHA fixed across prepare/coordinator/
receive; it is an extra workflow input, not an extension inferred from generic
fixture JSON. No application is launched by this runner. A later separately reviewed
step may invoke candidate_runner.run_installer on admitted paths with independent
helper pins and actual-host gates.

## Boundaries and local evidence

Ciphertext remains strictly below2GiB and complete-chain retention bounds remain
unchanged. Before download, free space must cover ciphertext plus three authenticated
payload copies and128MiB margin; full_chain repeats its own decryption/restoration
checks. The complete candidate may still exceed these bounds and must be refused.
Response metadata is bounded to64KiB, draft/job list bounds remain fail-closed, and
expiry is checked before/after long operations. Full-chain flags remain native_executed,
source_closure_complete and release_qualified false even after successful admission.

```sh
python -m unittest discover -s native/qa/installer-followup/rendezvous \
  -p 'test_full_exchange.py' -v
```

Fourteen focused tests pass with documentation-shaped offline GitHub responses and
actual ephemeral GPG plus actual locally recorded four-stage evidence fixtures.
The complete coordinator→authenticated descriptor/ciphertext→receiver child→decrypt→
restore→actual verify_chain→scoped cleanup round-trip preserves exact ZIP bytes.
Other tests reject wrong operator/attempt/chain pins before any fake draft action,
changed/replayed descriptor/request, foreign asset uploader, published releases,
unrecorded cleanup assets and insufficient disk. Expiry cleans the owned key home
and produces failure evidence with no native claim. Upload-failure tests preserve
recorded scope and redact raw errors.

Still pending: reviewed real-candidate manual workflow, actual complete candidate
retention, measured real envelope sizes/timing, real GitHub complete-chain exchange,
and actual ARM/Intel installed first/upgrade GUI/security/exit tests plus separate
installed-path TLS/Python evidence. The earlier harmless hosted exchange and these
local cryptographic/chain fixtures do not satisfy those candidate-specific gates.

Upload readiness correction: both expected asset names may exist before their bytes
are complete. The receiver now waits for both API states to be `uploaded`, allowing
only documented `starter` while waiting, keeping operator/name/duplicate checks
active. Unknown states fail; zero size or missing digest is never accepted by final
response validation. Original deadline remains unchanged. Tests exercise a present
response asset transitioning starter→uploaded and an incomplete ciphertext upload
expiring without any download, followed by owned-key cleanup. The separate harmless
fixture receiver has the same narrow correction and independent tests. GitHub also
notes that failed uploads can leave empty starter assets; a stalled one therefore
times out rather than becoming admissible. See the [asset API](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset).
