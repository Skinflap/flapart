# Native functional probe

This is a test-only Krita Python plugin; do not include it in end-user downloads.
Copy `flapart_probe.desktop` and `flapart_probe/` into the test profile's Krita
`pykrita` resource folder alongside the Flapart Studio plugin. Enable both
`enable_flapart=true` and `enable_flapart_probe=true` under `[python]` in the
appropriate test config. Set `FLAPART_QA_OUTPUT` to an absolute writable directory.
Set `FLAPART_NATIVE=1` for a runtime-overlay test; the compiled fork sets it itself.

The official engine uses `kritarc` and the `krita` resource directory. The
namespaced compiled fork uses `flapartnativerc` and `flapart-native` resources.
On a macOS test runner ordinary Krita resources are normally
`~/Library/Application Support/krita/pykrita` and configuration
`~/Library/Preferences/kritarc`; verify actual paths/logs on the runner.
On Windows use the real Known Folder paths, not spoofed APPDATA environment vars.
Use only a disposable test profile; the probe intentionally creates/saves art and
ends the test process with `os._exit(0)` after writing its receipt and screenshot.

Launch the actual native application in a GUI session. The probe waits for startup,
creates a64×64 document, writes known pixels, invokes the actual Studio PNG helper
with test-controlled dialogs, checks KRA save/reopen, verifies layer/pixel identity,
tests focus restoration, and records the fixed browser URL without opening it.
The screenshot captures the application's Qt widget, avoiding whole-screen capture.
A process exit alone is insufficient: validate `result.json` booleans, dimensions,
exact pixel `[70,110,191,255]`, layer name, and absence of `error`.
Physical tablet/pressure, all engines, signing and clean-machine compatibility
require separate checks.
