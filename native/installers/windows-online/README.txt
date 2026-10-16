FLAPART STUDIO — WINDOWS INSTALLER CANDIDATE

This is preparatory source, not a released or tested Windows installer. The
included release.json deliberately prevents download or installation until a
qualified, independently namespaced runtime is frozen. No package is published
by these scripts. The frozen 0.1.1 Studio plugin ZIP remains unchanged.

WHY THE INDEPENDENT BUILD
Official Krita 5.3.4.1 is a complete engine, but its Windows settings use native
KnownFolder paths. APPDATA or XDG overrides do not isolate them, and the engine
has no configuration-profile command line switch. This installer therefore
requires the compiled Flapart namespace (flapart-native, flapartnativerc,
flapartnativedisplayrc, flapartnativeshortcutsrc, independent singleton and logs).
It never changes a user's ordinary Krita profile. The full engine retains its
Krita credits; Studio adds the Flaptown theme, Syne Mono, simpler entry flow,
focus mode, and manual browser handoff. No unrelated SDK is bundled.

PLANNED USER FLOW AFTER QUALIFICATION
Extract the ZIP and double-click Install Flapart.exe. A small native window uses
Flaptown colours and Syne Mono and lets you choose a folder. It downloads one
pinned HTTPS runtime, verifies SHA-256, safely extracts it, and installs for your
Windows account. Users need neither Python, PowerShell scripts, nor a compiler.
.NET Framework4.8 is included with supported Windows10/11 systems. No admin
password, account enrollment, or execution-policy change is used. Windows may
ask you to review an unsigned developer application; no approval is automated.
Open Flapart Studio from Start after installation. Local painting, KRA projects
and PNG export work offline. Account sharing is a manual PNG import into the
browser followed by explicit posting/saving. The app stores no account tokens.

UPGRADES AND REMOVAL
Versions live under LocalAppData/Programs/FlapartStudio/releases. An atomic
receipt selects the active version; failed downloads do not replace it. Earlier
runtime folders and your drawings are retained. Your namespaced settings are
outside runtime releases. Do not save artwork inside runtime folders. Remove
the application folder and Start shortcut to uninstall; separately decide
whether to remove your own Flapart settings. The installer never deletes art.

RELEASE/CI HANDOFF
freeze-release.py requires exact archive digest and native evidence for profile
isolation, ordinary Krita preservation, canvas/PNG/KRA tests, runtime dependency
collection and complete corresponding source. It also byte-checks the frozen
plugin, theme, font and license in the runtime ZIP. The output is a NEW manifest;
replace the candidate manifest only during a new reviewed release preparation.
build-installer.ps1 compiles the native GUI installer/launcher on Windows CI.
Test-Installer.ps1 tests real Windows installer execution and corrupt-upgrade
refusal; without a runtime it checks that the blocked manifest is refused.
ci_e2e.py is the complete fresh-runner test: installed launcher, actual native
canvas/PNG/KRA/pixel checks, Studio menu reopening, ordinary Krita sentinels,
failed upgrade and successful upgrade preserving saved art/settings. SDK paths
are removed from the test environment so undeployed dependencies cannot hide.
It consumes --archive, --manifest, --probe, --output. A temporary ci-candidate
manifest is promoted only inside disposable test storage, never a public release.
No runtime binary is uploaded by any helper. A missing standard Windows security
approval produces a blocked result, never an automated approval or false pass.

Native engine target: Windows x86_64. Artifact layout and build are not yet frozen.
Source and notices: COPYING and studio-plugin.zip. Plugin GPL-3.0-or-later; Syne
Mono SIL OFL. The actual full native package must retain all dependency notices
and provide its exact corresponding source. https://flaptown.com/flapsoft/
