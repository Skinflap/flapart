FLAPART STUDIO — LINUX ONLINE INSTALLER 0.1.2
Flaptown Advancements · https://flaptown.com/flapsoft/

A full native drawing and painting application using the official Krita 5.3.4.1
engine, with Flapart's simpler starting screen, Flaptown theme, focus mode,
editable projects, PNG export, and browser handoff to your Flaptown profile
or Town Hall. Krita's advanced brushes, layers, masks, animation, and other
native tools stay available. This is a Flapart workspace integration using
Krita, not a separately compiled or renamed Krita engine.

INSTALL
1. Extract this ZIP into a folder.
2. Open a terminal in that folder and run: sh install.sh
3. Open Flapart Studio from your applications menu.

Linux x86_64, Python 3.9 or later, an X11/XWayland graphical session, and an internet
connection are required. The installer downloads about 366 MiB directly from
KDE and Ubuntu and verifies pinned SHA-256 hashes before extraction. It refreshes
the engine’s TLS libraries using Ubuntu jammy-security libssl3 3.0.2-0ubuntu1.30.
Allow 1.5 GiB free space.
It needs no administrator password. Afterwards, drawing and export work offline.
Your browser and a connection are required for Flaptown account features.

Your ordinary Krita configuration is preserved. Flapart uses separate folders:
~/.config/flapart-studio, ~/.local/share/flapart-studio, ~/.cache/flapart-studio.
The app is installed in ~/.local/opt/flapart-studio. An upgrade retains the
previous application folder beside it. Existing drawings are never deleted.
If you use custom XDG folders, Flapart follows those instead.

ACCOUNT HANDOFF
Choose Save to my profile or Share to Town Hall in Flapart Studio. Export a PNG,
then import that PNG in the browser page that opens and finish saving/posting.
The app never silently uploads art and does not store your account credentials.
Save an editable .kra project separately to retain layers and other native data.

REMOVE
Remove ~/.local/opt/flapart-studio and the menu shortcut
~/.local/share/applications/com.flaptown.FlapartStudio.desktop.
Settings and your art remain unless you separately choose to remove them.

VALIDATION AND LIMITS
The official download, installation, isolated launch, creation, PNG export,
editable KRA save/reopen with exact pixel preservation, and focus restore were
tested on Linux with a virtual display. Physical pen/tablet pressure, every
native tool, and every Linux distribution have not been qualified. Windows and
macOS require their own installers and testing; this download is Linux only.

LICENSE AND SOURCE
Flapart plugin, launcher, and installer: GPL-3.0-or-later; all source is in this
ZIP and COPYING contains the license. Syne Mono is SIL Open Font License;
its license is in plugin/flapart/OFL-SyneMono.txt. Your art belongs to you.
Krita and its bundled dependencies are fetched from KDE rather than redistributed
inside this ZIP. The pinned TLS refresh is fetched directly from Ubuntu; its
license and exact package provenance are retained under third-party/ubuntu-openssl
in the installation. Source: https://launchpad.net/ubuntu/+source/openssl/3.0.2-0ubuntu1.30
The launcher uses your distribution’s maintained system certificate bundle and
preserves an explicit SSL_CERT_FILE override. No private trust store is installed.
The receipt distinguishes the original engine from this library refresh. Krita license/source: https://krita.org/en/about/license/
Exact engine source: https://download.kde.org/stable/krita/6.0.4.1/krita-6.0.4.1.tar.xz
(The upstream source has both Qt5/Krita 5.3.4.1 and Qt6/Krita 6.0.4.1 versions.)
The official engine retains its upstream credits, notices, and licenses.
