# Flapart browser editor

Original dependency-free painting editor for Flaptown, with the shared Slate & Oak palette, existing Flaptown sigil, and self-hosted Syne Mono. No Krita source or assets are included. This is not a Krita-compatible document editor or a claim of feature parity.

## Use

Serve this directory over HTTP; `python -m http.server 8937 --bind 127.0.0.1 --directory web` from the project root is sufficient. Open `http://127.0.0.1:8937`. Production account functionality uses the Flaptown accounts service and its authenticated cookie session; anonymous users can draw and download freely.

Choose a brush and draw. Eraser, tolerance fill, composite color picker, line, rectangle, ellipse, linear/radial gradients, text, rectangular selection and layer/selection move are available in the left toolbar. Ink, pencil, soft paint, spray and block presets expose hardness, paint flow, stamp spacing, pen pressure and mirror drawing under tool settings. Overall brush opacity is applied per stroke; flow controls overlapping stamps. Solid shapes, gradient endpoint colors, fill tolerance and text settings are there too. Layers support visibility, opacity, six blend modes, duplication, reordering, rename (double-click), clearing, flipping and rotating 90 degrees. Canvas controls include whole-image resampling (smooth or pixel art), centered canvas resize and cropping every layer to the selection. Brightness, contrast, saturation, grayscale and invert adjustments operate on the active layer or its selection. All of these document changes support undo. Rotation clips pixels outside the current canvas; enlarge the canvas first to retain rotated edges. New canvases support transparent, white and slate backgrounds. PNG/JPEG/WebP/GIF imports become centered layers; GIF imports are still images. The first imported image must fit within the documented image limits.

Download `.flapart` projects to preserve layers. PNG exports preserve transparency; JPEG composites onto white; WebP supports quality and transparency. Grid/selection guides do not appear in exports. IndexedDB stores one recovery copy per browser/origin, debounced after changes; quota or storage errors are shown visibly. Recovery is not a durable backup. Save a project before clearing browser data or moving devices.

Keyboard: B brush, E eraser, F fill, I picker, L line, R rectangle, O ellipse, G gradient, T text, S select, V move, H pan; Space+drag pans; Ctrl/Cmd+wheel zooms; Ctrl/Cmd+Z undo, Shift+Z or Ctrl/Cmd+Y redo; Ctrl/Cmd+S downloads project; Ctrl/Cmd+A selects canvas; Escape deselects; Delete erases selected pixels; brackets change brush size. Native input editing shortcuts remain available while editing fields.

## Integration contract

`window.flapart` becomes available after app initialization. `flapart:ready` is dispatched once; integration modules loaded later should also check the property directly.

- `await exportProject()` returns a serializable project object.
- `await loadProject(project)` validates the full project before replacing current artwork. Rejects while another import or pointer gesture is active. Imports preserve current work on failure.
- `await exportPreview()` returns flattened PNG data URI, excluding guides.
- `getName()`, `getRevision()`, `setStatus(message)`, and `limits` are available.
- `ask(title, fields, description)` supplies an accessible native modal helper; resolves fields or null for cancellation.
- `flapart:change` is dispatched after document changes with `{revision}` detail.
- The existing account buttons also dispatch `flapart:save-profile` and `flapart:post-townhall`; `integration.js` attaches its own click handlers and manages authenticated cloud actions.

Project format:

```json
{"format":"flapart","version":1,"name":"untitled","width":1200,"height":800,"layers":[{"name":"drawing","opacity":1,"blend":"source-over","visible":true,"data":"data:image/png;base64,..."}]}
```

Layer order is bottom first. Supported blends: source-over, multiply, screen, overlay, darken, lighten. All layers have exactly the document dimensions. Limits: integer dimensions 1–4096, 1–32 layers, at most 48 million layer pixels, 48 MiB JSON text, names up to 100 characters. PNG layer signatures, IHDR dimensions and complete chunk boundaries/end markers are checked before browser decode. Imported standalone images are limited to 32 MiB, 16384 pixels per side and 64 million pixels, with dimensions parsed before decode and output scaled to fit the canvas. JPEG headers must be within the first 256 KiB. Cloud service limits are separate and intentionally smaller.

## Security and operation

No HTML is constructed from project names, layer names, or account text. App scripts/styles/fonts are external and self-hosted. Validated project data contains raster PNG only. No network calls are made by the painting engine; account integration makes explicit account calls. A compatible CSP uses `default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob: https://accounts.flaptown.com; connect-src 'self' https://accounts.flaptown.com; base-uri 'none'; object-src 'none'; form-action 'self'`. Embedding restrictions and production response headers belong to deployment.

Undo/redo uses bounded in-memory canvas snapshots, targeting 128 MB of undo storage with at least one snapshot. Large canvases/layer stacks require additional browser memory. Fill uses a scanline queue to avoid one JavaScript queue entry per filled pixel. Async imports make the editor inert until completion. Local file decoder security ultimately depends on the browser. No application can promise unlimited canvas sizes or exhaustive security.

## Verification

Python Playwright and its Chromium browser are test-only requirements; the shipped application has no runtime dependencies. With the local server running:

```sh
python web/test_editor.py http://127.0.0.1:8937
python web/test_security.py http://127.0.0.1:8937
python web/test_art_depth.py http://127.0.0.1:8937
python web/test_interaction.py http://127.0.0.1:8937
```

The first suite checks actual Syne Mono loading, painting, undo/redo, layers, project pixel roundtrip, malformed input, shape/selection move, downloads, recovery and mobile overflow. The second applies a strict production-like CSP, rejects malformed projects without mutating artwork, verifies full/selected fill, bounded imports, JPEG/WebP bytes, and signed-out account UI. The art-depth suite verifies actual pixels for per-stroke opacity, mirror symmetry, gradients, rotation, five adjustments, image/canvas resizing and cropping, plus four alternate brush presets. The interaction suite checks multi-pointer ownership, pointer-cancel rollback with redo preservation, unsaved-open/new cancellation and keyboard isolation during async imports. Screenshots are written to `/tmp/flapart-desktop.png` and `/tmp/flapart-mobile.png`. Tests do not publish user content or perform authenticated account mutations. Do not copy these tests/README into the public asset tree unless intentionally exposing development documentation.

Not implemented: .kra compatibility, CMYK/ICC color-management controls, vector paths, filter masks, animation timelines, collaborative painting, or Krita plugin/brush compatibility. The desktop wrapper can reuse these static assets but platform packaging/signing and native verification are separate responsibilities.
