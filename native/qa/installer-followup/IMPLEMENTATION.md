# Scoped installer evidence implementation

Local implementation only; no CI, native execution, secret enrollment, transfer,
release freeze or publication. The private exact-candidate transfer design remains
in `PROPOSAL.md`. No Windows installer/launcher implementation or binary changed.
The parent authorized the small portable child-probe identity hook and its owner
confirmed no conflicting edits.

Changed producer files:

- Both identical `native/installers/{macos-online,windows-online}/ci_e2e.py` copies.
- `native/installers/macos-online/Flapart Studio.command` (explicit QA branch only).
- `native/qa/portable/flapart_probe/__init__.py` (native-image observation and Windows
  process/hardware measurement; existing Qt close/lifecycle logic preserved).

The driver requires `--archive-sha256` and `--architecture arm64|x86_64`. The archive
must match both this independent pin and the candidate manifest. Only the known
installer-generated assessment files or Windows launcher may appear outside the
ZIP member set. It compares every
installed ZIP member's actual bytes/symlink target with that archive, checks the
installed launcher matches its tested source, and binds the child's process-image
path/hash to the pinned installed executable. Mac uses `_NSGetExecutablePath`;
Windows uses `GetModuleFileNameW`, corroborated by Qt's application file path.
Embedded Python's executable setting is not used as native image identity. The child also
records its actual PID. After the launcher returns, the driver requires that PID
to have exited: POSIX signal-zero observation, or a Windows process wait handle.
It never sends a termination signal to that reported native PID.
Windows `IsWow64Process2` supplies actual machine identity; unsupported translated
Windows execution remains rejected under the present freeze architecture contract.

The Mac QA branch requires the explicit architecture option, the existing compiled
probe flag and output directory environment. It uses `open -n -W --arch` while the
ordinary invocation remains `open -a ... --args ...`. No security-policy checks
were removed. Parent workflow integration must add the two required driver args.
An explicit `--disposable-native-host` switch supports a private native host without
pretending GitHub Actions ran; both modes require an absent Flapart profile. Use
separate fresh OS users/VMs for different architecture runs. No real profile is
cleared. The test intentionally seeds ordinary Krita sentinel files only on such
a disposable host and verifies they remain intact.

Receipts start with `passed:false`, `native_execution:false`, and
`release_qualified:false`. Actual checked stages update individual outcomes. Every
stage retains argv, direct executable hash before/after, combined log/hash and exit
code or timeout state; failure writes a final receipt. Child identity fields are
copied only after actual probe validation. `native_probe_sha256` binds exact raw
child output; `installed_executable` binds its archive member. Input hashes retain
producer, original manifest, archive, installer/launcher/font and probe identities.
There is no claim that nested commands were independently observed. The runtime
uses an allowlisted environment; only its key names are recorded, never a full
inherited environment or secrets.

The corruption attempt must preserve the receipt, artwork and settings; its
explicit missing flag is now emitted after comparison. Before/after snapshots
hash all previous-runtime files and record confined symlinks, instead of checking
only directory existence. The subsequent same-archive CI edition upgrade is
verified against ZIP bytes again. This is an installer upgrade mechanics test;
it **does not launch the upgraded edition** or imply a separately built version.
Probe artwork and profile snapshots must be unchanged throughout the upgrades.
Source closure and public release qualification are not produced by this driver.

Qualification run locally:

```sh
python3 -m unittest discover -s native/qa/installer-followup -v
python3 native/installers/windows-online/test_freeze_release.py
python3 -m py_compile native/installers/macos-online/ci_e2e.py native/installers/windows-online/ci_e2e.py native/qa/portable/flapart_probe/__init__.py
bash -n 'native/installers/macos-online/Flapart Studio.command'
```

Twenty-three portable tests pass, plus the existing freeze contract test. Tests use
synthetic bytes and an isolated shell harness for the launch branch. The shell
harness replaces `open` only inside its own temporary script; production security
checks are unchanged. No synthetic receipt is native qualification.

## Still requires actual native checks

- Verify `open -n -W --arch` support, probe environment inheritance and requested
  child architecture on the approved Mac host. Run real ARM and x86_64 (Intel or
  explicitly measured Rosetta) separately against the exact retained archive.
- Run the actual image-path APIs and Qt corroboration inside Krita, not host Python.
- `open -W` returns launcher status, not an independently observed native process
  exit status. The driver requires complete Qt lifecycle/`about_to_quit`, normal launcher
  completion and observed native PID exit. A real portable child-process test
  proves a launcher returning zero before its child exits is rejected. These
  checks still do not distinguish a late shutdown crash from a clean Mac exit. If a
  strict native exit-code gate is desired, add a reviewed Mac process-exit observer;
  do not fabricate it from `open`'s exit code. Windows launcher already waits and
  checks its child exit code.
- A timed-out Mac LaunchServices child can outlive its `open` process. The driver
  does not kill unrelated apps or automate security review. Treat that disposable
  session as failed and clean it up explicitly; never reuse it for another claim.
- Verify normal signature/quarantine behavior and user-review blocking. No
  Gatekeeper/SmartScreen bypass or automatic approval has been added.
- Native TLS/Python receipts and source closure remain separate requirements. The
  current retained candidate is not made public or release-qualified by these edits.
