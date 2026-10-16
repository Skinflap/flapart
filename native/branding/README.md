# Flapart native branding overlay v1

Apply `python native/branding/apply-branding.py PREPARED_SOURCE` after `native/scripts/prepare-fork.py`. This is a separate overlay; it does not change the frozen Studio 0.1.1 plugin or base source patch. It preflights every textual replacement before modifying the prepared checkout and refuses repeated application.

The icons reuse Flaptown's existing sigil. The splash and FLAPART banner use exact Syne Mono glyph outlines, with its OFL license retained at `native/plugin/flapart/OFL-SyneMono.txt`. `build-assets.py` reproduces the committed images with fontTools and librsvg's `rsvg-convert`. Flaptown artwork is provided under CC-BY-SA-4.0; attribution: Flaptown Advancements. Build/overlay scripts are GPL-3.0-or-later.

Native branding selects the Flapart icons, splash, product name, macOS bundle identity, and Flapsoft source link. Original Krita engine authors, legal notices, documentation, support links, and sources remain credited and available. The original splash asset stays in the source tree, while the displayed replacement correctly credits Flaptown Advancements. Existing Qt6 experimental safeguards remain active.

Qualification is separate from asset generation. The Xcode 26 Icon Composer metadata is a candidate until compiled on that toolchain; older Xcode and other platforms use the provided PNG icons.
