# Exact-candidate installed-runtime follow-up

Baseline review, recorded before the scoped implementation. See `IMPLEMENTATION.md`
for the current edits and remaining native checks. This document describes the
pre-change producer and the private transfer proposal. No native run, workflow edit,
CI dispatch, secret enrollment, candidate transfer, or publication performed.
The parent reports run **38906245762** retained its exact Mac candidate encrypted.
That candidate may be reused for a later private installed-runtime test; this
review has not decrypted it or independently validated its retention chain.
Relocation/TLS execution from the build is not an installer journey.

## Inspected contracts and concrete gaps

Both `native/installers/{macos-online,windows-online}/ci_e2e.py` copies are currently
byte-identical. Both freeze scripts share the schema-2 contract documented in
`windows-online/FREEZE-EVIDENCE.md`. Neither existing file is modified here.

| Existing behavior | Gap for an actual qualification receipt | Minimal producer change, requiring owner review |
| --- | --- | --- |
| E2E verifies the ZIP hash from a candidate manifest, then changes status to `qualified` in a temporary installer copy. | That status only unlocks installer mechanics. It must never become a shipped pin. | Retain the original candidate manifest plus the temporary manifest as hashed test inputs; mark the output `release_qualified:false` permanently. Do not call freeze or publish. |
| Success reports `payload_sha256` and `platform.platform()` only. | Freeze requires `target_platform`, `runtime_scope:installed-runtime`, `native_execution:true`, and process/hardware/mode identity. | Copy measured identity from the **actual launched application child** after checking it against the requested architecture. Never fill these from the Python driver or runner label. Canonical universal target is `macos-universal2`; installer manifest uses `macos-universal`. |
| Portable plugin already emits Mac process architecture and `sysctl.proc_translated` mode. Windows emits process architecture but not hardware/mode. | Driver drops Mac identity; Windows needs trustworthy actual OS/native-machine information, especially under emulation. | Preserve Mac child fields. Windows producer should use actual process/native-machine APIs (e.g. IsWow64Process2), normalize supported values, and fail on unsupported combinations. Do not infer physical hardware from a workflow matrix. |
| Failed upgrade asserts unchanged install receipt, artwork, and profile. | It emits only `failed_upgrade_preserved_receipt`, omitting the required `failed_upgrade_preserved_artwork_and_settings`. | Emit the second flag **immediately after the existing byte-snapshot comparison**, not in a later receipt converter. Save the failure exit code/log and before/after snapshot digests. |
| Successful upgrade compares artwork/profile/ordinary-Krita snapshots and checks old release directory exists. | The prior runtime is not byte-checked, and the upgraded runtime is not launched. | Snapshot old release including confined symlinks before/after; require exact preservation. Record this is same engine ZIP with CI-only version tag. Launch the newly selected installed release as a separate upgrade test if claiming upgraded launch health. |
| Mac launcher ends with `open -a "$app" --args ...`; driver waits for `open`, then polls probe output. | `open` can return before app exit, select native architecture automatically, or reuse an existing process. Wrapping the driver with `arch -x86_64` does not force LaunchServices child architecture. | Add an explicitly reviewed QA launch selector that still invokes the real installed launcher, uses LaunchServices `-n -W --arch <arch>` supported on the target Mac, and verifies resulting child identity. Preserve normal launcher behavior. Never substitute direct executable launch while calling it launcher qualification. Validate flags on the actual native host first. |
| Driver polls a fresh result directory, but ignores launch return code and has no actual executable path/hash binding. | A receipt can describe the wrong image or a child which later fails shutdown. | Child records `_NSGetExecutablePath`/resolved executable identity and SHA; driver checks it is the selected installed release and matches the inventory member. Require orderly app exit and retain its code. Preserve the installed release selected in `flapart-install.json`. |
| Environment removes several Python/Qt/DYLD keys and replaces PATH. | It inherits other injection/search variables, e.g. DYLD_LIBRARY_PATH, DYLD_INSERT_LIBRARIES, QT_QPA_PLATFORM_PLUGIN_PATH, QTWEBENGINEPROCESS_PATH. | Use a reviewed minimal runtime environment, preserve only actual UI-session essentials, and retain an allowlisted environment receipt. Never log a full environment. Verify loaded runtime files are bundled/system, not SDK. |
| Probe code is copied into the private profile; output/logs are not hash-bound from E2E. | No receipt chain binds exact installer, launcher, helper, probe, font and child results to this run. | Record SHA/bytes for these explicit inputs and initial/final install receipts, all stage logs, child receipt and snapshots. Include exact argv and exit codes, with no secret environment or broad workspace dump. |
| Most failures raise before `installer-e2e.json` is written. | Failed native attempts are poorly distinguishable from missing evidence. | Write a failure-first receipt and append checked stages under try/finally. A partial run must stay failed. Preserve raw probe error and bounded logs. Do not convert missing fields to true. |
| Driver requires Darwin/Windows and literal GitHub Actions + CI env flags. Profile must be absent. | It cannot legitimately run on a fresh local/private Mac as-is; setting fake CI flags misstates provenance. Running ARM then Intel in one profile also fails freshness. | Add a separate explicitly authorized disposable-host mode with truthful host type and enforced fresh OS user/profile; or use actual fresh hosted runners. Keep architecture runs in separate fresh accounts/VMs. Never erase a real user's profile to satisfy the test. |

The screenshot/PNG/KRA probe already checks a real 64×64 canvas, pixel round-trip,
Studio action reopening, font and browser handoff URL. It intercepts browser open
inside the probe; it does **not** prove browser login/publication. The downloaded
Gatekeeper approval path also remains explicitly untested. No helper may automate
Open Anyway, disable assessment, strip quarantine, or re-sign the retained app to
make a test pass. A security prompt is a recorded blocked result requiring actual
user review, not permission to bypass system policy.

## Reuse the exact private candidate without a rebuild

1. Pin the retained ciphertext SHA/size and authenticated commit/run identity.
   Recover locally using `native/distribution/private-retention/retain.py decrypt`
   with the existing protected GPG home. The long-lived private key stays here;
   do not export it, upload it, put it in CI secrets, or pass its unlock value in
   argv/environment. Verify retention inventory and `verify_chain.py` against the
   recovered stage manifest before selecting `candidate.zip`. Record its actual
   SHA and original candidate inventory. Do not rezip, modify, re-sign or replace
   bundled Studio/plugin bytes with current working-tree files.
2. Select a fresh, approved private Mac destination (native ARM and Intel, or ARM
   plus installed Rosetta with explicitly labeled translated x86_64 execution).
   Universal freeze requires both actual process architectures; a physical Intel
   machine is optional under the existing gate. VM/host names are not measurements.
3. Preferred transfer is authenticated private transport to a disposable private
   Mac with encrypted storage. If untrusted/shared transport is needed, generate
   an ephemeral recipient key on that Mac, independently verify its full public
   fingerprint through the authenticated host channel, and locally re-encrypt
   only the explicit candidate/follow-up inputs to that public recipient using
   the existing retention envelope. The original retention private key never
   leaves this host. Destination retains only its own ephemeral key. Delete
   temporary plaintext normally after evidence recovery; do not promise SSD
   secure erase. No plaintext public artifact or public candidate URL is needed.
4. A future hosted-runner path needs a reviewed ephemeral-recipient rendezvous:
   authenticate run identity plus exported public fingerprint, send only freshly
   encrypted recipient-bound bytes, and keep decrypt key solely on that runner.
   This is extra workflow design, **not** an existing callable mechanism or a
   reason to enroll the long-lived key as a secret. A private self-hosted Mac is
   simpler for interactive system-security review. No workflow is proposed as
   ready to dispatch until transfer, UI session, disk budget and cleanup are reviewed.
5. Use the original pinned ZIP via the installer's existing local-archive argument.
   Its hash must match the retained candidate. A test-only manifest can enable
   installer mechanics exactly as current E2E does, but remains private and labeled
   CI/test-only. Validate layout/inventory first. Keep source closure unqualified;
   reuse is diagnostic testing, not public redistribution of an unclosed runtime.
6. Run each architecture with a fresh profile and private output. Bind raw child
   results to installed executable bytes and the selected install receipt. Capture
   installation, first launch, corrupt upgrade refusal, same-bytes edition upgrade,
   profile/artwork/ordinary-Krita preservation and previous-runtime byte equality.
   Transfer only explicit evidence back, then retain it with original candidate SHA.
7. Separately run packaged TLS/Python probes from the **installed** bundle if
   installed scope is wanted, using bundled Python `-I -B` and its maintained CLI,
   unmodified default trust, explicit baseline manifest and exact archive. Existing
   relocated receipts stay relocated; never relabel them installed. Final freeze
   still needs all architecture/categories, complete native inventory and reviewed
   corresponding-source closure. An installer pass cannot close those gaps.

## Reviewable local implementation

`audit_installer_receipt.py` is a read-only, fail-closed audit of **captured claims**.
It hashes the actual candidate before/after, requires an independently supplied
SHA, checks all current freeze installer gates, validates actual child architecture
agreement and requires a new producer's `native_probe_sha256` binding. Missing
fields stay gaps. It outputs only `installer_fields_complete`, never a release
receipt; even complete submitted claims do not prove execution occurred. It does
not parse/extract the ZIP or replace native inventory/source closure validation.
Inputs reject symlink paths/parents; receipts are bounded to 4 MiB; outputs cannot
overwrite existing files. Local native artifact custody and producer integrity
remain separate review requirements.

```sh
python3 -m unittest discover -s native/qa/installer-followup -v
python3 native/qa/installer-followup/audit_installer_receipt.py \
  --archive /private/recovered/candidate.zip --sha256 REVIEWED_CANDIDATE_SHA256 \
  --receipt /private/run/installer-e2e.json --child /private/run/native-first/result.json \
  --target macos-universal2 --architecture arm64 --output /private/run/installer-audit.json
```

Ten portable tests pass: existing producer shape fails, each missing gate fails,
wrong requested/child identity fails, translated execution remains explicit,
changed child/archive bytes fail, wrong scope/hash and symlinks fail, automated
security approval fails, and a fully synthetic field fixture never becomes release
or native-execution proof. These are not native installer tests. Next edge: approve
specific producer/launcher changes and private native-host transfer plan, then run
actual exact-byte journeys. Existing native-agent files/workflows remain untouched.
