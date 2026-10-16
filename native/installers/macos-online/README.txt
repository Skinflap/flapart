FLAPART STUDIO — MAC INSTALLER CANDIDATE

Preparatory source only: release.json blocks installation until an actual,
qualified namespaced Mac runtime is frozen. No native installer execution has
been claimed from this Linux workstation. Do not publish this as a ready app.

Official Krita uses Library/Preferences and Library/Application Support paths;
XDG settings cannot safely isolate it. The installer therefore requires the
compiled Flapart namespace, not a renamed or modified signed official app.
The engine keeps Krita credits. Frozen Studio integration supplies Flaptown
colours, Syne Mono, onboarding, focus mode and explicit PNG browser handoff.

AFTER QUALIFICATION
Extract the installer ZIP and open Install Flapart.command. It downloads a
pinned HTTPS ZIP, checks SHA-256, and installs into ~/Applications/Flapart Studio.
No administrator password, paid enrollment, or system-policy changes are used.
Open Flapart Studio.command in that folder afterwards. The native app and its
settings are separate from ordinary Krita. Internet is needed for initial setup
and browser account sharing; local painting, KRA projects and PNG export work
offline. Save editable KRA artwork separately. Sharing requires exporting PNG,
then importing and explicitly posting/saving it in the browser.

MAC SECURITY
The installer records actual signature information and preserves signatures and
quarantine. It does not imply Developer ID or notarization for unsigned/ad-hoc
open-source builds, and never automatically approves them. After you try to open
an unnotarized app, if you trust this release, macOS may offer the per-app Open
Anyway option in System Settings > Privacy & Security. Review that decision
yourself. Do not override a warning about malware, a revoked app or damaged code.
Apple's current instructions: https://support.apple.com/en-ie/102445
Managed Macs may not permit such exceptions. A locally ad-hoc signed application
can have an integrity signature without being notarized or developer-identified.

UPGRADES
Versioned runtimes and earlier receipts are retained. A failed download or
checksum leaves the active installation unchanged. Art and namespaced settings
are never removed; do not keep artwork inside runtime folders. Removing the
application directory uninstalls the launcher/runtime; your artwork and profile
remain unless you separately choose to remove them.

RELEASE/CI
freeze-release.py validates the exact archive, native namespace/profile safety,
canvas/PNG/KRA tests, runtime dependency collection and source/license closure.
It byte-checks the frozen Studio plugin/theme/font/license files. A deployable
ZIP must contain just Flapart Studio.app/ with runtime dependencies collected
using upstream deployment tooling, not the SDK build prefix. Record actual
unsigned/ad-hoc/Developer ID signature status; retain Gatekeeper evidence.
Run test_installer.py on a disposable Mac runner. Without payload it tests
syntax/refusal; with --archive --manifest --output it tests transactional install,
quarantine retention and corrupt-upgrade refusal. It never launches an app by
bypassing security approval. For the full installed-launcher journey, ci_e2e.py consumes --archive, --manifest,
--probe and --output on a fresh native hosted runner. It verifies actual artwork,
KRA pixels, Studio menu reopening, normal Krita preservation, and failed/successful
upgrades retaining art/settings. SDK paths are removed. A ci-candidate manifest
is eligible only in temporary CI storage; public freezing has separate gates.
If ordinary macOS launch requires per-app user review, the test reports a blocked
launch without granting an exception, removing quarantine, or claiming success.
The installer itself needs only built-in Mac tools; Python is CI/release-only. Do not upload a binary before complete source/license closure.

COPYING covers GPL-3.0-or-later source; studio-plugin.zip is frozen 0.1.1 and
includes the Syne Mono SIL OFL license. Native dependency notices and exact source
must accompany the qualified full distribution. https://flaptown.com/flapsoft/
