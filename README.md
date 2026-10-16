# Flapart / Flapsoft

Free art tools and an open software workshop for Flaptown Advancements.

- `web/`: original browser painting application, export and account integrations.
- `native/`: GPL Krita-based native source overlay and Flapart Studio Python plugin. Read its README and UPSTREAM.json for exact source identity, build requirements and limits.
- `flapsoft/`: simple source-hosting workshop frontend.
- `flapsoft-backend/`: bounded source projects, immutable versions, private/public visibility, forks, ZIP export, discussions, reporting and owner moderation.
- `backend/`: artwork routes and integration patch for the existing Flaptown account service. No production credentials or user data belong in source distribution.
- `research/`: retained REA evidence and the observed/native-versus-browser capability boundary.

## Browser development

Serve web/ using a local static HTTP server. The editor works without accounts; production account APIs accept only Flaptown origins. Run `python web/test_editor.py` and `python web/test_security.py` with Python Playwright and Chromium. The README in web/ records actual limits and hooks. Do not weaken CSP for development convenience.

## Account deployment

These modules extend Flaptown's existing account issuer; they are not a standalone identity service. Provision schemas offline, enable explicit feature flags, preserve existing database/config/source, and qualify the real listener and public edge. See backend/INTEGRATION.md. New project and artwork saves are private. Publication is an explicit separate operation. Never put credentials, production config, user files, databases or unrelated source in a release ZIP.

## License and credits

Original Flapart/Flapsoft code is GPL-3.0-only, copyright 2026 Flaptown Advancements. See LICENSE. Krita source and included third-party dependencies retain their own copyrights/licenses; the native overlay does not remove upstream notices. Syne Mono is under the SIL Open Font License included alongside it. Your artwork remains yours; application licensing does not require licensing artwork under GPL.

The first Flapsoft workshop is source hosting with snapshots, forks and discussions. It does not implement Git transport, continuous integration or automatic execution of uploaded code. Files remain inert text until a user downloads and chooses to run them locally.

## Release truth

See STATUS.md and bounded evidence. A source recipe/plugin is not a compiled desktop installer; building a target is not the same as running it on its native OS. Do not mark untested operating systems supported or claim absolute security from a finite test suite.

## Build and test mirror

The public workshop and downloads are at https://flaptown.com/flapsoft/flapart/. This source mirror provides reproducible cross-platform CI on standard hosted runners. It contains source and tests only, no production accounts or configuration. Native runtime downloads are fetched directly from upstream and verified against pinned hashes. CI evidence is not a supported desktop release.
