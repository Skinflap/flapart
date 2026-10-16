# One-archive Windows qualification

`qualify-candidate.py` reuses the existing native application, ANGLE WARP,
embedded Python/TLS and installer journey helpers. It never uploads, publishes,
dispatches CI, or infers corresponding-source completion. The initial version
has portable safety tests; its combined orchestration still needs a native run.
The constituent gates passed separately against the retained Windows candidate.

Run only on a disposable Windows host using a Python interpreter outside every
build prefix being hidden. The collected directory must be named
`Flapart-Studio`. Supply its existing ZIP, explicit SHA256, the actual earlier
interpreter's extension baseline and hash, and a matching private `ci-candidate`
manifest. The directory's complete file set and bytes must match the ZIP.
No ZIP extraction or archive regeneration is performed by this helper.

```text
python qualify-candidate.py --disposable-windows-host \
  --candidate C:/qa/candidate/Flapart-Studio \
  --archive C:/qa/artifacts/Flapart-Studio.zip --archive-sha256 <sha256> \
  --baseline C:/qa/baseline.json --baseline-sha256 <sha256> \
  --manifest C:/qa/candidate.json \
  --installer-directory C:/source/native/installers/windows-online \
  --installer-binary-output "C:/qa/artifacts/Install Flapart.exe" \
  --temporary-root C:/qa/temporary --output C:/qa/evidence \
  --hide-build-prefix C:/build/sdk --hide-build-prefix C:/build/toolchain
```

The displayed continuations are explanatory; use appropriate Windows shell
continuation syntax or place the command on one line. Optional `--https-proxy`
passes a scoped HTTP CONNECT transport to the existing TLS helper without
changing certificate trust. Application timeout defaults to240seconds.

The helper compiles the existing native C# installer with Windows' .NET Framework
compiler. Installer binary output and temporary runtime copies are forbidden
inside the evidence output. The original Flapart profile is preserved separately
around application and installer tests. A stage checks for leftover processes by
actual executable image under its fresh private QA directory; forced cleanup
keeps the gate failed. If child exit cannot be verified, original profile backups
remain retained for recovery. Hidden build prefixes are restored by the
existing fail-closed context manager, which retains conflicting backups rather
than overwriting anything. Copied QA inputs are made writable; originals are not
modified. No ordinary Krita settings or user artwork are intentionally replaced.

Every stage checks the same explicit archive hash before and after execution.
Receipts and raw logs remain under `--output`, while `qualification.json` records
stage exit status, input hashes, original profile restoration and build-prefix
restoration. Failure never becomes a release qualification. The installer driver
still requires both initial and upgraded native launches, rejected corrupt
upgrade, retained earlier runtime, preserved artwork/settings and ordinary Krita.
The graphics probe remains software ANGLE WARP, not a physical GPU/tablet test.
Downloaded-file security approval, signing, source/license closure and publication
remain separate.

Required source siblings are the existing `test-packaged-runtime.py`,
`test-compiled.py`, `capture-startup.py`, `graphics-probe.py`, portable
`test-relocated.py`, `package-runtime-probe.py`, `flapart_probe` inputs, and the
shared TLS helper plus `tls_fixture.py`. Installer input consists of the existing
`ci_e2e.py`, `FlapartInstaller.cs`, and `SyneMono-Regular.ttf`.

The14portable safety checks include original-profile recovery and retained backups
when child exit cannot be verified. Run them with `python test_qualify_candidate.py`. These exercise
output separation, immutable pins, copied-input permissions, link rejection and
fail-closed binding of existing native outcomes; they do not claim native execution.
