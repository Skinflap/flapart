# Hosted full-chain CLI and manual workflow draft

`hosted_full.py` is the new explicit orchestration layer. The workflow remains a
review draft at `native/ci/drafts/native-installer-full-chain.yml`, outside
`.github/workflows`. No dispatch, candidate upload, secret enrollment, publication
or native execution was performed. A real retained candidate is not established by
this work; source closure remains false.

The draft accepts only exact candidate SHA/bytes, original inventory SHA, original
ci-candidate installer manifest SHA and independent four-stage chain SHA. These
inputs enter the CLI through environment values, never as shell-interpolated code.
Strict SHA/decimal/architecture validation occurs before use. Each fresh Mac job
binds repository, exact workflow path, commit, run, attempt, original and triggering
actor IDs to authenticated GitHub GET results. Attempt-specific job lookup requires
the exact active `installer-arm64` or `installer-x86_64` job and approved runner label.
No peer response supplies those independent pins.

`prepare` verifies local HEAD against the authenticated commit, and compares each
used installer/launcher/font/probe/helper file's actual SHA against `git show` bytes
at that exact commit. These checks cover rendezvous, retention, provenance and native
metadata helpers as well as the installer/probe input set. They reject changed or
untracked inputs instead of recording whatever happens to be present as trusted.
The private session stores context and hashes; `run` repeats both API and committed
helper checks and requires the immutable session to match current workflow inputs.

Prepare calls separate runner_full ephemeral-key preparation. The workflow uploads
only the two named public request files. It captures the artifact action's returned
artifact ID and passes that exact positive ID to the receiver. No coordinator/upload
command is run by this workflow; the independently authenticated local operator
still performs the reviewed encrypted draft exchange. The receiver authenticates
that descriptor/response and complete retained chain before proceeding.

Only after receiver passed:true AND chain_verified:true does the CLI call
candidate_runner.run_installer with original admitted ZIP/installer manifest,
independent helper hashes, requested architecture and actual ciphertext pin. That
entry point repeats full admission and requires real hosted Darwin, GUI session,
fresh profile, measured disk and actual native receipt outcomes. Failed admission
never invokes it. Native success is recorded only from its real measured result;
source_closure_complete and release_qualified remain false in every CLI outcome.
The draft has independent fresh `macos-15` and `macos-15-intel` jobs, fail-fast:false
and no cancellation of an existing exchange. The unchanged request deadline still
applies; the100-minute job timeout does not extend its45-minute admission lifetime.

Explicit workflow token env is consumed by the CLI into memory. It is removed from
process environment before helper subprocesses. Git/source, GPG/decryption and native
children use existing sanitized allowlists; tokens and full environment dumps are
never retained. The long-lived local retention key is not accepted by this workflow.
The receiver normally removes its owned ephemeral key; a separate always cleanup
step handles interruption. Hard cancellation/runner loss can still bypass cleanup;
there is no secure-erasure claim.

## Bounded retained evidence

`collect` copies only seven explicit potential JSON receipts: hosted summary,
receiver summary, chain admission, installer adapter summary, installer E2E and the
two native probe result JSON files. It never recursively copies recovered evidence,
keys, state, descriptor arguments, source trees, raw logs, PNG/KRA artwork or runtime
ZIPs. Each selected file is strict JSON, regular and confined with no symlink
ancestors, at most1MiB; total is at most7MiB. Selection metadata records exact
hashes/bytes and keeps release/source flags false. Oversized or invalid selected
files cause refusal, never truncation or synthetic passing fields. The artifact step
uploads only the fresh selected-json directory's JSON files. Selection alone is not
qualification; missing native receipts remain missing evidence.

## Local validation

```sh
python -m unittest discover -s native/qa/installer-followup/rendezvous \
  -p 'test_hosted_full.py' -v
```

Eleven focused checks pass locally. They validate immutable inputs and API identities,
actual temporary Git commit/helper byte comparison, failure-only installer gating,
private/artwork/recovered-tree exclusion, JSON/symlink bounds and no-op cleanup when
no state was created. PyYAML-based review checks (available locally) inspect the draft
manual trigger/input/matrix/action pins/always cleanup and run every shell block
through `bash -n`; test environments without PyYAML skip those two explicitly.
No test returns a synthetic native-success result. Draft shell contains no inline
GitHub expression interpolation; expressions appear only in declarative env/action
fields. Checkout does not persist credentials; actions are pinned to exact commits.

Parent must review before moving the draft into .github/workflows, mirroring source
and deciding any manual dispatch. Actual complete candidate retention, full-envelope
size/disk admission, hosted full-chain exchange and real installed ARM/Intel GUI,
security and first/upgrade lifecycle results remain pending. Separate installed-path
TLS/Python and downloaded-user security approval gates remain unresolved as already
documented; this draft does not claim them.
