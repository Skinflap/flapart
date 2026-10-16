# Actual Mac packaging stage recording

`package-candidate.py --stage-evidence /private/fresh-package-evidence` opts into actual command recording. Existing callers without this option retain direct command execution. Evidence must be fresh and outside the candidate output directory (neither may contain the other). `--retain-native-bytes` additionally requests local private native snapshots; it requires stage recording and never uploads them.

Four commands share the exact tree label `package` and root `<output>/Flapart Studio.app`:

1. `collector`: run the actual upstream `packaging/macos/macos-deploy.py`, then rename the single app and update its Flaptown plist in the same recorded command. The initial bundle is absent; the after snapshot is the actual collected bundle.
2. `completion`: run the existing maintained-runtime completion helper, including relocation.
3. `codesign`: actual ad-hoc codesign operation.
4. `verify`: actual strict/deep codesign verification.

The recorder receives the packaging driver and collector wrapper as hashed helpers; collection also records the upstream collector. Completion records its helper and native parser. Required tools are resolved against the same environment PATH used by the commands and passed for identity capture: collector install_name_tool, lipo, otool, codesign, rsync, file, PlistBuddy, krita_version, python, macdeployqt; qtpaths is captured when available (upstream has an explicit absence branch). Completion records install_name_tool; both signing operations record codesign. Missing required tools refuse recorded execution. This is explicit identity capture, not an OS-wide subprocess audit or a claim that every listed tool was invoked.

No past transformation is reconstructed. Collection additionally captures the named `sdk` input tree before and after the actual command; later stages capture only `package`, so SDK bytes are not retained four times. The collector wrapper separately hashes all regular SDK files and records symlink targets/directory membership before and after, refusing changes (including non-native files). It logs the measured regular-file byte total. Parent read-only baseline compatibility evidence reports 602 native files totaling 1,122,976,032 bytes; expect roughly that native input retention plus actual package outputs, with content-addressed deduplication within each stage. The collected bundle's original build provenance remains separate. Recording failures stop packaging and retain the recorder's failed receipt when execution began. Final inventory retains `publishable:false`, `source_closure_complete:false`, and `relocation_test_passed:false`. Chain verification, actual relocated execution/TLS tests, source/license closure, and final artifact binding remain independent gates.

The completion report remains outside the app but inside candidate output, as before. Stage receipts/logs/native snapshots remain entirely outside candidate output. No signing identity or notarization claim is introduced.

Portable validation:

```sh
python native/qa/macos-build/test_package_stage.py -v
```

Eight tests pass: exact common tree/tool/retention arguments, unrecorded compatibility, disjoint/fresh evidence layout, actual recorder success and failed command propagation, collector rename/plist preservation, SDK mutation refusal, and missing-tool refusal. The recorder tests execute small synthetic Python commands on the host, never a Mac runtime. Native packaging and tool compatibility remain pending a real Mac run. No workflow, mirror, CI dispatch, or publication was performed.

The exact stage names match the chain verifier. The package child environment sets `PYTHONDONTWRITEBYTECODE=1` (included in the recorder allowlist), rather than ignoring pycache mutations afterward. The original retained SDK was inspected read-only: bin/python -> python3 -> ../lib/Python.framework/Versions/3.13/bin/python3; the resolved target exists. The driver requires this SDK command to exist and resolve inside the supplied prefix before packaging.
