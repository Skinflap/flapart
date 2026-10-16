# Read-only artwork metadata regression

The pinned upstream adapter returns a temporary string through Exiv2 0.28's reference-returning `path()` interface. A failed read-write open of a read-only RAW document reaches error formatting with that dangling reference. `native/patches/metadata-readonly.patch` stores the absolute path for the adapter lifetime and falls back to read-only access. The shared source preparation applies this patch.

The class layout changes. Rebuild both `kritaexifcommon` and every constructor consumer, including `krita_raw_import`, `krita_tiff_import` and `krita_tiff_export`; replacing only the shared library is insufficient. `consumer-audit.txt` records matches across every pinned tracked source file, without an extension filter. `source-receipt.json` binds the exact original and patched source files.

`regression.cpp` is an ordinary-input native regression. Compile against the matching generated Krita headers, patched metadata library, QtCore and Exiv2, with assertions enabled (`-UNDEBUG` after any `-DNDEBUG`). Supply a valid Bayer DNG at `/fixtures/synthetic-bayer.dng` on a read-only filesystem and leave `/fixtures/absent.dng` absent. Ensure the loader maps the patched library via its SONAME alias, not merely the link-time pathname. The test checks reference lifetime after allocation churn, metadata parsing, refused writes and a missing-file exception. Preserve and compare the fixture bytes separately.

A passing isolated regression does not qualify the full application or a relocated package. Each desktop edition must import the read-only DNG through the actual application, preserve the input bytes, export/reopen artwork, and pass its existing package and installer journeys. No public desktop release is certified by this source bundle.
