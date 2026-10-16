# Actual native stage evidence

`stage_recorder.py` runs a new command and records what actually happened. It does
not produce historical proofs, source-closure selections, a release qualification,
or an upload. It supports the existing Mach-O/all-slice and PE64 parser, explicit i386 PE32 capture, and thin/universal
static archives as native build inputs. Static archive rows retain real member
counts/architectures/member UUIDs separately; archives receive no invented UUID. ELF and
unsupported native formats fail rather than acquiring fictional metadata.

Example for a **future** post-build signing stage, after reviewing retention:

```sh
python3 native/distribution/provenance/stage_recorder.py \
  --stage final-ad-hoc-sign \
  --cwd /private/build \
  --tree 'package=/private/candidate/Flapart Studio.app' \
  --evidence /private/evidence/final-sign \
  --tool /usr/bin/codesign \
  --retain-native-bytes \
  -- /usr/bin/codesign --force --deep --sign - '/private/candidate/Flapart Studio.app'
```

Every stage requires a fresh evidence directory **outside** all captured trees;
that directory cannot contain a captured tree either. Capture the whole SDK when
its framework aliases refer elsewhere within that SDK. Tree roots may be absent
before a build, but cannot be symlinks. All links must remain inside their tree,
including aliases not pointing to native binaries. Invalid/truncated native data,
broken links and changing files fail capture. This is a trusted-build observer,
not a sandbox against a malicious child or concurrent filesystem adversary.

Use explicit argv after `--`; no shell expansion is performed. The first executable
is resolved and hashed. Supply every relevant script with repeated `--helper` and
nested build/relocation/signing tools with repeated `--tool`; they are hashed before
and checked again afterward. The recorder/parser are recorded automatically.
An interpreter executing a script requires `--helper script.py`: hashing Python
alone does not identify its input program. Nested process discovery is not claimed.
Relative executable paths are interpreted from `--cwd`.

## Output and failure behavior

The private evidence directory contains:

- `before.json`, written and hashed **before** starting the command.
- Raw separate `stdout.log` and `stderr.log`, with SHA256 and byte lengths.
- Atomic `receipt.json`: exact requested/executed argv, working directory,
  UTC start/end and elapsed time, actual return code, tool/helper hashes,
  allowlisted actual child environment, complete before/after snapshots and
  per-path added/removed/modified records.
- With `--retain-native-bytes`, `native-bytes/SHA256` contains the exact captured
  input/output file bytes, privately readable, deduplicated within that stage.
  Each native snapshot row references its retained blob. Without the flag, the
  recorder retains hashes/metadata only: **it cannot recover binary bytes later**.

Executable/shared-library native rows include path, SHA256, byte length, mode, architecture set, every
slice's UUID/imports/rpaths, and canonical format. Symlink aliases are separate
rows. Matching UUIDs are merely one field; they never substitute for byte hashes
or establish unchanged executable code. Code-signature changes therefore appear
as actual SHA changes even when UUIDs stay the same.

Nonzero commands retain logs and after-images. Setup/capture failures after
creation retain a failed receipt; safety-layout/credential checks fail before
creating evidence or executing the command. If a snapshot fails, comparison is
marked incomplete, and the recorder does not invent removals for the missing
snapshot. Tool/helper mutation fails the stage even when the command exits zero.
CLI exits zero only when the command and both capture passes succeed. Importers
must check `passed`, `comparison_complete`, and return code, not receipt existence.

`--timeout SECONDS` terminates the child process group on POSIX; on Windows it
terminates the direct child only. Windows jobs needing timeout-safe descendant
control require a Job Object or equivalent integration before using timeouts for
build stages. A timeout is always failed evidence. Commands must finish their
children before returning; background builds cannot produce a stable stage chain.

## Environment and privacy boundary

The child receives only the fixed `ENV_KEYS` allowlist in the script: build paths,
compiler/linker settings, selected SDK/deployment configuration, locale/temp/home,
Python/Qt dependency paths and local trust/provider paths. Unlisted variables,
including credential/service tokens, are neither passed nor recorded. There is no
arbitrary environment-dump option. Confirm that a required setting is permitted
before integrating a build; do not silently replace this with the parent process's
full environment.

A conservative credential-like argv/value check rejects obvious password/token
arguments and credential-bearing URLs. It is not a universal secret detector.
Only run reviewed build/package commands without credentials in arguments,
allowlisted settings or their output. Raw command logs are evidence and are not
silently redacted; do not use this wrapper for login, deployment or secret-bearing
commands. Do not pass signing credentials here. The example is local ad-hoc
signing, not Developer ID signing or notarization.

`--retain-native-bytes` is an explicit **local** retention decision. No networking,
remote storage, encryption enrollment or publication is implemented. Keep the
unclosed binaries private. The current diagnostics-only CI job is not changed.
For a later job, storage/recipient-encryption and the final archive must be handled
by its separately reviewed retention design; this recorder does not authorize
uploading native blobs.

## Integration points and limits

Wrap each stage separately: component build/install; original SDK to promoted SDK;
upstream collector; runtime completion; final codesign; signature verification.
Capture both source-input and destination native trees where applicable, and
check that each next before-hash equals the preceding output-hash. Capture final
installed prefixes, not enormous compiler scratch trees unless those object files
are needed. Hashes of source files/patches are **not** native-tree snapshots: retain
actual source archives, prepared-tree diffs, generated feature/config files,
licenses and build recipes separately and bind those artifact hashes in the
reviewed component provenance.

The stage recorder observes an outer command and before/after bytes. Its argv is
not a claim to have logged every internal subprocess. For upstream collector and
runtime completion, retain their own detailed operation receipts/logs as hashed
helpers/artifacts and review internal commands. A source change to the helper must
change the recorded hash. A failed or partially successful stage remains failed;
do not promote it by manually setting JSON status fields.

Also retain a toolchain manifest with compiler/linker versions, Xcode/OS/SDK
identities and generated build settings; executable SHA alone does not describe
an entire toolchain. Following final signing, bind archive member bytes to these
final output hashes and retain the **exact ZIP**. Runtime tests and the
source-qualification producer must consume that same payload. This utility never
sets source closure or release qualification true.

Portable tests run real short subprocesses against synthetic thin/fat Mach-O
fixtures, exercising failure retention and byte hashing rather than fabricated
successful native builds:

```
python3 -m unittest discover -s native/distribution/provenance -p 'test_*.py' -v
```

Native Mac/Windows build-stage integration remains unvalidated until actually run.

A real retained SDK `libhwy_test.a` was additionally inspected read-only: both
arm64/x86_64 static-archive slices parsed with two members each. Whole original
SDK trees also contain foreign PE32 development assets. The recorder now captures
those exact bytes, actual i386 CPU and normal/delay imports, so the collector's
before-completion tree remains observable. This does not approve shipping PE32 in
a Mac app: the chain verifier still rejects every PE final member. The specific
retained `pyqtbuild/bundle/dlls/openssl-32/libssl-1_1.dll` parsed as i386 PE with nine
imports, SHA256 `f5ba7eef440ad9f83a7d59236499c412d7849a1856b5a5c689c4635db35f27a7`;
local `file` independently identified PE32 Intel80386. There is no broad foreign
binary skip or invented host architecture. Preserve original SDK archive/hash
correspondence separately. No native build was executed by these checks.
