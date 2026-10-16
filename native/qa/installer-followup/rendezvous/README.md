# Offline exact-candidate rendezvous protocol

`protocol.py` produces and validates the explicit transfer root and exchange
metadata. It performs no network action, key enrollment, encryption, native launch,
workflow dispatch or publication. This is a protocol component, not an authenticated
GitHub client. Callers must keep authenticated API observations separate from files
provided by an exchange peer.

## Contract

- `request(binding, public_key_bytes, fingerprint, nonce, created, expires)` creates
  a strict request. Binding includes repository/workflow/run/attempt/commit/job,
  actual requested architecture, expected operator numeric ID, ZIP SHA/bytes and
  original inventory/manifest SHA. Deadline is at most one hour. Nonce must be a
  newly generated 256-bit random value (use `secrets.token_hex(32)`); the pure checker
  cannot prove randomness. Full uppercase v4 fingerprint is required.
- `authenticate_request(raw, key, expected, run, job, artifact, now)` compares the
  request with independently pinned dispatch inputs and authenticated observations.
  `run` and `job` normalized shapes are exact as shown in tests. Adapter must fetch
  run and attempt-specific job from the expected repository; verify job ID and
  approved matrix job name/labels before normalizing `architecture`. It must verify
  the expected workflow/event/actor/commit and job still in progress.
- `artifact` is normalized metadata from the authenticated artifact ID download:
  id, run_id, expired, request_sha256, key_sha256. The latter two are computed from
  the exact downloaded members, not values supplied in JSON. The adapter must bind
  the GitHub artifact archive digest, run/attempt and unique architecture-specific
  name, then extract only those two bounded regular members with no links or
  duplicates. The artifact service does not expose a trusted architecture field.
  Never derive trusted observations from `request.json` itself.
- Public-key SHA is checked here; actual OpenPGP parsing and fingerprint matching
  are deliberately delegated to existing `retain.py encrypt`, which imports only
  public material into an isolated home and pins the full recipient. Callers MUST
  use that check before encryption; merely passing this module is not key validation.
- `pack(request, inputs, fresh_output, now)` takes exactly three absolute regular
  input paths mapped to candidate.zip, candidate-inventory.json and
  candidate-manifest.json. It checks all pins, copies exact bytes into a private
  staged root, rechecks original inputs, validates copied bytes and publishes the
  new root only on success. Inputs/output must have no symlink ancestors and no
  overlap; resolve known platform temporary-directory aliases before selecting
  paths, not after accepting untrusted paths. Original files are never modified.
- Output contains those three files, exchange.json and retention-compatible
  inventory.json. `validate_pack` checks exact members, sizes/hashes, original
  candidate pins and complete request binding, including nonce/expiry. No ZIP
  extraction occurs here. Original candidate inventory semantics and packaging
  chain must already be validated locally; this module establishes byte identity,
  not source closure or validity of an application archive.
- Encrypt the root using existing `retain.py encrypt` with this inventory and the
  checked ephemeral public key. `response` records the actual ciphertext hash/size
  plus returned draft/asset IDs. Serialize its result with `encode`.
- `validate_response` checks downloaded response/ciphertext bytes against the exact
  original request and independently authenticated release, ciphertext asset and
  response asset observations. Normalize their shapes as shown in tests. Draft
  author AND both asset uploader numeric IDs must match the expected operator;
  reject a published release. Adapter obtains request_sha256 from the authenticated
  draft's explicit exchange body, not untrusted response JSON. It must verify the
  unique draft tag/exchange identity, complete asset listing (no ambiguous response
  sets), actual API asset IDs, actual lengths/digests and request deadline before
  calling this function. Ciphertext is not decrypted here.
- Decrypt using existing `retain.py decrypt` and the runner's ephemeral GPG home,
  then call `validate_pack` again with the original in-memory request, not the one
  recovered from exchange.json. Deadline checks must occur at each admission step.
  Network adapter must admit one response only per job and never overwrite admitted
  output. A pure stateless verifier cannot enforce a global replay ledger.

Transfer total/ciphertext limit is strictly below 2 GiB, matching the minimal
single-release-asset design. Metadata limit is 64 KiB. Larger transfers need a
separately reviewed bounded chunk protocol. No secret is put in metadata. This code
assumes private, nonconcurrently modified input/output workspaces; it is not a
hostile same-UID filesystem isolation boundary. It does not claim encrypted transport
itself, authenticate caller-supplied observations, or turn any native outcome true.

## Portable verification

```sh
python -m unittest discover -s native/qa/installer-followup/rendezvous -p 'test_*.py' -v
```

Fixtures contain exact arbitrary ZIP/ciphertext bytes rather than real native apps
or valid OpenPGP material. They test identity, expiry, replay binding, authenticated
observation mismatch, input/output mutations, recomputed attacker inventory, duplicate
JSON keys, symlinks, missing/extra members and output overlap. No native qualification
is manufactured. A harmless real GPG/GitHub handshake remains separate future work.

## Read-only GitHub adapter

`github_read.py` adds GET/download only. `Client(token)` requires an explicit caller-
supplied token; it does not discover credentials or inspect environment/credential
files. `fetch_request` checks the authenticated workflow run, exact attempt's job
membership, fixed `installer-arm64` / `installer-x86_64` job name and approved
`macos-15` / `macos-15-intel` label, then authenticates the explicit artifact ID/name,
run/commit, API digest and exact downloaded ZIP bytes. The archive permits only two
bounded regular files: request.json and recipient-public.asc. No extraction to disk.

`fetch_response` requires an explicit draft ID and fresh absolute ciphertext path.
It verifies draft tag (`draft_tag(request)`), author, exact commit, unpublished state
and strict exchange body before downloading. Body must be `encode({'schema':1,
'request_sha256':digest(encode(request))})`. Complete asset listing must contain only
candidate.gpg and response.json; both authenticated uploaders must be the expected
operator. API hashes/lengths/IDs and response bindings are checked before ciphertext
admission. Ciphertext is streamed with a byte bound to an exclusively created file,
then rehashed. Failure removes only this attempt's file. No existing file is replaced.

Metadata is bounded to 2 MiB, artifact ZIP to 1 MiB, each request/key member to 64 KiB,
response metadata to 64 KiB and ciphertext strictly below 2 GiB. Missing API digests
fail closed. A job listing exceeding one complete 100-item page is refused; this
minimal workflow should contain only its two known jobs. Deadlines are rechecked
with elapsed monotonic time after download. Caller still owns poll cadence, retry
admission, cancellation, ephemeral-key lifetime and independent native-job outcome.

Authorization is sent only to api.github.com. Download redirects are explicitly
processed, HTTPS-only, without credentials/userinfo/fragments, to githubusercontent.com
or Azure blob.core.windows.net subdomains. Redirected requests contain no authorization,
and no automatic redirect handler is enabled. New storage origins fail closed and
need review. Raw transport errors are replaced with fixed messages; no URL, signed
query, API body or token is logged or included in returned evidence. The HTTP adapter
only returns the normalized metadata and exact input bytes needed by the caller.

Sources for response shapes and GET/download behavior:
[Artifacts API](https://docs.github.com/en/rest/actions/artifacts),
[workflow job attempt API](https://docs.github.com/en/rest/actions/workflow-jobs),
[release assets API](https://docs.github.com/en/rest/releases/assets).
Tests use documentation-shaped offline HTTP fixtures, not captured live requests.
No actual token permission, redirect origin or hosted GUI behavior is proven by them.

The additional parent-owned `test_encrypted_exchange.py` executes real local GPG
pack→encrypt→decrypt→validate with ephemeral homes and a harmless exact payload.
It checks ciphertext corruption (including recomputed outer hash) and expiry. That
is actual local encryption evidence; the original protocol tests use opaque fixture
ciphertext. Neither suite executes a native application. A real GitHub harmless
handshake remains future work, separate from these offline adapter tests.

Parent's read-only live check, recorded separately in
`../github-read-live-observation.json`, downloaded an existing harmless artifact and
matched its API byte count and SHA. It found that the artifact ZIP endpoint requires
the documented vendor-JSON Accept header; release asset binary requests use
octet-stream. The adapter now distinguishes these endpoints and tests both headers.
That observation establishes the tested artifact download behavior only, not a live
rendezvous/draft exchange or native execution. Run authentication also requires the
API's triggering_actor ID, so a different rerun operator is not silently accepted.
