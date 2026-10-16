# Flapart Native

Flapart Studio adds a simpler starting point to Krita's native painting engine. It keeps the full brush, layer, mask, color, animation and format tools available. It is free GPLv3-or-later software. Your art remains yours.

## Available now: Flapart Studio plugin source

Use Krita 5.3 with Python support. Download `flapart-studio-0.1.1-krita-plugin.zip`, open **Tools → Scripts → Import Python Plugin from File**, select the ZIP, enable **Flapart Studio** in **Settings → Configure Krita → Python Plugin Manager**, and restart Krita. Open **Tools → Scripts → Flapart Studio**, or press **Ctrl+Alt+F**.

You can start a canvas, save an editable original, export a PNG, open brush settings, and hide/restore panels. Profile/Town Hall actions first export a picture locally, then open Flapart in your browser. Import the PNG and choose the destination. The plugin does not silently upload your art, store account credentials or replace the layered original.

Remove the plugin in the Python Plugin Manager to disable it. The canvas focus action restores the panels it hid; all menus remain available. This add-on does not replace your Krita installation.

## Source-based desktop edition

The `upstream/` checkout is the actual KDE Krita source at commit `bd6e8d061d2f0388c5b10278786cf0fe62e3135f`, tag `v6.0.4.1`. Upstream CMake builds version 5.3.4.1 with Qt5 and 6.0.4.1 with Qt6. Flapart's modifications add its Studio onboarding/theme, independent application and settings/resource identities, distinct logs and single-instance key, and a measured Qt6 color-selector apex fix. Upstream engine credits and installed resource discovery remain intact.

Reproduce the source overlay in a fresh checkout:

```sh
git clone --branch v6.0.4.1 --depth 1 https://invent.kde.org/graphics/krita.git krita-flapart
python3 scripts/prepare-fork.py ./krita-flapart
cmake -S ./krita-flapart -B ./build -G Ninja -DBUILD_WITH_QT6=OFF -DBUILD_TESTING=OFF -DCMAKE_INSTALL_PREFIX="$PWD/install"
cmake --build ./build
cmake --install ./build
```

Install the platform-specific dependencies described by upstream before configuring. Do not assume a successful configure or cross-compile is a native release test. The source patch is in `patches/flapart-native.patch`; the plugin source is in `plugin/`. The preparation script refuses dirty or incorrectly pinned checkouts.

The complete Qt6 native fork has been compiled and installed in an isolated Linux prefix. Its native functional probe passes creation, PNG export, KRA save/reopen, exact pixel/layer preservation and focus restoration. Seeded ordinary Krita configuration, resource and log files remain unchanged. Upstream explicitly marks Qt6 builds experimental; this is a qualified same-machine development build, not a stable cross-platform installer. Windows/macOS native build and runtime qualification, physical tablet QA and clean-machine installation remain outstanding.

A separately packaged Linux online installer downloads the official stable Krita5.3.4.1 runtime directly from KDE and adds the Flapart Studio integration. It is a full native-runtime installation, clearly distinguished from this independently compiled Qt6 fork. The frozen plugin ZIP remains a source add-on for existing Krita installations.

## Licensing and distribution

`COPYING` contains GPLv3. Flapart plugin code is GPL-3.0-or-later. Preserve upstream notices, third-party licenses, and corresponding source for every distributed derivative binary. Syne Mono has its separate included OFL license. This source overlay and its exact upstream identity are available for review; original Krita binaries used for testing remain upstream binaries, not renamed Flapart releases.

Build the plugin archive with `python3 scripts/package-plugin.py`. Its SHA-256 and byte length are recorded in `dist/plugin-manifest.json`.

## Validation

The native tests use isolated profiles and a virtual display, without attaching to a user's desktop. A test-only Python plugin creates a document through Flapart, writes known pixels, invokes its real PNG helper with a controlled chooser, checks the fixed browser URL without publishing, saves/reopens KRA, checks exact pixels, panel restoration, registered-menu reopening and the default shortcut, and captures the Studio window. The compiled source test also seeds ordinary Krita settings/resources/logs to verify separation. Official Windows runtime plus Studio passes native Windows 11 evaluation VM drawing, PNG/KRA, and menu regression checks; official macOS runtime plus Studio passes an Intel macOS hosted-runner probe. These are distinct from compiled-fork qualification. Portable test source is supplied separately for native Windows/macOS runners. Physical pen pressure/tilt and every native tool need additional qualification.
