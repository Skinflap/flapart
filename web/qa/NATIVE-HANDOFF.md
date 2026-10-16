# Local native export handoff check

`python3 web/qa/test_native_handoff.py` serves only the local web source with a
strict CSP and uses an actual Chromium file chooser/PNG import. Account GET
responses are local fixtures; any attempted POST aborts and fails the test. No
account mutations or live publication are performed. Screenshots and the result
are written under `evidence/native-handoff-local/`, outside shipped web assets.

Recognized URLs have one exact `from=native` and one exact
`destination=profile|townhall`; invalid or duplicate handoff parameters do nothing.
No image, filename, local path or identity is added to the URL. Guidance uses the
existing theme/font. Only the banner's chooser arms the handoff. Non-PNG files are
rejected before the normal importer runs. Cancel/failure keeps the person in the
editor. A successfully added PNG opens the existing destination's sharing review
(or existing sign-in flow); publishing remains an explicit action.

The banner offers two explicit choices. **Open PNG as new drawing** asks for
replacement confirmation and offers a separate **save current project first**
button. The selected PNG is read, validated, decoded and drawn to a staging canvas
before the current drawing is checkpointed or changed. It becomes one transparent
layer at its exact source dimensions. New drawings exceeding 4096 pixels per side
are refused with instructions to resize/export a smaller PNG in Studio; they are
never silently fitted. Normal undo restores the previous canvas, and normal local
recovery then follows the chosen drawing. There is no automatic project download
or recovery deletion. Cancel, corrupt files and oversize refusal leave the current
canvas and stored recovery untouched.

**Add PNG to current drawing** retains the ordinary fitting/layer behavior. The
banner explicitly says sharing includes all visible layers of the combined canvas.
Ordinary toolbar import continues to add a layer and never advances the handoff.

The scoped editor API `chooseImage({mode: "new"|"layer"})` opens the existing picker;
its default remains layer import. `flapart:image-import` is emitted after import
releases its busy state or for refusal/cancellation. Its detail contains only
`{state: "success"|"error"|"cancel", type: MIME_STRING, mode: "new"|"layer"}`;
no filename, image bytes, filesystem path or account information.

Checks cover both destinations, PNG import and undo, recovered private artwork,
exact dimensions and transparent pixels with no old art, explicit combined-canvas
choice, corrupt PNG, oversize refusal, non-PNG rejection, confirmation and picker
cancellation, unchanged recovery on failure, dismissal, sign-in refresh preserving
the review choice, 320/390px overflow, invalid params, ordinary import/account UI,
loaded Syne Mono, no page errors, and zero account mutations. The sign-in refresh
handler reloads inside the existing dialog so its busy guard does not block it.

Local browser qualification is not a claim of live deployment. Source/publication
pins remain unchanged until the parent completes separate release qualification.

Cross-browser replay uses `FLAPART_QA_BROWSER=firefox` or
`FLAPART_QA_BROWSER=webkit` with the same test command. Each engine writes to a
separate evidence directory. Both passed the full local handoff assertions on
2026-10-16, including recovered-art replacement, transparency, undo, failed
imports, explicit combined-canvas choice and zero account writes. Linux WebKit
is not a claim of native Safari or physical iOS device qualification.
