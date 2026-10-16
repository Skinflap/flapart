# Native delivery status

Snapshot: 2026-10-16. Live Linux online installer 0.1.3 includes maintained CPython 3.13.16 and the pinned Ubuntu OpenSSL security refresh. Studio plugin 0.1.1 fixes borrowed-window callbacks and registers its shortcut through Krita action metadata. Previously published artifacts remain immutable.

## Qualified deliveries

- Plugin 0.1.1: `dist/flapart-studio-0.1.1-krita-plugin.zip`, SHA256 `7401d694e5a0b408663f87548cc856f7f39de2790bbdc9f19021e6610e5094c2`.
- Linux x86_64 online installer 0.1.3: `dist/flapart-studio-0.1.3-linux-online-installer.zip`, SHA256 `aff2fcbe896298770b53db26c06f04d50720912841962d0de9854380f4ad21b9`. It downloads a pinned official Krita engine, the complete verified CPython 3.13.16 refresh, and Ubuntu OpenSSL `3.0.2-0ubuntu1.30`, then installs Studio into isolated Linux configuration/data paths.
- Actual network installation, upgrade, exact pixels/layers, PNG/editable KRA, menu/shortcut, preserved settings/artwork and corrupt-payload refusal pass. Installed Python and Qt accept valid TLS and reject unknown CA, wrong hostname and expired certificates; default-trust real HTTPS succeeds. Fresh Ubuntu22.04 runtime tests also pass without build directories. Evidence: `qa/linux-installer-0.1.3/QUALIFICATION.md`, including `network-qa`, `ubuntu-runtime`, and final compatibility-preflight/upgrade receipts.
- Actual Windows 11 evaluation VM: brush input, undo/redo, native save/reopen, real PNG chooser/export, menu reopening and Ctrl+Alt+F pass. The ordinary Microsoft evaluation was activated normally. The preserved VM is now running an isolated namespaced source build from a read-only payload ISO. Evidence: `qa/windows-vm/QUALIFICATION.md`.
- Actual Intel and Apple Silicon macOS hosted runners pass the official-engine plus Studio enhanced probe; parent owns current GitHub run evidence and public release qualification.

These are official-engine plus Studio integrations, not yet a qualified independent Windows/macOS compiled application distribution.

## Independently compiled source fork

The full Linux Qt6 source fork builds and passes the native functional/style/menu probe, including separate settings/resource/log sentinels. Qt6 upstream marks this branch experimental. Source preparation reproduces the patch exactly from pinned upstream commit `bd6e8d061d2f0388c5b10278786cf0fe62e3135f`. Latest patch SHA256: `198503f7dc85487a71c08bebf0220c4d6c03cd3cbd6127405e7950325132dc97`.

The Windows Qt5 source build compiled successfully in hosted CI but its startup probe timed out; a local Windows VM build now preserves state for diagnosis. The original Mac ARM compile remains active; the Intel attempt failed because SDK qmake is ARM-only. The next Mac build is configured for a universal binary from the ARM host. New CI dispatches are temporarily held while notification noise is reviewed. Corrected SDK locks derive the upstream dependency seed and complete dependency graph; obsolete registry leftovers are excluded. Both SDKs passed complete collision audits and extraction, including case-insensitive paths. Windows has 83 packages; Mac has 76. An exact Mac Python framework directory alias is explicitly resolved. These dated SDK inputs are reproducible build choices, not claims of exact historic upstream release SDK identity.

## Remaining release work

Compile/runtime qualification of the independent Windows/macOS fork; collect and relocate runtime dependencies using upstream packaging rules; prove package launch without SDK/compiler/Python environment; finish corresponding-source and license inventories against actual packaged binaries; qualify installers and native platform launch behavior. Candidate scripts explicitly report `publishable: false` until these gates pass. Mac local ad-hoc signing is distinct from Developer ID and notarization. Physical tablet pressure/tilt and broad hardware qualification remain outside the automated probes.

`distribution/sources/platform-closure/` retains exact recipes, source archive receipts, additional platform sources, and SDK binary identities. The older full offline Linux runtime archive remains unpublished; its additional distro-library source inventory is not closed. No incomplete desktop artifact should be presented as a released supported application.

## Security refresh and branding work

The SDK TLS audit found unsupported OpenSSL 1.1.1 in the Windows/macOS Qt5 packages; switching to the inspected Qt6 SDK would retain that problem. Final binaries are held while isolated native CI builds OpenSSL 3.5.9 and maintained CPython 3.13.16, rebuilds QtNetwork, and verifies real HTTPS plus trusted, unknown-CA, wrong-hostname, and expired-certificate fixtures. Build helpers and workflow are public; native success is not assumed from static checks. First maintained-TLS experiment: GitHub Actions run `38889995113`.

Historical Linux installer 0.1.2 refreshed OpenSSL while retaining upstream Python 3.13.5. Live installer 0.1.3 replaces that interpreter and standard library with verified CPython 3.13.16 while preserving all 71 baseline extensions and PyQt/SIP integration. This bounded refresh does not claim every bundled engine dependency or every native function is security-qualified.

`branding/` contains a separate v2 source overlay using Flaptown's existing sigil, Syne Mono, splash, app icons, product names and Flapsoft source links. The base source patch and frozen plugin ZIPs remain unchanged. The v1 overlay passed Linux compilation and the native drawing/theme/settings-isolation probe. V2 additionally fixes macOS bundled-Python discovery for the renamed Flapart app; fresh-source reproduction passes, and native Windows/macOS validation remains pending. Upstream Krita authors, licenses and engine documentation remain credited.
