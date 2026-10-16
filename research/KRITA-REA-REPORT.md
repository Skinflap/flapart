# Krita REA evidence and Flapart implementation boundary

Inspected 2026-10-16. This is a shipped-artifact investigation, not a completed Flapart parity claim.

## Target and provenance

No installed Krita executable was found in the bounded search of `/usr/bin/krita`, `~/Applications`, `~/Downloads`, `/opt`, `/usr/local`, and `/var/lib/flatpak`. Instead, the explicitly requested Krita target was resolved to the official portable Windows distribution advertised at https://download.kde.org/stable/krita/5.3.4.1/ . No Krita application was launched, installed, or modified.

- Acquisition: https://download.kde.org/stable/krita/5.3.4.1/krita-x64-5.3.4.1.zip
- Local artifact: `artifacts/krita-x64-5.3.4.1.zip`
- SHA-256: `eda810059a120171d30d4661c7684c73a8feb72b01ad5709531cbebe6b84d032`
- REA archive inspection: `ev_c865d1e59ea6d5c6341bb5c19e77a7cbcd305672a42fe35b848acac3aa61a1bb`
- Inventory evidence: `ev_a364a9ea5cdc42eb15e9640117f4658b2bc911f73555ade149c810bca70ef827`
- Manifest: `agm_aec635897f85c7f3d21c28c6ec038265e78c571454d76dc5e4951765f25a935f`
- Full retained archive evidence: `krita-rea-evidence.json` (3 records, 9,157,573 bytes).
- Acquisition establishes HTTPS upstream provenance; an independent upstream signature verification was not performed.

REA observed 3,510 regular files, 510 directories, 4,020 occurrences, 3,768 content-addressed nodes, and zero reported archive integrity contradictions. Coverage is ZIP central-directory members; non-entry bytes and application execution are outside this result.

## Observations and implications

| Question | Observed evidence | Confidence / limitation | Flapart implication |
|---|---|---|---|
| Is Krita a single canvas widget? | Separate `libkritaimage.dll`, `libkritaui.dll`, `libkritalibpaintop.dll`, and many plugin DLLs in the shipped archive | Static package structure; filenames alone do not prove behavior | Preserve document/renderer/tool/format separation in the design |
| Is brush depth merely different cursor sizes? | Fourteen plugin DLL names contain `paintop`, including color smudge, grid, hairy, hatching, MyPaint, particle, spray, and tangent normal | Shipped module presence plus official brush-engine manual; algorithms were not decompiled | A handful of Canvas2D strokes is a useful smaller editor, but not brush-engine parity |
| Are layers just PNG overlays? | Packaged action XML declares group, clone, selection-mask and other layer actions; layer docker/split/group-switcher modules are present | 681 action records parsed from shipped `.action` XML into `packaged-actions.json`; declarations are not runtime tests | Keep stable layer IDs, ordering, visibility, opacity, blend modes, and explicit mask/group support boundaries |
| How does KRA export work? | Native Ghidra decompilation calls `KisDocument::savingImage`, constructs `KraConverter`, reads filename and `isAutosaving`, calls `KraConverter::buildFile`, and returns an export error code | One export procedure only; not the underlying KRA encoder implementation | KRA is a document codec requiring deeper document support, not a PNG with a new extension |
| Which format families are shipped? | Import/export DLL pairs for KRA, ORA, PSD, PNG, JPEG, WebP, TIFF, EXR, GIF, JXL, HEIF and others | Presence not fidelity/compatibility certification | Offer only actually implemented/export-tested formats; label flattened exports |
| Does analysis establish platform compatibility? | Windows x86-64 portable ZIP and one PE DLL statically inspected on Linux | No native Windows, macOS, Linux UI execution in this investigation | Require separate native launch, input, persistence and export QA for each released build |

## Native REA trace

Selected ZIP member `krita-x64-5.3.4.1/lib/kritaplugins/kritakraexport.dll` was extracted without execution into `artifacts/kritakraexport.dll` (84,184 bytes), SHA-256 `cf7847b8127e8db7f23880cbdaa61c643a9b3ae2080d4cc8ba9f06d6ece73549`.

REA Ghidra 12.1.4 analysis profile `47d858f47f8fe97a8c640e44c06a1b85690588ed84e37afab1614c9be8ea9872`:

1. `search_procedures("save")`: no named matches; this is not proof that save functionality is absent. Evidence `ev_dba082e692ae606e007c5ebf9a116b9dfb63ef006aee6e7b273ead16390c587d`.
2. `search_strings("Kra")`: found `KraExport::convert result =` at `0x1800089a0`, source-path literal and imported `KraConverter` names. Evidence `ev_6726234bf710c267649ba78055d408a018edd72db6723cc5b2d62cd8a499d909`.
3. `xrefs(0x1800089a0)`: reference at `0x180003c8d`. Evidence `ev_a811023bfbb44d38d51224915756c57c728a3f8d0b03b84bf6436ec3867026c0`.
4. `procedure_pseudo_code(0x180003c8d)`: recovered `KraExport::convert` as described above. Evidence `ev_d093cc6668022e67222b2dd7d4cf47a1010dbc74fbe343ec783d6533658fe397`.

Full native evidence is retained in `krita-kra-native-evidence.json`. Pseudocode is inferred representation of binary behavior, not original source. Debug/PDB load state was unknown, indirect calls can remain unresolved, and this did not execute an export. REA sessions were closed after export.

## Primary documentation corroboration

- https://docs.krita.org/en/general_concepts/file_formats/file_kra.html — KRA is a ZIP-like internal format preserving Krita features, with a merged PNG preview. KRZ omits that preview and always compresses.
- https://docs.krita.org/en/general_concepts/file_formats/file_ora.html — OpenRaster exchanges layers as PNGs with XML inside a ZIP. It is a sensible layered bridge; it does not promise full Krita document fidelity.
- https://docs.krita.org/en/reference_manual/layers_and_masks.html — Paint, vector, group, clone, file, fill, filter layers and several masks expose substantially more structure than a flat canvas.
- https://docs.krita.org/en/reference_manual/brushes/brush_engines.html — Krita documents multiple brush engines with differing behavior.
- https://krita.org/en/about/license/ — Krita as a whole is GPLv3; distributed changes and plugins need GPL-compatible publication. Original artwork belongs to its creator. Keep upstream and third-party attribution and corresponding-source availability with redistributed derivatives.

## Recommended product architecture (design choices, not REA findings)

Browser: build a genuinely approachable Flaptown editor around progressive disclosure: everyday draw/erase/fill/shapes/text and color controls first; layers, brush settings, selections, transforms and filters in expandable panels. Keep guest drawing and local export available. Native editable project save, autosave/recovery, lossless PNG, and supported layered interchange are separate controls. Any flattening should be explicit. Store profile works privately by default; Town Hall publication is a separate user action with a preview and destination.

Desktop preserving Krita depth: fork the upstream GPLv3 source and retain its rendering, brush, color-management, layer/mask, file-format, tablet, animation and plugin foundations. Add Flapart branding, a simplified default workspace with full tools discoverable, and narrowly scoped Flaptown save/post integration. Publish full corresponding source, exact upstream revision, patches, build instructions and dependency licenses alongside builds. A webview shell containing the browser editor is a legitimate desktop edition of that editor, but does not inherit Krita's feature depth.

Browser full parity requires deliberate porting of native foundations or a broader implementation project. REA does not make Qt desktop code automatically executable in browsers. No WASM compatibility was established here. Avoid marketing an initial browser release or PWA installation as a complete cross-platform Krita replacement.

Flapsoft: provide plain-language project pages with Try, Download, Source, Changes, Help, Report a problem and License. Each build needs an immutable version, size, digest, OS/architecture, source revision, and tested status. Source browsing, release history and contribution paths make an open software hub useful; calling a download directory a GitHub equivalent overstates repository, issue, review and permission capabilities.

## Release evidence still required

- Browser real pointer/touch/stylus interactions; undo/redo after every document operation; round-trip native projects; invalid file bounds; autosave and offline recovery; actual exported pixels and dimensions.
- Layer/composite correctness with transparent/opaque fixtures, blend modes, transform clipping and reorder/merge/duplicate/delete undo.
- Server authorization and ownership enforcement, CSRF/same-origin handling, size/dimension limits, safe re-encoding, public/private isolation, deletion behavior, output escaping and restrictive content policy. Do not execute user-uploaded source from Flapsoft.
- Native Windows, macOS and Linux builds actually installed/launched on those OSes, with pressure input, file dialogs, export, quit/relaunch, offline operation and account integration exercised. Record unavailable test platforms honestly.
- Verify source archive corresponds to each binary; show accurate signing/notarization state. A build job definition or uploaded archive is not proof the native app works.

Checklist status: shipped identity answered; modular architecture partially answered; export entry path answered; full brush/layer algorithms unresolved; browser port compatibility unresolved; native release compatibility unresolved. This report is a foundation for implementation, not a completion certificate.
